"""Canvas views, list widgets, worker jobs, and UI helpers for PDFiu."""

from bisect import bisect_left, bisect_right
from contextlib import ExitStack
from dataclasses import dataclass, field as dataclass_field
from math import ceil, floor
from pathlib import Path
import json

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QRectF, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QImage, QKeySequence, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QFrame, QGraphicsDropShadowEffect, QGraphicsScene, QGraphicsView,
    QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QStyle, QStyleOptionViewItem,
    QStyledItemDelegate, QTabBar,
)

from pdf_ops import Coordinates, OperationCancelled, document_text, page_text, pdfium_reader, render_page, render_page_tile
from pdfiu_ui import SEARCH_EXCERPT_ROLE, icon, text_line_boxes
from tool_help import tool_hint
from translations import tr


SEARCH_PAGE_COUNT_ROLE = Qt.ItemDataRole.UserRole + 3


def search_result_item(page, match=None, *, count=None):
    page_label = tr("Página {0}").format(page + 1)
    if count is not None:
        page_label = tr("{0} · {1} coincidencia(s)").format(page_label, count)
    if match is None:
        context = tr("Página incluida por la condición de exclusión.")
        item = QListWidgetItem(page_label + "\n" + context)
        item.setData(Qt.ItemDataRole.UserRole, [page])
        item.setData(SEARCH_EXCERPT_ROLE, ["", "", context])
    else:
        start, length, excerpt = match
        before, found, after = (" ".join(part.split()) for part in excerpt)
        if before and (excerpt[0][-1].isspace() or before.endswith("…")):
            before += " "
        if after and excerpt[2][0].isspace():
            after = " " + after
        context = before + found + after
        item = QListWidgetItem(page_label + "\n" + context)
        item.setData(Qt.ItemDataRole.UserRole, [page, start, length])
        item.setData(SEARCH_EXCERPT_ROLE, [before, found, after])
    item.setToolTip(context)
    item.setData(Qt.ItemDataRole.UserRole + 2, page_label)
    item.setData(SEARCH_PAGE_COUNT_ROLE, count)
    return item


def as_qimage(image):
    return QImage(image.tobytes(), image.width, image.height, image.width * 3, QImage.Format.Format_RGB888).copy()


def file_size_label(count):
    return f"{count / (1024**2):.2f} MiB" if count >= 1024**2 else f"{count / 1024:.1f} KiB"


def button(label, handler, *, primary=False, glyph=None):
    widget = QPushButton(tr(label))
    widget.setProperty("sourceLabel", label)
    widget.setToolTip(tool_hint(label))
    widget.setToolTipDuration(15000)
    widget.clicked.connect(lambda: handler())
    if primary:
        widget.setObjectName("primary")
    if glyph:
        widget.setProperty("iconGlyph", (glyph, 16, primary, False))
        widget.setIcon(icon(glyph, color="#ffffff" if primary else None))
    return widget


def icon_button(label, glyph, handler, *, size=32, glyph_size=20):
    control = button("", handler)
    control.setProperty("iconGlyph", (glyph, glyph_size, False, False))
    control.setIcon(icon(glyph, glyph_size))
    control.setIconSize(QSize(glyph_size, glyph_size))
    control.setProperty("role", "icon")
    control.setFixedSize(size, size)
    control.setToolTip(label)
    control.setAccessibleName(label)
    return control


def action_menu(label, entries, glyph=None):
    control = QPushButton(tr(label))
    control.setProperty("sourceLabel", label)
    control.setToolTip(tool_hint(label))
    control.setToolTipDuration(15000)
    menu = QMenu(control)
    for title, handler in entries:
        action = menu.addAction(title, handler)
        action.setToolTip(tool_hint(title))
    menu.setToolTipsVisible(True)
    control.setMenu(menu)
    if glyph:
        control.setProperty("iconGlyph", (glyph, 16, False, False))
        control.setIcon(icon(glyph))
    return control


@dataclass
class WorkDocument:
    path: Path
    name: str
    dirty: bool = False
    page: int = 0
    saved_path: Path | None = None
    protected_source: Path | None = None
    redactions: dict = dataclass_field(default_factory=dict)
    password: str | None = dataclass_field(default=None, repr=False)


MEASURE_UNITS = {
    "m": ("metros", 1), "cm": ("centímetros", 0.01), "mm": ("milímetros", 0.001),
    "ft": ("pies", 0.3048), "in": ("pulgadas", 0.0254),
}


@dataclass(frozen=True)
class PageCalibration:
    meters_per_point: float
    unit: str


class PageView(QGraphicsView):
    selected = Signal(QRectF)
    point_selected = Signal(QPointF)
    zoom_changed = Signal(int)
    text_error = Signal(str)
    text_selection_changed = Signal(bool)
    selection_finished = Signal(QPoint)
    text_copied = Signal()
    form_clicked = Signal(QPointF)
    signature_clicked = Signal(str)
    shape_drawn = Signal(QPointF, QPointF)

    def __init__(self):
        super().__init__()
        self.password = None
        self.setScene(QGraphicsScene(self))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.mode = None
        self.page_rect = QRectF()
        self.start = None
        self.rubber = None
        self.guides = []
        self.measure_marks = []
        self.fit = True
        self.text_source = None
        self.text_handles = ExitStack()
        self.text_page = None
        self.text_anchor = self.text_end = None
        self.text_marks = []
        self.form_items = []
        self.form_rects = []
        self.signature_targets = []
        self.form_press = None
        self.inline_editor = None
        self.space_pan = False
        self.pan_anchor = None
        self.shape_preview_color = QColor("#3569aa")
        self.shape_preview_width = 2
        self.shape_preview_dashed = False
        self.shape_preview_filled = False
        self.viewport().setMouseTracking(True)
        self.copied_text = ""
        self.image_item = None
        self.zoom_render = QTimer(self)
        self.zoom_render.setSingleShot(True)
        self.zoom_render.setInterval(140)
        self.zoom_render.timeout.connect(self.refresh_resolution)
        self.zoom_changed.connect(lambda _: self.zoom_render.start())

    def page(self, image=None, *, text_source=None, preserve_zoom=False):
        self.finish_inline(commit=False)
        self.clear_text()
        self.zoom_render.stop()
        previous_percent = self.percent()
        self.text_source = text_source
        self.start = self.rubber = None
        self.guides.clear()
        self.measure_marks.clear()
        self.form_items.clear()
        self.form_rects.clear()
        self.signature_targets.clear()
        self.form_press = None
        self.scene().clear()
        self.image_item = None
        self.page_rect = QRectF()
        if image is None:
            item = self.scene().addText(tr("Abre un PDF para empezar"))
            item.setDefaultTextColor(QColor("#435d67"))
            self.scene().setSceneRect(item.boundingRect().adjusted(-20, -20, 20, 20))
            self.resetTransform()
            return
        self.image_item = self.scene().addPixmap(QPixmap.fromImage(as_qimage(image)))
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(19)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(37, 51, 78, 43))
        self.image_item.setGraphicsEffect(shadow)
        self.image_item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.page_rect = self.image_item.boundingRect()
        self.rendered_width = image.width
        self.scene().setSceneRect(self.page_rect.adjusted(-25, -25, 25, 25))
        if not preserve_zoom:
            self.fit = True
        if preserve_zoom and not self.fit and text_source:
            self.set_percent(previous_percent)
        else:
            self.apply_fit()

    def refresh_resolution(self):
        if not self.text_source or self.image_item is None or self.text_page is not None:
            return
        path, index, _ = self.text_source
        requested = max(128, self.page_rect.width() * self.transform().m11() * self.devicePixelRatioF())
        limit = 6000 * min(1, self.page_rect.width() / self.page_rect.height())
        target = round(min(limit, requested))
        if abs(target - self.rendered_width) <= 2:
            return
        try:
            with pdfium_reader(path, password=self.password) as document:
                image = render_page(document, index, width=target)
        except Exception:
            return
        self.image_item.setPixmap(QPixmap.fromImage(as_qimage(image)))
        self.image_item.setTransform(QTransform.fromScale(self.page_rect.width() / image.width, self.page_rect.height() / image.height))
        self.rendered_width = image.width
        self.update_raster_interpolation(self.image_item)

    def update_raster_interpolation(self, item):
        scale = self.transform().m11() * self.devicePixelRatioF()
        bounds = item.sceneBoundingRect()
        raster = item.pixmap()
        near_native = (abs(bounds.width() * scale - raster.width()) <= 2 and
                       abs(bounds.height() * scale - raster.height()) <= 3)
        # Avoid averaging adjacent pixels at fractional positions once the raster fits the screen.
        item.setTransformationMode(Qt.TransformationMode.FastTransformation if near_native else
                                   Qt.TransformationMode.SmoothTransformation)

    def fit_page(self):
        self.fit = True
        self.apply_fit()

    def fit_width(self):
        self.fit = "width"
        self.apply_fit()

    def apply_fit(self):
        if not self.page_rect.isEmpty():
            if self.fit == "width":
                width = min(self.viewport().width(), self.maximumViewportSize().width() - 18)
                self.set_zoom(max(1, width - 6) / self.sceneRect().width())
            elif self.fit:
                self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
                self.zoom_changed.emit(self.percent())
            else:
                self.zoom_changed.emit(self.percent())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.fit:
            self.apply_fit()

    def percent(self):
        return round(self.transform().m11() * 100 / self.actual_scale())

    def actual_scale(self):
        if self.text_source:
            return 96 / 72 * sum(value * value for value in self.text_source[2].right) ** 0.5
        return 1

    def set_percent(self, percent):
        self.fit = False
        self.set_zoom(percent * self.actual_scale() / 100)

    def set_zoom(self, scale):
        self.scale(scale / self.transform().m11(), scale / self.transform().m11())
        self.update_zoom_interpolation()
        self.zoom_changed.emit(self.percent())

    def update_zoom_interpolation(self):
        if self.image_item is not None:
            self.update_raster_interpolation(self.image_item)

    def zoom(self, factor, *, at_mouse=False):
        if self.page_rect.isEmpty():
            return
        target = self.transform().m11() * factor
        scale = min(8 * self.actual_scale(), max(0.10 * self.actual_scale(), target))
        self.fit = False
        if at_mouse:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.set_zoom(scale)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.angleDelta().y():
            self.zoom(1.2 ** (event.angleDelta().y() / 120), at_mouse=True)
            event.accept()
        else:
            super().wheelEvent(event)

    def clear_text(self):
        self.text_handles.close()
        self.text_page = None
        self.text_anchor = self.text_end = None
        self.set_copied_text("")
        self.clear_text_marks()

    def set_copied_text(self, value):
        self.copied_text = value
        self.text_selection_changed.emit(bool(value.strip()))

    def clear_text_marks(self):
        for mark in self.text_marks:
            self.scene().removeItem(mark)
        self.text_marks.clear()

    def begin_text(self, point):
        self.clear_text()
        try:
            path, index, coordinates = self.text_source
            self.text_page = self.text_handles.enter_context(page_text(path, index, password=self.password))
            if not self.text_page.count_chars():
                self.text_error.emit(tr("Esta página no tiene texto seleccionable. Aplica OCR si es un escaneo."))
                self.clear_text()
                return
            self.text_page.count_rects()
            self.text_anchor = self.text_page.get_index(*coordinates.at(point.x(), point.y()), 12, 8)
            if self.text_anchor is None:
                self.clear_text()
        except Exception as error:
            self.clear_text()
            self.text_error.emit(str(error))

    def extend_text(self, point):
        coordinates = self.text_source[2]
        x, y = coordinates.at(point.x(), point.y())
        end = self.text_page.get_index(x, y, 8, 12)
        if end is None:
            end = self.text_page.get_index(x, y, 144, 12)
        if end is None or end == self.text_end:
            return
        self.text_end = end
        start, stop = sorted((self.text_anchor, end))
        self.mark_text_range(self.text_page, coordinates, start, stop - start + 1)

    def mark_text_range(self, content, coordinates, start, count):
        self.clear_text_marks()
        for rect in self.text_range_rects(content, coordinates, start, count):
            self.text_marks.append(self.scene().addRect(rect, QPen(Qt.PenStyle.NoPen), QColor(50, 113, 211, 88)))

    @staticmethod
    def text_range_rects(content, coordinates, start, count):
        boxes = []
        for index in range(content.count_rects(start, count)):
            x1, y1, x2, y2 = content.get_rect(index)
            boxes.append(QRectF(QPointF(x1, y1), QPointF(x2, y2)).normalized())
        for box in text_line_boxes(boxes):
            rect = QRectF(QPointF(*coordinates.device(box.left(), box.top())),
                          QPointF(*coordinates.device(box.right(), box.bottom())))
            yield rect.normalized()

    def show_text_match(self, start, count):
        if not self.text_source:
            return
        self.clear_text()
        path, index, coordinates = self.text_source
        with page_text(path, index, password=self.password) as content:
            content.count_rects()
            self.mark_text_range(content, coordinates, start, count)
            self.set_copied_text(content.get_text_range(start, count))
        if self.text_marks:
            self.ensureVisible(self.text_marks[0], 32, 32)

    def finish_text(self, point):
        try:
            self.extend_text(point)
            if self.text_end is not None:
                start, stop = sorted((self.text_anchor, self.text_end))
                self.set_copied_text(self.text_page.get_text_range(start, stop - start + 1))
                if self.copied_text.strip():
                    self.selection_finished.emit(self.mapFromScene(point))
        except Exception as error:
            self.clear_text()
            self.text_error.emit(str(error))
        finally:
            self.text_handles.close()
            self.text_page = None

    def copy_text(self):
        if self.copied_text.strip():
            QApplication.clipboard().setText(self.copied_text)
            self.text_copied.emit()
            return True
        return False

    def keyPressEvent(self, event):
        if self.inline_editor is None and event.matches(QKeySequence.StandardKey.Copy):
            if not self.copy_text():
                self.text_error.emit(tr("Selecciona el texto arrastrando sobre la página y vuelve a pulsar Ctrl+C."))
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        if self.copied_text.strip():
            menu = QMenu(self)
            menu.addAction(tr("Copiar texto"), self.copy_text)
            menu.exec(event.globalPos())
        else:
            super().contextMenuEvent(event)

    def set_mode(self, mode):
        self.clear_text()
        self.mode = mode
        if self.rubber is not None:
            self.scene().removeItem(self.rubber)
            self.rubber = None
        self.start = None
        self.form_press = None
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag if mode == "pan" else QGraphicsView.DragMode.NoDrag)
        self.update_mode_cursor()

    def update_mode_cursor(self):
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.space_pan or self.mode == "pan" else
                       Qt.CursorShape.CrossCursor if self.mode else
                       Qt.CursorShape.IBeamCursor if self.text_source else Qt.CursorShape.ArrowCursor)

    def start_space_pan(self):
        if self.page_rect.isEmpty() or any(value is not None for value in
                                           (self.inline_editor, self.start, self.text_page, self.form_press)):
            return False
        self.space_pan = True
        self.update_mode_cursor()
        return True

    def stop_space_pan(self):
        if self.space_pan:
            self.space_pan = False
            self.pan_anchor = None
            self.update_mode_cursor()

    def edit_inline(self, field, coordinates, on_save):
        self.finish_inline()
        x1, y1, x2, y2 = field.box
        rect = QRectF(QPointF(*coordinates.device(x1, y1)),
                      QPointF(*coordinates.device(x2, y2))).normalized()
        multiline = field.kind == "/Tx" and bool(field.flags & (1 << 12))
        if multiline:
            editor = QPlainTextEdit(str(field.value))
            value = editor.toPlainText
        elif field.kind == "/Tx":
            editor = QLineEdit(str(field.value))
            value = editor.text
        else:
            editor = QComboBox()
            editor.setEditable(bool(field.flags & (1 << 18)))
            for label, export in field.options:
                editor.addItem(label, export)
            selected = editor.findData(str(field.value))
            editor.setCurrentIndex(selected)
            if selected < 0 and editor.isEditable():
                editor.setEditText(str(field.value))

            def value():
                if editor.isEditable() and editor.currentText() != editor.itemText(editor.currentIndex()):
                    return editor.currentText()
                return editor.currentData()

        self.mount_editor(editor, rect, field.name, str(field.value), value, on_save, multiline=multiline)

    def edit_existing_text(self, block, coordinates, on_save):
        self.finish_inline()
        left, bottom, right, top = block.box
        rect = QRectF(QPointF(*coordinates.device(left, bottom)),
                      QPointF(*coordinates.device(right, top))).normalized()
        rect = rect.adjusted(-3, -5, 5, 5)
        rect.setWidth(max(rect.width(), 160))
        editor = QLineEdit(block.value)
        self.mount_editor(editor, rect, tr("Texto existente"), block.value, editor.text, on_save)
        editor.selectAll()

    def mount_editor(self, editor, rect, label, initial, value, on_save, *, multiline=False):
        font_size = max(12, min(30, round(rect.height() * (0.20 if multiline else 0.63))))
        editor.setStyleSheet(f"background:#fff; color:#162737; border:1px solid #2874cc; padding:0 3px; font-size:{font_size}px;")
        editor.setAccessibleName(label)
        proxy = self.scene().addWidget(editor)
        proxy.setGeometry(rect.adjusted(0, 0, max(0, 32 - rect.width()), max(0, 17 - rect.height())))
        proxy.setZValue(10)
        self.inline_editor = (proxy, editor, value, initial, on_save)
        editor.installEventFilter(self)
        if isinstance(editor, QLineEdit):
            editor.editingFinished.connect(self.finish_inline)
        elif isinstance(editor, QComboBox):
            editor.activated.connect(lambda _: self.finish_inline())
            if editor.isEditable():
                editor.lineEdit().installEventFilter(self)
                editor.lineEdit().returnPressed.connect(self.finish_inline)
        self.ensureVisible(proxy, 16, 16)
        editor.setFocus()
        if isinstance(editor, QComboBox):
            editor.showPopup()

    def finish_inline(self, *, commit=True):
        if self.inline_editor is None:
            return
        proxy, editor, get_value, initial, on_save = self.inline_editor
        self.inline_editor = None
        value = get_value()
        proxy.setWidget(None)
        self.scene().removeItem(proxy)
        editor.deleteLater()
        proxy.deleteLater()
        if commit and value is not None and value != initial:
            on_save(value)

    def eventFilter(self, watched, event):
        editing = self.inline_editor
        if editing and (watched is editing[1] or watched.parent() is editing[1]):
            if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress):
                cancel = event.key() == Qt.Key.Key_Escape
                accept = (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                          and event.modifiers() & Qt.KeyboardModifier.ControlModifier)
                if event.type() == QEvent.Type.ShortcutOverride and (cancel or accept):
                    event.accept()
                    return True
                if cancel:
                    self.finish_inline(commit=False)
                    return True
                if accept:
                    self.finish_inline()
                    return True
            if event.type() == QEvent.Type.FocusOut and isinstance(editing[1], QPlainTextEdit):
                self.finish_inline()
        return super().eventFilter(watched, event)

    def show_fields(self, coordinates, fields, *, tint):
        for item in self.form_items:
            self.scene().removeItem(item)
        self.form_items.clear()
        self.form_rects.clear()
        for field in fields:
            x1, y1, x2, y2 = field.box
            rect = QRectF(QPointF(*coordinates.device(x1, y1)),
                          QPointF(*coordinates.device(x2, y2))).normalized()
            self.form_rects.append(rect)
            if tint:
                pen = QPen(QColor(36, 89, 173, 135), 1)
                pen.setCosmetic(True)
                self.form_items.append(self.scene().addRect(rect, pen, QColor(112, 164, 247, 59)))

    def mark_boxes(self, coordinates=None, occupied=(), chosen=None):
        for item in self.guides:
            self.scene().removeItem(item)
        self.guides.clear()
        boxes = [(box, "#ac591d", QColor(183, 106, 39, 30)) for box in occupied]
        if chosen:
            boxes.append((chosen, "#146c5d", QColor(34, 135, 115, 42)))
        for (x1, y1, x2, y2), color, fill in boxes:
            corner1 = QPointF(*coordinates.device(x1, y1))
            corner2 = QPointF(*coordinates.device(x2, y2))
            pen = QPen(QColor(color), 2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self.guides.append(self.scene().addRect(QRectF(corner1, corner2).normalized(), pen, fill))

    def page_point(self, event):
        point = self.mapToScene(event.position().toPoint())
        return QPointF(
            min(self.page_rect.right(), max(self.page_rect.left(), point.x())),
            min(self.page_rect.bottom(), max(self.page_rect.top(), point.y())),
        )

    def mousePressEvent(self, event):
        if self.space_pan and event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.pan_anchor = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self.mode == "pan":
            super().mousePressEvent(event)
            return
        if self.inline_editor:
            proxy = self.inline_editor[0]
            if proxy.sceneBoundingRect().contains(self.mapToScene(event.position().toPoint())):
                super().mousePressEvent(event)
                return
            self.finish_inline()
        if not self.mode and self.text_source and event.button() == Qt.MouseButton.LeftButton:
            if self.page_rect.contains(self.mapToScene(event.position().toPoint())):
                point = self.page_point(event)
                signature = next((name for rect, name in self.signature_targets if rect.contains(point)), None)
                if signature is not None or any(rect.contains(point) for rect in self.form_rects):
                    self.clear_text()
                    self.form_press = (point, event.position(), signature)
                else:
                    self.setFocus(Qt.FocusReason.MouseFocusReason)
                    self.begin_text(point)
            else:
                self.clear_text()
            event.accept()
            return
        if self.mode and event.button() == Qt.MouseButton.LeftButton and self.page_rect.contains(self.mapToScene(event.position().toPoint())):
            self.start = self.page_point(event)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.space_pan:
            if self.pan_anchor is not None:
                position = event.position().toPoint()
                delta = self.pan_anchor - position
                self.pan_anchor = position
                horizontal, vertical = self.horizontalScrollBar(), self.verticalScrollBar()
                horizontal.setValue(horizontal.value() + delta.x())
                vertical.setValue(vertical.value() + delta.y())
            event.accept()
            return
        if self.form_press is not None:
            point, device_point, _ = self.form_press
            if (event.position() - device_point).manhattanLength() < QApplication.startDragDistance():
                return
            self.form_press = None
            self.begin_text(point)
        if self.text_page is not None:
            try:
                self.extend_text(self.page_point(event))
            except Exception as error:
                self.clear_text()
                self.text_error.emit(str(error))
            return
        if (self.mode or "").startswith("shape-") and self.start is not None:
            point = self.page_point(event)
            rect = QRectF(self.start, point).normalized()
            if self.rubber is None:
                pen = QPen(self.shape_preview_color, self.shape_preview_width)
                if self.shape_preview_dashed:
                    pen.setStyle(Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                fill = QColor(self.shape_preview_color)
                fill.setAlpha(round(fill.alpha() * 0.24) if self.shape_preview_filled else 0)
                if self.mode == "shape-ellipse":
                    self.rubber = self.scene().addEllipse(rect, pen, fill)
                elif self.mode in ("shape-line", "shape-arrow"):
                    self.rubber = self.scene().addLine(self.start.x(), self.start.y(), point.x(), point.y(), pen)
                else:
                    self.rubber = self.scene().addRect(rect, pen, fill)
            elif self.mode in ("shape-line", "shape-arrow"):
                self.rubber.setLine(self.start.x(), self.start.y(), point.x(), point.y())
            else:
                self.rubber.setRect(rect)
            return
        if self.mode in ("signature", "redact") and self.start is not None:
            rect = QRectF(self.start, self.page_point(event)).normalized()
            if self.rubber is None:
                pen = QPen(QColor("#146c5d"), 2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self.rubber = self.scene().addRect(rect, pen, QColor(34, 135, 115, 42))
            else:
                self.rubber.setRect(rect)
            return
        if not self.mode and self.text_source:
            point = self.mapToScene(event.position().toPoint())
            if (any(rect.contains(point) for rect, _ in self.signature_targets) or
                    any(rect.contains(point) for rect in self.form_rects)):
                cursor = Qt.CursorShape.PointingHandCursor
            elif self.page_rect.contains(point):
                cursor = Qt.CursorShape.IBeamCursor
            else:
                cursor = Qt.CursorShape.ArrowCursor
            self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.space_pan and event.button() == Qt.MouseButton.LeftButton:
            self.pan_anchor = None
            self.update_mode_cursor()
            event.accept()
            return
        if self.inline_editor and self.inline_editor[0].sceneBoundingRect().contains(
            self.mapToScene(event.position().toPoint())
        ):
            super().mouseReleaseEvent(event)
            return
        if self.form_press is not None and event.button() == Qt.MouseButton.LeftButton:
            point, _, signature = self.form_press
            self.form_press = None
            event.accept()
            if signature is None:
                self.form_clicked.emit(point)
            else:
                self.signature_clicked.emit(signature)
            return
        if self.text_page is not None and event.button() == Qt.MouseButton.LeftButton:
            self.finish_text(self.page_point(event))
            event.accept()
            return
        if self.mode and self.start is not None and event.button() == Qt.MouseButton.LeftButton:
            point = self.page_point(event)
            rect = QRectF(self.start, point).normalized()
            if self.mode in ("signature", "redact"):
                self.start = None
                self.selected.emit(rect)
            elif self.mode.startswith("shape-"):
                start, self.start = self.start, None
                self.shape_drawn.emit(start, point)
            else:
                self.start = None
                self.point_selected.emit(point)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class ContinuousPageView(PageView):
    active_page_changed = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.source = None
        self.frames = []
        self.tops = []
        self.bottoms = []
        self.rendered = {}
        self.tiles = {}
        self.search_ranges = {}
        self.search_items = {}
        self.active_index = None
        self.positioning = False
        for scrollbar in (self.verticalScrollBar(), self.horizontalScrollBar()):
            scrollbar.valueChanged.connect(self.schedule_pages)
        self.scroll_render = QTimer(self)
        self.scroll_render.setSingleShot(True)
        self.scroll_render.setInterval(35)
        self.scroll_render.timeout.connect(self.render_visible)

    def schedule_pages(self):
        if self.source and not self.positioning:
            self.scroll_render.start()

    def reset_document(self):
        self.set_search_ranges({})
        self.stop_space_pan()
        self.source = None
        self.password = None
        self.scroll_render.stop()
        self.zoom_render.stop()
        self.set_mode(None)
        self.frames.clear()
        self.tops.clear()
        self.bottoms.clear()
        self.rendered.clear()
        self.tiles.clear()
        self.active_index = None
        self.page()

    def set_document(self, path, sizes, index, *, keep_position=False, initial_fit=None, password=None):
        self.set_search_ranges({})
        self.stop_space_pan()
        location = None
        if keep_position and not self.page_rect.isEmpty():
            center = self.mapToScene(self.viewport().rect().center())
            location = ((center.x() - self.page_rect.left()) / self.page_rect.width(),
                        (center.y() - self.page_rect.top()) / self.page_rect.height())
        percent = self.percent()
        if initial_fit is not None:
            self.fit = initial_fit
        self.positioning = True
        try:
            self.finish_inline(commit=False)
            self.clear_text()
            self.set_mode(None)
            self.zoom_render.stop()
            self.scroll_render.stop()
            self.guides.clear()
            self.measure_marks.clear()
            self.form_items.clear()
            self.form_rects.clear()
            self.scene().clear()
            self.rendered.clear()
            self.tiles.clear()
            self.source = path
            self.password = password
            self.frames = []
            width = max(w for w, _ in sizes) * 96 / 72
            top = 18.0
            for page_width, page_height in sizes:
                w, h = page_width * 96 / 72, page_height * 96 / 72
                self.frames.append(QRectF((width-w)/2, top, w, h))
                top += h + 20
            self.tops = [rect.top() for rect in self.frames]
            self.bottoms = [rect.bottom() for rect in self.frames]
            self.scene().setSceneRect(QRectF(-22, 0, width+44, top))
            self.active_index = None
            self.activate(index)
            if self.fit:
                self.apply_fit()
            else:
                self.set_percent(percent)
            if location:
                frame = self.frames[index]
                self.centerOn(frame.left()+location[0]*frame.width(), frame.top()+location[1]*frame.height())
            else:
                self.center_page(index)
        finally:
            self.positioning = False
        self.schedule_pages()

    def actual_scale(self):
        return 1

    def zoom(self, factor, *, at_mouse=False):
        super().zoom(factor, at_mouse=at_mouse)
        self.schedule_pages()

    def apply_fit(self):
        if self.page_rect.isEmpty():
            return
        if not self.fit:
            self.zoom_changed.emit(self.percent())
            return
        already_positioning = self.positioning
        self.positioning = True
        try:
            width = self.viewport().width() - 30
            height = self.viewport().height() - 28
            scale = width / (self.page_rect.width() + 18)
            if self.fit != "width":
                scale = min(scale, height / (self.page_rect.height() + 16))
            self.set_zoom(max(0.02, scale))
            self.center_page(self.active_index)
        finally:
            self.positioning = already_positioning
        self.schedule_pages()

    def center_page(self, index):
        rect = self.frames[index]
        visible = self.viewport().height() / self.transform().m11()
        self.centerOn(rect.center().x(), min(rect.center().y(), rect.top() - 9 + visible/2))

    def jump(self, index):
        self.positioning = True
        try:
            self.activate(index)
            if self.fit:
                self.apply_fit()
            else:
                self.center_page(index)
        finally:
            self.positioning = False
        self.schedule_pages()

    def render_items(self, indices, *, visible=None):
        desired = {}
        for index in indices:
            rect = self.frames[index]
            value = round(max(128, rect.width() * self.transform().m11() * self.devicePixelRatioF()))
            offscreen = visible is not None and index not in visible
            if offscreen:
                value = min(value, 480)
            limit = int(6000 * min(1, rect.width()/rect.height()))
            size = max(1, limit // 3) if value > limit else value
            previous = self.rendered.get(index)
            # Match the visible physical pixel width. PDFium can round by one pixel.
            tolerance = max(2, round(size * 0.15)) if offscreen else 2
            if previous is None or abs(size - previous[2]) > tolerance:
                desired[index] = size
        if not desired:
            return
        with pdfium_reader(self.source, password=self.password) as document:
            for index, size in desired.items():
                rect = self.frames[index]
                image, mapping = render_page(document, index, width=size, with_coordinates=True)
                sx, sy = rect.width()/image.width, rect.height()/image.height
                r = tuple(axis/sx for axis in mapping.right)
                d = tuple(axis/sy for axis in mapping.down)
                origin = tuple(value - rect.left()*rx - rect.top()*dy for value, rx, dy in zip(mapping.origin, r, d))
                coords = Coordinates(origin, r, d)
                if index in self.rendered:
                    item = self.rendered[index][0]
                    item.setPixmap(QPixmap.fromImage(as_qimage(image)))
                else:
                    item = self.scene().addPixmap(QPixmap.fromImage(as_qimage(image)))
                    item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
                    item.setZValue(-2)
                    item.setPos(rect.topLeft())
                item.setTransform(QTransform.fromScale(sx, sy))
                self.update_raster_interpolation(item)
                self.rendered[index] = (item, coords, image.width)

    def update_zoom_interpolation(self):
        for item, _, _ in self.rendered.values():
            self.update_raster_interpolation(item)

    def render_visible_tiles(self, visible, shown):
        scale = self.transform().m11() * self.devicePixelRatioF()
        tile_size = 768
        required = {}
        for index in shown:
            frame = self.frames[index]
            width, height = ceil(frame.width() * scale), ceil(frame.height() * scale)
            if max(width, height) <= 6000:
                continue
            region = visible.intersected(frame)
            if region.isEmpty():
                continue
            x1 = max(0, floor((region.left() - frame.left()) * scale))
            y1 = max(0, floor((region.top() - frame.top()) * scale))
            x2 = min(width, ceil((region.right() - frame.left()) * scale))
            y2 = min(height, ceil((region.bottom() - frame.top()) * scale))
            for top in range(y1 // tile_size * tile_size, y2, tile_size):
                for left in range(x1 // tile_size * tile_size, x2, tile_size):
                    rect = (left, top, min(width, left + tile_size), min(height, top + tile_size))
                    required[(index, scale, left, top)] = rect
        for key in self.tiles.keys() - required.keys():
            self.scene().removeItem(self.tiles.pop(key))
        pending = required.keys() - self.tiles.keys()
        if not pending:
            return
        with pdfium_reader(self.source, password=self.password) as document:
            for key in sorted(pending):
                index, _, left, top = key
                image = render_page_tile(document, index, scale * 96 / 72, required[key])
                item = self.scene().addPixmap(QPixmap.fromImage(as_qimage(image)))
                frame = self.frames[index]
                item.setPos(frame.left() + left / scale, frame.top() + top / scale)
                item.setScale(1 / scale)
                item.setZValue(-1.5)
                self.tiles[key] = item

    def activate(self, index):
        if index == self.active_index:
            return
        self.render_items((index,))
        self.clear_text()
        self.active_index = index
        self.page_rect = self.frames[index]
        self.image_item, coords, self.rendered_width = self.rendered[index]
        self.text_source = self.source, index, coords
        self.active_page_changed.emit(index, coords)

    def render_visible(self):
        if not self.source or self.positioning or not self.isEnabled():
            return
        visible = self.mapToScene(self.viewport().rect()).boundingRect()
        first = bisect_right(self.bottoms, visible.top())
        last = bisect_left(self.tops, visible.bottom())
        index = min(len(self.frames)-1, bisect_right(self.bottoms, visible.center().y()))
        shown = set(range(first, last)) | {index}
        keep = set(range(max(0, first - 1), min(len(self.frames), last + 1)))
        keep.add(index)
        if self.active_index is not None:
            keep.add(self.active_index)
        try:
            for stale in self.rendered.keys() - keep:
                self.scene().removeItem(self.rendered.pop(stale)[0])
            self.render_items(sorted(keep, key=lambda page: (page not in shown, abs(page - index))), visible=shown)
            self.render_visible_tiles(visible, shown)
            self.refresh_search_marks(shown)
            selection_visible = any(visible.intersects(mark.rect()) for mark in self.text_marks)
            if not (self.start is not None or self.text_page or self.form_press or self.inline_editor or selection_visible):
                self.activate(index)
        except Exception as error:
            self.text_error.emit(str(error))

    def refresh_resolution(self):
        self.render_visible()

    def set_search_ranges(self, ranges):
        for items in self.search_items.values():
            for item in items:
                self.scene().removeItem(item)
        self.search_items.clear()
        self.search_ranges = ranges
        if ranges:
            self.schedule_pages()

    def refresh_search_marks(self, visible):
        for page in self.search_items.keys() - visible:
            for item in self.search_items.pop(page):
                self.scene().removeItem(item)
        pending = visible & self.search_ranges.keys() - self.search_items.keys()
        if not pending:
            return
        with pdfium_reader(self.source, password=self.password) as document:
            for page in sorted(pending):
                coordinates = self.rendered[page][1]
                strokes = QPainterPath()
                strokes.setFillRule(Qt.FillRule.WindingFill)
                with document_text(document, page) as content:
                    for start, count in self.search_ranges[page]:
                        for rect in self.text_range_rects(content, coordinates, start, count):
                            strokes.addRect(rect)
                item = self.scene().addPath(strokes, QPen(Qt.PenStyle.NoPen), QColor(244, 171, 35, 125))
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                item.setZValue(-1)
                self.search_items[page] = [item]

    def mousePressEvent(self, event):
        if self.source and event.button() == Qt.MouseButton.LeftButton and not self.space_pan and self.mode != "pan":
            point = self.mapToScene(event.position().toPoint())
            in_editor = self.inline_editor and self.inline_editor[0].sceneBoundingRect().contains(point)
            if not in_editor:
                self.finish_inline()
                point = self.mapToScene(event.position().toPoint())
                index = bisect_right(self.bottoms, point.y())
                if index < len(self.frames) and self.frames[index].contains(point):
                    try:
                        self.activate(index)
                    except Exception as error:
                        self.text_error.emit(str(error))
                        return
        super().mousePressEvent(event)


class BookmarkRows(QStyledItemDelegate):
    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        tree = self.parent()
        level, parent = 1, index.parent()
        while parent.isValid():
            level += 1
            parent = parent.parent()
        width = max(40, tree.viewport().width() - level * tree.indentation() - 12)
        text = str(index.data() or "")
        bounds = option.fontMetrics.boundingRect(0, 0, width, 10000, Qt.TextFlag.TextWordWrap, text)
        size.setHeight(max(size.height() + 5, bounds.height() + 5))
        return size


class Job(QThread):
    progress = Signal(int, int)

    def __init__(self, function, callback, parent, *, cancellable=False):
        super().__init__(parent)
        self.function = function
        self.callback = callback
        self.result = self.failure = None
        self.cancellable = cancellable
        self.cancelled = False

    def run(self):
        try:
            self.result = self.function(self.report_progress)
        except OperationCancelled:
            self.cancelled = True
        except Exception as error:
            self.failure = str(error) or type(error).__name__
        finally:
            self.function = None

    def report_progress(self, done, total):
        if self.cancellable:
            check_cancellation()
        self.progress.emit(done, total)


def check_cancellation(*_):
    if QThread.currentThread().isInterruptionRequested():
        raise OperationCancelled()


class PageList(QListWidget):
    page_mime = "application/x-pdfiu-pages"

    def __init__(self, window):
        super().__init__(objectName="pageList")
        self.window = window
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(False)
        self.setAutoScroll(False)
        self.setToolTip(tr("Ctrl o Mayús para seleccionar varias páginas. Arrastra páginas o suelta un PDF entre miniaturas."))
        self.insert_line = QFrame(self.viewport(), objectName="pageInsertLine")
        self.insert_line.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.insert_line.hide()
        self.drag_point = None
        self.insertion_index = None
        self.drag_scroll = QTimer(self, interval=45)
        self.drag_scroll.timeout.connect(self.scroll_during_drag)

    @staticmethod
    def pdf_paths(mime):
        urls = mime.urls()
        if urls and all(url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() == ".pdf" for url in urls):
            return [Path(url.toLocalFile()) for url in urls]
        return []

    def startDrag(self, _actions):
        self.window.view.finish_inline()
        path = self.window.path
        indices = sorted(item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems())
        if path is None or not indices or self.window.job is not None:
            return
        mime = QMimeData()
        mime.setData(self.page_mime, json.dumps([str(path), indices]).encode())
        drag = QDrag(self)
        drag.setMimeData(mime)
        thumbnail = self.item(indices[0]).icon()
        if not thumbnail.isNull():
            drag.setPixmap(thumbnail.pixmap(self.iconSize()))
        drag.exec(Qt.DropAction.CopyAction)
        drag.deleteLater()

    def drop_sources(self, mime):
        if not mime.hasFormat(self.page_mime):
            return [(path, None) for path in self.pdf_paths(mime)]
        data = bytes(mime.data(self.page_mime))
        if len(data) > 1024 * 1024:
            return []
        try:
            source, selection = json.loads(data)
            path = Path(source)
            if path.is_absolute() and path.suffix.lower() == ".pdf" and isinstance(selection, list) and selection and all(
                type(index) is int and index >= 0 for index in selection
            ):
                return [(path, selection)]
        except (ValueError, TypeError, RecursionError):
            pass
        return []

    def insertion_at(self, point):
        row = self.indexAt(QPoint(4, point.y())).row()
        if row == -1:
            return 0 if point.y() < 0 else self.count()
        rect = self.visualItemRect(self.item(row))
        return row + int(point.y() > rect.center().y())

    def show_insertion(self, point):
        position = self.insertion_at(point)
        if position != self.insertion_index:
            self.insertion_index = position
            if position == self.count():
                self.window.note(tr("Insertar al final · después de la página {0}").format(position))
            else:
                self.window.note(tr("Insertar antes de la página {0}").format(position + 1))
        if position == self.count():
            y = self.visualItemRect(self.item(position - 1)).bottom() + 1
        else:
            y = self.visualItemRect(self.item(position)).top()
        y = max(0, min(y - 1, self.viewport().height() - 3))
        self.insert_line.setGeometry(3, y, self.viewport().width() - 6, 3)
        self.insert_line.show()
        self.insert_line.raise_()

    def scroll_during_drag(self):
        if self.drag_point is None:
            return
        y = self.drag_point.y()
        scroll = self.verticalScrollBar()
        if y < 26:
            scroll.setValue(scroll.value() - 16)
        elif y >= self.viewport().height() - 26:
            scroll.setValue(scroll.value() + 16)
        self.show_insertion(self.drag_point)

    def clear_insertion(self):
        self.drag_point = None
        self.insertion_index = None
        self.drag_scroll.stop()
        self.insert_line.hide()

    def dragEnterEvent(self, event):
        if (self.count() and self.window.job is None and event.possibleActions() & Qt.DropAction.CopyAction
                and self.drop_sources(event.mimeData())):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self.count() or self.window.job is not None:
            self.clear_insertion()
            event.ignore()
            return
        self.drag_point = event.position().toPoint()
        self.show_insertion(self.drag_point)
        if not self.drag_scroll.isActive():
            self.drag_scroll.start()
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.clear_insertion()
        event.accept()

    def dropEvent(self, event):
        self.clear_insertion()
        sources = self.drop_sources(event.mimeData())
        if (not sources or not self.count() or self.window.job is not None
                or not event.possibleActions() & Qt.DropAction.CopyAction):
            event.ignore()
            return
        position = self.insertion_at(event.position().toPoint())
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if event.source() is self and sources[0][1] is not None:
            self.window.reorder_pages(sources[0][1], position)
        else:
            self.window.insert_documents(position, sources)


class WorkspaceList(QListWidget):
    open_requested = Signal(QListWidgetItem)

    def checkbox_rect(self, item):
        option = QStyleOptionViewItem()
        self.initViewItemOption(option)
        option.rect = self.visualItemRect(item)
        option.features |= QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
        return self.style().subElementRect(QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, self)

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        item = self.itemAt(point)
        if (item is None or event.button() != Qt.MouseButton.LeftButton or
                event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
            super().mouseReleaseEvent(event)
            return
        indicator = self.checkbox_rect(item)
        super().mouseReleaseEvent(event)
        if not indicator.contains(point):
            self.open_requested.emit(item)


class DocumentTabBar(QTabBar):
    """Tab bar that supports tearing off a tab into a new window by dragging it outside."""

    tab_detached = Signal(int, QPoint)

    def __init__(self, parent=None, *, objectName=None):
        super().__init__(parent)
        if objectName:
            self.setObjectName(objectName)
        self._drag_index = -1
        self._drag_origin = QPoint()
        self._detaching = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            self._drag_index = self.tabAt(pos)
            self._drag_origin = pos
            self._detaching = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_index >= 0 and (event.buttons() & Qt.MouseButton.LeftButton):
            pos = event.position().toPoint()
            outside_y = pos.y() < -32 or pos.y() > self.height() + 32
            outside_x = pos.x() < -48 or pos.x() > self.width() + 48
            if outside_y or outside_x:
                if not self._detaching:
                    self._detaching = True
                    self.setCursor(Qt.CursorShape.DragMoveCursor)
                return
            if self._detaching:
                self._detaching = False
                self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self._drag_index
        detaching = self._detaching
        self._drag_index = -1
        self._detaching = False
        if detaching:
            self.unsetCursor()
            super().mouseReleaseEvent(event)
            if index >= 0 and index < self.count():
                self.tab_detached.emit(index, event.globalPosition().toPoint())
            return
        super().mouseReleaseEvent(event)
