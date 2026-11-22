"""Regenerate the PDFiu welcome guide and its practice appendix."""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


ASSETS = Path(__file__).resolve().parents[1] / "assets" / "bienvenida"
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 49
BODY_WIDTH = PAGE_WIDTH - 2 * MARGIN
PAPER = HexColor("#f9f8f4")
INK = HexColor("#18263a")
SUBTLE = HexColor("#46566a")
ACCENT = HexColor("#244e75")
RULE = HexColor("#d9dfe3")
PANEL = HexColor("#eaf0f4")


def label(page, value, x, y, *, size=11, color=INK, family="Helvetica"):
    page.setFont(family, size)
    page.setFillColor(color)
    page.drawString(x, y, value)


def paragraph(page, value, x, top, width, *, size=12, leading=17, color=SUBTLE):
    style = ParagraphStyle("copy", fontName="Helvetica", fontSize=size, leading=leading,
                           textColor=color, alignment=TA_LEFT)
    block = Paragraph(value, style)
    _, height = block.wrap(width, 800)
    block.drawOn(page, x, top - height)
    return top - height


def rule(page, y):
    page.setStrokeColor(RULE)
    page.setLineWidth(0.6)
    page.line(MARGIN, y, PAGE_WIDTH - MARGIN, y)


def page_template(filename, title, section, footer):
    page = Canvas(str(ASSETS / filename), pagesize=A4, pageCompression=1, invariant=1)
    page.setTitle(title)
    page.setAuthor("PDFiu")
    page.setSubject(title)
    page_chrome(page, section, footer)
    return page


def page_chrome(page, section, footer):
    page.setFillColor(PAPER)
    page.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, fill=1, stroke=0)
    label(page, "PDFiu", MARGIN, 784, size=17, family="Helvetica-Bold")
    page.setFillColor(ACCENT)
    page.setFont("Helvetica", 10)
    page.drawRightString(PAGE_WIDTH - MARGIN, 785, section)
    rule(page, 765)
    rule(page, 63)
    label(page, footer, MARGIN, 42, size=10, color=SUBTLE)


def welcome(language):
    spanish_steps = [
        ("Abre el anexo", "Pulsa <b>Abrir el anexo</b> en la cinta superior. La bienvenida y el anexo aparecerán en Archivos."),
        ("Marca los dos PDF", "En <b>Archivos</b>, marca la casilla de cada documento. El panel indicará «2 PDF seleccionados»."),
        ("Únelos", "Pulsa <b>Unir PDFs</b>. Revisa el orden. Si quieres cambiarlo, arrastra las filas antes de confirmar."),
        ("Guarda el resultado", "Pulsa <b>Guardar</b>, elige una carpeta y confirma. La visita te mostrará dónde quedó el archivo."),
    ]
    english_steps = [
        ("Open the appendix", "Click <b>Open appendix</b> in the bar above the page. Both PDFs will appear under Files."),
        ("Select both PDFs", "Under <b>Files</b>, check both documents. The tools panel will say “2 PDFs selected”."),
        ("Merge them", "Click <b>Merge PDFs</b>. Check the order. To change it, drag the rows before confirming."),
        ("Save the result", "Click <b>Save</b>, choose a folder, and confirm. The tour will show you where the file was saved."),
    ]
    if language == "en":
        page = page_template("Welcome to PDFiu.pdf", "Welcome to PDFiu", "QUICK START",
                             "PDFiu   /   Help › Guided tour")
        title, heading = "Welcome to PDFiu", "Your first merged PDF"
        intro = "Open, organize, and sign PDFs on your computer. In this tour, you’ll merge two practice PDFs and save the result."
        tip_title = "Everyday tools on page 2"
        tip = "Find the exact menu paths for exporting, copying a page as an image, signing, unlocking, numbering and redacting."
        outline = "Welcome"
        steps = english_steps
    else:
        page = page_template("Bienvenida a PDFiu.pdf", "Bienvenida a PDFiu", "GUÍA DE INICIO",
                             "PDFiu   /   Ayuda › Visita guiada")
        title, heading = "Bienvenido a PDFiu", "Tu primer PDF unido"
        intro = "Abre, organiza y firma PDF desde tu equipo. En esta visita vas a unir dos documentos de ejemplo y guardar el resultado."
        tip_title = "Herramientas habituales en la página 2"
        tip = "Consulta dónde exportar, copiar una página como imagen, firmar, desbloquear, numerar y censurar datos."
        outline = "Bienvenida"
        steps = spanish_steps
    page.bookmarkPage("welcome")
    page.addOutlineEntry(outline, "welcome")
    label(page, title, MARGIN, 687, size=48, family="Times-Roman")
    paragraph(page, intro, MARGIN, 657, 390, size=15, leading=22)
    label(page, heading, MARGIN, 553, size=24, family="Times-Roman")
    for number, (title, detail) in enumerate(steps, start=1):
        y = 525 - (number - 1) * 78
        rule(page, y)
        label(page, str(number), MARGIN, y - 34, size=24, color=ACCENT, family="Times-Roman")
        label(page, title, MARGIN + 39, y - 23, size=13, family="Helvetica-Bold")
        assert paragraph(page, detail, MARGIN + 39, y - 31, BODY_WIDTH - 45) > y - 76
    rule(page, 213)

    page.setFillColor(PANEL)
    page.rect(MARGIN, 94, BODY_WIDTH, 87, fill=1, stroke=0)
    label(page, tip_title, MARGIN + 17, 156, size=13, family="Helvetica-Bold")
    assert paragraph(page, tip, MARGIN + 17, 145, BODY_WIDTH - 34, size=11, leading=16) > 99
    page.showPage()
    tool_guide(page, language)
    page.save()


def tool_guide(page, language):
    if language == "en":
        heading = "Everyday PDF tools"
        page_chrome(page, "TOOL GUIDE", "PDFiu   /   Help › Tool guide")
        subtitle = "Find each command and follow the steps with your own PDF."
        tools = [
            ("Export to Word, Excel or Markdown",
             "<b>File › Export</b>. Choose a format and select all pages, the current page or a range."),
            ("Copy a page as an image",
             "<b>File › Export</b>. Choose <b>Copy page to clipboard</b> to paste it into Word, or <b>PNG image…</b> to save it as a file."),
            ("Sign with a digital certificate",
             "<b>Sign › Sign with a certificate</b>. Draw the signature box, choose your certificate and save the signed copy."),
            ("Sign several PDFs",
             "<b>Sign › Batch sign</b>. Choose the files and set where each signature goes. You can also reuse the same box across the batch."),
            ("Unlock a PDF",
             "<b>Protect › Unlock PDF</b>. Create an unlocked copy. PDFiu asks for the password when it is required to open the file."),
            ("Add headers and footers",
             "<b>Edit › Headers and footers</b>. Enter your text and choose its position and page range."),
            ("Number pages",
             "<b>Edit › Number pages</b>. Choose a starting number, a position and the pages to number."),
            ("Redact sensitive information",
             "<b>Protect › Redact information</b>. Mark the areas, select <b>Save redacted copy…</b> and check the copy before sharing."),
        ]
    else:
        heading = "Herramientas del día a día"
        page_chrome(page, "GUÍA DE HERRAMIENTAS", "PDFiu   /   Ayuda › Guía de herramientas")
        subtitle = "Encuentra cada herramienta y sigue los pasos con tu propio PDF."
        tools = [
            ("Exportar a Word, Excel o Markdown",
             "<b>Archivo › Exportar</b>. Elige un formato y selecciona todas las páginas, la actual o un intervalo."),
            ("Copiar una página como imagen",
             "<b>Archivo › Exportar</b>. Elige <b>Copiar página al portapapeles</b> para pegarla en Word, o <b>Imagen PNG…</b> para guardarla como archivo."),
            ("Firmar con certificado digital",
             "<b>Firmar › Firmar con certificado</b>. Dibuja el recuadro, elige tu certificado y guarda la copia firmada."),
            ("Firmar varios PDF",
             "<b>Firmar › Firmar lote</b>. Elige los archivos e indica dónde irá cada firma. También puedes aplicar el mismo recuadro a todo el lote."),
            ("Desbloquear un PDF",
             "<b>Proteger › Desbloquear PDF</b>. Crea una copia desbloqueada. PDFiu pide la contraseña si el archivo la exige para abrirse."),
            ("Añadir encabezados y pies de página",
             "<b>Editar › Encabezados y pies</b>. Escribe tu texto y elige la posición y el intervalo de páginas."),
            ("Numerar páginas",
             "<b>Editar › Numerar páginas</b>. Indica el número inicial, la posición y las páginas que quieres numerar."),
            ("Censurar datos sensibles",
             "<b>Proteger › Censurar datos</b>. Marca las zonas, pulsa <b>Guardar copia censurada…</b> y comprueba la copia antes de compartirla."),
        ]
    page.bookmarkPage("tools")
    page.addOutlineEntry(heading, "tools")
    label(page, heading, MARGIN, 719, size=35, family="Times-Roman")
    paragraph(page, subtitle, MARGIN, 698, BODY_WIDTH, size=12, leading=17)
    for index, (title, detail) in enumerate(tools):
        y = 663 - index * 69
        rule(page, y)
        label(page, title, MARGIN, y - 22, size=13, family="Helvetica-Bold")
        assert paragraph(page, detail, MARGIN, y - 30, BODY_WIDTH, size=11.5, leading=15) > y - 68
    page.showPage()


def appendix(language):
    if language == "en":
        page = page_template("Practice appendix.pdf", "PDFiu practice appendix", "PRACTICE DOCUMENT",
                             "PDFiu   /   Practice appendix")
        title, heading = "Practice appendix", "Check the order"
        intro = "This is the second document in the tour. Merge it with the welcome guide to create a three-page PDF."
        detail = ("If you keep the welcome guide first, this appendix will be the last page of the result. "
                  "You can change the order in <b>Merge PDFs</b>.")
    else:
        page = page_template("Anexo de ejemplo.pdf", "Anexo de ejemplo de PDFiu", "DOCUMENTO DE PRÁCTICA",
                             "PDFiu   /   Anexo de ejemplo")
        title, heading = "Anexo de ejemplo", "Comprueba el orden"
        intro = "Este es el segundo documento de la visita. Únelo a la bienvenida para crear un PDF de tres páginas."
        detail = ("Si dejas la bienvenida primero, encontrarás este anexo en la última página del resultado. "
                  "Puedes cambiar el orden en el diálogo <b>Unir PDFs</b>.")
    label(page, title, MARGIN, 687, size=47, family="Times-Roman")
    paragraph(page, intro, MARGIN, 657, 375, size=15, leading=22)
    rule(page, 558)
    label(page, heading, MARGIN, 522, size=24, family="Times-Roman")
    paragraph(page, detail, MARGIN, 504, 380)
    page.showPage()
    page.save()


if __name__ == "__main__":
    ASSETS.mkdir(parents=True, exist_ok=True)
    for language in ("es", "en"):
        welcome(language)
        appendix(language)
