"""Generate genuine app screenshots and 1920x1080 Microsoft Store slides (ES & EN)."""

import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtWidgets import QApplication
from reportlab.pdfgen import canvas as rl_canvas

import pdfiu
import pdfiu_ui
import translations
from pdfiu_dialogs import CompressDialog, OrganizePagesDialog, RevisionComparison, VisualSignatureDialog


def _font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _grab_pil(widget, app):
    widget.show()
    app.processEvents()
    app.processEvents()
    pix = widget.grab()
    qimg = pix.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = qimg.width(), qimg.height()
    ptr = qimg.constBits()
    return Image.frombytes("RGBA", (w, h), bytes(ptr), "raw", "RGBA", qimg.bytesPerLine())


def _make_sample_pdfs(folder):
    main_pdf = folder / "Proyecto_PDFiu_2026.pdf"
    c = rl_canvas.Canvas(str(main_pdf), pagesize=(595, 842))
    sections = [
        ("Memoria Técnica · Proyecto PDFiu", "Documento de muestra · 100 % local y privado", [
            "1. Resumen ejecutivo del proyecto y especificaciones generales.",
            "2. Control documental: firmas digitales PAdES (RSA / ECDSA) y firma visual.",
            "3. Compresión inteligente con estimación previa y comparación visual al 100 %.",
            "4. Organización de páginas, división por rangos, OCR offline y exportación.",
        ]),
        ("Presupuesto y Mediciones", "Página 2 · Tabla de partidas", [
            "Partida 01 · Levantamiento de planos a escala 1:100 ............. 1.250,00 EUR",
            "Partida 02 · Revisión documental y visado colegial .............. 480,00 EUR",
            "Partida 03 · Entrega final en formato PDF/A ..................... 320,00 EUR",
        ]),
        ("Plano de Planta · Escala 1:100", "Página 3 · Esquema técnico", [
            "Zona A: Oficina técnica (42,5 m²) · Zona B: Archivo (18,0 m²)",
            "Cota principal: 12,40 m × 6,80 m · Verificado sin cambios.",
        ]),
        ("Anexo de Firmas y Conformidad", "Página 4 · Cierre del expediente", [
            "Firmado electrónicamente mediante certificado instalado en Windows.",
            "Documento íntegro y verificable sin subir archivos a la nube.",
        ]),
    ]
    for idx, (title, sub, bullets) in enumerate(sections, 1):
        c.setFillColorRGB(0.09, 0.16, 0.24)
        c.rect(0, 760, 595, 82, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(48, 804, title)
        c.setFillColorRGB(0.59, 0.84, 0.76)
        c.setFont("Helvetica", 11)
        c.drawString(48, 780, sub)
        c.setFillColorRGB(0.12, 0.18, 0.24)
        c.setFont("Helvetica", 12)
        y = 710
        for line in bullets:
            c.drawString(48, y, line)
            y -= 28
        if idx == 3:
            c.setStrokeColorRGB(0.19, 0.50, 0.45)
            c.setLineWidth(2)
            c.rect(70, 340, 440, 260, stroke=1, fill=0)
            c.line(290, 340, 290, 600)
            c.line(70, 470, 290, 470)
            c.setFont("Helvetica-Bold", 11)
            c.drawString(120, 530, "OFICINA 42,5 m2")
            c.drawString(340, 470, "SALA TECNICA 36,0 m2")
        c.setFillColorRGB(0.45, 0.52, 0.58)
        c.setFont("Helvetica", 9)
        c.drawRightString(547, 34, f"PDFiu · {idx} / 4")
        c.showPage()
    c.save()

    rev_pdf = folder / "Proyecto_PDFiu_Rev2.pdf"
    c2 = rl_canvas.Canvas(str(rev_pdf), pagesize=(595, 842))
    c2.setFillColorRGB(0.09, 0.16, 0.24)
    c2.rect(0, 760, 595, 82, fill=1, stroke=0)
    c2.setFillColorRGB(1, 1, 1)
    c2.setFont("Helvetica-Bold", 20)
    c2.drawString(48, 804, "Plano de Planta · Escala 1:100 (Rev. 2)")
    c2.setStrokeColorRGB(0.19, 0.50, 0.45)
    c2.setLineWidth(2)
    c2.rect(70, 340, 440, 260, stroke=1, fill=0)
    c2.line(330, 340, 330, 600)
    c2.line(70, 450, 330, 450)
    c2.setStrokeColorRGB(0.80, 0.20, 0.20)
    c2.rect(360, 380, 110, 90, stroke=1, fill=0)
    c2.setFont("Helvetica-Bold", 11)
    c2.setFillColorRGB(0.12, 0.18, 0.24)
    c2.drawString(120, 520, "OFICINA AMPLIADA 49,2 m2")
    c2.drawString(368, 420, "NUEVA SALA")
    c2.showPage()
    c2.save()

    sig_img = folder / "firma_ejemplo.png"
    img = Image.new("RGB", (420, 150), "white")
    d = ImageDraw.Draw(img)
    pts = [(35, 108), (75, 36), (95, 112), (145, 58), (175, 102), (225, 48), (255, 96), (320, 78), (385, 86)]
    d.line(pts, fill=(18, 42, 98), width=6, joint="curve")
    d.line([(45, 122), (370, 112)], fill=(18, 42, 98), width=3)
    img.save(sig_img)

    return main_pdf, rev_pdf, sig_img


def _compose_slide(shot, headline, subtitle, pills, *, dark_bg=True):
    W, H = 1920, 1080
    bg = Image.new("RGBA", (W, H), (15, 23, 34, 255) if dark_bg else (244, 247, 245, 255))
    draw = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / (H - 1)
        if dark_bg:
            r = int(15 + (24 - 15) * t)
            g = int(23 + (38 - 23) * t)
            b = int(34 + (54 - 34) * t)
        else:
            r = int(246 - 8 * t)
            g = int(249 - 6 * t)
            b = int(247 - 5 * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))

    # Top accent line
    draw.rectangle([0, 0, W, 6], fill=(49, 127, 114, 255))

    # Headline & subtitle
    title_color = (242, 247, 252, 255) if dark_bg else (24, 42, 61, 255)
    sub_color = (158, 178, 198, 255) if dark_bg else (81, 100, 114, 255)
    f_title = _font(52, bold=True)
    f_sub = _font(26, bold=False)
    f_pill = _font(20, bold=True)

    draw.text((88, 52), headline, font=f_title, fill=title_color)
    draw.text((88, 122), subtitle, font=f_sub, fill=sub_color)

    # Pills row
    px = 88
    py = 172
    for pill in pills:
        bbox = draw.textbbox((0, 0), pill, font=f_pill)
        tw = bbox[2] - bbox[0]
        pw = tw + 32
        ph = 38
        fill = (29, 60, 53, 255) if dark_bg else (220, 241, 232, 255)
        border = (79, 179, 157, 255) if dark_bg else (164, 214, 198, 255)
        tcol = (143, 240, 212, 255) if dark_bg else (25, 72, 63, 255)
        draw.rounded_rectangle([px, py, px + pw, py + ph], radius=19, fill=fill, outline=border, width=2)
        draw.text((px + 16, py + 6), pill, font=f_pill, fill=tcol)
        px += pw + 14

    # Scale screenshot to fit nicely in bottom area
    max_w, max_h = 1744, 795
    scale = min(max_w / shot.width, max_h / shot.height)
    nw, nh = int(shot.width * scale), int(shot.height * scale)
    resized = shot.resize((nw, nh), Image.Resampling.LANCZOS)

    # Rounded mask + soft shadow
    rad = 16
    mask = Image.new("L", (nw, nh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, nw, nh], radius=rad, fill=255)
    framed = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
    framed.paste(resized, (0, 0), mask)

    sx = (W - nw) // 2
    sy = 238 + (max_h - nh) // 2

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [sx - 4, sy + 10, sx + nw + 4, sy + nh + 18],
        radius=rad + 4,
        fill=(0, 0, 0, 120 if dark_bg else 55),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    bg.alpha_composite(shadow)
    bg.alpha_composite(framed, (sx, sy))

    # Crisp border around screenshot
    bcol = (54, 68, 86, 255) if dark_bg else (210, 222, 217, 255)
    ImageDraw.Draw(bg).rounded_rectangle([sx, sy, sx + nw, sy + nh], radius=rad, outline=bcol, width=2)
    return bg.convert("RGB")


def _capture_for_lang(app, lang, main_pdf, rev_pdf, sig_img, out_dir, docs_dir=None):
    translations.initialize_language(lang)
    out_dir.mkdir(parents=True, exist_ok=True)
    is_es = lang == "es"

    # 1) Main window (light theme)
    pdfiu_ui.apply_theme(app, "light")
    win = pdfiu.PDFiu(show_startup=False)
    win.resize(1340, 820)
    win.open_path(main_pdf, remember_recent=False)
    app.processEvents()
    shot_main = _grab_pil(win, app)

    # 2) CompressDialog (light theme)
    comp = CompressDialog(win)
    comp.advanced_toggle.setChecked(True)
    shot_compress = _grab_pil(comp, app)
    comp.close()

    # 3) VisualSignatureDialog (light theme)
    vsig = VisualSignatureDialog(win, initial_path=str(sig_img), remove_white=True)
    shot_vsig = _grab_pil(vsig, app)
    vsig.close()

    # 4) OrganizePagesDialog (light theme)
    org = OrganizePagesDialog(main_pdf, 4, parent=win)
    org.resize(900, 560)
    org.show()
    app.processEvents()
    org.render_visible_thumbnails()
    app.processEvents()
    shot_org = _grab_pil(org, app)
    org.close()

    # 5) Dark mode + Signatures panel with sample cards
    pdfiu_ui.apply_theme(app, "dark")
    win.tool_group.button(3).click()
    win.signature_data = [
        {
            "name": "Elena Navarro Ruiz",
            "identifier": "IDCES-12345678Z",
            "identifier_label": "DNI / NIF",
            "organization": "Estudio Técnico",
            "field_name": "Firma_1",
            "signed_at": "2026-11-26 10:15",
            "valid_now": True,
            "valid_at_reported_time": True,
            "integrity": True,
            "trusted": True,
            "coverage": "Todo el documento",
            "issuer": "AC FNMT Usuarios",
            "not_before": "2024-05-01",
            "not_after": "2028-05-01",
            "key_algorithm": "RSA 2048",
            "certificate_serial": "4A91F20C88",
        },
        {
            "name": "Dirección de Obra · Colegio Oficial",
            "identifier": "CIF-Q0300123A",
            "identifier_label": "CIF",
            "organization": "Colegio Profesional",
            "field_name": "Visado_2",
            "signed_at": "2026-11-26 10:32",
            "valid_now": True,
            "valid_at_reported_time": True,
            "integrity": True,
            "trusted": True,
            "coverage": "Revisión firmada",
            "issuer": "AC Representación",
            "not_before": "2025-01-10",
            "not_after": "2029-01-10",
            "key_algorithm": "ECDSA P-256",
            "certificate_serial": "7E20B114D2",
        },
    ]
    win.choose_navigation(win.signatures_panel, refresh=False)
    win.populate_signatures_list()
    win.body_splitter.setSizes([340, 1000])
    app.processEvents()
    shot_sig_dark = _grab_pil(win, app)

    # 6) RevisionComparison (light theme)
    pdfiu_ui.apply_theme(app, "light")
    rev = RevisionComparison(win, [(main_pdf, None), (rev_pdf, None)])
    rev.showNormal()
    rev.resize(1180, 720)
    rev.page_inputs[0][0].setValue(3)
    rev.request_render()
    app.processEvents()
    shot_compare = _grab_pil(rev, app)
    rev.close()
    win.close()

    if docs_dir is not None:
        docs_dir.mkdir(parents=True, exist_ok=True)
        shot_compress.convert("RGB").save(docs_dir / "compress.png", optimize=True)
        shot_sig_dark.convert("RGB").save(docs_dir / "signatures-dark.png", optimize=True)
        shot_org.convert("RGB").save(docs_dir / "organize.png", optimize=True)
        shot_vsig.convert("RGB").save(docs_dir / "visual-sign.png", optimize=True)

    slides = [
        (
            "01-portada.png" if is_es else "01-overview.png",
            shot_main,
            "Tu editor de PDF 100 % local y sin suscripciones" if is_es else "Your 100% local PDF editor—zero subscriptions",
            "Pago único tras 15 días de prueba gratis. Sin cuentas, sin límites diarios y sin subir archivos." if is_es else "One-time purchase after a 15-day free trial. No accounts, no daily caps, zero cloud uploads.",
            (["100 % Local", "Pago único", "15 días gratis", "Sin cuenta"] if is_es else ["100% Local", "One-Time Purchase", "15-Day Free Trial", "No Account"]),
            True,
        ),
        (
            "02-comprimir.png" if is_es else "02-compress.png",
            shot_compress,
            "Comprime PDF y estima el ahorro antes de guardar" if is_es else "Compress PDFs & estimate savings before saving",
            "3 niveles sencillos más opciones avanzadas (ICC, CMYK, SMask, grises) y comparación visual al 100 %." if is_es else "3 simple presets plus advanced options (ICC, CMYK, SMask, grayscale) and 100% side-by-side preview.",
            (["Estimación previa", "Comparación al 100 %", "Limpieza de metadatos"] if is_es else ["Size Estimator", "100% Preview", "Metadata Cleanup"]),
            False,
        ),
        (
            "03-firmas-oscuro.png" if is_es else "03-signatures-dark.png",
            shot_sig_dark,
            "Firma múltiple (RSA y ECDSA), desbloqueo y censura" if is_es else "Batch signing (RSA & ECDSA), unlock & true redaction",
            "Certificados de Windows o .pfx/.p12, explorador de firmas en tarjetas, desbloqueo y censura irreversible." if is_es else "Windows certificates or .pfx/.p12, card-based signature explorer, offline unlock & irreversible redaction.",
            (["Firma en lote", "RSA & ECDSA", "Desbloqueo offline", "Tema oscuro"] if is_es else ["Batch Signing", "RSA & ECDSA", "Offline Unlock", "Dark Mode"]),
            True,
        ),
        (
            "04-firma-visual.png" if is_es else "04-visual-signature.png",
            shot_vsig,
            "Firma visual con imagen (PNG, JPG) o PDF en 2 clics" if is_es else "Visual signature from PNG, JPG, or PDF in 2 clicks",
            "Quita el fondo blanco automáticamente, previsualiza en vivo y estampa tu firma o sello sin perder calidad." if is_es else "Automatic white background removal, live preview, and crisp stamping while keeping selectable text.",
            (["PNG / JPG / PDF", "Fondo transparente", "Deshacer (Ctrl+Z)"] if is_es else ["PNG / JPG / PDF", "Transparent Ink", "Full Undo"]),
            False,
        ),
        (
            "05-organizar.png" if is_es else "05-organize.png",
            shot_org,
            "Organiza, une y divide páginas arrastrando" if is_es else "Drag-and-drop organize, merge & split pages",
            "Cuadrícula visual rápida para reordenar, girar o borrar páginas, unir expedientes y dividir por rangos." if is_es else "Fast thumbnail grid to reorder, rotate, or delete pages, merge dossiers, and split by page ranges.",
            (["Cuadrícula visual", "Unir con índice", "Dividir cada N págs."] if is_es else ["Thumbnail Grid", "Merge + Outline", "Split by Range"]),
            True,
        ),
        (
            "06-comparar-planos.png" if is_es else "06-compare-drawings.png",
            shot_compare,
            "Compara dos PDF visualmente y mide planos 1:N" if is_es else "Compare two PDFs visually & measure 1:N drawings",
            "Detecta diferencias en contratos, imágenes o planos técnicos en paralelo, superpuestos o en color." if is_es else "Spot changes across contracts, images, or technical drawings side by side, overlaid, or with diffs.",
            (["Comparar 2 PDF", "Diferencias en color", "Medición 1:N", "OCR offline"] if is_es else ["Compare 2 PDFs", "Color Diffs", "1:N Measurement", "Offline OCR"]),
            False,
        ),
    ]

    for filename, shot, headline, subtitle, pills, dark_bg in slides:
        slide = _compose_slide(shot, headline, subtitle, pills, dark_bg=dark_bg)
        slide.save(out_dir / filename, optimize=True)


def main():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    for font_file in ("segoeui.ttf", "segoeuib.ttf", "segoeuisb.ttf", "segoeuii.ttf", "arial.ttf", "arialbd.ttf"):
        path = Path(r"C:\Windows\Fonts") / font_file
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))
    with tempfile.TemporaryDirectory() as tmp:
        main_pdf, rev_pdf, sig_img = _make_sample_pdfs(Path(tmp))
        _capture_for_lang(app, "es", main_pdf, rev_pdf, sig_img, ROOT / "build" / "store-slides" / "es", docs_dir=ROOT / "docs" / "screenshots")
        _capture_for_lang(app, "en", main_pdf, rev_pdf, sig_img, ROOT / "build" / "store-slides" / "en")
    print("Generated 12 Store slides (6 ES + 6 EN) and 4 docs screenshots successfully.")


if __name__ == "__main__":
    main()
