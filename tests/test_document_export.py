import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HAS_EXPORT_DEPS = all(
    importlib.util.find_spec(m) is not None
    for m in ("pypdf", "pypdfium2", "reportlab", "pdfplumber", "docx", "openpyxl")
)


def _make_sample_pdf(destination):
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(destination), pagesize=(595, 842))
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, 760, "Informe de prueba")
    c.setFont("Helvetica", 11)
    c.drawString(72, 730, "Contenido exportable a TXT, Markdown y Word.")
    c.showPage()
    c.save()


@unittest.skipUnless(HAS_EXPORT_DEPS, "Export dependencies not installed in this environment")
class DocumentExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._patch = patch.dict(sys.modules, {"translations": type("M", (), {"tr": staticmethod(lambda s: s)})()})
        cls._patch.start()
        import document_export
        cls.document_export = document_export

    @classmethod
    def tearDownClass(cls):
        cls._patch.stop()

    def test_export_txt_markdown_and_docx(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "sample.pdf"
            _make_sample_pdf(src)

            txt = root / "out.txt"
            self.document_export.export_document(src, txt, "txt", [0], lambda *_: None)
            self.assertIn("Informe de prueba", txt.read_text(encoding="utf-8"))

            md_text, warnings = self.document_export.markdown_from_pdf(src, "sample", [0], lambda *_: None)
            self.assertIn("Informe de prueba", md_text)
            self.assertEqual(warnings, [])

            docx = root / "out.docx"
            self.document_export.export_document(src, docx, "docx", [0], lambda *_: None)
            self.assertTrue(docx.is_file())
            self.assertGreater(docx.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
