import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_logging


class AppLoggingTests(unittest.TestCase):
    def test_setup_logging_creates_log_file_and_records_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_file = app_logging.setup_logging("PDFiu", "0.10.39", directory=tmp)
            self.assertTrue(log_file.is_file())
            # Flush handlers so content is written to disk before reading
            for handler in app_logging.logging.getLogger("pdfiu").handlers[:]:
                handler.flush()
                handler.close()
                app_logging.logging.getLogger("pdfiu").removeHandler(handler)
            text = log_file.read_text(encoding="utf-8")
            self.assertIn("Start PDFiu 0.10.39", text)


if __name__ == "__main__":
    unittest.main()
