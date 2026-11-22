"""Application strings and language selection."""

import json
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QLocale, QTranslator


_language = None
_catalog = {}


def initialize_language(preference):
    global _language, _catalog
    if _language is not None:
        return
    system = "en" if QLocale.system().language() == QLocale.Language.English else "es"
    _language = preference if preference in ("es", "en") else system
    application = QCoreApplication.instance()
    if _language == "en":
        path = Path(__file__).resolve().parent / "assets" / "languages" / "en.json"
        with path.open(encoding="utf-8") as stream:
            _catalog = json.load(stream)
    elif application is not None:
        translator = QTranslator(application)
        directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load("qtbase_es", directory):
            application.installTranslator(translator)


def current_language():
    return _language or "es"


def tr(source):
    return _catalog.get(source, source)
