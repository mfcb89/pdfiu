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

    def test_page_grid_accepts_drops_and_reorders_items(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QMimeData, QPointF, Qt
        from PySide6.QtGui import QDragEnterEvent, QDropEvent
        from PySide6.QtWidgets import QApplication, QListWidgetItem
        from pdfiu_dialogs import _PageGrid

        app = QApplication.instance() or QApplication([])
        grid = _PageGrid()
        self.assertTrue(grid.acceptDrops())
        self.assertTrue(grid.viewport().acceptDrops())
        for i in range(4):
            item = QListWidgetItem(f"P{i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            grid.addItem(item)
        grid.resize(600, 400)
        grid.show()
        app.processEvents()

        mime = QMimeData()
        mime.setData(_PageGrid.GRID_MIME, b"0")
        enter = QDragEnterEvent(grid.viewport().rect().center(), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        grid.dragEnterEvent(enter)
        self.assertTrue(enter.isAccepted())

        # Drop page 0 at the end (after page 3)
        drop_pos = QPointF(grid.viewport().width() - 5, grid.viewport().height() - 5)
        drop = QDropEvent(drop_pos, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        grid.dropEvent(drop)
        self.assertTrue(drop.isAccepted())
        order = [grid.item(r).data(Qt.ItemDataRole.UserRole) for r in range(grid.count())]
        self.assertEqual(order, [1, 2, 3, 0])
        grid.close()

    def test_compress_dialog_presets_and_advanced_toggle(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from pdfiu_dialogs import CompressDialog

        app = QApplication.instance() or QApplication([])
        dialog = CompressDialog(None)
        try:
            self.assertEqual(dialog.current_settings()["preset"], "recommended")
            self.assertTrue(dialog.advanced_box.isHidden())
            dialog.advanced_toggle.setChecked(True)
            self.assertFalse(dialog.advanced_box.isHidden())
            dialog.grayscale.setChecked(True)
            self.assertEqual(dialog.current_settings()["preset"], "custom")
            self.assertTrue(dialog.current_settings()["grayscale"])
            dialog.apply_preset_index(2)
            self.assertEqual(dialog.current_settings()["preset"], "extreme")
            self.assertTrue(dialog.current_settings()["clean_metadata"])
            self.assertFalse(dialog.current_settings()["grayscale"])
        finally:
            dialog.close()


if __name__ == "__main__":
    unittest.main()
