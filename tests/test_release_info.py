import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Allow importing release_info even without PySide6 installed in lightweight test environments.
with patch.dict(sys.modules, {"translations": type("M", (), {"tr": staticmethod(lambda s: s)})()}):
    import release_info


class ReleaseInfoTests(unittest.TestCase):
    def test_https_url_accepts_valid_https(self):
        self.assertEqual(
            release_info.https_url("https://example.com/updates.json"),
            "https://example.com/updates.json",
        )

    def test_https_url_rejects_http_credentials_and_whitespace(self):
        for bad in (
            "",
            "http://example.com/updates.json",
            "https://user:pass@example.com/updates.json",
            "https://example.com/has space.json",
            "https://example.com\\back.json",
            "javascript:alert(1)",
        ):
            with self.assertRaises(ValueError, msg=bad):
                release_info.https_url(bad)

    def test_is_newer_version(self):
        self.assertTrue(release_info.is_newer_version("0.10.40", "0.10.39"))
        self.assertTrue(release_info.is_newer_version("1.0.0", "0.10.39"))
        self.assertFalse(release_info.is_newer_version("0.10.39", "0.10.39"))
        self.assertFalse(release_info.is_newer_version("0.10.38", "0.10.39"))
        with self.assertRaises(ValueError):
            release_info.is_newer_version("v0.10.40", "0.10.39")

    def test_parse_release_manifest_with_notes_and_sha256(self):
        sha = "a" * 64
        payload = json.dumps(
            {
                "version": "0.10.40",
                "url": "https://example.com/pdfiu/0.10.40",
                "notes": "  Mejoras de rendimiento y firma.  ",
                "sha256": sha.upper(),
            }
        ).encode("utf-8")
        info = release_info.parse_release_manifest(payload, current_version="0.10.39")
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.10.40")
        self.assertEqual(info.url, "https://example.com/pdfiu/0.10.40")
        self.assertEqual(info.notes, "Mejoras de rendimiento y firma.")
        self.assertEqual(info.sha256, sha)

    def test_parse_release_manifest_returns_none_when_up_to_date(self):
        payload = json.dumps(
            {"version": "0.10.39", "url": "https://example.com/pdfiu/0.10.39"}
        ).encode("utf-8")
        self.assertIsNone(release_info.parse_release_manifest(payload, current_version="0.10.39"))

    def test_parse_release_manifest_ignores_invalid_sha256(self):
        payload = json.dumps(
            {
                "version": "0.10.40",
                "url": "https://example.com/pdfiu/0.10.40",
                "sha256": "not-a-valid-hash",
            }
        ).encode("utf-8")
        info = release_info.parse_release_manifest(payload, current_version="0.10.39")
        self.assertEqual(info.sha256, "")

    def test_parse_release_manifest_rejects_oversized_payload(self):
        with self.assertRaises(ValueError):
            release_info.parse_release_manifest(b"x" * 16385, current_version="0.10.39")

    def test_repo_updates_json_is_valid(self):
        raw = (ROOT / "updates.json").read_bytes()
        manifest = json.loads(raw)
        self.assertTrue(release_info.https_url(manifest["url"]))
        # Must parse without error against an older version.
        info = release_info.parse_release_manifest(raw, current_version="0.0.1")
        self.assertIsNotNone(info)
        self.assertEqual(info.version, release_info.APP_VERSION)

    def test_default_update_channel_is_https(self):
        channel = release_info.update_channel()
        self.assertIsNotNone(channel)
        self.assertTrue(channel.startswith("https://"))


if __name__ == "__main__":
    unittest.main()
