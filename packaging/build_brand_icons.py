"""Export PDFiu's vector icons to the formats used by the desktop platforms."""

from pathlib import Path

from PIL import Image
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


BRAND = Path(__file__).resolve().parents[1] / "assets" / "brand"
WINDOWS_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def rasterize(source):
    renderer = QSvgRenderer(str(source))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {source}")
    image = QImage(1024, 1024, QImage.Format.Format_RGBA8888)
    image.fill(0)
    with QPainter(image) as painter:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
    return Image.frombytes("RGBA", (image.width(), image.height()), bytes(image.constBits()))


if __name__ == "__main__":
    app = rasterize(BRAND / "pdfiu-app.svg")
    app.save(BRAND / "pdfiu-app.png", optimize=True)
    app.save(BRAND / "pdfiu-app.ico", sizes=[(size, size) for size in WINDOWS_SIZES])
    app.save(BRAND / "pdfiu-app.icns")
    document = rasterize(BRAND / "pdfiu-document.svg")
    document.save(BRAND / "pdfiu-document.ico", sizes=[(size, size) for size in WINDOWS_SIZES])
