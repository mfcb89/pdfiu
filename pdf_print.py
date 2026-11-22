"""Plan and render PDF print jobs."""

from dataclasses import dataclass
from math import ceil, floor

from PySide6.QtCore import QRectF
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPrintSupport import QPrinter

from pdf_ops import page_range, pdfium_reader, reader_for, render_page_tile
from translations import tr


@dataclass(frozen=True)
class PrintSheet:
    placements: tuple
    clipped: bool = False


def requested_pages(count, current, scope, expression, parity, reverse):
    if scope == "current":
        pages = [current]
    elif scope == "range":
        if not expression.strip():
            raise ValueError(tr("Escribe las páginas que quieres imprimir."))
        pages = page_range(expression, count)
    else:
        pages = list(range(count))
    if parity != "all":
        pages = [page for page in pages if (page + 1) % 2 == (parity == "odd")]
    if not pages:
        raise ValueError(tr("El intervalo de impresión no contiene páginas."))
    if reverse:
        pages.reverse()
    return pages


def sheet_layout(width, height, paper_width, paper_height, mode, *, percent=100, overlap_mm=8):
    if min(width, height, paper_width, paper_height) <= 0:
        raise ValueError(tr("Elige una impresora y un tamaño de papel válidos."))
    scale = percent / 100 if mode in ("custom", "poster") else 1.0
    if mode == "poster":
        overlap = overlap_mm * 72 / 25.4
        if overlap >= min(paper_width, paper_height):
            raise ValueError(tr("El solape debe ser menor que el área imprimible."))
        step_x, step_y = paper_width - overlap, paper_height - overlap
        columns = 1 + max(0, ceil((width * scale - paper_width) / step_x))
        rows = 1 + max(0, ceil((height * scale - paper_height) / step_y))
        if rows * columns > 2000:
            raise ValueError(tr("La página necesita demasiadas hojas. Usa un tamaño de papel mayor."))
        return [(-column * step_x, -row * step_y, scale) for row in range(rows) for column in range(columns)]
    if mode in ("fit", "shrink"):
        scale = min(paper_width / width, paper_height / height)
        if mode == "shrink":
            scale = min(1.0, scale)
    return [((paper_width - width * scale) / 2, (paper_height - height * scale) / 2, scale)]


def booklet_groups(pages, side, binding):
    padded = list(pages) + [None] * (-len(pages) % 4)
    for first in range(0, len(padded) // 2, 2):
        last = len(padded) - first - 1
        pairs = ((padded[last], padded[first]), (padded[first + 1], padded[last - 1]))
        for which, pair in zip(("front", "back"), pairs):
            if side in ("both", which):
                yield pair if binding == "left" else pair[::-1]


def plan_sheets(pages, sizes, width, height, *, mode="shrink", percent=100, overlap_mm=8,
                grid=(2, 1), order="across", booklet_side="both", binding="left"):
    if mode not in ("multiple", "booklet"):
        area = QRectF(0, 0, width, height)
        result = []
        for index in pages:
            w, h, _ = sizes[index]
            for x, y, scale in sheet_layout(w, h, width, height, mode, percent=percent, overlap_mm=overlap_mm):
                clipped = mode != "poster" and (x < -.1 or y < -.1)
                result.append(PrintSheet(((index, (x, y, scale), area),), clipped))
        return result
    if mode == "booklet":
        columns, rows = 2, 1
        groups = booklet_groups(pages, booklet_side, binding)
        order = "across"
    else:
        columns, rows = grid
        capacity = columns * rows
        groups = (pages[start:start + capacity] for start in range(0, len(pages), capacity))
    cell_w, cell_h = width / columns, height / rows
    gap = min(4, cell_w / 10, cell_h / 10)
    result = []
    for group in groups:
        placements = []
        for position, index in enumerate(group):
            if index is None:
                continue
            if order.startswith("down"):
                column, row = divmod(position, rows)
            else:
                row, column = divmod(position, columns)
            if order.endswith("reverse"):
                column = columns - 1 - column
            cell = QRectF(column * cell_w + gap, row * cell_h + gap, cell_w - 2 * gap, cell_h - 2 * gap)
            w, h, _ = sizes[index]
            target = sheet_layout(w, h, cell.width(), cell.height(), "fit")[0]
            placements.append((index, target, cell))
        result.append(PrintSheet(tuple(placements)))
    return result


def paint_sheet(painter, document, index, unit, sheet, area, dpi, raster_dpi, *, grayscale=False, annotations=True,
                visible=None):
    width, height = document.get_page_size(index)
    left, top, factor = sheet
    device_scale = dpi / 72
    scale = factor * unit * device_scale
    raster_scale = factor * unit * raster_dpi / 72
    left = area.left() + left * device_scale
    top = area.top() + top * device_scale
    pixels_w, pixels_h = ceil(width * raster_scale), ceil(height * raster_scale)
    pixel_x, pixel_y = width * scale / pixels_w, height * scale / pixels_h
    clip = area if visible is None else area.intersected(visible)
    if clip.isEmpty():
        return
    start_x = max(0, floor((clip.left() - left) / pixel_x))
    start_y = max(0, floor((clip.top() - top) / pixel_y))
    end_x = min(pixels_w, ceil((clip.right() - left) / pixel_x))
    end_y = min(pixels_h, ceil((clip.bottom() - top) / pixel_y))
    painter.save()
    try:
        painter.setClipRect(clip)
        for y in range(start_y, end_y, 2048):
            for x in range(start_x, end_x, 2048):
                right, bottom = min(x + 2048, end_x), min(y + 2048, end_y)
                image = render_page_tile(document, index, raster_scale, (x, y, right, bottom), annotations=annotations)
                if grayscale:
                    image = image.convert("L").convert("RGB")
                buffer = image.tobytes()
                tile = QImage(buffer, image.width, image.height, image.width * 3, QImage.Format.Format_RGB888)
                target = QRectF(left + x * pixel_x, top + y * pixel_y, (right - x) * pixel_x, (bottom - y) * pixel_y)
                painter.drawImage(target, tile)
    finally:
        painter.restore()


def paint_print_sheet(painter, document, sizes, sheet, area, dpi, quality, *, grayscale=False, annotations=True,
                      visible=None):
    scale = dpi / 72
    for index, placement, cell in sheet.placements:
        box = QRectF(area.x() + cell.x() * scale, area.y() + cell.y() * scale,
                     cell.width() * scale, cell.height() * scale)
        paint_sheet(painter, document, index, sizes[index][2], placement, box, dpi, quality,
                    grayscale=grayscale, annotations=annotations, visible=visible)


def document_sizes(source, reader, password):
    with pdfium_reader(source, password=password) as document:
        sizes = []
        for index, page in enumerate(reader.pages):
            unit = float(page.get("/UserUnit", 1))
            w, h = document.get_page_size(index)
            sizes.append((w * unit, h * unit, unit))
        return sizes


def print_pages(source, password, printer, pages, progress, *, mode="shrink", sheets=None, sizes=None,
                quality=300, grayscale=False, annotations=True, copies=1, collate=True):
    if sizes is None:
        reader = reader_for(source, allow_empty_password=True, password=password)
        sizes = document_sizes(source, reader, password)
    if sheets is None:
        area = printer.pageRect(QPrinter.Unit.Point)
        sheets = plan_sheets(pages, sizes, area.width(), area.height(), mode=mode)
    if not sheets:
        raise ValueError(tr("El intervalo de impresión no contiene páginas."))
    hardware_copies = printer.supportsMultipleCopies()
    printer.setCopyCount(copies if hardware_copies else 1)
    printer.setCollateCopies(collate)
    if not hardware_copies and copies > 1:
        if printer.duplex() != QPrinter.DuplexMode.DuplexNone:
            faces = list(sheets) + [PrintSheet(())] * (len(sheets) % 2)
            if collate:
                sheets = faces * copies
            else:
                sheets = [face for index in range(0, len(faces), 2) for _ in range(copies)
                          for face in faces[index:index + 2]]
        else:
            sheets = sheets * copies if collate else [sheet for sheet in sheets for _ in range(copies)]
    with pdfium_reader(source, password=password) as document:
        painter = QPainter()
        if not painter.begin(printer):
            raise ValueError(tr("No se pudo iniciar la impresión."))
        try:
            size = printer.pageRect(QPrinter.Unit.DevicePixel).size()
            area = QRectF(0, 0, size.width(), size.height())
            dpi = printer.resolution()
            for position, sheet in enumerate(sheets):
                progress(position, len(sheets))
                if position and not printer.newPage():
                    raise ValueError(tr("La impresora no pudo preparar la siguiente página."))
                paint_print_sheet(painter, document, sizes, sheet, area, dpi, min(dpi, quality),
                                  grayscale=grayscale, annotations=annotations)
        except Exception:
            printer.abort()
            painter.end()
            raise
        if not painter.end() or printer.printerState() == QPrinter.PrinterState.Error:
            raise ValueError(tr("No se pudo completar la impresión."))
