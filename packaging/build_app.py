"""Freeze PDFiu on the target operating system. See LEEME.md."""

import argparse
import os
import platform
import shlex
import subprocess
import sys
import sysconfig
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from release_info import APP_NAME, APP_VERSION, https_url
from collect_notices import collect_notices, write_windows_binary_inventory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tessdata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle-id", default="local.pdfiu.desktop")
    parser.add_argument("--arch", choices=("x86_64", "arm64", "universal2"))
    parser.add_argument("--updates-url", help="Dirección HTTPS del canal de versiones de PDFiu.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if sys.platform not in ("win32", "darwin"):
        parser.error("Compila en Windows o macOS según el destino.")
    if not all((args.tessdata / f"{language}.traineddata").is_file() for language in ("spa", "eng")):
        parser.error("La carpeta de OCR debe incluir spa.traineddata y eng.traineddata.")
    if args.arch and sys.platform != "darwin":
        parser.error("En Windows, usa un Python de la arquitectura que quieras empaquetar.")
    if sys.platform == "win32" and sysconfig.get_platform() != "win-amd64":
        parser.error("La receta de Windows requiere Python x64.")
    if args.updates_url:
        try:
            https_url(args.updates_url)
        except ValueError as error:
            parser.error(str(error))

    output = args.output.resolve()
    notices = output / "third-party"
    icon_format = "ico" if sys.platform == "win32" else "icns"
    command = [
        sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--name", APP_NAME,
        "--icon", str(ROOT / "assets" / "brand" / f"pdfiu-app.{icon_format}"),
        "--exclude-module", "numpy",
        "--exclude-module", "pyphen",
        "--exclude-module", "PIL.AvifImagePlugin",
        "--distpath", str(output / "dist"), "--workpath", str(output / "build"),
        "--specpath", str(output / "spec"),
    ]
    for package in ("pypdfium2", "pypdfium2_raw", "pypdfium2_cfg", "tesserocr"):
        command.extend(("--collect-all", package))
    for package in ("python-docx", "openpyxl", "et-xmlfile", "pdfplumber", "pdfminer.six"):
        command.extend(("--copy-metadata", package))
    for source, destination in (
        (ROOT / "assets", "assets"),
        (ROOT / "LEEME.md", "."),
        (ROOT / "USER_GUIDE.en.md", "."),
        (ROOT / "LICENSE", "."),
        (ROOT / "THIRD_PARTY_NOTICES.md", "."),
        (notices, "third-party"),
        (args.tessdata / "spa.traineddata", "runtime/tessdata"),
        (args.tessdata / "eng.traineddata", "runtime/tessdata"),
    ):
        command.extend(("--add-data", f"{source.resolve()}:{destination}"))
    if sys.platform == "win32":
        command.extend(("--add-data", f"{ROOT / 'windows_cert.ps1'}:."))
    else:
        command.extend(("--osx-bundle-identifier", args.bundle_id))
        command.extend(("--target-arch", args.arch or platform.machine()))
    if args.updates_url:
        channel = output / "update-channel.txt"
        command.extend(("--add-data", f"{channel}:."))
    command.append(str(ROOT / "pdfiu.py"))
    if args.dry_run:
        for part in command:
            print(shlex.quote(part))
        return
    (output / "spec").mkdir(parents=True, exist_ok=True)
    collect_notices(ROOT, notices, args.tessdata)
    if args.updates_url:
        channel.write_text(args.updates_url + "\n", encoding="utf-8")
    build_env = {**os.environ, "PYTHONNOUSERSITE": "1"}
    if sys.platform == "win32":
        # Do not resolve DLL dependencies from unrelated applications on the host PATH.
        windows = Path(os.environ["SystemRoot"])
        build_env["PATH"] = os.pathsep.join(map(str, (
            windows / "System32", windows, Path(sys.base_prefix), Path(sys.executable).parent,
        )))
    subprocess.run(command, check=True, cwd=ROOT, env=build_env)
    if sys.platform == "win32":
        # The application supplies its own English text and only loads qtbase_es.
        translations = output / "dist" / APP_NAME / "_internal" / "PySide6" / "translations"
        for catalog in translations.glob("*.qm"):
            if catalog.name != "qtbase_es.qm":
                catalog.unlink()
        compiler = windows / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe"
        for source, executable in (("ExplorerCombine.cs", "PDFiuExplorer.exe"), ("ClosePDFiu.cs", "PDFiuClose.exe")):
            binary = output / "dist" / APP_NAME / executable
            subprocess.run([
                str(compiler), "/nologo", "/target:winexe", "/platform:x64", "/optimize+",
                "/reference:System.Windows.Forms.dll", f"/out:{binary}",
                str(Path(__file__).with_name(source)),
            ], check=True, cwd=ROOT, env=build_env)
        write_windows_binary_inventory(output / "dist" / APP_NAME)
        (output / "release.iss").write_text(
            f'#define ProductName "{APP_NAME}"\n#define ReleaseVersion "{APP_VERSION}"\n', encoding="utf-8"
        )


if __name__ == "__main__":
    main()
