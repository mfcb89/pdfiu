from translations import tr

import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


APP_NAME = "PDFiu"
APP_VERSION = "0.10.38"


def https_url(value):
    if isinstance(value, str) and value and not any(
        char.isspace() or ord(char) < 32 or char == "\\" for char in value
    ):
        url = urlsplit(value)
        if url.scheme == "https" and url.hostname and url.username is None and url.password is None:
            return value
    raise ValueError(tr("El canal de actualizaciones requiere una dirección HTTPS válida."))


def update_channel():
    config = Path(__file__).with_name("update-channel.txt")
    return https_url(config.read_text(encoding="utf-8").strip()) if config.is_file() else None


class HttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def latest_release(channel):
    opener = build_opener(HttpsRedirects())
    request = Request(https_url(channel), headers={"Accept": "application/json"})
    with opener.open(request, timeout=5) as response:
        raw = response.read(16385)
    if len(raw) > 16384:
        raise ValueError(tr("La respuesta del canal de actualizaciones es demasiado grande."))
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError(tr("El canal de actualizaciones no devolvió una versión válida."))
    version = manifest.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]{1,6}(?:\.[0-9]{1,6}){2}", version):
        raise ValueError(tr("El canal de actualizaciones no devolvió una versión válida."))
    url = https_url(manifest.get("url"))
    return (version, url) if tuple(map(int, version.split("."))) > tuple(map(int, APP_VERSION.split("."))) else None
