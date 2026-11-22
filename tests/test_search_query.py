import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

with patch.dict(sys.modules, {"translations": type("M", (), {"tr": staticmethod(lambda s: s)})()}):
    from search_query import SearchQuery, SearchSyntaxError


class SearchQueryTests(unittest.TestCase):
    def _contains(self, text):
        lower = text.lower()
        return lambda pair: pair[0].lower() in lower

    def test_boolean_and_or_not(self):
        q = SearchQuery('(plano OR croquis) AND NOT borrador')
        self.assertIsNotNone(q.matching_terms(self._contains("Este es un plano definitivo")))
        self.assertIsNotNone(q.matching_terms(self._contains("Croquis de obra")))
        self.assertIsNone(q.matching_terms(self._contains("Plano en borrador")))
        self.assertIsNone(q.matching_terms(self._contains("Memoria sin dibujo")))

    def test_implicit_and_and_quoted_phrase(self):
        q = SearchQuery('"health and safety" report')
        terms = q.matching_terms(self._contains("Annual Health and Safety report 2026"))
        self.assertEqual(terms, {("health and safety", True), ("report", False)})
        self.assertIsNone(q.matching_terms(self._contains("Safety and health report")))

    def test_double_negation(self):
        q = SearchQuery("NOT NOT firma")
        self.assertEqual(q.matching_terms(self._contains("Firma digital")), {("firma", False)})
        self.assertIsNone(q.matching_terms(self._contains("Sin rúbrica")))

    def test_syntax_errors(self):
        for bad in (
            "",
            '("sin cerrar)',
            '"frase sin cerrar',
            '""',
            "(plano OR croquis",
            "plano AND",
            "OR plano",
            "plano)",
            " ".join(["a"] * 65),
        ):
            with self.assertRaises(SearchSyntaxError, msg=bad):
                SearchQuery(bad)


if __name__ == "__main__":
    unittest.main()
