"""Generate genuine ES & EN app screenshots, 1920x1080 Store slides, and User Guide visuals."""

import argparse
import os
import subprocess
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


def _make_sample_pdfs(folder, lang):
    is_es = lang == "es"
    main_pdf = folder / ("Proyecto_PDFiu_2026.pdf" if is_es else "PDFiu_Project_2026.pdf")
    c = rl_canvas.Canvas(str(main_pdf), pagesize=(595, 842))
    sections = (
        [
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
        if is_es
        else [
            ("Technical Specification · PDFiu Project", "Sample document · 100% local & private", [
                "1. Executive overview and core architectural specifications.",
                "2. Document control: PAdES digital signatures (RSA / ECDSA) & visual ink stamps.",
                "3. Smart compression with upfront size estimation and 100% side-by-side preview.",
                "4. Drag-and-drop page organizer, range splitting, offline OCR & Office export.",
            ]),
            ("Budget & Measurements", "Page 2 · Line items summary", [
                "Item 01 · 1:100 architectural floor plan survey ................. 1,250.00 EUR",
                "Item 02 · Document review and formal sign-off ................... 480.00 EUR",
                "Item 03 · Archival PDF/A final delivery ......................... 320.00 EUR",
            ]),
            ("Floor Plan · Scale 1:100", "Page 3 · Technical drawing", [
                "Zone A: Technical office (42.5 m²) · Zone B: Archive (18.0 m²)",
                "Main dimension: 12.40 m × 6.80 m · Verified baseline.",
            ]),
            ("Signatures & Compliance Annex", "Page 4 · Dossier closing", [
                "Electronically signed with a Windows store or .pfx/.p12 certificate.",
                "Cryptographic integrity verified locally with zero cloud uploads.",
            ]),
        ]
    )
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
            bp = ROOT / "build" / "sample-assets" / "blueprint.jpg"
            if bp.is_file():
                c.drawImage(str(bp), 42, 160, width=510, height=382, preserveAspectRatio=True, anchor="c")
            else:
                c.setStrokeColorRGB(0.18, 0.48, 0.44)
                c.setLineWidth(2)
                c.rect(58, 220, 480, 320, fill=0, stroke=1)
                c.line(298, 220, 298, 540)
                c.line(58, 380, 298, 380)
        c.setFillColorRGB(0.45, 0.52, 0.58)
        c.setFont("Helvetica", 9)
        footer_text = f"PDFiu · Página {idx} de 4" if is_es else f"PDFiu · Page {idx} of 4"
        c.drawString(48, 34, footer_text)
        c.showPage()
    c.save()

    rev_pdf = folder / ("Proyecto_PDFiu_RevB.pdf" if is_es else "PDFiu_Project_RevB.pdf")
    c2 = rl_canvas.Canvas(str(rev_pdf), pagesize=(595, 842))
    for idx, (title, sub, bullets) in enumerate(sections, 1):
        c2.setFillColorRGB(0.09, 0.16, 0.24)
        c2.rect(0, 760, 595, 82, fill=1, stroke=0)
        c2.setFillColorRGB(1, 1, 1)
        c2.setFont("Helvetica-Bold", 20)
        rev_tag = f"{title} (Rev B)" if idx == 3 else title
        c2.drawString(48, 804, rev_tag)
        c2.setFillColorRGB(0.59, 0.84, 0.76)
        c2.setFont("Helvetica", 11)
        c2.drawString(48, 780, sub)
        c2.setFillColorRGB(0.12, 0.18, 0.24)
        c2.setFont("Helvetica", 12)
        y = 710
        for line in bullets:
            if idx == 3 and ("42,5" in line or "42.5" in line):
                line = (
                    "Zona A: Oficina ampliada (48,0 m²) · Zona B: Sala reuniones (18,0 m²)"
                    if is_es
                    else "Zone A: Expanded office (48.0 m²) · Zone B: Meeting room (18.0 m²)"
                )
            c2.drawString(48, y, line)
            y -= 28
        if idx == 3:
            bp = ROOT / "build" / "sample-assets" / "blueprint.jpg"
            if bp.is_file():
                c2.drawImage(str(bp), 42, 160, width=510, height=382, preserveAspectRatio=True, anchor="c")
            c2.setStrokeColorRGB(0.82, 0.18, 0.22)
            c2.setLineWidth(2.6)
            c2.rect(318, 250, 178, 128, fill=0, stroke=1)
            c2.setFillColorRGB(0.82, 0.18, 0.22)
            c2.setFont("Helvetica-Bold", 11)
            c2.drawString(328, 355, "NUEVA PARTICIÓN +2,4 m" if is_es else "NEW PARTITION +2.4 m")
            c2.setStrokeColorRGB(0.0, 0.52, 0.45)
            c2.circle(165, 340, 32, fill=0, stroke=1)
            c2.setFillColorRGB(0.0, 0.52, 0.45)
            c2.drawString(125, 294, "ACCESO REV B" if is_es else "ACCESS REV B")
        c2.showPage()
    c2.save()

    sample_sig = ROOT / "build" / "sample-assets" / "signature.jpg"
    if sample_sig.is_file():
        sig_img = sample_sig
    else:
        sig_img = folder / "signature.png"
        im = Image.new("RGB", (600, 220), "white")
        d = ImageDraw.Draw(im)
        pts = [
            (40, 145), (85, 70), (110, 155), (155, 95), (190, 145),
            (235, 80), (275, 138), (330, 88), (395, 130), (470, 98), (545, 122),
        ]
        d.line(pts, fill=(18, 42, 86), width=8, joint="curve")
        d.line([(55, 175), (510, 162)], fill=(18, 42, 86), width=4)
        im.save(sig_img)

    return main_pdf, rev_pdf, sig_img


def _compose_slide(screenshot, headline, subtitle, pills, *, dark_bg=False):
    W, H = 1920, 1080
    bg = Image.new("RGBA", (W, H), (16, 22, 29, 255) if dark_bg else (244, 248, 246, 255))
    draw = ImageDraw.Draw(bg)

    if dark_bg:
        draw.rectangle([0, 0, W, 8], fill=(79, 179, 157, 255))
        title_col = (242, 247, 251, 255)
        sub_col = (162, 180, 198, 255)
        pill_bg = (29, 60, 53, 255)
        pill_border = (62, 138, 120, 255)
        pill_text = (152, 242, 214, 255)
    else:
        draw.rectangle([0, 0, W, 8], fill=(49, 127, 114, 255))
        title_col = (24, 42, 61, 255)
        sub_col = (81, 100, 114, 255)
        pill_bg = (224, 242, 234, 255)
        pill_border = (165, 210, 194, 255)
        pill_text = (25, 72, 63, 255)

    draw.text((88, 56), headline, fill=title_col, font=_font(52, bold=True))
    draw.text((88, 124), subtitle, fill=sub_col, font=_font(26, bold=False))

    px = 88
    pill_font = _font(20, bold=True)
    for pill in pills:
        bbox = draw.textbbox((0, 0), pill, font=pill_font)
        pw = (bbox[2] - bbox[0]) + 34
        ph = 38
        draw.rounded_rectangle([px, 174, px + pw, 174 + ph], radius=19, fill=pill_bg, outline=pill_border, width=2)
        draw.text((px + 17, 180), pill, fill=pill_text, font=pill_font)
        px += pw + 14

    max_w, max_h = 1744, 796
    sw, sh = screenshot.size
    scale = min(max_w / sw, max_h / sh)
    nw, nh = int(sw * scale), int(sh * scale)
    resized = screenshot.resize((nw, nh), Image.Resampling.LANCZOS)

    rad = 20
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

    bcol = (54, 68, 86, 255) if dark_bg else (210, 222, 217, 255)
    ImageDraw.Draw(bg).rounded_rectangle([sx, sy, sx + nw, sy + nh], radius=rad, outline=bcol, width=2)
    return bg.convert("RGB")


def _capture_single_lang(lang):
    import translations

    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    for font_file in ("segoeui.ttf", "segoeuib.ttf", "segoeuisb.ttf", "segoeuii.ttf", "arial.ttf", "arialbd.ttf"):
        path = Path(r"C:\Windows\Fonts") / font_file
        if path.is_file():
            QFontDatabase.addApplicationFont(str(path))

    # Initialize language BEFORE importing pdfiu/dialogs so every module-level string is localized
    translations.initialize_language(lang)

    import pdfiu
    import pdfiu_ui
    from pdfiu_dialogs import (
        CommandPaletteDialog,
        CompressDialog,
        OrganizePagesDialog,
        RevisionComparison,
        SplitDialog,
        VisualSignatureDialog,
    )

    is_es = lang == "es"
    out_dir = ROOT / "build" / "store-slides" / lang
    out_dir.mkdir(parents=True, exist_ok=True)
    guide_dir = ROOT / "docs" / "guide-shots" / lang
    guide_dir.mkdir(parents=True, exist_ok=True)
    docs_dir = (ROOT / "docs" / "screenshots") if is_es else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        main_pdf, rev_pdf, sig_img = _make_sample_pdfs(tmp_path, lang)

        # 0) Welcome screen with Recent Document Cards (light theme)
        pdfiu_ui.apply_theme(app, "light")
        win = pdfiu.PDFiu(show_startup=False)
        win.resize(1340, 820)
        win.welcome_offer.hide()
        sample_recents = [main_pdf, rev_pdf]
        win.recent_files = lambda: sample_recents
        win.refresh_recent_files()
        app.processEvents()
        shot_welcome = _grab_pil(win, app)

        # 1) Main window with document + Floating HUD clearly visible (light theme)
        win.open_path(main_pdf, remember_recent=False)
        win._hud_opacity.setOpacity(1.0)
        win.position_viewer_hud()
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

        # 5) Command Palette Ctrl+K (light theme)
        palette = CommandPaletteDialog(win.collect_palette_commands(), win)
        palette.search.setText("firm" if is_es else "sign")
        palette.search.deselect()
        app.processEvents()
        raw_palette = _grab_pil(palette, app)
        shot_palette = Image.new("RGBA", raw_palette.size, (238, 243, 241, 255))
        shot_palette.alpha_composite(raw_palette)
        palette.close()

        # 6) SplitDialog (light theme)
        split_dlg = SplitDialog(12, main_pdf.stem, tmp_path, win)
        split_dlg.folder.setText("Documents/PDFiu_Split" if not is_es else "Documentos/PDFiu_Dividido")
        shot_split = _grab_pil(split_dlg, app)
        split_dlg.close()

        # 7) Dark mode + Signatures panel with localized sample cards
        pdfiu_ui.apply_theme(app, "dark")
        win.tool_group.button(3).click()
        win._hud_opacity.setOpacity(1.0)
        win.position_viewer_hud()
        win.signature_data = [
            {
                "name": "Elena Navarro Ruiz",
                "identifier": "IDCES-12345678Z",
                "identifier_label": "DNI / NIF" if is_es else "Tax / National ID",
                "organization": "Estudio Técnico" if is_es else "Engineering Studio",
                "field_name": "Firma_1" if is_es else "Signature_1",
                "signed_at": "2026-11-26 10:15",
                "valid_now": True,
                "valid_at_reported_time": True,
                "integrity": True,
                "trusted": True,
                "coverage": "Todo el documento" if is_es else "Entire document",
                "issuer": "AC FNMT Usuarios" if is_es else "Qualified Trust CA",
                "not_before": "2024-05-01",
                "not_after": "2028-05-01",
                "key_algorithm": "RSA 2048",
                "certificate_serial": "4A91F20C88",
            },
            {
                "name": "Dirección de Obra · Colegio Oficial" if is_es else "Project Lead · Technical Board",
                "identifier": "CIF-Q0300123A" if is_es else "ORG-8840219A",
                "identifier_label": "CIF" if is_es else "Organization ID",
                "organization": "Colegio Profesional" if is_es else "Professional Board",
                "field_name": "Visado_2" if is_es else "Approval_2",
                "signed_at": "2026-11-26 10:32",
                "valid_now": True,
                "valid_at_reported_time": True,
                "integrity": True,
                "trusted": True,
                "coverage": "Revisión firmada" if is_es else "Signed revision",
                "issuer": "AC Representación" if is_es else "Corporate Representation CA",
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

        # 8) RevisionComparison (light theme)
        pdfiu_ui.apply_theme(app, "light")
        rev = RevisionComparison(win, [(main_pdf, None), (rev_pdf, None)])
        rev.showNormal()
        rev.resize(1180, 720)
        rev.show()
        rev.page_inputs[0][0].setValue(3)
        rev.render_pair()
        app.processEvents()
        app.processEvents()
        shot_compare = _grab_pil(rev, app)
        rev.close()
        win.dirty = False
        win.close()

        # Save clean standalone guide screenshots (WEBP, lightweight)
        guide_shots = {
            "01-workspace.webp": shot_main,
            "02-compress.webp": shot_compress,
            "03-signatures-dark.webp": shot_sig_dark,
            "04-visual-signature.webp": shot_vsig,
            "05-organize.webp": shot_org,
            "06-compare.webp": shot_compare,
            "07-command-palette.webp": shot_palette,
            "08-split.webp": shot_split,
            "09-welcome-recent.webp": shot_welcome,
        }
        for fname, img in guide_shots.items():
            img.convert("RGB").save(guide_dir / fname, "WEBP", quality=88, method=4)

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

        webp_dir = ROOT / "docs" / "slides" / lang
        webp_dir.mkdir(parents=True, exist_ok=True)
        for filename, shot, headline, subtitle, pills, dark_bg in slides:
            slide = _compose_slide(shot, headline, subtitle, pills, dark_bg=dark_bg)
            slide.save(out_dir / filename, optimize=True)
            slide.save(webp_dir / (Path(filename).stem + ".webp"), "WEBP", quality=86, method=4)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=("es", "en"))
    args = parser.parse_args()
    if args.lang:
        _capture_single_lang(args.lang)
        print(f"Generated slides and guide screenshots for {args.lang}.")
        return
    for lang in ("es", "en"):
        subprocess.run([sys.executable, __file__, "--lang", lang], check=True)
    print("Generated 12 Store slides (6 ES + 6 EN) and 18 guide screenshots (9 ES + 9 EN).")


if __name__ == "__main__":
    main()
