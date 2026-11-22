"""Export and independently validate a local PDF/A copy."""

from pathlib import Path
from shutil import copyfile, which
from subprocess import PIPE, Popen, TimeoutExpired
from tempfile import TemporaryDirectory
from xml.etree import ElementTree
import os
import subprocess
import sys

from PIL import ImageCms

from pdf_ops import atomic_output, reader_for, unlock_pdf
from translations import tr


PROFILES = ("1b", "2b", "3b")
OUTPUT_INTENT = """%!
/ICCProfile (pdfiu-srgb.icc) def
[/_objdef {icc_PDFiu} /type /stream /OBJ pdfmark
[{icc_PDFiu} << /N 3 >> /PUT pdfmark
[{icc_PDFiu} ICCProfile (r) file /PUT pdfmark
[/_objdef {intent_PDFiu} /type /dict /OBJ pdfmark
[{intent_PDFiu} << /Type /OutputIntent /S /GTS_PDFA1
 /DestOutputProfile {icc_PDFiu} /OutputConditionIdentifier (sRGB)
 /Info (sRGB) >> /PUT pdfmark
[{Catalog} << /OutputIntents [{intent_PDFiu}] >> /PUT pdfmark
"""


def archive_tools():
    ghostscript = which("gswin64c" if sys.platform == "win32" else "gs")
    java_home = os.environ.get("JAVA_HOME")
    java = which(str(Path(java_home) / "bin" / "java")) if java_home else None
    java = java or which("java")
    launcher = which("verapdf")
    roots = [Path(path) / "veraPDF" for var in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
             if (path := os.environ.get(var))]
    roots.extend((Path.home() / "veraPDF", Path.home() / "Applications" / "veraPDF"))
    if launcher:
        roots.insert(0, Path(launcher).parent)
    jars = (candidate for root in roots for folder in (root, root / "bin")
            for candidate in sorted(folder.glob("greenfield-apps-*.jar"), reverse=True))
    return ghostscript, java, next(jars, None)


def run_tool(args, cwd, heartbeat, *, valid_codes=(0,)):
    with Popen(list(map(str, args)), cwd=cwd, stdout=PIPE, stderr=PIPE,
               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) as process:
        try:
            while True:
                heartbeat()
                try:
                    output, errors = process.communicate(timeout=.3)
                    break
                except TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.communicate()
            raise
        if process.returncode not in valid_codes:
            detail = (errors or output).decode("utf-8", errors="replace").strip()
            raise ValueError(tr("La herramienta {0} devolvió un error.").format(Path(args[0]).name)
                             + ("\n" + detail[-1500:] if detail else ""))
        return output


def validate_archive(source, profile, java, validator, heartbeat):
    output = run_tool((java, "-jar", validator, "--format", "xml", "--flavour", profile, source),
                      source.parent, heartbeat, valid_codes=(0, 1))
    try:
        report = ElementTree.fromstring(output).find("./jobs/job/validationReport")
    except ElementTree.ParseError:
        report = None
    if report is None:
        raise ValueError(tr("veraPDF no devolvió un informe de validación válido."))
    if report.get("isCompliant") != "true":
        rules = [rule.findtext("description") for rule in report.findall("./details/rule")[:3]]
        raise ValueError(tr("La copia no cumple PDF/A-{0}.").format(profile) +
                         "".join("\n• " + rule for rule in rules if rule))


def export_archive(source, destination, profile, ghostscript, java, validator, progress, *, password=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if profile not in PROFILES or source == destination:
        raise ValueError(tr("Elige un perfil PDF/A y un archivo de salida distinto."))
    reader = reader_for(source, allow_empty_password=True, password=password)
    with TemporaryDirectory(prefix=".pdfiu-pdfa-") as folder:
        work = Path(folder)
        if reader.is_encrypted:
            original = source
            source = work / "input.pdf"
            unlock_pdf(original, source, password or "", remove_signatures=True)
        profile_path = work / "pdfiu-srgb.icc"
        profile_candidates = (
            Path(os.environ.get("SystemRoot", "/")) / "System32/spool/drivers/color/sRGB Color Space Profile.icm",
            Path("/System/Library/ColorSync/Profiles/sRGB Profile.icc"),
            Path("/usr/share/color/icc/ghostscript/srgb.icc"),
        )
        system_profile = next((path for path in profile_candidates if path.is_file()), None)
        if system_profile:
            copyfile(system_profile, profile_path)
        else:
            profile_path.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
        definition = work / "output-intent.ps"
        definition.write_text(OUTPUT_INTENT, encoding="ascii")
        staged = work / "archive.pdf"
        run_tool((ghostscript, "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite",
                  "-sColorConversionStrategy=RGB", f"-dPDFA={profile[0]}", "-dPDFACompatibilityPolicy=2",
                  "--permit-file-read=pdfiu-srgb.icc", f"-sOutputFile={staged}", definition, source),
                 work, lambda: progress(1, 2))
        result = reader_for(staged)
        if result.is_encrypted or len(result.pages) != len(reader.pages):
            raise ValueError(tr("La copia PDF/A no conserva todas las páginas."))
        validate_archive(staged, profile, java, validator, lambda: progress(2, 2))
        progress(2, 2)
        with atomic_output(destination) as temporary:
            copyfile(staged, temporary)
