import importlib.util
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HAS_PYSIDE6 = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_PYSIDE6, "PySide6 not installed in this environment")
class UiSmokeTests(unittest.TestCase):
    def test_main_window_initializes_themes_and_command_palette(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        import pdfiu

        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        window = pdfiu.PDFiu(show_startup=False)
        try:
            self.assertEqual(pdfiu.apply_theme(app, "dark"), "dark")
            self.assertEqual(pdfiu.apply_theme(app, "light"), "light")
            commands = window.collect_palette_commands()
            self.assertGreater(len(commands), 10)
            window.filter_bookmarks("test")
            window.filter_bookmarks("")
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
