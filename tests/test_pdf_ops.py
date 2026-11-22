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


if __name__ == "__main__":
    unittest.main()
