"""Modal dialogs for compression preview, comparison, merging, and signing."""

import base64
from html import escape
from pathlib import Path
import unicodedata

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)

from pdf_ops import pdfium_reader, project_signature_box, reader_for, render_page, signature_boxes, signature_plan
from pdfiu_views import PageView, button
from translations import tr


class CompressionPreview(QDialog):
    def __init__(self, parent, original, compressed, page=0):
        super().__init__(parent)
        self.setWindowTitle(tr("Comparar antes de guardar"))
        available = parent.screen().availableGeometry()
        self.resize(min(1200, available.width() - 35), min(760, available.height() - 60))
        self.setMinimumSize(760, 430)
        self.paths = (original, compressed)
        self.views = (PageView(), PageView())
        self.syncing = False
        self.percent = 100
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(tr("Página")))
        self.page_number = QSpinBox()
        counts = [len(reader_for(path).pages) for path in self.paths]
        self.page_number.setRange(1, min(counts))
        self.page_number.setValue(page + 1)
        controls.addWidget(self.page_number)
        controls.addWidget(button("Ajustar", lambda: self.zoom_to(None)))
        controls.addWidget(button("100 %", lambda: self.zoom_to(100)))
        controls.addWidget(button("200 %", lambda: self.zoom_to(200)))
        self.zoom_label = QLabel("100 %", objectName="muted")
        controls.addWidget(self.zoom_label)
        controls.addStretch(1)
        controls.addWidget(button("Volver al resultado", self.accept))
        layout.addLayout(controls)
        side = QWidget()
        columns = QHBoxLayout(side)
        columns.setContentsMargins(0, 0, 0, 0)
        labels = [tr("Original"), tr("Copia comprimida")]
        for index, (label, view) in enumerate(zip(labels, self.views)):
            pane = QVBoxLayout()
            pane.addWidget(QLabel(label, objectName="chapter"))
            pane.addWidget(view, 1)
            columns.addLayout(pane, 1)
            view.set_mode("pan")
            view.horizontalScrollBar().valueChanged.connect(lambda _, key=index: self.sync_position(key))
            view.verticalScrollBar().valueChanged.connect(lambda _, key=index: self.sync_position(key))
            view.zoom_changed.connect(lambda _, key=index: self.sync_zoom(key))
        layout.addWidget(side, 1)
        self.page_note = "" if counts[0] == counts[1] else tr(" Se muestran las primeras {0} páginas comunes ({1} y {2} en total).").format(min(counts), counts[0], counts[1])
        self.hint = QLabel(tr("Arrastra cualquiera de las vistas. Ctrl + rueda cambia el zoom en ambas."), objectName="muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.page_number.valueChanged.connect(self.load_page)
        self.load_page()

    def load_page(self):
        index = self.page_number.value() - 1
        try:
            rendered = []
            for path, view in zip(self.paths, self.views):
                with pdfium_reader(path) as pdf:
                    rendered.append(render_page(pdf, index, dpi=96 * view.devicePixelRatioF(), with_coordinates=True))
        except Exception as error:
            self.hint.setText(tr("No se pudo mostrar la página {0}: {1}").format(index + 1, error))
            return
        self.syncing = True
        try:
            for view, path, (image, coords) in zip(self.views, self.paths, rendered):
                view.page(image, text_source=(path, index, coords))
                view.set_mode("pan")
        finally:
            self.syncing = False
        self.zoom_to(self.percent, reset_position=True)
        self.hint.setText(tr("Arrastra cualquiera de las vistas. Ctrl + rueda cambia el zoom en ambas.") + self.page_note)

    def zoom_to(self, percent, *, reset_position=False):
        self.syncing = True
        self.percent = percent
        try:
            for view in self.views:
                if percent is None:
                    view.fit_page()
                else:
                    view.set_percent(percent)
                if reset_position:
                    for scrollbar in (view.horizontalScrollBar(), view.verticalScrollBar()):
                        scrollbar.setValue(scrollbar.minimum())
        finally:
            self.syncing = False
        self.zoom_label.setText(f"{percent} %" if percent is not None else tr("Ajustado"))
        self.sync_position(0)

    def sync_zoom(self, index):
        if self.syncing or self.views[index].fit:
            return
        self.syncing = True
        try:
            source, target = self.views[index], self.views[1 - index]
            ratio = source.transform().m11() / source.actual_scale()
            self.percent = source.percent()
            target.fit = False
            target.set_zoom(ratio * target.actual_scale())
            self.zoom_label.setText(f"{self.percent} %")
        finally:
            self.syncing = False
        self.sync_position(index)

    def sync_position(self, index):
        source, target = self.views[index], self.views[1 - index]
        if self.syncing or source.page_rect.isEmpty() or target.page_rect.isEmpty():
            return
        self.syncing = True
        try:
            center = source.mapToScene(source.viewport().rect().center())
            u, v = center.x() / source.page_rect.width(), center.y() / source.page_rect.height()
            target.centerOn(u * target.page_rect.width(), v * target.page_rect.height())
        finally:
            self.syncing = False


class RevisionComparison(QDialog):
    def __init__(self, parent, inputs):
        super().__init__(parent)
        self.setWindowTitle(tr("Comparar planos"))
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint | Qt.WindowType.WindowCloseButtonHint)
        self.setSizeGripEnabled(True)
        self.setWindowState(Qt.WindowState.WindowMaximized)
        available = parent.screen().availableGeometry()
        self.resize(min(1200, available.width() - 35), min(780, available.height() - 60))
        self.setMinimumSize(740, 440)
        self.inputs = inputs
        self.locked = False
        self.images = None
        self.zoom_percent = None
        self.page_pair = None
        self.views = (PageView(), PageView())
        self.overlay = PageView()
        self.page_inputs = []

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        for label, (path, password) in zip(("Original", "Revisión"), inputs):
            try:
                reader = reader_for(path, allow_empty_password=True, password=password)
                units = [float(page.get("/UserUnit", 1)) for page in reader.pages]
            except Exception as error:
                raise ValueError(f"{path.name}: {error}") from error
            field = QSpinBox()
            field.setRange(1, len(units))
            field.setKeyboardTracking(False)
            field.setAccessibleName(tr("{0} · página").format(tr(label)))
            field.valueChanged.connect(self.request_render)
            self.page_inputs.append((field, units))
            name = QLabel(f"{tr(label)} · {path.name}")
            name.setTextFormat(Qt.TextFormat.PlainText)
            name.setWordWrap(True)
            name.setToolTip(str(path))
            top.addWidget(name, 1)
            top.addWidget(field)
        layout.addLayout(top)
        tools = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems([tr("En paralelo"), tr("Superponer"), tr("Diferencias")])
        self.mode.setCurrentIndex(2)
        self.mode.currentIndexChanged.connect(self.update_display)
        tools.addWidget(self.mode)
        tools.addWidget(button("Anterior", lambda: self.step(-1)))
        tools.addWidget(button("Siguiente", lambda: self.step(1)))
        tools.addWidget(button("Ajustar", lambda: self.set_zoom(None)))
        tools.addWidget(button("100 %", lambda: self.set_zoom(100)))
        tools.addStretch()
        tools.addWidget(button("Cerrar", self.accept))
        layout.addLayout(tools)

        self.overlay_options = QWidget()
        tools = QHBoxLayout(self.overlay_options)
        tools.setContentsMargins(0, 0, 0, 0)
        self.color = QComboBox()
        for label, value in (("Gris", "#565b66"), ("Rosa", "#cb4180"), ("Azul", "#1466cb"), ("Rojo", "#d32032")):
            self.color.addItem(tr(label), value)
        self.color.setCurrentIndex(2)
        self.color.currentIndexChanged.connect(self.update_display)
        color_label = QLabel(tr("Color"))
        color_label.setBuddy(self.color)
        self.color.setAccessibleName(tr("Color de revisión"))
        tools.addWidget(color_label)
        tools.addWidget(self.color)
        self.opacity = QSpinBox()
        self.opacity.setRange(10, 100)
        self.opacity.setValue(85)
        self.opacity.setSuffix(" %")
        self.opacity.setKeyboardTracking(False)
        self.opacity.valueChanged.connect(self.update_display)
        intensity_label = QLabel(tr("Intensidad"))
        tools.addWidget(intensity_label)
        tools.addWidget(self.opacity)
        self.tint_controls = (color_label, self.color, intensity_label, self.opacity)
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 100)
        self.tolerance.setValue(20)
        self.tolerance.setKeyboardTracking(False)
        self.tolerance.setAccessibleName(tr("Tolerancia de diferencias"))
        self.tolerance.setToolTip(tr("Aumenta la tolerancia para ignorar diferencias leves de color o suavizado."))
        self.tolerance.valueChanged.connect(self.update_display)
        tolerance_label = QLabel(tr("Tolerancia"))
        tolerance_label.setBuddy(self.tolerance)
        tools.addWidget(tolerance_label)
        tools.addWidget(self.tolerance)
        self.difference_controls = (tolerance_label, self.tolerance)
        self.offsets = []
        tools.addWidget(QLabel(tr("Alineación")))
        for axis, label in (("X", "Desplazar X"), ("Y", "Desplazar Y")):
            field = QDoubleSpinBox()
            field.setRange(-1000, 1000)
            field.setSuffix(" mm")
            field.setKeyboardTracking(False)
            field.setAccessibleName(tr(label))
            field.setToolTip(tr(label))
            field.valueChanged.connect(self.update_display)
            self.offsets.append(field)
            tools.addWidget(QLabel(axis))
            tools.addWidget(field)
        reset = button("Restablecer", self.reset_offset)
        reset.setMinimumWidth(101)
        tools.addWidget(reset)
        tools.addStretch()
        layout.addWidget(self.overlay_options)
        self.overlay_options.hide()
        self.legend = QLabel()
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.legend.setWordWrap(True)
        layout.addWidget(self.legend)
        self.legend.hide()

        self.display = QStackedWidget()
        parallel = QWidget()
        split = QHBoxLayout(parallel)
        split.setContentsMargins(0, 0, 0, 0)
        for index, view in enumerate(self.views):
            split.addWidget(view, 1)
            view.horizontalScrollBar().valueChanged.connect(lambda _, key=index: self.sync_scroll(key))
            view.verticalScrollBar().valueChanged.connect(lambda _, key=index: self.sync_scroll(key))
            view.zoom_changed.connect(lambda _, key=index: self.sync_zoom(key))
        self.display.addWidget(parallel)
        self.display.addWidget(self.overlay)
        for view in (*self.views, self.overlay):
            view.setBackgroundBrush(QColor("#e7eeea"))
            view.set_mode("pan")
            view.installEventFilter(self)
            view.viewport().installEventFilter(self)
        self.overlay.zoom_changed.connect(lambda _: self.remember_zoom(self.overlay))
        layout.addWidget(self.display, 1)
        self.status = QLabel(tr("Cargando páginas…"), objectName="muted")
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.timer = QTimer(self, singleShot=True, interval=45)
        self.timer.timeout.connect(self.render_pair)
        self.request_render()

    def request_render(self, *_):
        if hasattr(self, "timer"):
            self.status.setText(tr("Cargando páginas…"))
            self.timer.start()

    def render_pair(self):
        pages = tuple(field.value() - 1 for field, _ in self.page_inputs)
        units = [values[index] for (_, values), index in zip(self.page_inputs, pages)]
        try:
            from plan_comparison import render_revision_pair
            paths, passwords = zip(*self.inputs)
            self.images, self.density = render_revision_pair(paths, passwords, pages, units)
        except Exception as error:
            self.images = None
            for view in (*self.views, self.overlay):
                view.page()
            self.status.setText(str(error))
            return
        self.page_pair = pages
        self.set_views(self.views, self.images)
        self.update_display()

    def set_views(self, views, images, *, reset=False):
        self.locked = True
        try:
            for view, image in zip(views, images):
                if reset or view.page_rect.isEmpty():
                    center = None
                else:
                    center = view.mapToScene(view.viewport().rect().center())
                    center = (center.x() / view.page_rect.width(), center.y() / view.page_rect.height())
                view.page(image)
                view.set_mode("pan")
                self.apply_view_zoom(view)
                if center:
                    view.centerOn(center[0] * view.page_rect.width(), center[1] * view.page_rect.height())
        finally:
            self.locked = False

    def update_display(self, *_):
        mode = self.mode.currentIndex()
        self.overlay_options.setVisible(bool(mode))
        self.display.setCurrentIndex(int(bool(mode)))
        for widget in self.tint_controls:
            widget.setVisible(mode == 1)
        for widget in self.difference_controls:
            widget.setVisible(mode == 2)
        self.legend.setVisible(mode == 2)
        self.legend.setText(" &nbsp; ".join(
            f'<span style="color:{color}; font-weight:600;">● {escape(tr(label))}</span>'
            for color, label in (("#007d73", "Añadido"), ("#bb2535", "Quitado"), ("#a25c00", "Cambio de color"))
        ))
        if self.images is None:
            return
        changed = True
        if mode:
            from plan_comparison import highlight_differences, overlay_revision
            try:
                offset = [field.value() for field in self.offsets]
                if mode == 2:
                    merged, changed = highlight_differences(self.images, self.tolerance.value(), offset, self.density)
                else:
                    merged = overlay_revision(self.images, self.color.currentData(), self.opacity.value(), offset, self.density)
                self.set_views((self.overlay,), (merged,))
            except ValueError as error:
                self.overlay.page()
                self.status.setText(str(error))
                return
        self.set_zoom(self.zoom_percent)
        a, b = self.page_pair
        status = tr("Original · página {0}     Revisión · página {1}").format(a + 1, b + 1)
        if not changed:
            status += "   ·   " + tr("Sin diferencias visibles con esta tolerancia.")
        self.status.setText(status)

    def reset_offset(self):
        for field in self.offsets:
            with QSignalBlocker(field):
                field.setValue(0)
        self.update_display()

    def step(self, direction):
        if not all(field.minimum() <= field.value() + direction <= field.maximum() for field, _ in self.page_inputs):
            return False
        for field, _ in self.page_inputs:
            with QSignalBlocker(field):
                field.setValue(field.value() + direction)
        self.request_render()
        return True

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_PageUp):
                self.step(-1)
                return True
            if event.key() in (Qt.Key.Key_Right, Qt.Key.Key_PageDown):
                self.step(1)
                return True
        if (event.type() == QEvent.Type.Wheel and not event.modifiers()
                and abs(event.angleDelta().y()) >= 120):
            for view in (*self.views, self.overlay):
                if watched is view.viewport() and view.isVisible():
                    bar = view.verticalScrollBar()
                    direction = -1 if event.angleDelta().y() > 0 else 1
                    edge = bar.minimum() if direction < 0 else bar.maximum()
                    if bar.value() == edge and self.step(direction):
                        return True
        return super().eventFilter(watched, event)

    def apply_view_zoom(self, view):
        if self.zoom_percent is None:
            view.fit_page()
        else:
            view.fit = False
            view.set_zoom(self.zoom_percent / self.density * 96 / 7200)

    def set_zoom(self, percent):
        self.zoom_percent = percent
        self.locked = True
        try:
            for view in (*self.views, self.overlay):
                if not view.page_rect.isEmpty():
                    self.apply_view_zoom(view)
        finally:
            self.locked = False

    def remember_zoom(self, view):
        if not self.locked and not view.fit and self.images is not None:
            self.zoom_percent = view.transform().m11() * self.density * 7200 / 96

    def sync_zoom(self, index):
        source = self.views[index]
        if self.locked or source.fit or self.mode.currentIndex():
            return
        self.remember_zoom(source)
        self.locked = True
        try:
            self.apply_view_zoom(self.views[1 - index])
        finally:
            self.locked = False
        self.sync_scroll(index)

    def sync_scroll(self, index):
        if self.locked or self.mode.currentIndex():
            return
        source, target = self.views[index], self.views[1 - index]
        if source.page_rect.isEmpty() or target.page_rect.isEmpty():
            return
        self.locked = True
        try:
            center = source.mapToScene(source.viewport().rect().center())
            target.centerOn(center.x() * target.page_rect.width() / source.page_rect.width(),
                            center.y() * target.page_rect.height() / source.page_rect.height())
        finally:
            self.locked = False


class MergeDialog(QDialog):
    def __init__(self, parent, paths, names=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Unir PDFs"))
        self.resize(560, 390)
        layout = QVBoxLayout(self)
        note = QLabel(tr("Añade los archivos y arrástralos para ajustar el orden."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.items = QListWidget()
        self.items.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        layout.addWidget(self.items, 1)
        self.with_index = QCheckBox(tr("Crear índice con un marcador por archivo"))
        layout.addWidget(self.with_index)
        actions = QHBoxLayout()
        actions.addWidget(button("Añadir archivos", self.add_files))
        actions.addWidget(button("Quitar", self.remove_file))
        actions.addStretch()
        layout.addLayout(actions)
        choices = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.accept_button = choices.button(QDialogButtonBox.StandardButton.Ok)
        self.accept_button.setText(tr("Unir PDFs"))
        self.accept_button.setObjectName("primary")
        choices.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Cancelar"))
        choices.accepted.connect(self.accept)
        choices.rejected.connect(self.reject)
        layout.addWidget(choices)
        self.names = names or {}
        self.add_paths(paths)

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("Añadir PDFs"), filter="PDF (*.pdf)")
        self.add_paths(files)

    def add_paths(self, paths):
        for path in paths:
            item = QListWidgetItem(self.names.get(str(path), Path(path).name))
            item.setToolTip(str(path))
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.items.addItem(item)
        self.accept_button.setEnabled(self.items.count() >= 2)

    def remove_file(self):
        row = self.items.currentRow()
        if row >= 0:
            self.items.takeItem(row)
        self.accept_button.setEnabled(self.items.count() >= 2)

    def paths(self):
        return [self.items.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.items.count())]


class CertificateDialog(QDialog):
    def __init__(self, parent, identities, warning=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Certificado digital"))
        self.resize(590, 420)
        self.identity = None
        self.pfx = None
        self.password = None
        self.warning = warning
        layout = QVBoxLayout(self)
        note = QLabel(tr("Elige un certificado personal válido y revisa los datos del titular antes de firmar."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.options = QComboBox()
        from pdf_sign import certificate_details

        for identity in identities:
            try:
                details = certificate_details(base64.b64decode(identity["der"]))
            except Exception:
                details = identity
            label = tr("{0}  ·  {1}  ·  vence {2}").format(
                details.get("name", identity["name"]), details.get("organization") or details.get("issuer", identity["issuer"]),
                details.get("not_after", identity["expiry"]),
            )
            self.options.addItem(label, identity)
        if not identities:
            self.options.addItem(tr("Consulta no disponible") if warning else tr("No hay certificados RSA aptos"))
        layout.addWidget(self.options)
        self.details = QLabel(objectName="muted")
        self.details.setWordWrap(True)
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setMinimumHeight(145)
        layout.addWidget(self.details, 1)
        self.options.currentIndexChanged.connect(self.update_details)
        self.update_details()
        row = QHBoxLayout()
        row.addWidget(button("Archivo .p12 / .pfx…", self.pick_file))
        row.addStretch()
        row.addWidget(button("Cancelar", self.reject))
        from_store = button("Usar certificado", self.pick_identity, primary=True)
        from_store.setEnabled(bool(identities))
        row.addWidget(from_store)
        layout.addLayout(row)

    def update_details(self):
        identity = self.options.currentData()
        if not identity:
            self.details.setText(
                (self.warning or tr("Los almacenes personales del usuario y del equipo no contienen certificados RSA vigentes con clave privada y uso de firma."))
                + tr("\nPuedes abrir un archivo .p12 o .pfx.")
            )
            return
        from pdf_sign import certificate_details

        try:
            details = certificate_details(base64.b64decode(identity["der"]))
        except Exception as error:
            self.details.setText(tr("No se pudieron leer los datos del certificado: {0}").format(error))
            return
        state = tr("Vigente hoy") if details["valid_now"] else tr("Fuera de su periodo de validez hoy")
        rows = [
            tr("Titular: {0}").format(details["name"]),
            tr("Empresa: {0}").format(details["organization"] or tr("No consta")),
            f'{details["identifier_label"]}: {details["identifier"]}' if details["identifier"] else tr("DNI/NIF: no consta en el certificado"),
            tr("Emisor: {0}").format(details["issuer"]),
            tr("Validez: {0} — {1}").format(details["not_before"], details["not_after"]),
            tr("Clave: {0} · {1}").format(details["key_algorithm"], state),
            tr("Almacén: equipo local") if identity.get("location") == "LocalMachine" else tr("Almacén: usuario actual"),
        ]
        if details["unit"]:
            rows.insert(2, tr("Unidad: {0}").format(details["unit"]))
        if details["title"]:
            rows.insert(3, tr("Cargo: {0}").format(details["title"]))
        self.details.setText("\n".join(rows))

    def pick_identity(self):
        self.identity = self.options.currentData()
        self.accept()

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, tr("Certificado"), filter=tr("Certificados (*.p12 *.pfx)"))
        if not path:
            return
        password, ok = QInputDialog.getText(
            self, tr("Contraseña del certificado"), tr("Contraseña (déjala vacía si el archivo no tiene):"), QLineEdit.EchoMode.Password
        )
        if ok:
            self.pfx, self.password = path, password
            self.accept()


class BatchDialog(QDialog):
    def __init__(self, parent, sources, names=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Firmar varios PDFs"))
        self.resize(1080, 750)
        self.sources = list(dict.fromkeys(sources))
        self.names = names or {}
        self.positions = {}
        self.all_pages = set()
        self.plans = {}
        self.reader = None
        self.coordinates = None
        self.path = None
        layout = QVBoxLayout(self)
        title = QLabel(tr("Coloca una firma en cada PDF"), objectName="chapter")
        layout.addWidget(title)
        self.note = QLabel(tr("Arrastra sobre la página. El borde naranja marca campos ocupados."), objectName="muted")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        options = QHBoxLayout()
        self.scope = QCheckBox(tr("Todas las páginas de este PDF"))
        self.scope.setToolTip(tr("Se crea una firma digital por página. Windows puede solicitar el PIN varias veces."))
        self.scope.toggled.connect(self.set_scope)
        options.addWidget(self.scope)
        self.repeat = button("Usar este recuadro en todo el lote…", self.repeat_position)
        options.addWidget(self.repeat)
        options.addStretch(1)
        layout.addLayout(options)
        row = QHBoxLayout()
        self.files = QListWidget()
        self.files.setFixedWidth(240)
        self.files.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for source in self.sources:
            item = QListWidgetItem(self.names.get(source, Path(source).name))
            item.setToolTip(source)
            self.files.addItem(item)
        row.addWidget(self.files)
        self.view = PageView()
        self.view.selected.connect(self.set_position)
        row.addWidget(self.view, 1)
        layout.addLayout(row, 1)

        actions = QHBoxLayout()
        actions.addWidget(QLabel(tr("Página")))
        self.page_number = QSpinBox()
        self.page_number.setMinimum(1)
        self.page_number.valueChanged.connect(self.show_page)
        actions.addWidget(self.page_number)
        actions.addWidget(button("Borrar recuadro", self.clear_position))
        actions.addWidget(button("−", lambda: self.view.zoom(0.8)))
        actions.addWidget(button("Ajustar", self.view.fit_page))
        actions.addWidget(button("+", lambda: self.view.zoom(1.25)))
        actions.addStretch()
        self.total = QLabel("", objectName="muted")
        actions.addWidget(self.total)
        actions.addWidget(button("Cancelar", self.reject))
        self.confirm = button("Elegir certificado…", self.accept, primary=True)
        actions.addWidget(self.confirm)
        layout.addLayout(actions)
        self.files.currentRowChanged.connect(self.open_source)
        self.files.setCurrentRow(0)
        self.refresh_total()

    def refresh_total(self):
        count = len(self.plans)
        total_signatures = sum(len(plan) for plan in self.plans.values())
        self.total.setText(tr("{0}/{1} PDF · {2} firmas").format(count, len(self.sources), total_signatures))
        self.confirm.setEnabled(count == len(self.sources))
        self.repeat.setEnabled(self.path in self.positions and len(self.sources) > 1 and self.reader is not None)

    def sync_scope(self):
        self.scope.blockSignals(True)
        self.scope.setChecked(self.path in self.all_pages)
        self.scope.setEnabled(self.reader is not None and len(self.reader.pages) > 1)
        self.scope.blockSignals(False)

    def update_file_label(self, source):
        label = self.names.get(source, Path(source).name)
        if source in self.positions:
            page, _ = self.positions[source]
            label += tr(" · {0} páginas").format(len(self.plans[source])) if source in self.all_pages else tr(" · pág. {0}").format(page + 1)
        self.files.item(self.sources.index(source)).setText(label)

    def open_source(self, row):
        if row < 0:
            return
        self.path = self.sources[row]
        try:
            self.reader = reader_for(self.path)
        except Exception as error:
            self.reader = None
            self.view.page()
            self.note.setText(str(error))
            self.sync_scope()
            self.refresh_total()
            return
        self.sync_scope()
        self.refresh_total()
        page, _ = self.positions.get(self.path, (0, None))
        self.page_number.blockSignals(True)
        self.page_number.setMaximum(len(self.reader.pages))
        self.page_number.setValue(page + 1)
        self.page_number.blockSignals(False)
        self.show_page()

    def show_page(self):
        if self.reader is None:
            return
        page = self.page_number.value() - 1
        try:
            with pdfium_reader(self.path) as document:
                image, self.coordinates = render_page(document, page, width=1350, with_coordinates=True)
            self.view.page(image)
            self.refresh_guides()
            self.note.setText(tr("Arrastra sobre la página. El borde naranja marca campos ocupados."))
        except Exception as error:
            self.coordinates = None
            self.view.page()
            self.note.setText(str(error))

    def refresh_guides(self):
        if self.reader is None or self.coordinates is None:
            return
        page = self.page_number.value() - 1
        box = self.plans.get(self.path, {}).get(page)
        self.view.set_mode("signature")
        self.view.mark_boxes(
            self.coordinates, signature_boxes(self.reader.pages[page]),
            box,
        )

    def set_position(self, rect):
        if self.coordinates is None:
            return
        page = self.page_number.value() - 1
        box = self.coordinates.box(rect.left(), rect.top(), rect.right(), rect.bottom())
        try:
            plan = signature_plan(self.reader, page, box, all_pages=self.path in self.all_pages)
        except ValueError as error:
            self.note.setText(str(error))
        else:
            self.positions[self.path] = (page, box)
            self.plans[self.path] = plan
            self.update_file_label(self.path)
            self.note.setText(tr("Recuadro colocado en {0} página(s). Puedes ajustarlo o reutilizarlo en el lote.").format(len(plan)))
        self.refresh_guides()
        self.refresh_total()

    def clear_position(self):
        if self.positions.pop(self.path, None):
            self.plans.pop(self.path, None)
            self.update_file_label(self.path)
            if self.coordinates is not None:
                self.refresh_guides()
            self.refresh_total()

    def set_scope(self, every_page):
        if self.reader is None:
            return
        if self.path in self.positions:
            page, box = self.positions[self.path]
            try:
                self.plans[self.path] = signature_plan(self.reader, page, box, all_pages=every_page)
            except ValueError as error:
                self.sync_scope()
                self.note.setText(str(error))
                return
        if every_page:
            self.all_pages.add(self.path)
        else:
            self.all_pages.discard(self.path)
        self.update_file_label(self.path)
        self.refresh_guides()
        self.refresh_total()
        self.note.setText(tr("Aplicado a todas las páginas de este PDF.") if every_page and self.path in self.plans
                          else tr("Dibuja o ajusta el recuadro en el visor."))

    def repeat_position(self):
        if self.path not in self.positions:
            return
        page, box = self.positions[self.path]
        same_page = tr("Solo la página {0} de cada PDF").format(page + 1)
        all_pages = tr("Todas las páginas de cada PDF")
        keep_scope = tr("Mantener el alcance de cada PDF")
        choice, accepted = QInputDialog.getItem(
            self, tr("Reutilizar recuadro"), tr("Dónde colocar el recuadro en los demás PDFs"),
            [same_page, all_pages, keep_scope], 0, False,
        )
        if not accepted:
            return
        new_positions, new_plans, new_scope = {}, {}, set()
        anchor = self.reader.pages[page]
        for source in self.sources:
            try:
                reader = self.reader if source == self.path else reader_for(source)
                whole = choice == all_pages or (choice == keep_scope and source in self.all_pages)
                target = self.positions.get(source, (page, None))[0] if choice == keep_scope else page
                if whole and target >= len(reader.pages):
                    target = 0
                if target >= len(reader.pages):
                    raise ValueError(tr("El documento no tiene página {0}.").format(target + 1))
                projected = box if source == self.path and page == target else project_signature_box(anchor, reader.pages[target], box)
                new_plans[source] = signature_plan(reader, target, projected, all_pages=whole)
                new_positions[source] = (target, projected)
                if whole:
                    new_scope.add(source)
            except Exception as error:
                name = self.names.get(source, Path(source).name)
                self.note.setText(tr("{0}: {1} Coloca el recuadro por archivo o elige otra posición.").format(name, error))
                return
        self.positions, self.plans, self.all_pages = new_positions, new_plans, new_scope
        for source in self.sources:
            self.update_file_label(source)
        self.sync_scope()
        self.refresh_guides()
        self.refresh_total()
        self.note.setText(tr("Recuadro aplicado al lote. Puedes revisar y ajustar cada PDF antes de firmar."))

    def placements(self):
        return [(source, page, box) for source in self.sources for page, box in self.plans[source].items()]


def _fold_text(value):
    normalized = unicodedata.normalize("NFD", value.casefold())
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


class CommandPaletteDialog(QDialog):
    def __init__(self, entries, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Paleta de comandos"))
        self.resize(520, 420)
        self.entries = entries
        self.chosen = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Buscar comando o herramienta…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)

        self.results = QListWidget()
        self.results.setAlternatingRowColors(False)
        self.results.itemActivated.connect(self.accept_selected)
        layout.addWidget(self.results, 1)

        hint = QLabel(tr("Pulsa Enter para ejecutar o Esc para cerrar."), objectName="muted")
        layout.addWidget(hint)

        self.refresh()
        self.search.setFocus()

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                count = self.results.count()
                if count:
                    row = self.results.currentRow()
                    step = 1 if key == Qt.Key.Key_Down else -1
                    self.results.setCurrentRow((row + step) % count)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.accept_selected()
                return True
        return super().eventFilter(watched, event)

    def refresh(self):
        terms = _fold_text(self.search.text().strip()).split()
        self.results.clear()
        for label, group, shortcut, callback in self.entries:
            haystack = _fold_text(f"{label} {group} {shortcut}")
            if any(term not in haystack for term in terms):
                continue
            display = f"{label}  —  {group}" if group else label
            if shortcut:
                display = f"{display}  ({shortcut})"
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, callback)
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)

    def accept_selected(self, item=None):
        target = item or self.results.currentItem()
        if target is None:
            return
        self.chosen = target.data(Qt.ItemDataRole.UserRole)
        self.accept()
