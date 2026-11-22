"""Collect third-party notices from the environment used to freeze PDFiu."""

from importlib import metadata
from pathlib import Path
from shutil import copy2
import hashlib
import sys


SUPPLEMENTAL_PACKAGES = (
    "altgraph", "Brotli", "fonttools", "packaging", "PyInstaller",
    "python-dateutil", "setuptools", "six", "zopfli",
)


def write_windows_binary_inventory(bundle):
    """Record the native binaries actually copied into the installer."""
    notices = bundle / "_internal" / "third-party"
    with (notices / "binarios-windows.sha256").open("w", encoding="utf-8", newline="\n") as inventory:
        for path in sorted(bundle.rglob("*")):
            if path.suffix.lower() not in (".dll", ".pyd", ".exe") or not path.is_file():
                continue
            with path.open("rb") as binary:
                digest = hashlib.file_digest(binary, "sha256").hexdigest()
            inventory.write(f"{digest}  {path.relative_to(bundle).as_posix()}\n")


def collect_notices(root, destination, tessdata):
    destination.mkdir(parents=True, exist_ok=True)
    direct = (line.partition("==")[0] for line in (root / "requirements.txt").read_text().splitlines()
              if line and not line.startswith("#"))
    packages = set(direct) | set(SUPPLEMENTAL_PACKAGES)
    pending = list(packages)
    inventory = []
    visited = set()
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    while pending:
        name = pending.pop()
        key = canonicalize_name(name)
        if key in visited:
            continue
        visited.add(key)
        try:
            dist = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            continue
        for entry in dist.requires or ():
            requirement = Requirement(entry)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
        notices = []
        for file in dist.files or ():
            if ".." in file.parts or not file.parts:
                continue
            is_notice = file.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "AUTHORS", "COPYRIGHT"))
            in_license_tree = any(part.lower() in ("licenses", "build_licenses", ".wheel-licenses") for part in file.parts)
            if not (is_notice or in_license_tree):
                continue
            source = Path(dist.locate_file(file))
            if source.is_file():
                target = destination / (key + "-" + dist.version) / file
                target.parent.mkdir(parents=True, exist_ok=True)
                copy2(source, target)
                notices.append(file)
        value = dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See upstream"
        status = "NOTICE FILES COPIED" if notices else "REVIEW: no license files found"
        inventory.append(f"{dist.metadata['Name']} {dist.version} | {value.splitlines()[0]} | {status}")

    for source in sorted((root / "packaging" / "licencias-externas").glob("*.txt")):
        copy2(source, destination / source.name)
    for name in ("LICENSE.txt", "LICENSE"):
        python_license = Path(sys.base_prefix) / name
        if python_license.is_file():
            copy2(python_license, destination / "CPython-LICENSE.txt")
            break
    model_lines = []
    for name in ("spa.traineddata", "eng.traineddata"):
        with (tessdata / name).open("rb") as stream:
            model_lines.append(f"{name} | SHA-256 {hashlib.file_digest(stream, 'sha256').hexdigest()}")
    (destination / "inventario.txt").write_text(
        "Entorno de compilación: dependencias de la app y paquetes auxiliares.\n"
        "Los avisos se copian de los metadatos instalados. Este inventario puede incluir paquetes "
        "que no acaban en el binario y requiere contraste con los archivos distribuidos.\n\n"
        + "\n".join(sorted(inventory, key=str.casefold)) + "\n\nModelos OCR\n"
        + "\n".join(model_lines) + "\n",
        encoding="utf-8",
    )
