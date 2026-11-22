import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_CATALOG = ROOT / "assets" / "languages" / "en.json"


def collect_tr_strings():
    strings = set()
    for path in sorted(ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "tr"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                strings.add(node.args[0].value)
    return strings


class TranslationCatalogTests(unittest.TestCase):
    def test_en_json_is_valid_and_covers_all_tr_calls(self):
        catalog = json.loads(EN_CATALOG.read_text(encoding="utf-8"))
        self.assertIsInstance(catalog, dict)
        missing = sorted(collect_tr_strings() - set(catalog))
        self.assertEqual(missing, [], f"Missing English translations in en.json: {missing}")


if __name__ == "__main__":
    unittest.main()
