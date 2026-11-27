import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HAS_PDF_DEPS = all(importlib.util.find_spec(m) is not None for m in ("pypdf", "pypdfium2", "reportlab", "PIL"))


def _make_text_pdf(destination, pages):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(destination), pagesize=(595, 842))
    for text in pages:
        c.setFont("Helvetica", 12)
        c.drawString(72, 750, text)
        c.showPage()
    c.save()


@unittest.skipUnless(HAS_PDF_DEPS, "PDF dependencies not installed in this environment")
class PdfOpsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._patch = patch.dict(sys.modules, {"translations": type("M", (), {"tr": staticmethod(lambda s: s)})()})
        cls._patch.start()
        import pdf_ops
        cls.pdf_ops = pdf_ops

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()

    def test_page_range_parsing(self):
        self.assertEqual(self.pdf_ops.page_range("1,3-5", 6), [0, 2, 3, 4])
        self.assertEqual(self.pdf_ops.page_range("2", 5), [1])
        with self.assertRaises(ValueError):
            self.pdf_ops.page_range("0", 5)
        with self.assertRaises(ValueError):
            self.pdf_ops.page_range("1-9", 5)

    def test_blank_merge_edit_protect_unlock_and_search(self):
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            blank = root / "blank.pdf"
            self.pdf_ops.blank_pdf(blank, 595, 842)
            self.assertEqual(len(PdfReader(str(blank)).pages), 1)

            a = root / "a.pdf"
            b = root / "b.pdf"
            _make_text_pdf(a, ["Plano general de medición", "Detalle de estructura"])
            _make_text_pdf(b, ["Memoria de cálculo"])

            merged = root / "merged.pdf"
            self.pdf_ops.merge(
                [a, b], merged, with_index=True, names={str(a): "Planos", str(b): "Memoria"}
            )
            self.assertEqual(len(PdfReader(str(merged)).pages), 3)

            # Reorder & extract subset
            edited = root / "edited.pdf"
            self.pdf_ops.edit_pages(merged, edited, [2, 0])
            self.assertEqual(len(PdfReader(str(edited)).pages), 2)
            with self.pdf_ops.page_text(edited, 0) as text_page:
                self.assertIn("Memoria", text_page.get_text_bounded())
            with self.pdf_ops.page_text(edited, 1) as text_page:
                self.assertIn("Plano", text_page.get_text_bounded())

            # Search with and without accent matching
            hits_no_accents = self.pdf_ops.search_document(edited, "medicion", lambda *_: None, match_accents=False)
            self.assertEqual(len(hits_no_accents), 1)
            hits_exact = self.pdf_ops.search_document(edited, "medicion", lambda *_: None, match_accents=True)
            self.assertEqual(len(hits_exact), 0)

            # Protect with password and unlock
            protected = root / "protected.pdf"
            self.pdf_ops.protect_copy(edited, protected, "secreto123")
            self.assertTrue(PdfReader(str(protected)).is_encrypted)

            unlocked = root / "unlocked.pdf"
            self.pdf_ops.unlock_pdf(protected, unlocked, password="secreto123")
            self.assertFalse(PdfReader(str(unlocked)).is_encrypted)
            self.assertEqual(len(PdfReader(str(unlocked)).pages), 2)

    def test_redact_copy_destroys_text_and_strips_metadata(self):
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "secret_raw.pdf"
            _make_text_pdf(raw, ["DATO CONFIDENCIAL 12345678Z"])
            src = root / "secret.pdf"
            writer = PdfWriter(clone_from=PdfReader(str(raw)))
            writer.add_metadata({"/Author": "Autor Secreto", "/Title": "Titulo Privado"})
            with src.open("wb") as stream:
                writer.write(stream)

            redacted = root / "redacted.pdf"
            self.pdf_ops.redact_copy(src, redacted, {0: [(60, 730, 350, 775)]}, lambda *_: None)
            with self.pdf_ops.page_text(redacted, 0) as text_page:
                extracted = text_page.get_text_bounded()
            self.assertNotIn("CONFIDENCIAL", extracted)
            self.assertNotIn("12345678Z", extracted)
            meta = PdfReader(str(redacted)).metadata or {}
            self.assertNotEqual(meta.get("/Author"), "Autor Secreto")
            self.assertNotEqual(meta.get("/Title"), "Titulo Privado")

    def test_compress_copy_reduces_image_pdf_size(self):
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "heavy.pdf"
            img = Image.effect_noise((1400, 1400), 40).convert("RGB")
            c = canvas.Canvas(str(src), pagesize=(595, 842))
            c.drawImage(ImageReader(img), 40, 120, width=500, height=500)
            c.showPage()
            c.save()

            compressed = root / "compressed.pdf"
            before, after, _, _ = self.pdf_ops.compress_copy(src, compressed, quality=65, dpi=150, allow_larger=False)
            self.assertGreater(before, after)
            self.assertTrue(compressed.is_file())

    def test_split_pdf_and_edit_pages_rotations(self):
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "multi.pdf"
            _make_text_pdf(src, ["Hoja 1", "Hoja 2", "Hoja 3", "Hoja 4", "Hoja 5"])

            parts_dir = root / "parts"
            created = self.pdf_ops.split_pdf(src, parts_dir, every=2, stem="dossier")
            self.assertEqual(len(created), 3)
            self.assertEqual([len(PdfReader(str(p)).pages) for p in created], [2, 2, 1])

            reordered = root / "reordered.pdf"
            self.pdf_ops.edit_pages(src, reordered, [4, 0, 2], rotations={0: 90, 2: 180})
            reader = PdfReader(str(reordered))
            self.assertEqual(len(reader.pages), 3)
            self.assertEqual(reader.pages[0].rotation % 360, 90)
            self.assertEqual(reader.pages[2].rotation % 360, 180)

    def test_compress_strips_bloat_and_metadata(self):
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = root / "base.pdf"
            _make_text_pdf(base, ["Texto importante de prueba"])
            bloated = root / "bloated.pdf"
            out = root / "out.pdf"

            writer = PdfWriter(clone_from=PdfReader(str(base)))
            piece_stream = DecodedStreamObject()
            piece_stream.set_data(b"ADOBE_PRIVATE_DATA_" * 4000)
            piece_ref = writer._add_object(piece_stream)
            writer.pages[0][NameObject("/PieceInfo")] = DictionaryObject({NameObject("/Illustrator"): piece_ref})
            meta_stream = DecodedStreamObject()
            meta_stream[NameObject("/Type")] = NameObject("/Metadata")
            meta_stream.set_data(b"<x:xmpmeta>" + (b"X" * 20000) + b"</x:xmpmeta>")
            writer.root_object[NameObject("/Metadata")] = writer._add_object(meta_stream)
            with bloated.open("wb") as handle:
                writer.write(handle)

            before, after, _, _ = self.pdf_ops.compress_copy(bloated, out, quality=None, strip_bloat=True, clean_metadata=True)
            self.assertLess(after, before * 0.4)
            cleaned = PdfReader(str(out))
            self.assertNotIn("/PieceInfo", cleaned.pages[0])
            self.assertNotIn("/Metadata", cleaned.root_object)

    def test_compress_handles_smask_icc_and_grayscale(self):
        from io import BytesIO
        from PIL import Image
        from pypdf import PdfReader, PdfWriter
        from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject, NumberObject

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / "images.pdf"
            out_rgb = root / "out_rgb.pdf"
            out_gray = root / "out_gray.pdf"

            # Create a 600x600 RGBA photo-like image embedded via reportlab (generates RGB + /SMask)
            img = Image.new("RGBA", (600, 600))
            px = img.load()
            for y in range(600):
                for x in range(600):
                    px[x, y] = ((x * 3) % 256, (y * 5) % 256, ((x + y) * 7) % 256, 200 if x > 100 else 255)
            png_buf = BytesIO()
            img.save(png_buf, format="PNG")
            png_buf.seek(0)

            from reportlab.lib.utils import ImageReader
            from reportlab.pdfgen.canvas import Canvas

            canvas = Canvas(str(src), pagesize=(300, 300))
            canvas.drawImage(ImageReader(png_buf), 20, 20, width=144, height=144, mask="auto")
            canvas.save()

            # Also test ICCBased RGB wrapping on the main image XObject
            reader = PdfReader(str(src))
            writer = PdfWriter(clone_from=reader)
            xobjs = writer.pages[0]["/Resources"]["/XObject"].get_object()
            for ref in xobjs.values():
                obj = ref.get_object()
                if obj.get("/Subtype") == "/Image" and obj.get("/ColorSpace") == "/DeviceRGB":
                    icc = DecodedStreamObject()
                    icc[NameObject("/N")] = NumberObject(3)
                    icc.set_data(b"\x00" * 128)
                    obj[NameObject("/ColorSpace")] = ArrayObject([NameObject("/ICCBased"), writer._add_object(icc)])
            with src.open("wb") as handle:
                writer.write(handle)

            before, after_rgb, optimized, resized = self.pdf_ops.compress_copy(src, out_rgb, quality=75, dpi=96, compact=True)
            self.assertLess(after_rgb, before)
            self.assertGreaterEqual(optimized, 1)
            self.assertGreaterEqual(resized, 1)

            _, after_gray, _, _ = self.pdf_ops.compress_copy(src, out_gray, quality=75, dpi=96, compact=True, grayscale=True)
            self.assertLess(after_gray, before)
            gray_reader = PdfReader(str(out_gray))
            gray_xobjs = gray_reader.pages[0]["/Resources"]["/XObject"].get_object()
            image_cs = [ref.get_object().get("/ColorSpace") for ref in gray_xobjs.values() if ref.get_object().get("/Subtype") == "/Image"]
            self.assertIn("/DeviceGray", image_cs)

    def test_add_signature_stamp_png_and_pdf(self):
        from PIL import Image, ImageDraw
        from pypdf import PdfReader

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            base = root / "contract.pdf"
            _make_text_pdf(base, ["Contrato original con texto seleccionable"])
            stamp_jpg = root / "firma.jpg"
            stamp_pdf = root / "firma.pdf"
            out_jpg = root / "signed_jpg.pdf"
            out_pdf = root / "signed_pdf.pdf"

            img = Image.new("RGB", (240, 100), "white")
            draw = ImageDraw.Draw(img)
            draw.line([(20, 70), (120, 20), (210, 65)], fill=(15, 35, 95), width=6)
            img.save(stamp_jpg, format="JPEG")
            _make_text_pdf(stamp_pdf, ["Firma S.L."])

            self.pdf_ops.add_signature_stamp(base, out_jpg, 0, (100, 100, 260, 170), stamp_jpg, remove_white=True)
            self.pdf_ops.add_signature_stamp(base, out_pdf, 0, (100, 100, 260, 170), stamp_pdf, remove_white=True)

            for out in (out_jpg, out_pdf):
                reader = PdfReader(str(out))
                self.assertEqual(len(reader.pages), 1)
                self.assertIn("Contrato original", reader.pages[0].extract_text() or "")
                xobjs = reader.pages[0]["/Resources"].get("/XObject", {})
                self.assertGreater(len(xobjs), 0)

    def test_readonly_form_field_text_is_selectable_and_searchable(self):
        from pypdf import PdfReader
        from reportlab.pdfgen.canvas import Canvas

        with tempfile.TemporaryDirectory() as folder:
            src = Path(folder) / "diploma_form.pdf"
            canvas = Canvas(str(src), pagesize=(595, 842))
            canvas.setFont("Helvetica", 12)
            canvas.drawString(72, 760, "Certificado de asistencia")
            canvas.acroForm.textfield(
                name="nombreAlumno",
                value="Nombre Campo Solo Lectura",
                x=72,
                y=700,
                width=300,
                height=24,
                fontName="Helvetica",
                fontSize=12,
                fieldFlags="readOnly",
            )
            canvas.showPage()
            canvas.save()

            before_bytes = src.read_bytes()
            with self.pdf_ops.page_text(src, 0) as content:
                extracted = content.get_text_range()
            self.assertIn("Certificado de asistencia", extracted)
            self.assertIn("Nombre Campo Solo Lectura", extracted)

            hits = self.pdf_ops.search_document(src, "Solo Lectura", lambda *_: None)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0][0], 0)
            # Original PDF on disk remains untouched and unflattened.
            self.assertEqual(src.read_bytes(), before_bytes)
            self.assertIn("/AcroForm", PdfReader(str(src)).root_object)


if __name__ == "__main__":
    unittest.main()
