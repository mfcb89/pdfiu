from translations import tr

from dataclasses import dataclass
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


APP_NAME = "PDFiu"
APP_VERSION = "0.12.0"
STORE_ID = "9NK06R3SRRW3"
STORE_PROTOCOL_URL = f"ms-windows-store://pdp/?productid={STORE_ID}"
STORE_WEB_URL = f"https://apps.microsoft.com/detail/{STORE_ID}"
DEFAULT_UPDATE_CHANNEL = "https://raw.githubusercontent.com/mfcb89/pdfiu/main/updates.json"
_VERSION_RE = re.compile(r"[0-9]{1,6}(?:\.[0-9]{1,6}){2}")
_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


def is_store_package():
    if Path(__file__).with_name("msix-store.flag").is_file():
        return True
    if Path(__file__).resolve().parent.joinpath("msix-store.flag").is_file():
        return True
    return False


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    url: str
    notes: str = ""
    sha256: str = ""


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
    if config.is_file():
        return https_url(config.read_text(encoding="utf-8").strip())
    return https_url(DEFAULT_UPDATE_CHANNEL) if DEFAULT_UPDATE_CHANNEL else None


def is_newer_version(candidate, current=APP_VERSION):
    if not isinstance(candidate, str) or not _VERSION_RE.fullmatch(candidate):
        raise ValueError(tr("El canal de actualizaciones no devolvió una versión válida."))
    if not isinstance(current, str) or not _VERSION_RE.fullmatch(current):
        raise ValueError(tr("El canal de actualizaciones no devolvió una versión válida."))
    return tuple(map(int, candidate.split("."))) > tuple(map(int, current.split(".")))


def parse_release_manifest(raw, current_version=APP_VERSION):
    if len(raw) > 16384:
        raise ValueError(tr("La respuesta del canal de actualizaciones es demasiado grande."))
    manifest = json.loads(raw)
    if not isinstance(manifest, dict):
        raise ValueError(tr("El canal de actualizaciones no devolvió una versión válida."))
    version = manifest.get("version")
    if not is_newer_version(version, current_version):
        return None
    url = https_url(manifest.get("url"))
    raw_notes = manifest.get("notes", "")
    notes = raw_notes.strip()[:2000] if isinstance(raw_notes, str) else ""
    raw_sha = manifest.get("sha256", "")
    sha256 = raw_sha.strip().lower() if isinstance(raw_sha, str) and _SHA256_RE.fullmatch(raw_sha.strip()) else ""
    return ReleaseInfo(version=version, url=url, notes=notes, sha256=sha256)


class HttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        https_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def latest_release(channel, current_version=APP_VERSION):
    opener = build_opener(HttpsRedirects())
    request = Request(
        https_url(channel),
        headers={
            "Accept": "application/json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    with opener.open(request, timeout=5) as response:
        raw = response.read(16385)
    return parse_release_manifest(raw, current_version=current_version)
