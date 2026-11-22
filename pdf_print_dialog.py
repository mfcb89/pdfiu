"""Print settings and live sheet preview."""

import sys

from PySide6.QtCore import QEvent, QRectF, QSizeF, Qt, QSignalBlocker, QTimer
from PySide6.QtGui import QColor, QImage, QIntValidator, QPageLayout, QPageSize, QPainter, QPen, QPixmap, QResizeEvent
from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrinterInfo
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from pdf_ops import pdfium_reader
from pdf_print import paint_print_sheet, plan_sheets, requested_pages
from translations import tr


def choices(options):
    control = QComboBox()
    control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    control.setMinimumContentsLength(10)
    for label, value in options:
        control.addItem(tr(label), value)
    return control


def spin(minimum, maximum, value, suffix=""):
    control = QSpinBox()
    control.setRange(minimum, maximum)
    control.setValue(value)
    control.setSuffix(suffix)
    return control


def section(title, control, layout):
    control.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    heading = QLabel(tr(title))
    heading.setObjectName("printSection")
    layout.addWidget(heading)
    layout.addLayout(control)


class PrintDialog(QDialog):
    def __init__(self, parent, source, password, name, sizes, current):
        super().__init__(parent)
        self.source, self.password, self.name = source, password, name
        self.sizes, self.current = sizes, current
        self.sheets = []
        self.printer = None
        self.native_driver = self.native_metrics = None
        self.setWindowTitle(tr("Imprimir PDF"))
        self.resize(960, 690)
        self.setMinimumSize(720, 470)
        self.setStyleSheet(
            "QLabel#printSection {font-weight:600; color:#173831; padding-top:6px;}"
            "QFrame#printPreview {background:#e7edea; border:1px solid #d9e3df; border-radius:12px;}"
            "QLabel#printWarning {color:#8b451e; font-weight:600;}"
        )
        self.timer = QTimer(self, singleShot=True, interval=55)
        self.timer.timeout.connect(self.refresh_plan)
        layout = QVBoxLayout(self)
        title = QLabel(name, objectName="resultHeading")
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        body = QHBoxLayout()
        body.setSpacing(20)
        layout.addLayout(body, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(327)
        scroll.setMaximumWidth(410)
        settings = QWidget()
        scroll.setWidget(settings)
        left = QVBoxLayout(settings)
        left.setContentsMargins(0, 0, 9, 0)
        body.addWidget(scroll, 2)

        self.device = choices(())
        self.device.addItem(tr("Guardar como PDF"), "")
        for printer in QPrinterInfo.availablePrinterNames():
            self.device.addItem(printer, printer)
        default = self.device.findData(QPrinterInfo.defaultPrinterName())
        self.device.setCurrentIndex(max(0, default))
        self.paper = choices(())
        self.paper_width = spin(30, 5000, 210, " mm")
        self.paper_height = spin(30, 5000, 297, " mm")
        custom_paper = QHBoxLayout()
        custom_paper.addWidget(self.paper_width)
        custom_paper.addWidget(QLabel("×"))
        custom_paper.addWidget(self.paper_height)
        self.custom_paper = custom_paper
        self.orientation = choices((("Vertical", QPageLayout.Orientation.Portrait),
                                    ("Horizontal", QPageLayout.Orientation.Landscape)))
        self.orientation.setCurrentIndex(int(sizes[current][0] > sizes[current][1]))
        self.copies = spin(1, 999, 1)
        self.collate = QCheckBox(tr("Intercalar"))
        self.collate.setChecked(True)
        copies_row = QHBoxLayout()
        copies_row.addWidget(self.copies)
        copies_row.addWidget(self.collate)
        self.duplex = choices(())
        self.gray = QCheckBox(tr("Escala de grises"))
        self.driver = QPushButton(tr("Propiedades de la impresora…") if sys.platform == "win32"
                                  else tr("Opciones del controlador…"))
        self.driver.clicked.connect(self.driver_options)
        self.reset_driver_button = QPushButton(tr("Volver a los ajustes de PDFiu"))
        self.reset_driver_button.clicked.connect(self.reset_driver)
        self.reset_driver_button.hide()
        output = QFormLayout()
        output.addRow(tr("Destino"), self.device)
        output.addRow(tr("Papel"), self.paper)
        output.addRow(tr("Ancho × alto"), custom_paper)
        output.addRow(tr("Orientación"), self.orientation)
        output.addRow(tr("Copias"), copies_row)
        output.addRow(tr("Doble cara"), self.duplex)
        output.addRow(self.gray)
        output.addRow(self.driver)
        output.addRow(self.reset_driver_button)
        self.paper_form = output
        section("Impresora y papel", output, left)

        self.scope = choices((("Todas", "all"), ("Página actual", "current"), ("Intervalo", "range")))
        self.expression = QLineEdit()
        self.expression.setPlaceholderText("1, 3-5")
        self.expression.setAccessibleName(tr("Intervalo de páginas"))
        self.expression.installEventFilter(self)
        self.parity = choices((("Pares e impares", "all"), ("Solo impares", "odd"), ("Solo pares", "even")))
        self.reverse = QCheckBox(tr("Orden inverso"))
        selection = QFormLayout()
        selection.addRow(tr("Imprimir"), self.scope)
        selection.addRow(tr("Intervalo"), self.expression)
        selection.addRow(tr("Incluir"), self.parity)
        selection.addRow(self.reverse)
        section("Páginas", selection, left)

        self.mode = choices((("Reducir páginas grandes", "shrink"), ("Ajustar al papel", "fit"),
                             ("Tamaño real (100 %)", "actual"), ("Escala personalizada", "custom"),
                             ("Mosaico para planos", "poster"), ("Varias páginas por hoja", "multiple"),
                             ("Folleto", "booklet")))
        self.scale = spin(10, 600, 100, " %")
        self.overlap = QDoubleSpinBox()
        self.overlap.setRange(0, 50)
        self.overlap.setValue(8)
        self.overlap.setSuffix(" mm")
        self.grid = choices(tuple((str(x * y), (x, y)) for x, y in ((2, 1), (2, 2), (2, 3), (3, 3), (4, 4))))
        self.order = choices((("Por filas", "across"), ("Por filas, de derecha a izquierda", "across-reverse"),
                              ("Por columnas", "down"), ("Por columnas, de derecha a izquierda", "down-reverse")))
        self.booklet_side = choices((("Ambas caras", "both"), ("Solo anversos", "front"), ("Solo reversos", "back")))
        self.binding = choices((("Izquierda", "left"), ("Derecha", "right")))
        self.annotations = QCheckBox(tr("Incluir anotaciones y campos"))
        self.annotations.setChecked(True)
        self.quality = choices((("Borrador (150 ppp)", 150), ("Normal (300 ppp)", 300), ("Alta (600 ppp)", 600)))
        self.quality.setCurrentIndex(1)
        self.layout_form = QFormLayout()
        self.layout_form.addRow(tr("Modo"), self.mode)
        self.layout_form.addRow(tr("Escala"), self.scale)
        self.layout_form.addRow(tr("Solape"), self.overlap)
        self.layout_form.addRow(tr("Páginas por hoja"), self.grid)
        self.layout_form.addRow(tr("Orden de páginas"), self.order)
        self.layout_form.addRow(tr("Caras del folleto"), self.booklet_side)
        self.layout_form.addRow(tr("Encuadernación"), self.binding)
        self.layout_form.addRow(tr("Calidad de imagen"), self.quality)
        self.layout_form.addRow(self.annotations)
        section("Distribución", self.layout_form, left)
        left.addStretch()

        pane = QVBoxLayout()
        body.addLayout(pane, 3)
        header = QLabel(tr("Vista previa de impresión"), objectName="printSection")
        pane.addWidget(header)
        self.preview = QLabel()
        self.preview.setObjectName("printPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.preview.setMinimumSize(250, 235)
        self.preview.setAccessibleName(tr("Vista previa de impresión"))
        pane.addWidget(self.preview, 1)
        self.sheet = QLineEdit("1")
        self.sheet_index = 0
        self.sheet_validator = QIntValidator(1, 1, self.sheet)
        self.sheet.setValidator(self.sheet_validator)
        self.sheet.setAccessibleName(tr("Hoja de vista previa"))
        self.sheet.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sheet.setFixedWidth(68)
        self.sheet.editingFinished.connect(self.go_to_sheet)
        self.sheet.installEventFilter(self)
        self.previous = QPushButton("‹")
        self.previous.setAccessibleName(tr("Hoja anterior"))
        self.previous.clicked.connect(lambda: self.go_to_sheet(self.sheet_index - 1))
        self.following = QPushButton("›")
        self.following.setAccessibleName(tr("Hoja siguiente"))
        self.following.clicked.connect(lambda: self.go_to_sheet(self.sheet_index + 1))
        self.counter = QLabel()
        self.counter.setMinimumWidth(52)
        self.detail = QLabel()
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail.setMinimumHeight(24)
        pane.addWidget(self.detail)
        navigator = QHBoxLayout()
        navigator.addStretch()
        navigator.addWidget(self.previous)
        navigator.addWidget(self.sheet)
        navigator.addWidget(self.counter)
        navigator.addWidget(self.following)
        navigator.addStretch()
        pane.addLayout(navigator)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.warning = QLabel(objectName="printWarning")
        self.warning.setWordWrap(True)
        pane.addWidget(self.summary)
        pane.addWidget(self.warning)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel.setText(tr("Cancelar"))
        cancel.setMinimumWidth(95)
        self.submit = buttons.addButton(tr("Imprimir"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.submit.setObjectName("primary")
        self.submit.setMinimumWidth(145)
        self.submit.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.device.currentIndexChanged.connect(self.setup_printer)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        for control in (self.paper, self.orientation, self.duplex, self.scope, self.parity, self.grid,
                        self.order, self.booklet_side, self.binding, self.quality):
            control.currentIndexChanged.connect(self.schedule)
        for control in (self.gray, self.reverse, self.collate, self.annotations):
            control.toggled.connect(self.schedule)
        for control in (self.copies, self.scale, self.overlap, self.paper_width, self.paper_height):
            control.valueChanged.connect(self.schedule)
        self.expression.textChanged.connect(self.schedule)
        self.mode_changed()
        self.setup_printer()

    def setup_printer(self, *_):
        self.native_driver = self.native_metrics = None
        name = self.device.currentData()
        info = QPrinterInfo.printerInfo(name) if name else QPrinterInfo()
        self.printer = QPrinter(info, QPrinter.PrinterMode.HighResolution) if name else QPrinter(QPrinter.PrinterMode.HighResolution)
        self.printer.setDocName(self.name)
        if not name:
            self.printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            self.printer.setResolution(600)
        self.load_printer_options(info)
        self.driver.setEnabled(bool(name))
        self.copies.setEnabled(bool(name))
        self.submit.setText(tr("Imprimir") if name else tr("Guardar PDF…"))
        self.schedule()

    def load_printer_options(self, info):
        default = self.printer.pageLayout().pageSize()
        papers = info.supportedPageSizes()
        if not papers:
            identifiers = (QPageSize.PageSizeId.A4, QPageSize.PageSizeId.A3, QPageSize.PageSizeId.A5,
                           QPageSize.PageSizeId.A2, QPageSize.PageSizeId.A1, QPageSize.PageSizeId.A0,
                           QPageSize.PageSizeId.Letter, QPageSize.PageSizeId.Legal)
            papers = [QPageSize(identifier) for identifier in identifiers]
            if info.isNull():
                default = papers[0]
        if default.isValid() and all(paper.key() != default.key() for paper in papers):
            papers.insert(0, default)
        with QSignalBlocker(self.paper), QSignalBlocker(self.duplex):
            self.paper.clear()
            for paper in papers:
                self.paper.addItem(paper.name(), paper)
                if paper.key() == default.key():
                    self.paper.setCurrentIndex(self.paper.count() - 1)
            if info.isNull() or info.supportsCustomPageSizes() or default.id() == QPageSize.PageSizeId.Custom:
                self.paper.addItem(tr("Tamaño personalizado"), None)
            self.duplex.clear()
            self.duplex.addItem(tr("Una cara"), QPrinter.DuplexMode.DuplexNone)
            supported = info.supportedDuplexModes()
            for label, mode in (("Voltear por el borde largo", QPrinter.DuplexMode.DuplexLongSide),
                                ("Voltear por el borde corto", QPrinter.DuplexMode.DuplexShortSide)):
                if mode in supported or QPrinter.DuplexMode.DuplexAuto in supported:
                    self.duplex.addItem(tr(label), mode)
            default_mode = self.duplex.findData(self.printer.duplex())
            self.duplex.setCurrentIndex(max(0, default_mode))
        self.duplex.setEnabled(self.duplex.count() > 1)

    def driver_options(self):
        if sys.platform == "win32":
            self.windows_driver_options()
            return
        self.refresh_plan()
        dialog = QPrintDialog(self.printer, self)
        if dialog.exec():
            name = self.printer.printerName()
            with QSignalBlocker(self.device), QSignalBlocker(self.orientation):
                index = self.device.findData(name)
                if index >= 0:
                    self.device.setCurrentIndex(index)
                self.orientation.setCurrentIndex(int(self.printer.pageLayout().orientation() == QPageLayout.Orientation.Landscape))
            self.load_printer_options(QPrinterInfo.printerInfo(name))
            self.schedule()

    def windows_driver_options(self):
        from windows_print import DriverSettings

        paper = self.current_paper()
        size = paper.size(QPageSize.Unit.Millimeter)
        paper_id = 0 if paper.id() == QPageSize.PageSizeId.Custom else paper.windowsId()
        duplex = self.duplex.currentData()
        orientation = self.current_orientation()
        flip = {
            QPrinter.DuplexMode.DuplexShortSide: 3,
            QPrinter.DuplexMode.DuplexLongSide: 2,
        }.get(duplex, 1)
        if self.mode.currentData() == "booklet" and self.booklet_side.currentData() == "both":
            flip = 3 if self.duplex.findData(QPrinter.DuplexMode.DuplexShortSide) >= 0 else 1
        try:
            selected = DriverSettings.choose(
                int(self.winId()), self.device.currentData(),
                orientation=2 if orientation == QPageLayout.Orientation.Landscape else 1,
                paper=(paper_id, round(size.width() * 10), round(size.height() * 10)),
                color=1 if self.gray.isChecked() else 2, duplex=flip,
                copies=self.copies.value(), collate=self.collate.isChecked(), previous=self.native_driver,
            )
            if selected is None:
                return
            metrics = selected.metrics()
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, tr("Propiedades de la impresora…"), str(error))
            return
        self.native_driver, self.native_metrics = selected, metrics
        self.schedule()

    def reset_driver(self):
        self.native_driver = self.native_metrics = None
        self.schedule()

    def current_paper(self):
        paper = self.paper.currentData()
        if paper is not None:
            return paper
        width, height = sorted((self.paper_width.value(), self.paper_height.value()))
        return QPageSize(QSizeF(width, height), QPageSize.Unit.Millimeter,
                         tr("Tamaño personalizado"), QPageSize.SizeMatchPolicy.ExactMatch)

    def current_orientation(self):
        if self.mode.currentData() == "booklet":
            return QPageLayout.Orientation.Landscape
        return self.orientation.currentData()

    def geometry(self):
        if self.native_metrics is not None:
            return self.native_metrics.paper, self.native_metrics.area
        paper = self.printer.paperRect(QPrinter.Unit.Point)
        return paper, self.printer.pageRect(QPrinter.Unit.Point).translated(-paper.topLeft())

    def mode_changed(self, *_):
        mode = self.mode.currentData()
        for control, visible in ((self.scale, mode in ("custom", "poster")), (self.overlap, mode == "poster"),
                                 (self.grid, mode == "multiple"), (self.order, mode == "multiple"),
                                 (self.booklet_side, mode == "booklet"), (self.binding, mode == "booklet")):
            self.layout_form.setRowVisible(control, visible)
        self.schedule()

    def schedule(self, *_):
        use_driver = self.native_driver is not None
        self.expression.setEnabled(self.scope.currentData() == "range")
        self.paper_form.setRowVisible(self.custom_paper, self.paper.currentData() is None)
        self.paper.setEnabled(not use_driver)
        self.paper_width.setEnabled(not use_driver)
        self.paper_height.setEnabled(not use_driver)
        self.orientation.setEnabled(not use_driver and self.mode.currentData() != "booklet")
        self.copies.setEnabled(not use_driver and bool(self.device.currentData()))
        self.duplex.setEnabled(not use_driver and self.duplex.count() > 1)
        self.gray.setEnabled(not use_driver)
        self.collate.setEnabled(self.copies.isEnabled() and self.copies.value() > 1)
        self.reset_driver_button.setVisible(use_driver)
        self.submit.setEnabled(False)
        self.timer.start()

    def refresh_plan(self):
        self.timer.stop()
        try:
            if not self.printer.isValid():
                raise ValueError(tr("La impresora seleccionada no está disponible."))
            mode = self.mode.currentData()
            if self.native_driver is None:
                self.apply_standard_settings(mode)
            elif mode == "booklet":
                paper, _ = self.geometry()
                required = 3 if self.booklet_side.currentData() == "both" else 1
                if paper.width() < paper.height() or self.native_driver.duplex != required:
                    raise ValueError(tr("Para imprimir el folleto, ajusta la orientación horizontal y la doble cara en las propiedades de la impresora."))
            pages = requested_pages(len(self.sizes), self.current, self.scope.currentData(), self.expression.text(),
                                    self.parity.currentData(), self.reverse.isChecked())
            _, area = self.geometry()
            self.sheets = plan_sheets(pages, self.sizes, area.width(), area.height(), mode=mode, percent=self.scale.value(),
                                      overlap_mm=self.overlap.value(), grid=self.grid.currentData(), order=self.order.currentData(),
                                      booklet_side=self.booklet_side.currentData(), binding=self.binding.currentData())
            self.sheet_validator.setTop(len(self.sheets))
            self.sheet_index = min(self.sheet_index, len(self.sheets) - 1)
            self.sheet.setText(str(self.sheet_index + 1))
            copies = self.native_driver.copies if self.native_driver else (self.copies.value() if self.device.currentData() else 1)
            summary = tr("{0} página(s) del PDF · {1} cara(s) por copia · {2} copia(s)").format(len(pages), len(self.sheets), copies)
            if self.native_driver:
                summary += "\n" + tr("Usando las propiedades del controlador para este trabajo.")
            self.summary.setText(summary)
            clipped = sum(sheet.clipped for sheet in self.sheets)
            self.warning.setText(tr("{0} cara(s) tienen contenido fuera del área imprimible.").format(clipped) if clipped else "")
            self.paint_preview()
            self.submit.setEnabled(True)
        except Exception as error:
            self.sheets = []
            self.preview.clear()
            self.summary.clear()
            self.counter.clear()
            self.detail.clear()
            self.warning.setText(str(error))
            self.submit.setEnabled(False)

    def apply_standard_settings(self, mode):
        if not self.printer.setPageSize(self.current_paper()) or not self.printer.setPageOrientation(self.current_orientation()):
            raise ValueError(tr("La impresora no admite este formato u orientación."))
        duplex = self.duplex.currentData()
        if mode == "booklet":
            if self.booklet_side.currentData() in ("front", "back"):
                duplex = QPrinter.DuplexMode.DuplexNone
            elif self.device.currentData():
                if self.duplex.findData(QPrinter.DuplexMode.DuplexShortSide) < 0:
                    raise ValueError(tr("Para un folleto con esta impresora, imprime anversos y reversos por separado."))
                duplex = QPrinter.DuplexMode.DuplexShortSide
        self.printer.setDuplex(duplex)
        self.printer.setColorMode(QPrinter.ColorMode.GrayScale if self.gray.isChecked() else QPrinter.ColorMode.Color)

    def go_to_sheet(self, index=None):
        if not self.sheets:
            return
        if index is None:
            text = self.sheet.text().strip()
            index = int(text) - 1 if text.isdecimal() else self.sheet_index
        self.sheet_index = min(max(0, index), len(self.sheets) - 1)
        self.sheet.setText(str(self.sheet_index + 1))
        self.paint_preview()

    def paint_preview(self):
        if not self.sheets:
            return
        index = self.sheet_index
        self.previous.setEnabled(index > 0)
        self.following.setEnabled(index + 1 < len(self.sheets))
        self.counter.setText(tr("de {0}").format(len(self.sheets)))
        paper, area = self.geometry()
        unit = 25.4 / 72
        dimensions = tr("{0:.0f} × {1:.0f} mm").format(paper.width() * unit, paper.height() * unit)
        if len(self.sheets[index].placements) == 1 and self.mode.currentData() not in ("multiple", "booklet"):
            scale = self.sheets[index].placements[0][1][2]
            dimensions += f"  ·  {scale:.0%}"
        self.detail.setText(dimensions)
        ratio = min((self.preview.width() - 30) / paper.width(), (self.preview.height() - 30) / paper.height())
        ratio = max(.08, ratio)
        image = QImage(max(1, round(paper.width() * ratio)), max(1, round(paper.height() * ratio)), QImage.Format.Format_RGB32)
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            box = QRectF(area.x() * ratio, area.y() * ratio, area.width() * ratio, area.height() * ratio)
            with pdfium_reader(self.source, password=self.password) as document:
                paint_print_sheet(painter, document, self.sizes, self.sheets[index], box, ratio * 72, ratio * 72,
                                  grayscale=self.native_driver.grayscale if self.native_driver else self.gray.isChecked(),
                                  annotations=self.annotations.isChecked())
            color = "#a35324" if self.sheets[index].clipped else "#919ba8"
            painter.setPen(QPen(QColor(color), 1, Qt.PenStyle.DashLine))
            painter.drawRect(box)
        finally:
            painter.end()
        self.preview.setPixmap(QPixmap.fromImage(image))

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        if hasattr(self, "timer") and self.sheets:
            self.timer.start()

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if watched is self.sheet:
                self.go_to_sheet()
                return True
            if watched is self.expression:
                self.refresh_plan()
                return True
        return super().eventFilter(watched, event)

    def accept(self):
        self.refresh_plan()
        if self.sheets:
            super().accept()

    def render_settings(self):
        return dict(sheets=self.sheets, sizes=self.sizes, quality=self.quality.currentData(),
                    copies=self.copies.value() if self.device.currentData() else 1, collate=self.collate.isChecked(),
                    grayscale=self.gray.isChecked(), annotations=self.annotations.isChecked())
