"""Windows printer property sheets and jobs with per-job driver settings."""

from contextlib import contextmanager
from ctypes import POINTER, Structure, WinDLL, byref, cast, create_string_buffer, sizeof
from ctypes import wintypes as wt
from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from pdf_ops import pdfium_reader
from pdf_print import paint_print_sheet
from translations import tr


DM_OUT_BUFFER, DM_IN_PROMPT, DM_IN_BUFFER = 2, 4, 8
DM_ORIENTATION, DM_PAPERSIZE, DM_PAPERLENGTH, DM_PAPERWIDTH = 1, 2, 4, 8
DM_COPIES, DM_COLOR, DM_DUPLEX, DM_COLLATE = 0x100, 0x800, 0x1000, 0x8000
IDOK, IDCANCEL = 1, 2
DIB_RGB_COLORS, SRCCOPY = 0, 0x00CC0020
HALFTONE = 4


class DevModeHeader(Structure):
    # Only the public printer fields we use. The rest lives in the original buffer.
    _fields_ = [
        ("device_name", wt.WCHAR * 32), ("spec_version", wt.WORD), ("driver_version", wt.WORD),
        ("size", wt.WORD), ("driver_extra", wt.WORD), ("fields", wt.DWORD),
        ("orientation", wt.SHORT), ("paper_size", wt.SHORT), ("paper_length", wt.SHORT),
        ("paper_width", wt.SHORT), ("scale", wt.SHORT), ("copies", wt.SHORT),
        ("source", wt.SHORT), ("quality", wt.SHORT), ("color", wt.SHORT), ("duplex", wt.SHORT),
        ("y_resolution", wt.SHORT), ("tt_option", wt.SHORT), ("collate", wt.SHORT),
    ]


class DocInfo(Structure):
    _fields_ = [("size", wt.INT), ("name", wt.LPCWSTR), ("output", wt.LPCWSTR),
                ("datatype", wt.LPCWSTR), ("type", wt.DWORD)]


class BitmapInfo(Structure):
    _fields_ = [("size", wt.DWORD), ("width", wt.LONG), ("height", wt.LONG),
                ("planes", wt.WORD), ("bits", wt.WORD), ("compression", wt.DWORD),
                ("image_size", wt.DWORD), ("x_resolution", wt.LONG), ("y_resolution", wt.LONG),
                ("colors_used", wt.DWORD), ("colors_important", wt.DWORD)]


def api(library, name, result, *arguments):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = arguments
    return function


spooler = WinDLL("winspool.drv", use_last_error=True)
gdi = WinDLL("gdi32.dll", use_last_error=True)
open_printer = api(spooler, "OpenPrinterW", wt.BOOL, wt.LPWSTR, POINTER(wt.HANDLE), wt.LPVOID)
close_printer = api(spooler, "ClosePrinter", wt.BOOL, wt.HANDLE)
document_properties = api(spooler, "DocumentPropertiesW", wt.LONG, wt.HWND, wt.HANDLE,
                          wt.LPWSTR, wt.LPVOID, wt.LPVOID, wt.DWORD)
create_dc = api(gdi, "CreateDCW", wt.HDC, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.LPVOID)
delete_dc = api(gdi, "DeleteDC", wt.BOOL, wt.HDC)
get_device_caps = api(gdi, "GetDeviceCaps", wt.INT, wt.HDC, wt.INT)
start_doc = api(gdi, "StartDocW", wt.INT, wt.HDC, POINTER(DocInfo))
start_page = api(gdi, "StartPage", wt.INT, wt.HDC)
end_page = api(gdi, "EndPage", wt.INT, wt.HDC)
end_doc = api(gdi, "EndDoc", wt.INT, wt.HDC)
abort_doc = api(gdi, "AbortDoc", wt.INT, wt.HDC)
set_stretch_mode = api(gdi, "SetStretchBltMode", wt.INT, wt.HDC, wt.INT)
set_brush_origin = api(gdi, "SetBrushOrgEx", wt.BOOL, wt.HDC, wt.INT, wt.INT, wt.LPVOID)
stretch_dibits = api(gdi, "StretchDIBits", wt.INT, wt.HDC, *([wt.INT] * 8),
                    wt.LPVOID, POINTER(BitmapInfo), wt.UINT, wt.DWORD)


@contextmanager
def printer_handle(name):
    handle = wt.HANDLE()
    if not open_printer(name, byref(handle), None):
        raise ValueError(tr("Windows no pudo abrir la impresora seleccionada."))
    try:
        yield handle
    finally:
        close_printer(handle)


@dataclass(frozen=True)
class PageMetrics:
    dpi_x: int
    dpi_y: int
    width: int
    height: int
    offset_x: int
    offset_y: int
    paper_width: int
    paper_height: int

    @property
    def paper(self):
        return QRectF(0, 0, self.paper_width * 72 / self.dpi_x, self.paper_height * 72 / self.dpi_y)

    @property
    def area(self):
        return QRectF(self.offset_x * 72 / self.dpi_x, self.offset_y * 72 / self.dpi_y,
                      self.width * 72 / self.dpi_x, self.height * 72 / self.dpi_y)


class DriverSettings:
    def __init__(self, name, settings):
        self.name, self.settings = name, settings
        self.header = cast(settings, POINTER(DevModeHeader)).contents
        if self.header.size < DevModeHeader.collate.offset + sizeof(wt.SHORT):
            raise ValueError(tr("El controlador devolvió una configuración de impresión inválida."))

    @classmethod
    def choose(cls, owner, name, *, orientation, paper, color, duplex, copies, collate, previous=None):
        with printer_handle(name) as handle:
            size = document_properties(None, handle, name, None, None, 0)
            if size < sizeof(DevModeHeader):
                raise ValueError(tr("No se pudieron leer las propiedades de la impresora."))
            seed, output = create_string_buffer(size), create_string_buffer(size)
            if previous is not None and previous.name == name and sizeof(previous.settings) == size:
                seed = previous.settings
            else:
                if document_properties(None, handle, name, seed, None, DM_OUT_BUFFER) != IDOK:
                    raise ValueError(tr("No se pudieron leer las propiedades de la impresora."))
                header = cls(name, seed).header
                header.orientation, header.color, header.duplex = orientation, color, duplex
                header.copies, header.collate = copies, int(collate)
                header.fields |= DM_ORIENTATION | DM_COLOR | DM_DUPLEX | DM_COPIES | DM_COLLATE
                paper_id, width, height = paper
                if paper_id:
                    header.paper_size = paper_id
                    header.fields = (header.fields | DM_PAPERSIZE) & ~(DM_PAPERLENGTH | DM_PAPERWIDTH)
                else:
                    if not (0 < width <= 32767 and 0 < height <= 32767):
                        raise ValueError(tr("El papel personalizado supera lo que admite el controlador de Windows."))
                    header.paper_size = 0
                    header.paper_width, header.paper_length = width, height
                    header.fields = (header.fields | DM_PAPERLENGTH | DM_PAPERWIDTH) & ~DM_PAPERSIZE
            answer = document_properties(owner, handle, name, output, seed,
                                         DM_IN_BUFFER | DM_IN_PROMPT | DM_OUT_BUFFER)
        if answer == IDCANCEL:
            return None
        if answer != IDOK:
            raise ValueError(tr("No se pudieron abrir las propiedades del controlador."))
        return cls(name, output)

    @property
    def grayscale(self):
        return bool(self.header.fields & DM_COLOR and self.header.color == 1)

    @property
    def copies(self):
        return max(1, self.header.copies) if self.header.fields & DM_COPIES else 1

    @property
    def duplex(self):
        return self.header.duplex if self.header.fields & DM_DUPLEX else 1

    @contextmanager
    def context(self):
        dc = create_dc("WINSPOOL", self.name, None, self.settings)
        if not dc:
            raise ValueError(tr("Windows no pudo preparar la impresora con esos ajustes."))
        try:
            # LOGPIXELSX, LOGPIXELSY, HORZRES, VERTRES, PHYSICALOFFSETX/Y, PHYSICALWIDTH/HEIGHT.
            metrics = PageMetrics(*(get_device_caps(dc, index) for index in (88, 90, 8, 10, 112, 113, 110, 111)))
            if min(metrics.dpi_x, metrics.dpi_y, metrics.width, metrics.height,
                   metrics.paper_width, metrics.paper_height) <= 0:
                raise ValueError(tr("El controlador no devolvió un área imprimible válida."))
            yield dc, metrics
        finally:
            delete_dc(dc)

    def metrics(self):
        with self.context() as (_, metrics):
            return metrics


def print_driver_job(settings, source, password, name, sizes, sheets, progress,
                     *, quality=300, annotations=True, output=None):
    with settings.context() as (dc, metrics), pdfium_reader(source, password=password) as document:
        if start_doc(dc, byref(DocInfo(sizeof(DocInfo), name, output, None, 0))) <= 0:
            raise ValueError(tr("No se pudo iniciar la impresión."))
        try:
            for position, sheet in enumerate(sheets):
                progress(position, len(sheets))
                if start_page(dc) <= 0:
                    raise ValueError(tr("La impresora no pudo preparar la siguiente página."))
                send_sheet(dc, metrics, document, sizes, sheet, quality, settings.grayscale, annotations,
                           lambda: progress(position, len(sheets)))
                if end_page(dc) <= 0:
                    raise ValueError(tr("No se pudo completar la impresión."))
            progress(len(sheets), len(sheets))
            if end_doc(dc) <= 0:
                raise ValueError(tr("No se pudo completar la impresión."))
        except BaseException:
            abort_doc(dc)
            raise


def send_sheet(dc, metrics, document, sizes, sheet, quality, grayscale, annotations, checkpoint):
    dpi = min(metrics.dpi_x, metrics.dpi_y, quality)
    ratio_x, ratio_y = dpi / metrics.dpi_x, dpi / metrics.dpi_y
    width, height = ceil(metrics.width * ratio_x), ceil(metrics.height * ratio_y)
    full_sheet = QRectF(0, 0, metrics.width * ratio_x, metrics.height * ratio_y)
    set_stretch_mode(dc, HALFTONE)
    set_brush_origin(dc, 0, 0, None)
    # Keep the memory bounded on large sheets and at 600 ppp.
    band_height = max(1, min(256, (8 * 1024 * 1024) // (4 * width)))
    for row in range(0, height, band_height):
        checkpoint()
        rows = min(band_height, height - row)
        image = QImage(width, rows, QImage.Format.Format_RGB32)
        if image.isNull():
            raise ValueError(tr("No hay memoria suficiente para preparar la impresión."))
        image.fill(QColor("white"))
        painter = QPainter(image)
        try:
            painter.translate(0, -row)
            paint_print_sheet(painter, document, sizes, sheet, full_sheet, dpi, dpi,
                              grayscale=grayscale, annotations=annotations,
                              visible=QRectF(0, row, width, rows))
        finally:
            painter.end()
        first = round(row / ratio_y)
        last = min(metrics.height, round((row + rows) / ratio_y))
        bitmap = BitmapInfo(sizeof(BitmapInfo), width, -rows, 1, 32, 0, 0, 0, 0, 0, 0)
        raw = bytes(image.constBits())
        written = stretch_dibits(dc, 0, first, metrics.width, last - first, 0, 0, width, rows,
                                 raw, byref(bitmap), DIB_RGB_COLORS, SRCCOPY)
        if written in (0, -1):
            raise ValueError(tr("El controlador no pudo recibir una parte de la página."))
