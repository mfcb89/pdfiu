from translations import tr

from functools import lru_cache
from html import escape
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap, QTextCharFormat, QTextLayout, QTextOption
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QSplashScreen, QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTextEdit, QVBoxLayout, QWidget

from pdf_ops import HeaderRun


ICON_PATH = Path(__file__).resolve().parent / "assets" / "fluent"
BRAND_PATH = ICON_PATH.parent / "brand"
ICON_NAMES = {
    "arrows-collapse-full": "full_screen_minimize",
    "bookmark": "bookmark",
    "chat-2-text": "comment_text",
    "checkbox-list": "task_list_square_ltr",
    "chevron-down": "chevron_down",
    "chevron-left": "chevron_left",
    "chevron-right": "chevron_right",
    "chevron-up": "chevron_up",
    "close": "dismiss",
    "delete-bin": "delete",
    "document-award": "certificate",
    "document": "document",
    "edit-pen-2": "edit",
    "file": "document",
    "file-minus": "document_arrow_up",
    "file-plus": "document_add",
    "folder-plus": "folder_open",
    "hand": "hand_right",
    "image-frame": "image_arrow_forward",
    "image": "image",
    "image-multiple": "image_multiple",
    "key": "key",
    "layers": "layer",
    "lock": "lock_closed",
    "maximize": "full_screen_maximize",
    "minus": "subtract",
    "note-text-plus": "document_add",
    "paper-fold-text": "document_text",
    "plus": "add",
    "reload-circle": "arrow_clockwise",
    "save": "save",
    "scanner": "scan_text",
    "search": "search",
    "shooting-star": "star",
    "star": "star",
    "text": "text_font",
    "textbox": "textbox",
    "unlock-open": "lock_open",
    "view-columns": "layout_column_two",
    "combine": "merge",
    "export": "arrow_export_ltr",
    "extract": "document_arrow_up",
    "compress": "document_contract",
    "headers": "document_header_footer",
    "numbering": "document_number_1",
    "highlight": "highlight",
    "underline": "text_underline",
    "shapes": "shapes",
    "measure": "ruler",
    "redact": "eye_off",
    "sign": "signature",
    "batch-sign": "document_multiple",
    "add-note": "comment_add",
    "rail-files": "folder",
    "rail-pages": "document_copy",
    "rail-bookmarks": "bookmark",
    "rail-layers": "layer",
    "rail-comments": "comment_text",
    "rail-signatures": "document_signature",
    "rail-fit": "document_fit",
    "rail-previous": "chevron_up",
    "rail-next": "chevron_down",
    "rail-zoom-in": "zoom_in",
    "rail-zoom-out": "zoom_out",
}
INK = "#182a3d"
MINT = "#97d7c3"
SEARCH_EXCERPT_ROLE = Qt.ItemDataRole.UserRole + 1
ANNOTATION_CARD_ROLE = Qt.ItemDataRole.UserRole + 4


def signature_details_html(details):
    """Format certificate fields as selectable text with a clear reading order."""
    missing = tr("No consta")

    if details["valid_now"] is None:
        status, color = tr("Vigencia sin determinar"), "#516472"
    elif details["valid_now"]:
        status, color = tr("Vigente hoy"), "#256755"
    else:
        status, color = tr("Certificado fuera de vigencia"), "#885917"

    identity_label = details["identifier_label"] or tr("DNI, NIF u otro identificador")
    identity = escape(details["identifier"] or missing)

    at_signing = details["valid_at_reported_time"]
    comparison = {
        True: tr("El certificado cubría la fecha declarada por el PDF."),
        False: tr("El certificado no cubría la fecha declarada por el PDF."),
        None: tr("No se pudo comparar la fecha declarada con el certificado."),
    }[at_signing]
    rows = [
        (tr(label), details[key])
        for label, key in (("Organización", "organization"), ("Identificador de la organización", "organization_identifier"),
                           ("Unidad", "unit"), ("Cargo", "title"))
        if details.get(key)
    ]
    rows.extend((
        (tr("Periodo del certificado"), f'{details["not_before"]} – {details["not_after"]}'),
        (tr("Emisor"), details["issuer"]),
        (tr("Fecha declarada de firma"), details["signed_at"]),
        (tr("En la fecha de firma"), comparison),
        (tr("Cobertura"), details["coverage"]),
        (tr("Integridad criptográfica"), {
            True: tr("Comprobada en los bytes firmados"),
            False: tr("La comprobación ha fallado"),
            None: tr("No se pudo comprobar"),
        }[details.get("integrity")]),
        (tr("Confianza del certificado"), {
            True: tr("Cadena reconocida por las raíces disponibles"),
            False: tr("No se pudo establecer una cadena de confianza"),
            None: tr("Sin determinar"),
        }[details.get("trusted")]),
        (tr("Número de serie del certificado"), details.get("certificate_serial")),
        (tr("Algoritmo de clave"), details["key_algorithm"]),
        (tr("Campo PDF"), details["field_name"]),
    ))
    summary = "".join(
        f"<tr><td><b>{escape(label)}</b></td><td>{escape(str(value or missing))}</td></tr>"
        for label, value in rows
    )
    trust_note = tr("Comprobación local. El estado de revocación en línea no se consulta.")
    return (
        f'<h1 style="font-size:24px;margin-top:0;margin-bottom:4px;">{escape(details["name"])}</h1>'
        f'<p style="margin-top:0;margin-bottom:4px;"><span style="color:#516472;">{escape(identity_label)}</span>'
        f' &nbsp; <b style="font-size:16px;">{identity}</b></p>'
        f'<p style="font-size:15px;color:{color};margin-top:0;margin-bottom:8px;"><b>{escape(status)}</b></p>'
        f'<table width="100%" cellspacing="0" cellpadding="3" style="font-size:12px;">{summary}</table>'
        f'<p style="font-size:12px;color:#516472;margin-top:8px;">{escape(trust_note)}</p>'
    )


class SearchResultDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        card = index.data(ANNOTATION_CARD_ROLE)
        if card is not None:
            self._paint_annotation_card(painter, option, card)
            return
        excerpt = index.data(SEARCH_EXCERPT_ROLE)
        if excerpt is None:
            super().paint(painter, option, index)
            return
        row = QStyleOptionViewItem(option)
        self.initStyleOption(row, index)
        row.text = ""
        row.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, row, painter, row.widget)
        page_font = QFont(option.font)
        page_font.setPixelSize(11)
        page_font.setWeight(QFont.Weight.DemiBold)
        painter.save()
        painter.setClipRect(option.rect)
        painter.setFont(page_font)
        painter.setPen(option.palette.placeholderText().color())
        x, y = option.rect.x() + 10, option.rect.y() + 8
        painter.drawText(QRectF(x, y, option.rect.width() - 20, 15), index.data(Qt.ItemDataRole.UserRole + 2))
        before, match, after = excerpt
        layout = QTextLayout(before + match + after, option.font)
        settings = QTextOption()
        settings.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        layout.setTextOption(settings)
        bold = QTextLayout.FormatRange()
        bold.start = len(before.encode("utf-16-le")) // 2
        bold.length = len(match.encode("utf-16-le")) // 2
        bold.format.setFontWeight(QFont.Weight.Bold)
        bold.format.setForeground(option.palette.text().color())
        layout.setFormats([bold])
        painter.setPen(option.palette.text().color())
        layout.beginLayout()
        height = 0
        while (line := layout.createLine()).isValid():
            line.setLineWidth(max(1, option.rect.width() - 20))
            line.setPosition(QPointF(0, height))
            height += line.height()
        layout.endLayout()
        layout.draw(painter, QPointF(x, y + 18))
        painter.restore()

    def _paint_annotation_card(self, painter, option, card):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = option.rect.adjusted(4, 3, -4, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        accent = QColor(card.get("color", "#3b82f6"))
        base = option.palette.base().color()
        is_dark = base.lightness() < 128
        if selected:
            fill = QColor("#1f3a56") if is_dark else QColor("#eef5fc")
            border = QColor("#60a5fa") if is_dark else QColor("#6fa3d8")
        elif hovered:
            fill = QColor("#242b35") if is_dark else QColor("#f7fafd")
            border = QColor("#3f4a59") if is_dark else QColor("#c8d6e5")
        else:
            fill = QColor("#1d232b") if is_dark else QColor("#ffffff")
            border = QColor("#2f3846") if is_dark else QColor("#dce4ee")
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 8, 8)

        # Colored left accent bar
        bar_rect = QRectF(rect.x() + 1, rect.y() + 6, 3.5, max(8, rect.height() - 12))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(bar_rect, 2, 2)

        x = rect.x() + 12
        y = rect.y() + 7
        width = max(40, rect.width() - 20)

        meta_font = QFont(option.font)
        meta_font.setPixelSize(11)
        meta_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(meta_font)
        painter.setPen(accent)
        kind_text = card.get("kind", "")
        page_text = card.get("page_label", "")
        painter.drawText(QRectF(x, y, width, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, kind_text)
        painter.setPen(QColor("#94a3b8") if is_dark else QColor("#64748b"))
        painter.drawText(QRectF(x, y, width, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, page_text)

        body = card.get("text", "").strip()
        body_font = QFont(option.font)
        body_font.setPixelSize(12)
        if not body:
            body = card.get("empty_label", "")
            body_font.setItalic(True)
            painter.setPen(QColor("#8291a3") if is_dark else QColor("#7b8b9c"))
        else:
            painter.setPen(QColor("#e2e8f0") if is_dark else QColor("#1e293b"))
        painter.setFont(body_font)
        body_rect = QRectF(x, y + 20, width, max(18, rect.height() - 32))
        painter.drawText(body_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, body)
        painter.restore()

    def sizeHint(self, option, index):
        card = index.data(ANNOTATION_CARD_ROLE)
        if card is not None:
            body = card.get("text", "").strip()
            lines = 1 if not body else min(4, max(1, (len(body) // 34) + 1))
            return QSize(0, 38 + lines * (option.fontMetrics.lineSpacing() + 1))
        if index.data(SEARCH_EXCERPT_ROLE) is None:
            return super().sizeHint(option, index)
        return QSize(0, 34 + 4 * option.fontMetrics.lineSpacing())


def text_line_boxes(rectangles):
    """Combine adjacent PDFium rectangles that share a horizontal text line."""
    lines = []
    for box in rectangles:
        if box.width() <= 0 or box.height() <= 0:
            continue
        if lines:
            line = lines[-1]
            overlap = min(line.bottom(), box.bottom()) - max(line.top(), box.top())
            gap = max(box.left() - line.right(), line.left() - box.right())
            if overlap >= 0.75 * min(line.height(), box.height()) and gap <= 0.45 * max(line.height(), box.height()):
                lines[-1] = line.united(box)
                continue
        lines.append(box)
    return lines


def brand_icon(name="pdfiu-app"):
    return QIcon(str(BRAND_PATH / f"{name}.svg"))


def brand_pixmap(name="papel-en-vuelo", size=44):
    source = (BRAND_PATH / f"{name}.svg").read_bytes()
    if _active_theme == "dark" and name == "papel-en-vuelo":
        source = source.replace(b"#182a3d", b"#dce8f5").replace(b"#317f72", b"#3da391")
    renderer = QSvgRenderer(QByteArray(source))
    dpr = 2
    pixmap = QPixmap(size * dpr, size * dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    with QPainter(pixmap) as painter:
        renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def startup_screen(credit):
    pixmap = QPixmap(960, 472)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(QColor(INK))
    with QPainter(pixmap) as painter:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        brand_icon().paint(painter, QRect(199, 26, 82, 82))
        font = QFont("Segoe UI")
        font.setPixelSize(48)
        font.setWeight(QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor("#fffefa"))
        painter.drawText(QRect(0, 109, 480, 65), Qt.AlignmentFlag.AlignCenter, "PDFiu")
        font.setPixelSize(15)
        font.setWeight(QFont.Weight.Normal)
        painter.setFont(font)
        painter.setPen(QColor(MINT))
        painter.drawText(QRect(0, 182, 480, 28), Qt.AlignmentFlag.AlignCenter, credit)
    return QSplashScreen(pixmap)


_active_theme = "light"


def icon_ink(primary=False):
    if primary:
        return "#ffffff"
    return "#dce6f2" if _active_theme == "dark" else "#334353"


@lru_cache(maxsize=320)
def _render_icon(name, size, color, checked_color, disabled_color, filled_when_checked):
    stem = ICON_NAMES[name]
    sizes = sorted((16, 20, 24, 32), key=lambda grid: (abs(grid - size), -grid))
    regular = next(path for grid in sizes
                   if (path := ICON_PATH / f"{stem}_{grid}_regular.svg").is_file())
    variants = [(QIcon.State.Off, regular, color)]
    filled = ICON_PATH / f"{stem}_{size}_filled.svg"
    if filled_when_checked:
        variants.append((QIcon.State.On, filled if filled.is_file() else regular, checked_color))
    result = QIcon()
    for state, source_file, ink in variants:
        source = source_file.read_bytes()
        for mode, tone in ((QIcon.Mode.Normal, ink), (QIcon.Mode.Disabled, disabled_color)):
            renderer = QSvgRenderer(QByteArray(source.replace(b"<svg ", f'<svg fill="{tone}" '.encode("ascii"), 1)))
            for dpr in (1, 1.25, 1.5, 1.75, 2, 2.5, 3):
                pixels = round(size * dpr)
                pixmap = QPixmap(pixels, pixels)
                pixmap.fill(Qt.GlobalColor.transparent)
                with QPainter(pixmap) as painter:
                    renderer.render(painter, QRectF(0, 0, pixels, pixels))
                pixmap.setDevicePixelRatio(dpr)
                result.addPixmap(pixmap, mode, state)
    return result


def icon(name, size=16, color=None, *, filled_when_checked=False):
    dark = _active_theme == "dark"
    if color is None or (dark and color in ("#334353", "#3c4963")):
        ink = "#dce6f2" if dark else "#334353"
    else:
        ink = color
    checked_color = "#6ee7b7" if dark else "#236152"
    disabled_color = "#5a6878" if dark else "#8a979f"
    return _render_icon(name, size, ink, checked_color, disabled_color, filled_when_checked)


class PanelRail(QFrame):
    def paintEvent(self, event):
        super().paintEvent(event)
        with QPainter(self) as painter:
            border = QColor("#2b3440") if _active_theme == "dark" else QColor("#dde5e1")
            painter.fillRect(self.width() - 1, 0, 1, self.height(), border)


class TourSpotlight(QWidget):
    """Paint a window-local highlight without intercepting clicks or keyboard input."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setStyleSheet("background: transparent;")
        self.targets = []
        self.clear_area = QRect()
        self.hide()

    def highlight(self, anchors, *, keep_bright=None):
        parent = self.parentWidget()
        rectangles = []
        for widget, part in anchors:
            if not widget.isVisible():
                continue
            visible = widget.visibleRegion().boundingRect()
            area = visible if part is None else part.intersected(visible)
            if not area.isEmpty():
                area.translate(widget.mapTo(parent, QPoint()))
                rectangles.append(area.adjusted(-4, -4, 4, 4))
        self.targets = rectangles
        if keep_bright is not None and keep_bright.isVisible():
            self.clear_area = QRect(keep_bright.mapTo(parent, QPoint()), keep_bright.size())
        else:
            self.clear_area = QRect()
        self.setGeometry(parent.rect())
        self.setVisible(bool(rectangles))
        if rectangles:
            self.raise_()
            self.update()

    def follow_button(self, button):
        self.followed_button = button
        self.parentWidget().installEventFilter(self)
        button.installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.LayoutRequest):
            QTimer.singleShot(0, self, self.update_button_highlight)
        return False

    def update_button_highlight(self):
        self.highlight([(self.followed_button, None)])

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            dim = QPainterPath()
            dim.addRect(QRectF(self.rect()))
            for rect in (*self.targets, self.clear_area):
                if rect.isEmpty():
                    continue
                hole = QPainterPath()
                hole.addRoundedRect(QRectF(rect), 7, 7)
                dim = dim.subtracted(hole)
            painter.fillPath(dim, QColor(19, 34, 56, 52))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#2462b5"), 3))
            for rect in self.targets:
                painter.drawRoundedRect(QRectF(rect), 7, 7)


class PageNavigator(QWidget):
    center_requested = Signal(QPointF)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(126)
        self.setAccessibleName(tr("Minivisor de la página"))
        self.setToolTip(tr("Arrastra el recuadro o pulsa otra zona para mover la vista."))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.page = QRectF()
        self.visible = QRectF()
        self.preview = QPixmap()
        self.preview_item = None
        self.drag_offset = None

    def show_position(self, item, page, visible):
        if item is not self.preview_item:
            self.preview_item = item
            self.preview = item.pixmap().scaled(384, 240, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation) if item else QPixmap()
        if page != self.page:
            self.drag_offset = None
        self.page, self.visible = page, visible
        self.update()

    def preview_rect(self):
        if self.preview.isNull():
            return QRectF()
        size = self.preview.size().scaled(self.width() - 12, self.height() - 10, Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRectF(0, 0, size.width(), size.height())
        rect.moveCenter(QRectF(self.rect()).center())
        return rect

    def position_rect(self, preview):
        area = self.page.intersected(self.visible)
        if area.isEmpty():
            return QRectF()
        sx, sy = preview.width() / self.page.width(), preview.height() / self.page.height()
        return QRectF(preview.left() + (area.left() - self.page.left()) * sx,
                      preview.top() + (area.top() - self.page.top()) * sy, area.width() * sx, area.height() * sy)

    def paintEvent(self, event):
        preview = self.preview_rect()
        if preview.isEmpty():
            return
        with QPainter(self) as painter:
            painter.fillRect(self.rect(), QColor("#e9edf4"))
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(preview, self.preview, QRectF(self.preview.rect()))
            painter.setPen(QPen(QColor("#a0a9b9")))
            painter.drawRect(preview)
            position = self.position_rect(preview)
            if not position.isEmpty():
                painter.setPen(QPen(QColor("#184b9a"), 2))
                painter.setBrush(QColor(48, 105, 192, 37))
                painter.drawRect(position)

    def page_point(self, position, preview):
        return QPointF(self.page.left() + (position.x() - preview.left()) * self.page.width() / preview.width(),
                       self.page.top() + (position.y() - preview.top()) * self.page.height() / preview.height())

    def mousePressEvent(self, event):
        preview = self.preview_rect()
        if event.button() != Qt.MouseButton.LeftButton or not preview.contains(event.position()):
            return
        point = self.page_point(event.position(), preview)
        self.drag_offset = QPointF()
        if self.position_rect(preview).contains(event.position()):
            self.drag_offset = self.visible.center() - point
        self.center_requested.emit(point + self.drag_offset)

    def mouseMoveEvent(self, event):
        preview = self.preview_rect()
        if self.drag_offset is not None and not preview.isEmpty():
            self.center_requested.emit(self.page_point(event.position(), preview) + self.drag_offset)

    def mouseReleaseEvent(self, event):
        self.drag_offset = None


class HeaderEditor(QWidget):
    families = {"Helvetica": "Arial", "Times": "Times New Roman", "Courier": "Courier New"}

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        self.fonts = QComboBox()
        for family in self.families:
            self.fonts.addItem(family)
        self.fonts.setAccessibleName(tr("Fuente"))
        self.fonts.currentTextChanged.connect(self.set_family)
        toolbar.addWidget(self.fonts)
        self.bold = self.style_button(toolbar, "N", "Negrita", "bold")
        self.italic = self.style_button(toolbar, "C", "Cursiva", "italic")
        self.underline = self.style_button(toolbar, "S", "Subrayado", "underline")
        toolbar.addStretch(1)
        for label, marker in ((tr("Página"), "{página}"), ("Total", "{total}"), (tr("Archivo"), "{archivo}")):
            action = QPushButton(label)
            action.setProperty("role", "flat")
            action.setToolTip(tr("Insertar {0}").format(marker))
            action.clicked.connect(lambda _, token=marker: self.insert_marker(token))
            toolbar.addWidget(action)
        layout.addLayout(toolbar)
        self.text = QTextEdit()
        self.text.setAcceptRichText(False)
        self.text.setPlaceholderText(tr("Expediente · Página {página} de {total}"))
        self.text.setMinimumHeight(86)
        self.text.setAccessibleName(tr("Texto del encabezado o pie"))
        self.text.setFont(QFont(self.families["Helvetica"]))
        self.text.currentCharFormatChanged.connect(self.sync_toolbar)
        layout.addWidget(self.text)

    def style_button(self, toolbar, label, name, style):
        button = QPushButton(label)
        button.setCheckable(True)
        button.setFixedWidth(34)
        button.setAccessibleName(name)
        button.setToolTip(name)
        font = button.font()
        getattr(font, {"bold": "setBold", "italic": "setItalic", "underline": "setUnderline"}[style])(True)
        button.setFont(font)
        button.clicked.connect(lambda checked: self.apply_style(style, checked))
        toolbar.addWidget(button)
        return button

    def insert_marker(self, token):
        self.text.insertPlainText(token)
        self.text.setFocus()

    def set_family(self, family):
        fmt = QTextCharFormat()
        fmt.setFontFamilies([self.families[family]])
        self.text.mergeCurrentCharFormat(fmt)
        self.text.setFocus()

    def apply_style(self, style, enabled):
        fmt = QTextCharFormat()
        if style == "bold":
            fmt.setFontWeight(QFont.Weight.Bold if enabled else QFont.Weight.Normal)
        elif style == "italic":
            fmt.setFontItalic(enabled)
        else:
            fmt.setFontUnderline(enabled)
        self.text.mergeCurrentCharFormat(fmt)
        self.text.setFocus()

    def family_for(self, fmt):
        families = fmt.fontFamilies() or ()
        return next((name for name, system in self.families.items() if system in families), "Helvetica")

    def sync_toolbar(self, fmt):
        self.fonts.blockSignals(True)
        self.fonts.setCurrentText(self.family_for(fmt))
        self.fonts.blockSignals(False)
        self.bold.setChecked(fmt.fontWeight() >= QFont.Weight.Bold)
        self.italic.setChecked(fmt.fontItalic())
        self.underline.setChecked(fmt.fontUnderline())

    def formatted_lines(self):
        if not self.text.toPlainText().strip():
            raise ValueError(tr("Escribe el texto del encabezado o pie."))
        lines = []
        paragraph = self.text.document().begin()
        while paragraph.isValid():
            runs = []
            cursor = paragraph.begin()
            while not cursor.atEnd():
                chunk = cursor.fragment()
                if chunk.isValid():
                    fmt = chunk.charFormat()
                    runs.append(HeaderRun(chunk.text(), self.family_for(fmt),
                                          fmt.fontWeight() >= QFont.Weight.Bold,
                                          fmt.fontItalic(), fmt.fontUnderline()))
                cursor += 1
            lines.append(tuple(runs))
            paragraph = paragraph.next()
        return tuple(lines)


STYLE = """
QWidget { background: #fff; color: #182a3d; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QFrame#shellBar, QFrame#footer { background: #fff; }
QFrame#navigationRail { background: #fafbf9; border: 0; }
QFrame#navigationRail QScrollArea#railScroll,
QFrame#navigationRail QWidget#railViewport,
QFrame#navigationRail QWidget#railSections,
QFrame#readerControls,
QWidget#readerGroup { background: transparent; }
QFrame#navigationRail QWidget#readerZoomGroup {
    background: transparent; border-top: 1px solid #dde5e1;
}
QWidget#readerZoomGroup { background: transparent; }
QFrame#shellBar { border-bottom: 1px solid #e0e8e3; }
QFrame#footer { border-top: 1px solid #e0e8e3; }
QFrame#docTabStrip { background: #f3f6f4; border-bottom: 1px solid #dce6e1; }
QTabBar#docTabs { background: transparent; border: 0; }
QTabBar#docTabs::tab {
    background: transparent; color: #516472; border: 1px solid transparent; border-radius: 7px;
    padding: 5px 8px 5px 11px; margin: 3px 2px; max-width: 240px;
}
QTabBar#docTabs::tab:hover:!selected { background: #e8f0ec; color: #182a3d; }
QTabBar#docTabs::tab:selected { background: #ffffff; color: #182a3d; border-color: #d4e0da; font-weight: 600; }
QPushButton#tabClose {
    padding: 0; min-height: 0; border: 0; border-radius: 9px; background: transparent;
}
QPushButton#tabClose:hover { background: #dbe6e0; }
QFrame#findBar { background: #f8faf9; border-bottom: 1px solid #dce6e1; }
QFrame#sidebar, QFrame#navigationOverview, QWidget#workspaceFiles, QWidget#workspaceNavigation { background: #f3f6f4; }
QFrame#navigationOverview { border-bottom: 1px solid #dce6e1; }
QWidget#workspaceNavigation { border-right: 1px solid #dce6e1; }
QFrame#toolPanel, QWidget#toolRow { background: #fff; }
QFrame#toolPanel { border-left: 1px solid #dce6e1; }
QFrame#toolCategories { background: #f1f5f2; border: 1px solid #e0e8e3; border-radius: 10px; }
QFrame#formStrip { background: #edf4fb; border-bottom: 1px solid #dbe6f3; }
QFrame#signatureStrip { background: #edf4fb; border-bottom: 1px solid #dbe6f3; }
QFrame#signatureStrip QLabel { color: #19483f; font-weight: 600; }
QFrame#tourStrip { background: #edf7f0; border-bottom: 1px solid #dbe4ed; }
QLabel#tourTitle { color: #19483f; font-weight: 700; }
QFrame#welcomeOffer { background: transparent; border-top: 1px solid #dce6e1; }
QFrame#shapePanel { background: #f6f8fc; border: 1px solid #e0e8e3; border-radius: 8px; }
QFrame#shapePanel QCheckBox { background: transparent; }
QLabel { background: transparent; }
QLabel#brand { font-size: 18px; font-weight: 700; color: #182a3d; }
QFrame#toolbarDivider { background: #dce6e1; }
QLabel#chapter { font-size: 13px; font-weight: 650; color: #35415a; }
QLabel#fileTitle { font-weight: 600; color: #182a3d; }
QLabel#fileState { color: #8f662e; font-size: 12px; }
QFrame#redactionStrip { background: #fff6e6; border-bottom: 1px solid #e5cc9e; }
QFrame#redactionStrip QLabel { color: #6b4414; background: transparent; }
QLabel#muted { color: #516472; }
QTextBrowser#signatureDetails { background: #fff; border: 1px solid #dce6e1; border-radius: 8px; }
QLabel#panelLabel { color: #516472; font-size: 12px; font-weight: 600; }
QLabel#toolHeading, QLabel#resultHeading { color: #182a3d; font-size: 16px; font-weight: 650; }
QLabel#toolScope { color: #19483f; background: #eaf5ef; padding: 7px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
QLabel#emptyHeading { font-size: 29px; font-weight: 600; color: #182a3d; }
QLabel#emptyIcon { background: #e9f5ef; border-radius: 15px; }
QPushButton { padding: 7px 11px; min-height: 17px; border: 1px solid #dce6e1; border-radius: 7px; background: #fff; }
QPushButton:hover { background: #eff6f2; border-color: #d5dfea; }
QPushButton:pressed { background: #dcefe6; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #37796d; }
QPushButton:disabled { color: #a0a9b9; background: #f8f9fc; border-color: #edf0f5; }
QPushButton#primary { background: #182a3d; color: white; border-color: #182a3d; font-weight: 600; }
QPushButton#primary:hover { background: #294459; border-color: #294459; }
QPushButton#primary:disabled { color: #8d99ad; background: #f2f4f8; border-color: #e0e8e3; }
QPushButton:checked { background: #dcf1e8; border-color: #a5d2c2; color: #19483f; }
QPushButton[role="tool"] { text-align: left; padding: 9px 9px; border: 1px solid transparent; background: transparent; }
QPushButton[role="tool"]:hover { background: #edf5ef; }
QPushButton[role="tool"]:focus { border-color: #37796d; }
QPushButton[role="tool"]:checked { background: #dcf1e8; color: #19483f; border-color: #c4e4d7; }
QPushButton[role="tool"]:disabled { color: #a0a9b9; background: transparent; }
QPushButton[role="tool"][batchTool="true"]:enabled { color: #19483f; font-weight: 600; }
QPushButton[role="tool"][batchTool="true"]:enabled:hover { background: #eaf5ef; }
QPushButton[role="category"], QPushButton[role="icon"] { padding: 0; border: 1px solid transparent; background: transparent; }
QPushButton[role="category"] { padding: 4px 5px; text-align: left; font-size: 12px; }
QPushButton[role="category"]:hover, QPushButton[role="icon"]:hover { background: #e9f4ee; }
QPushButton[role="category"]:focus, QPushButton[role="icon"]:focus { border-color: #37796d; }
QPushButton[role="category"]:checked, QPushButton[role="icon"]:checked { background: #dcf1e8; border-color: #c4e4d7; }
QPushButton[role="category"]:checked { background: #dcf1e8; border-color: #c4e4d7; color: #19483f; font-weight: 600; }
QPushButton[role="category"]:checked:focus { border-color: #37796d; }
QPushButton[role="flat"] { text-align: left; padding: 7px 8px; background: transparent; border: 1px solid transparent; }
QPushButton[role="flat"]:hover { background: #e9f4ee; }
QPushButton[role="flat"]:focus { border-color: #37796d; }
QListWidget, QTreeWidget { background: #fff; border: 1px solid #e0e8e3; border-radius: 7px; outline: none; }
QListWidget#files, QListWidget#pageList { background: #f3f6f4; border: 0; }
QListWidget#files::indicator { width: 15px; height: 15px; }
QListWidget#files::item:focus { outline: 1px solid #37796d; }
QFrame#pageInsertLine { background: #317f72; border-radius: 1px; }
QListWidget::item { padding: 8px; border-radius: 7px; margin: 2px 3px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #dcf1e8; color: #19483f; }
QListWidget::item:hover:!selected { background: #eff5f1; }
QGraphicsView { border: 0; background: #e8edea; }
QWidget#emptyState { background: #f2f5f2; }
QFrame#emptyCard { background: #fff; border: 1px solid #dce6e1; border-radius: 18px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox { background: #fff; border: 1px solid #dce6e1; padding: 5px; border-radius: 6px; }
QComboBox { padding-right: 25px; }
QComboBox::drop-down { border: 0; width: 24px; subcontrol-origin: padding; subcontrol-position: top right; }
QLineEdit#zoomLevel { background: #f3f6fa; border-color: transparent; padding: 4px 5px; color: #35415a; }
QLineEdit#zoomLevel:focus { border-color: #37796d; }
QPushButton[role="railSection"], QPushButton[role="readerButton"], QPushButton[role="readerSize"] {
    padding: 0; min-height: 0; border: 1px solid transparent; border-radius: 5px; background: transparent;
}
QPushButton[role="railSection"]:hover, QPushButton[role="readerButton"]:hover, QPushButton[role="readerSize"]:hover {
    background: #eef2ef;
}
QPushButton[role="railSection"]:checked { background: #e1eee7; }
QPushButton[role="railSection"]:focus, QPushButton[role="readerButton"]:focus, QPushButton[role="readerSize"]:focus {
    border-color: #548b79;
}
QPushButton[role="readerSize"]::menu-indicator { image: none; width: 0; height: 0; }
QLabel#readerPageTotal { color: #52636e; font-size: 11px; padding-bottom: 3px; }
QLineEdit#readerPageNumber, QLineEdit#zoomLevel {
    padding: 0; color: #182a3d; font-size: 12px; font-weight: 600;
    background: transparent; border: 1px solid transparent; border-radius: 4px;
}
QLineEdit#readerPageNumber { background: #fff; border-color: #d4dfda; }
QLineEdit#readerPageNumber:hover, QLineEdit#zoomLevel:hover { background: #fff; border-color: #b8cec4; }
QLineEdit#readerPageNumber:focus, QLineEdit#zoomLevel:focus { background: #fff; border-color: #548b79; }
QWidget#navigationPanel { background: #fff; border-right: 1px solid #e0e7e3; }
QTabWidget#workspaceNavigation, QTabWidget#workspaceNavigation QFrame#sidebar,
QTabWidget#workspaceNavigation QWidget#workspaceFiles, QTabWidget#workspaceNavigation QWidget#sidebar {
    background: #fff;
}
QTabWidget#workspaceNavigation QLabel#panelLabel { color: #233a3b; font-size: 14px; font-weight: 600; }
QTabWidget#workspaceNavigation QListWidget, QTabWidget#workspaceNavigation QTreeWidget {
    background: #fff; border: 0; border-radius: 0;
}
QTabWidget#workspaceNavigation QListWidget::item, QTabWidget#workspaceNavigation QTreeWidget::item {
    padding-left: 5px; padding-right: 5px; border-radius: 5px;
}
QTabWidget#workspaceNavigation QListWidget::item:selected, QTabWidget#workspaceNavigation QTreeWidget::item:selected {
    background: #e2efe9; color: #214b40;
}
QProgressBar { max-height: 7px; background: #e8edf5; border: 0; border-radius: 3px; }
QProgressBar::chunk { background: #317f72; border-radius: 3px; }
QTabBar { background: transparent; }
QTabBar::tab { padding: 6px 10px; margin: 4px 2px 3px; border-radius: 6px; color: #516472; }
QTabBar::tab:selected { background: #dcf1e8; color: #19483f; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #eff5f1; }
QTabWidget::pane { border: 0; }
QDockWidget::title { background: #f0f3f8; padding: 7px; }
QMenuBar { background: white; color: #182a3d; border-bottom: 1px solid #dce6e1; padding: 2px 8px; }
QMenuBar::item { background: transparent; padding: 5px 9px; }
QMenuBar::item:selected { background: #dcf1e8; color: #19483f; }
QMenu { background: #fff; color: #182a3d; border: 1px solid #dbe4f1; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 23px 7px 12px; border: 1px solid transparent; border-radius: 5px; }
QMenu::item:selected { background: #dcf1e8; color: #19483f; border-color: #d6e3f7; }
QMenu::item:disabled { color: #8490a3; }
QMenu::separator { background: #e4eaf3; height: 1px; margin: 4px 6px; }
QComboBox QAbstractItemView { background: #fff; border: 1px solid #dbe4f1; padding: 4px;
                            outline: none; selection-background-color: #dcf1e8; selection-color: #19483f; }
QComboBox QAbstractItemView::item { min-height: 23px; padding: 3px 6px; }
QToolTip { background: #182a3d; color: #fffefa; border: 1px solid #294459; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #afc0b8; min-height: 24px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
STYLE += f'QComboBox::down-arrow {{ image: url("{(ICON_PATH / "chevron_down_16_regular.svg").as_posix()}"); width: 14px; height: 14px; }}'


DARK_STYLE = """
QMainWindow, QDialog, QWidget { background: #161b22; color: #e6edf3; font-family: "Segoe UI", "Helvetica Neue", Arial; font-size: 13px; }
QFrame#topbar, QFrame#shellBar, QFrame#readerFooter, QFrame#footer, QFrame#statusBar { background: #1c222b; border-bottom: 1px solid #2b3440; }
QFrame#docTabStrip { background: #181e26; border-bottom: 1px solid #2b3440; }
QTabBar#docTabs { background: transparent; border: 0; }
QTabBar#docTabs::tab {
    background: transparent; color: #8b9bb0; border: 1px solid transparent; border-radius: 7px;
    padding: 5px 8px 5px 11px; margin: 3px 2px; max-width: 240px;
}
QTabBar#docTabs::tab:hover:!selected { background: #222a35; color: #e6edf3; }
QTabBar#docTabs::tab:selected { background: #242d39; color: #f0f6fc; border-color: #364354; font-weight: 600; }
QPushButton#tabClose {
    padding: 0; min-height: 0; border: 0; border-radius: 9px; background: transparent;
}
QPushButton#tabClose:hover { background: #334052; }
QFrame#findBar { background: #1c222b; border-bottom: 1px solid #2b3440; }
QFrame#readerFooter, QFrame#footer, QFrame#statusBar { border-top: 1px solid #2b3440; border-bottom: 0; }
QFrame#rail, QFrame#navigationRail { background: #181e26; border-right: 1px solid #2b3440; }
QFrame#navigationRail QScrollArea#railScroll,
QFrame#navigationRail QWidget#railViewport,
QFrame#navigationRail QWidget#railSections,
QFrame#readerControls,
QWidget#readerGroup,
QWidget#readerZoomGroup { background: transparent; }
QFrame#navigationRail QWidget#readerZoomGroup { border-top: 1px solid #2b3440; }
QFrame#sidebar, QFrame#navigationOverview, QWidget#workspaceFiles, QWidget#workspaceNavigation { background: #1a2028; }
QFrame#navigationOverview { border-bottom: 1px solid #2b3440; }
QWidget#workspaceNavigation { border-right: 1px solid #2b3440; }
QFrame#toolPanel, QWidget#toolRow { background: #1c222b; }
QFrame#toolPanel { border-left: 1px solid #2b3440; }
QFrame#toolCategories { background: #161b22; border: 1px solid #2b3440; border-radius: 10px; }
QFrame#formStrip, QFrame#signatureStrip { background: #1b2a38; border-bottom: 1px solid #2b4257; }
QFrame#signatureStrip QLabel { color: #7dd3fc; font-weight: 600; }
QFrame#tourStrip { background: #172b26; border-bottom: 1px solid #26483e; }
QLabel#tourTitle { color: #6ee7b7; font-weight: 700; }
QFrame#welcomeOffer { background: transparent; border-top: 1px solid #2b3440; }
QFrame#shapePanel { background: #1d2530; border: 1px solid #2b3440; border-radius: 8px; }
QFrame#shapePanel QCheckBox { background: transparent; }
QLabel { background: transparent; color: #e6edf3; }
QLabel#brand { font-size: 18px; font-weight: 700; color: #f0f6fc; }
QFrame#toolbarDivider { background: #2b3440; }
QLabel#chapter { font-size: 13px; font-weight: 650; color: #c9d5e2; }
QLabel#fileTitle { font-weight: 600; color: #f0f6fc; }
QLabel#fileState { color: #fbbf24; font-size: 12px; }
QFrame#redactionStrip { background: #332614; border-bottom: 1px solid #6b4c1d; }
QFrame#redactionStrip QLabel { color: #fde68a; background: transparent; }
QLabel#muted { color: #8b9bb0; }
QTextBrowser#signatureDetails { background: #161b22; border: 1px solid #2b3440; border-radius: 8px; color: #e6edf3; }
QLabel#panelLabel { color: #9fb0c4; font-size: 12px; font-weight: 600; }
QLabel#toolHeading, QLabel#resultHeading { color: #f0f6fc; font-size: 16px; font-weight: 650; }
QLabel#toolScope { color: #6ee7b7; background: #17302a; padding: 7px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; }
QLabel#emptyHeading { font-size: 29px; font-weight: 600; color: #f0f6fc; }
QLabel#emptyIcon { background: #1e3531; border: 1px solid #2c4c46; border-radius: 15px; }
QPushButton { padding: 7px 11px; min-height: 17px; border: 1px solid #303a47; border-radius: 7px; background: #222a35; color: #e6edf3; }
QPushButton:hover { background: #2b3544; border-color: #3f4d60; }
QPushButton:pressed { background: #1f3c36; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border: 1px solid #4fb39d; }
QPushButton:disabled { color: #647285; background: #1b2028; border-color: #262e38; }
QPushButton#primary { background: #2f7d6d; color: #ffffff; border-color: #2f7d6d; font-weight: 600; }
QPushButton#primary:hover { background: #389380; border-color: #389380; }
QPushButton#primary:disabled { color: #6b7c8f; background: #212a34; border-color: #2b3440; }
QPushButton:checked { background: #1d3c35; border-color: #3c8675; color: #8ff0d4; }
QPushButton[role="tool"] { text-align: left; padding: 9px 9px; border: 1px solid transparent; background: transparent; color: #dde6f0; }
QPushButton[role="tool"]:hover { background: #252e3a; }
QPushButton[role="tool"]:focus { border-color: #4fb39d; }
QPushButton[role="tool"]:checked { background: #1d3c35; color: #8ff0d4; border-color: #327263; }
QPushButton[role="tool"]:disabled { color: #5b6778; background: transparent; }
QPushButton[role="tool"][batchTool="true"]:enabled { color: #6ee7b7; font-weight: 600; }
QPushButton[role="tool"][batchTool="true"]:enabled:hover { background: #1b312c; }
QPushButton[role="category"], QPushButton[role="icon"] { padding: 0; border: 1px solid transparent; background: transparent; color: #d0dae6; }
QPushButton[role="category"] { padding: 4px 5px; text-align: left; font-size: 12px; }
QPushButton[role="category"]:hover, QPushButton[role="icon"]:hover { background: #252e3a; }
QPushButton[role="category"]:focus, QPushButton[role="icon"]:focus { border-color: #4fb39d; }
QPushButton[role="category"]:checked, QPushButton[role="icon"]:checked { background: #1d3c35; border-color: #327263; }
QPushButton[role="category"]:checked { color: #8ff0d4; font-weight: 600; }
QPushButton[role="flat"] { text-align: left; padding: 7px 8px; background: transparent; border: 1px solid transparent; color: #dde6f0; }
QPushButton[role="flat"]:hover { background: #252e3a; }
QListWidget, QTreeWidget { background: #161b22; border: 1px solid #2b3440; border-radius: 7px; outline: none; color: #e6edf3; }
QListWidget#files, QListWidget#pageList { background: #1a2028; border: 0; }
QListWidget#files::indicator { width: 15px; height: 15px; }
QFrame#pageInsertLine { background: #4fb39d; border-radius: 1px; }
QListWidget::item { padding: 8px; border-radius: 7px; margin: 2px 3px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #1d3c35; color: #8ff0d4; }
QListWidget::item:hover:!selected { background: #222a35; }
QGraphicsView { border: 0; background: #101419; }
QWidget#emptyState { background: #12171d; }
QFrame#emptyCard { background: #1c222b; border: 1px solid #2b3440; border-radius: 18px; }
QLineEdit, QTextEdit, QComboBox, QSpinBox { background: #141920; color: #e6edf3; border: 1px solid #303a47; padding: 5px; border-radius: 6px; }
QComboBox { padding-right: 25px; }
QComboBox::drop-down { border: 0; width: 24px; subcontrol-origin: padding; subcontrol-position: top right; }
QLineEdit#zoomLevel { background: #202833; border-color: transparent; padding: 4px 5px; color: #d8e2ee; }
QLineEdit#zoomLevel:focus { border-color: #4fb39d; }
QPushButton[role="railSection"], QPushButton[role="readerButton"], QPushButton[role="readerSize"] {
    padding: 0; min-height: 0; border: 1px solid transparent; border-radius: 5px; background: transparent; color: #d0dae6;
}
QPushButton[role="railSection"]:hover, QPushButton[role="readerButton"]:hover, QPushButton[role="readerSize"]:hover {
    background: #252e3a;
}
QPushButton[role="railSection"]:checked { background: #1d3c35; }
QPushButton[role="readerSize"]::menu-indicator { image: none; width: 0; height: 0; }
QLabel#readerPageTotal { color: #8b9bb0; font-size: 11px; padding-bottom: 3px; }
QLineEdit#readerPageNumber, QLineEdit#zoomLevel {
    padding: 0; color: #f0f6fc; font-size: 12px; font-weight: 600;
    background: transparent; border: 1px solid transparent; border-radius: 4px;
}
QLineEdit#readerPageNumber { background: #141920; border-color: #303a47; }
QLineEdit#readerPageNumber:hover, QLineEdit#zoomLevel:hover { background: #1d242e; border-color: #465466; }
QLineEdit#readerPageNumber:focus, QLineEdit#zoomLevel:focus { background: #141920; border-color: #4fb39d; }
QWidget#navigationPanel { background: #1c222b; border-right: 1px solid #2b3440; }
QTabWidget#workspaceNavigation, QTabWidget#workspaceNavigation QFrame#sidebar,
QTabWidget#workspaceNavigation QWidget#workspaceFiles, QTabWidget#workspaceNavigation QWidget#sidebar {
    background: #1c222b;
}
QTabWidget#workspaceNavigation QLabel#panelLabel { color: #c9d5e2; font-size: 14px; font-weight: 600; }
QTabWidget#workspaceNavigation QListWidget, QTabWidget#workspaceNavigation QTreeWidget {
    background: #1c222b; border: 0; border-radius: 0;
}
QTabWidget#workspaceNavigation QListWidget::item, QTabWidget#workspaceNavigation QTreeWidget::item {
    padding-left: 5px; padding-right: 5px; border-radius: 5px;
}
QTabWidget#workspaceNavigation QListWidget::item:selected, QTabWidget#workspaceNavigation QTreeWidget::item:selected {
    background: #1d3c35; color: #8ff0d4;
}
QProgressBar { max-height: 7px; background: #242d39; border: 0; border-radius: 3px; }
QProgressBar::chunk { background: #4fb39d; border-radius: 3px; }
QTabBar { background: transparent; }
QTabBar::tab { padding: 6px 10px; margin: 4px 2px 3px; border-radius: 6px; color: #8b9bb0; }
QTabBar::tab:selected { background: #1d3c35; color: #8ff0d4; font-weight: 600; }
QTabBar::tab:hover:!selected { background: #222a35; }
QTabWidget::pane { border: 0; }
QDockWidget::title { background: #1f2631; padding: 7px; color: #e6edf3; }
QMenuBar { background: #1c222b; color: #e6edf3; border-bottom: 1px solid #2b3440; padding: 2px 8px; }
QMenuBar::item { background: transparent; padding: 5px 9px; }
QMenuBar::item:selected { background: #1d3c35; color: #8ff0d4; }
QMenu { background: #1c222b; color: #e6edf3; border: 1px solid #303a47; border-radius: 8px; padding: 5px; }
QMenu::item { padding: 7px 23px 7px 12px; border: 1px solid transparent; border-radius: 5px; }
QMenu::item:selected { background: #1d3c35; color: #8ff0d4; border-color: #327263; }
QMenu::item:disabled { color: #647285; }
QMenu::separator { background: #2b3440; height: 1px; margin: 4px 6px; }
QComboBox QAbstractItemView { background: #1c222b; color: #e6edf3; border: 1px solid #303a47; padding: 4px;
                            outline: none; selection-background-color: #1d3c35; selection-color: #8ff0d4; }
QComboBox QAbstractItemView::item { min-height: 23px; padding: 3px 6px; }
QToolTip { background: #0f141a; color: #f0f6fc; border: 1px solid #303a47; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3b4656; min-height: 24px; border-radius: 3px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


def resolve_theme(preference):
    if preference in ("light", "dark"):
        return preference
    try:
        scheme = QGuiApplication.styleHints().colorScheme()
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
    except AttributeError:
        pass
    return "light"


def refresh_widget_icons(application):
    for widget in application.allWidgets():
        if isinstance(widget, QPushButton):
            meta = widget.property("iconGlyph")
            if isinstance(meta, tuple) and len(meta) == 4:
                glyph, size, primary, filled = meta
                widget.setIcon(icon(glyph, size, "#ffffff" if primary else None, filled_when_checked=filled))
        elif isinstance(widget, QLabel):
            mark = widget.property("brandMark")
            if isinstance(mark, tuple) and len(mark) == 2:
                name, size = mark
                widget.setPixmap(brand_pixmap(name, size))


def apply_theme(application, preference="system"):
    global _active_theme
    mode = resolve_theme(preference)
    _active_theme = mode
    palette = QPalette()
    if mode == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor("#161b22"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#e6edf3"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#141920"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#1c222b"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#e6edf3"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#222a35"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#e6edf3"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1d3c35"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#8ff0d4"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8b9bb0"))
        application.setPalette(palette)
        application.setStyleSheet(DARK_STYLE)
    else:
        application.setPalette(application.style().standardPalette())
        application.setStyleSheet(STYLE)
    refresh_widget_icons(application)
    return mode
