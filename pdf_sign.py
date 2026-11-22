from translations import tr

import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory, TemporaryFile
from uuid import uuid4

from asn1crypto import x509
from pyhanko.pdf_utils.content import ResourceType
from pyhanko.pdf_utils.generic import ArrayObject, DictionaryObject, NumberObject, TextStringObject, pdf_name
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.misc import PdfStrictReadError
from pyhanko.pdf_utils.layout import BoxConstraints
from pyhanko.pdf_utils.metadata.model import VENDOR
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.sign import fields, signers
from pyhanko.stamp import TextStamp, TextStampStyle
from pyhanko_certvalidator.registry import SimpleCertificateStore

from pypdf import PdfWriter
from pypdf.errors import PdfReadError
from pdf_ops import atomic_output, has_signed_fields, reader_for, validate_signature_box


_IDENTIFIERS = (
    ("DNI/NIE", re.compile(r"(?<![A-Z0-9])(?:[XYZ]\d{7}[A-Z]|\d{8}[A-Z])(?![A-Z0-9])", re.I)),
    ("NIF", re.compile(r"(?<![A-Z0-9])[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J](?![A-Z0-9])", re.I)),
)


def _text(value):
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value if item)
    return str(value).strip() if value else ""


def _date_text(value):
    if value is None:
        return tr("No consta")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone().strftime("%d/%m/%Y %H:%M %Z")


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def certificate_details(der):
    certificate = x509.Certificate.load(der)
    subject = certificate.subject.native or {}
    issuer = certificate.issuer.native or {}
    given_name = _text(subject.get("given_name"))
    surname = _text(subject.get("surname"))
    common_name = _text(subject.get("common_name"))
    organization = _text(subject.get("organization_name"))
    organization_identifier = _text(subject.get("organization_identifier"))
    unit = _text(subject.get("organizational_unit_name"))
    title = _text(subject.get("title"))
    subject_serial = _text(subject.get("serial_number"))

    identifier = None
    identifier_label = None
    for label, pattern in _IDENTIFIERS:
        match = pattern.search(subject_serial.upper())
        if match:
            identifier = match.group(0)
            identifier_label = tr("{0} indicado en el certificado").format(label)
            break
    if not identifier and subject_serial:
        identifier = subject_serial
        identifier_label = tr("Identificador del sujeto (serialNumber)")

    not_before = certificate["tbs_certificate"]["validity"]["not_before"].native
    not_after = certificate["tbs_certificate"]["validity"]["not_after"].native
    now = datetime.now(timezone.utc)
    if not_before.tzinfo is None:
        not_before = not_before.replace(tzinfo=timezone.utc)
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=timezone.utc)
    issuer_name = _text(issuer.get("common_name")) or _text(issuer.get("organization_name")) or tr("No consta")

    return {
        "name": common_name or " ".join(part for part in (given_name, surname) if part) or organization or tr("Titular no identificado"),
        "given_name": given_name,
        "surname": surname,
        "organization": organization,
        "organization_identifier": organization_identifier,
        "unit": unit,
        "title": title,
        "identifier": identifier,
        "identifier_label": identifier_label,
        "issuer": issuer_name,
        "not_before": _date_text(not_before),
        "not_after": _date_text(not_after),
        "valid_now": not_before <= now <= not_after,
        "key_algorithm": certificate.public_key.algorithm.upper(),
        "certificate_serial": format(certificate.serial_number, "X"),
    }


def inspect_pdf_signatures(path, *, password=None):
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    with open(path, "rb") as stream:
        reader = PdfFileReader(stream, strict=False)
        if reader.security_handler is not None:
            reader.decrypt(password or "")
        trust_context = ValidationContext(allow_fetching=False)
        signatures = []
        coverage_labels = {
            "ENTIRE_FILE": tr("La firma cubre el archivo completo."),
            "ENTIRE_REVISION": tr("La firma cubre la revisión que se firmó; el PDF puede tener cambios posteriores."),
            "CONTIGUOUS_BLOCK_FROM_START": tr("La firma cubre una revisión parcial del PDF."),
            "UNCLEAR": tr("No se pudo determinar la cobertura de la firma."),
        }
        for embedded in reader.embedded_signatures:
            try:
                details = certificate_details(embedded.signer_cert.dump())
            except Exception:
                details = {
                    "name": tr("Certificado no disponible"),
                    "organization": "",
                    "unit": "",
                    "title": "",
                    "identifier": None,
                    "identifier_label": None,
                    "issuer": tr("No consta"),
                    "not_before": tr("No consta"),
                    "not_after": tr("No consta"),
                    "valid_now": None,
                    "key_algorithm": tr("No consta"),
                }
            try:
                coverage = embedded.evaluate_signature_coverage()
                coverage_name = getattr(coverage, "name", str(coverage))
            except Exception:
                coverage_name = "UNCLEAR"
            try:
                signed_at = embedded.self_reported_timestamp
            except Exception:
                signed_at = None
            details.update({
                "field_name": embedded.field_name,
                "signed_at": _date_text(signed_at),
                "signed_at_value": signed_at,
                "coverage": coverage_labels.get(coverage_name, tr("Cobertura no determinada.")),
                "coverage_name": coverage_name,
            })
            try:
                verification = validate_pdf_signature(embedded, signer_validation_context=trust_context)
                details["integrity"] = verification.intact and verification.valid
                details["trusted"] = bool(verification.trusted) if details["integrity"] else None
            except Exception:
                details["integrity"] = details["trusted"] = None
            if signed_at is not None and signed_at.tzinfo is None:
                signed_at = signed_at.replace(tzinfo=timezone.utc)
            if signed_at is not None and details.get("valid_now") is not None:
                certificate = embedded.signer_cert
                not_before = _as_utc(certificate["tbs_certificate"]["validity"]["not_before"].native)
                not_after = _as_utc(certificate["tbs_certificate"]["validity"]["not_after"].native)
                details["valid_at_reported_time"] = (
                    not_before <= _as_utc(signed_at) <= not_after
                )
            else:
                details["valid_at_reported_time"] = None
            signatures.append(details)
        return signatures


def windows_cert(operation, **parameters):
    source = Path(__file__).with_name("windows_cert.ps1").read_text(encoding="utf-8")
    encoded = base64.b64encode(source.encode("utf-16-le")).decode("ascii")
    shell = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    try:
        result = subprocess.run(
            [str(shell), "-NoLogo", "-NoProfile", "-EncodedCommand", encoded],
            input=json.dumps({"operation": operation, **parameters}),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=180 if operation == "sign" else 20,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(tr("Windows tardó demasiado en responder al consultar o usar el certificado.")) from error
    if result.returncode:
        if operation == "list":
            raise ValueError(tr("No se pudieron consultar los almacenes personales de Windows."))
        raise ValueError(tr("Windows no pudo acceder al certificado o completar la firma. Comprueba la clave, el PIN y el proveedor del certificado."))
    return json.loads(result.stdout)


class WindowsSigner(signers.Signer):
    def __init__(self, identity):
        self.thumbprint = identity["thumbprint"]
        self.location = identity.get("location", "CurrentUser")
        certificate = x509.Certificate.load(base64.b64decode(identity["der"]))
        registry = SimpleCertificateStore()
        for item in windows_cert("chain", thumbprint=self.thumbprint, location=self.location):
            registry.register(x509.Certificate.load(base64.b64decode(item)))
        super().__init__(signing_cert=certificate, cert_registry=registry, embed_roots=False)

    async def async_sign_raw(self, data, digest_algorithm, dry_run=False):
        if digest_algorithm != "sha256":
            raise ValueError(tr("La firma de Windows usa SHA-256."))
        if dry_run:
            key = self.signing_cert.public_key["public_key"].parsed
            return bytes((key["modulus"].native.bit_length() + 7) // 8)
        signature = await asyncio.to_thread(
            windows_cert, "sign", thumbprint=self.thumbprint, location=self.location,
            data=base64.b64encode(data).decode("ascii")
        )
        return base64.b64decode(signature)


@dataclass(frozen=True)
class SignatureStyle(TextStampStyle):
    page_rotation: int = 0
    archival: bool = False

    def create_stamp(self, writer, box, text_params):
        return SignatureStamp(writer, self, text_params, box)


class SignatureStamp(TextStamp):
    def __init__(self, writer, style, text_params, box):
        if style.page_rotation in (90, 270):
            box = BoxConstraints(width=box.height, height=box.width)
        super().__init__(writer, style, text_params=text_params, box=box)

    def _render_inner_content(self):
        if not self.style.archival:
            return super()._render_inner_content()
        from reportlab.pdfbase.pdfmetrics import getRegisteredFontNames, registerFont, stringWidth
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen.canvas import Canvas

        font = "PDFiuVera"
        if font not in getRegisteredFontNames():
            path = Path(__file__).resolve().parent / "assets" / "fonts" / "Vera.ttf"
            registerFont(TTFont(font, str(path)))
        parameters = self.get_default_text_params()
        parameters.update(self.text_params or {})
        lines = (self.style.stamp_text % parameters).splitlines()
        width, height = self.box.width, self.box.height
        content_width = max(stringWidth(line, font, 1) for line in lines)
        size = min(10.0, (width - 6) / max(content_width, 1), (height - 4) / (len(lines) * 1.22))
        stream = BytesIO()
        canvas = Canvas(stream, pagesize=(width, height), initialFontName=font, initialFontSize=size)
        canvas.setFillGray(0.18)
        canvas.setFont(font, size)
        for index, line in enumerate(lines):
            canvas.drawCentredString(width / 2, height / 2 + (len(lines) / 2 - index - .75) * size * 1.22, line)
        canvas.save()
        stream.seek(0)
        content = self.writer.import_page_as_xobject(PdfFileReader(stream))
        self.set_resource(ResourceType.XOBJECT, pdf_name("/PDFiuText"), content)
        return [b"/PDFiuText Do"]

    def as_form_xobject(self):
        form = super().as_form_xobject()
        width, height = self.box.width, self.box.height
        rotations = {
            90: (0, 1, -1, 0, height, 0),
            180: (-1, 0, 0, -1, width, height),
            270: (0, -1, 1, 0, 0, width),
        }
        if self.style.page_rotation in rotations:
            matrix = rotations[self.style.page_rotation]
            form[pdf_name("/Matrix")] = ArrayObject(NumberObject(value) for value in matrix)
        return form


def load_signer(identity=None, pfx=None, password=None):
    if identity is not None:
        return WindowsSigner(identity)
    signer = signers.SimpleSigner.load_pkcs12(str(pfx), passphrase=password.encode("utf-8") if password else None)
    if signer is None:
        raise ValueError(tr("No se pudo abrir el certificado. Comprueba el archivo y la contraseña."))
    signer.embed_roots = False
    return signer


def sign_document(source, destination, page, box, **credentials):
    return sign_with(source, destination, page, box, load_signer(**credentials))


def sign_document_pages(source, destination, positions, progress, **credentials):
    sign_pages(source, destination, positions, load_signer(**credentials), progress)


def sign_pages(source, destination, positions, signer, progress):
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError(tr("Guarda la firma en un PDF distinto del original."))
    if not positions:
        raise ValueError(tr("Elige al menos una página para firmar."))
    reader = reader_for(source)
    for page, box in positions.items():
        try:
            validate_signature_box(reader.pages[page], box)
        except (IndexError, ValueError) as error:
            raise ValueError(tr("Página {0}: {1}").format(page + 1, error)) from error
    if len(positions) == 1:
        page, box = next(iter(positions.items()))
        progress(1, 1)
        sign_with(source, destination, page, box, signer)
        return
    with TemporaryDirectory(prefix=".pdfiu-paginas-", dir=destination.parent) as staging:
        current = source
        staging = Path(staging)
        for step, (page, box) in enumerate(positions.items(), 1):
            progress(step, len(positions))
            pending = staging / f"{step % 2}.pdf"
            try:
                sign_with(current, pending, page, box, signer)
            except Exception as error:
                raise ValueError(tr("Página {0}: {1}").format(page + 1, error)) from error
            current = pending
        current.replace(destination)


def sign_with(source, destination, page, box, signer):
    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError(tr("Guarda la firma en un PDF distinto del original."))
    reader = reader_for(source)
    target = reader.pages[page]
    validate_signature_box(target, box)

    name = "Firma_" + uuid4().hex
    try:
        xmp = reader.xmp_metadata
        archival = bool(xmp and xmp.pdfaid_part)
    except (PdfReadError, ValueError, KeyError):
        archival = False
    appearance = SignatureStyle(
        page_rotation=target.rotation % 360,
        archival=archival,
        border_width=1,
        border_color=None if archival else (0.13, 0.34, 0.32),
        background=None,
        text_box_style=TextBoxStyle(font_size=10, text_color=(0.13, 0.27, 0.28)),
        stamp_text=tr("Firmado digitalmente\n%(signer)s\n%(ts)s"),
        timestamp_format="%d/%m/%Y %H:%M:%S %z",
    )
    field = fields.SigFieldSpec(sig_field_name=name, on_page=page, box=box)
    metadata = signers.PdfSignatureMetadata(field_name=name, md_algorithm="sha256", subfilter=fields.SigSeedSubFilter.PADES)
    pdf_signer = signers.PdfSigner(metadata, signer, stamp_style=appearance, new_field_spec=field)
    with atomic_output(destination) as temporary:
        with open(source, "rb") as src, temporary.open("wb") as output, TemporaryFile() as repaired:
            try:
                writer = IncrementalPdfFileWriter(src)
            except PdfStrictReadError as error:
                if "free xref with next generation 0" not in str(error):
                    raise
                if has_signed_fields(reader.get_fields() or {}):
                    raise ValueError(tr("La tabla de referencias de este PDF firmado necesita reparación. Usa el original sin firmar.")) from error
                PdfWriter(clone_from=reader).write(repaired)
                repaired.seek(0)
                writer = IncrementalPdfFileWriter(repaired)
            if archival and "/Info" in writer.trailer:
                info = DictionaryObject(dict(writer.trailer["/Info"]))
                # pyHanko writes its own producer to XMP. Keep both representations equivalent.
                info[pdf_name("/Producer")] = TextStringObject(VENDOR)
                writer.set_info(info)
            pdf_signer.sign_pdf(writer, output=output)
        with temporary.open("rb") as stream:
            signatures = PdfFileReader(stream).embedded_signatures
            if not any(signature.field_name == name for signature in signatures):
                raise ValueError(tr("La firma no apareció en el PDF de salida."))


def sign_batch(placements, directory, progress, *, names=None, **credentials):
    directory = Path(directory)
    signer = load_signer(**credentials)
    documents = {}
    for source, page, box in placements:
        documents.setdefault(Path(source), {})[page] = box
    total = sum(len(positions) for positions in documents.values())
    completed = 0
    reserved = {entry.name.casefold() for entry in directory.iterdir()}
    with TemporaryDirectory(prefix=".pdfiu-firmas-", dir=directory) as staging:
        prepared = []
        for source, positions in documents.items():
            display_name = (names or {}).get(str(source), source.name)
            stem = tr("{0} - firmado").format(Path(display_name).stem)
            name = f"{stem}.pdf"
            serial = 2
            while name.casefold() in reserved:
                name = f"{stem} ({serial}).pdf"
                serial += 1
            reserved.add(name.casefold())
            signed = Path(staging) / name
            try:
                sign_pages(source, signed, positions, signer, lambda step, _: progress(completed + step, total))
            except Exception as error:
                raise ValueError(f"{display_name}: {error}") from error
            prepared.append((signed, directory / name))
            completed += len(positions)

        published = []
        try:
            for signed, destination in prepared:
                signed.rename(destination)
                published.append(destination)
        except OSError as error:
            raise ValueError(tr("Se guardaron {0} archivos antes de un error al guardar en la carpeta elegida: {1}").format(len(published), error)) from error
    return published
