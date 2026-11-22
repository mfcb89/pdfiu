import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HAS_PDF_DEPS = all(importlib.util.find_spec(m) is not None for m in ("pypdf", "pypdfium2", "reportlab", "PIL"))


@dataclass
class DummyDoc:
    path: Path
    name: str
    dirty: bool = False
    page: int = 0
    saved_path: Path | None = None
    protected_source: Path | None = None
    redactions: dict = field(default_factory=dict)


@unittest.skipUnless(HAS_PDF_DEPS, "PDF dependencies not installed in this environment")
class SessionRecoveryTests(unittest.TestCase):
    def test_write_recover_and_retain(self):
        from session_recovery import RecoveryJournal, interrupted_sessions, retain_unrecovered

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session_dir = root / "pdfiu-test"
            session_dir.mkdir()
            pdf = session_dir / "trabajo.pdf"
            pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

            journal = RecoveryJournal(session_dir)
            # Clean docs produce no recovery.json
            journal.write([DummyDoc(path=pdf, name="trabajo.pdf", dirty=False)])
            self.assertFalse((session_dir / "recovery.json").exists())

            # Dirty doc creates recovery.json
            journal.write([DummyDoc(path=pdf, name="trabajo.pdf", dirty=True, page=2)])
            manifest = session_dir / "recovery.json"
            self.assertTrue(manifest.is_file())

            # Simulate dead PID so interrupted_sessions picks it up
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["pid"] = 99999999
            manifest.write_text(json.dumps(data), encoding="utf-8")

            found = list(interrupted_sessions(root))
            self.assertEqual(len(found), 1)
            found_manifest, records = found[0]
            self.assertEqual(found_manifest, manifest)
            self.assertEqual(records[0]["name"], "trabajo.pdf")
            self.assertEqual(records[0]["page"], 2)

            # Retaining empty list deletes the manifest
            retain_unrecovered(manifest, [])
            self.assertFalse(manifest.exists())


if __name__ == "__main__":
    unittest.main()
