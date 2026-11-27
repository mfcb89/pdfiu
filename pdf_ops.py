from translations import tr
from search_query import SearchQuery

from contextlib import contextmanager
from ctypes import byref, cast, c_double, c_void_p
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from math import ceil, floor, hypot, sqrt
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
import os
import re
import unicodedata
from zlib import compress as deflate, decompressobj, error as ZlibError

import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter, Transformation, apply_configuration
from pypdf.annotations import Ellipse, Highlight, Line, Polygon, Rectangle, Text
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, ContentStream, DecodedStreamObject, DictionaryObject, FloatObject, NameObject, NumberObject, RectangleObject, StreamObject, TextStringObject
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader


@contextmanager
def atomic_output(destination):
    destination = Path(destination)
    with NamedTemporaryFile(dir=destination.parent, prefix=".pdfiu-", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        yield temporary
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def pdfium_reader(path, *, password=None):
    document = pdfium.PdfDocument(str(path), password=password or None)
    try:
        document.init_forms()
        yield document
    finally:
        document.close()


class ProtectedPdf(ValueError):
    pass


class SignedPdf(ValueError):
    pass


class OperationCancelled(Exception):
    pass


def reader_for(path, *, allow_empty_password=False, password=None):
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        if password is not None:
            if not reader.decrypt(password):
                raise ProtectedPdf(tr("La contraseña de apertura no es correcta."))
        elif not (allow_empty_password and reader.decrypt("")):
            raise ProtectedPdf(tr("Este PDF está protegido. Usa Proteger → Desbloquear PDF para crear una copia editable."))
    if not reader.pages:
        raise ValueError(tr("El documento no contiene páginas."))
    return reader


def check_editable(reader):
    if pdf_has_signatures(reader):
        raise ValueError(tr("El PDF contiene una firma digital. Para editar o unir páginas, usa el original sin firmar."))


def has_signed_fields(fields):
    return any(field.get("/FT") == "/Sig" and field.get("/V") for field in fields.values())


def signature_value(value):
    value = value.get_object() if value is not None else None
    return isinstance(value, DictionaryObject) and "/ByteRange" in value and "/Contents" in value


def pdf_has_signatures(reader):
    if has_signed_fields(reader.get_fields() or {}):
        return True
    permissions = reader.root_object.get("/Perms")
    return permissions is not None and any(signature_value(value) for value in permissions.get_object().values())


def clear_signature_fields(reader):
    """Clear signed values before cloning so the signed byte ranges are not copied."""
    root = reader.root_object
    form = root.get("/AcroForm")
    seen = set()

    def clear(ref, signature_field=False):
        field = ref.get_object()
        if id(field) in seen:
            return
        seen.add(id(field))
        signature_field = field.get("/FT", "/Sig" if signature_field else None) == "/Sig"
        if signature_field:
            for key in ("/V", "/DV", "/AP", "/AS"):
                field.pop(key, None)
        for child in field.get("/Kids", ()):
            clear(child, signature_field)

    if form is not None:
        form = form.get_object()
        form.pop("/SigFlags", None)
        for field in form.get("/Fields", ()):
            clear(field)
    for page in reader.pages:
        for ref in page.get("/Annots", ()):
            widget = ref.get_object()
            if widget.get("/Subtype") == "/Widget" and widget.get("/FT") == "/Sig":
                clear(ref)
    root.pop("/Perms", None)
    root.pop("/DSS", None)


def unlock_pdf(source, destination, password="", *, skip_unprotected=False, remove_signatures=False):
    if Path(source).resolve() == Path(destination).resolve():
        raise ValueError(tr("Elige otro nombre para conservar el PDF original."))
    reader = PdfReader(str(source))
    if reader.is_encrypted and not reader.decrypt(password):
        raise ProtectedPdf(tr("La contraseña de apertura no es correcta."))
    signed = pdf_has_signatures(reader)
    if signed and not remove_signatures:
        raise SignedPdf(tr("La copia editable perderá las firmas digitales."))
    if not reader.is_encrypted and not signed:
        if skip_unprotected:
            return
        raise ValueError(tr("Este PDF ya está desbloqueado."))
    if signed:
        clear_signature_fields(reader)
    save_writer(PdfWriter(clone_from=reader), destination)


@contextmanager
def page_text(path, index, *, password=None):
    with pdfium_reader(path, password=password) as document:
        with document_text(document, index) as content:
            yield content


@contextmanager
def document_text(document, index):
    page = document[index]
    try:
        if pdfium.raw.FPDFPage_Flatten(page.raw, pdfium.raw.FLAT_NORMALDISPLAY) == pdfium.raw.FLATTEN_SUCCESS:
            page.close()
            page = None
            page = document[index]
        with document_text_on_page(page) as content:
            yield content
    finally:
        if page is not None:
            page.close()


_SEARCH_CLUSTERS = re.compile(r"\s+|\S[\u0300-\u036f]*")


@lru_cache(maxsize=2048)
def folded_search_cluster(cluster, match_accents):
    if cluster.isspace():
        return " "
    text = unicodedata.normalize("NFC", cluster.casefold())
    if match_accents or text == "ñ":
        return text
    return "".join(char for char in unicodedata.normalize("NFD", text) if not unicodedata.combining(char))


def folded_search_text(text, match_accents, *, phrase=False):
    if text.isascii() and not phrase:
        return text.lower(), None
    parts, offsets = [], []
    for cluster in _SEARCH_CLUSTERS.finditer(text):
        part = folded_search_cluster(cluster.group(), match_accents)
        parts.append(part)
        offsets.extend([(cluster.start(), cluster.end())] * len(part))
    return "".join(parts), offsets


def search_character_range(content, text, left, right, utf16):
    first = len(text[:left].encode("utf-16-le")) // 2 if utf16 else left
    last = len(text[:right].encode("utf-16-le")) // 2 - 1 if utf16 else right - 1
    start = pdfium.raw.FPDFText_GetCharIndexFromTextIndex(content.raw, first)
    end = pdfium.raw.FPDFText_GetCharIndexFromTextIndex(content.raw, last)
    if start < 0 or end < start:
        return None
    return start, end - start + 1


def search_context(text, left, right):
    before, after = max(0, left - 60), min(len(text), right + 85)
    return (
        ("…" if before else "") + text[before:left],
        text[left:right],
        text[right:after] + ("…" if after < len(text) else ""),
    )


@dataclass(frozen=True)
class SearchPage:
    page: int
    count: int
    excerpts: tuple
    ranges: tuple


def search_advanced_document(path, query, progress, *, match_accents=False, interrupted=lambda: False,
                             page_index=None, password=None, advanced=True):
    parsed = SearchQuery(query) if advanced else None
    literal = (" ".join(query.split()), False)

    @lru_cache(maxsize=64)
    def pattern(term, quoted):
        needle, _ = folded_search_text(term, match_accents, phrase=True)
        if not needle:
            return re.compile(r"(?!)")
        prefix = r"(?<!\w)" if quoted and re.match(r"\w", needle[0]) else ""
        suffix = r"(?!\w)" if quoted and re.match(r"\w", needle[-1]) else ""
        return re.compile(prefix + re.escape(needle) + suffix)

    pages = []
    with pdfium_reader(path, password=password) as document:
        indices = range(len(document)) if page_index is None else (page_index,)
        for page in indices:
            if interrupted():
                break
            progress(page + 1, len(document))
            with document_text(document, page) as content:
                text = content.get_text_range()
                if not text.strip():
                    continue
                folded, offsets = folded_search_text(text, match_accents, phrase=True)
                terms = parsed.matching_terms(lambda term: pattern(*term).search(folded) is not None) if parsed else {literal}
                if terms is None:
                    continue
                spans = set()
                for term in terms:
                    for hit in pattern(*term).finditer(folded):
                        spans.add((offsets[hit.start()][0], offsets[hit.end() - 1][1]))
                        if interrupted():
                            return pages
                if not spans and parsed is None:
                    continue
                glyphs = len(text.encode("utf-16-le")) != len(text) * 2
                excerpts, ranges = [], []
                for left, right in sorted(spans):
                    if interrupted():
                        return pages
                    located = search_character_range(content, text, left, right, glyphs)
                    if located is None:
                        continue
                    ranges.append(located)
                    if len(excerpts) < (1 if page_index is None else 1000):
                        excerpts.append((*located, search_context(text, left, right)))
                pages.append(SearchPage(page, len(spans), tuple(excerpts), tuple(ranges)))
    return pages


def search_document(path, query, progress, limit=1000, *, match_accents=False, interrupted=lambda: False, password=None):
    query = " ".join(query.split())
    phrase = " " in query
    needle, _ = folded_search_text(query, match_accents, phrase=phrase)
    if not needle:
        return []
    matches = []
    with pdfium_reader(path, password=password) as document:
        for page in range(len(document)):
            if interrupted():
                break
            progress(page + 1, len(document))
            with document_text(document, page) as content:
                text = content.get_text_range()
                folded, offsets = folded_search_text(text, match_accents, phrase=phrase)
                utf16 = len(text.encode("utf-16-le")) != len(text) * 2
                position = 0
                while (index := folded.find(needle, position)) >= 0:
                    position = index + len(needle)
                    left, right = (offsets[index][0], offsets[position - 1][1]) if offsets is not None else (index, position)
                    located = search_character_range(content, text, left, right, utf16)
                    if located is None:
                        continue
                    matches.append((page, *located, search_context(text, left, right)))
                    if len(matches) >= limit or interrupted():
                        return matches
    return matches


@dataclass(frozen=True)
class FormField:
    name: str
    kind: str
    flags: int
    value: object
    options: tuple
    box: tuple


def check_form_type(reader):
    root = reader.root_object.get("/AcroForm")
    if root and "/XFA" in root.get_object():
        raise ValueError(tr("Este formulario usa XFA. PDFiu admite formularios AcroForm."))


def has_xfa(reader):
    form = reader.root_object.get("/AcroForm")
    return bool(form and "/XFA" in form.get_object())


def convert_hybrid_form(source, destination):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    form = writer.root_object["/AcroForm"]
    form.pop(NameObject("/XFA"), None)
    fields = writer.get_fields() or {}
    exposed = set()
    for page in writer.pages:
        for ref in page.get("/Annots", ()):
            widget = ref.get_object()
            if widget.get("/Subtype") == "/Widget":
                exposed.add(writer._get_qualified_field_name(parent=widget_field(widget)))
    if not any(name in fields and fields[name].get("/FT") in ("/Tx", "/Btn", "/Ch") for name in exposed):
        raise ValueError(tr("El PDF usa XFA sin campos AcroForm compatibles."))
    values = {name: str(field["/V"]) for name, field in fields.items()
              if name in exposed and field.get("/FT") == "/Tx" and field.get("/V")}
    if values:
        writer.update_page_form_field_values(None, values, auto_regenerate=False)
    writer.compress_identical_objects(remove_identicals=False, remove_orphans=True)
    save_writer(writer, destination)


def widget_field(widget):
    if "/T" in widget or "/TM" in widget or "/Parent" not in widget:
        return widget
    return widget["/Parent"]


def form_fields(reader, index, *, known=None, visible_only=False):
    if known is None:
        check_form_type(reader)
        known = reader.get_fields() or {}
    fields = []
    for ref in reader.pages[index].get("/Annots", ()):
        widget = ref.get_object()
        if widget.get("/Subtype") != "/Widget" or "/Rect" not in widget:
            continue
        if visible_only and int(widget.get("/F", 0)) & 35:
            continue
        field = widget
        attributes = {}
        for _ in range(30):
            for key in ("/FT", "/Ff", "/V", "/Opt"):
                if key in field:
                    attributes.setdefault(key, field[key])
            if "/Parent" not in field:
                break
            field = field["/Parent"]
        name = reader._get_qualified_field_name(parent=widget_field(widget))
        kind = attributes.get("/FT")
        flags = int(attributes.get("/Ff", 0))
        if name not in known or kind not in ("/Tx", "/Btn", "/Ch") or flags & 1:
            continue
        options = []
        value = attributes.get("/V", "")
        if kind == "/Btn":
            if flags & (1 << 16):
                continue
            states = known[name].get("/_States_") or ()
            options = [(tr("Sin marcar") if state == "/Off" else str(state)[1:], str(state)) for state in states]
            if not options:
                continue
        elif kind == "/Ch":
            if flags & (1 << 21) and isinstance(value, (list, tuple)):
                value = tuple(map(str, value))
            for item in attributes.get("/Opt", ()):
                if isinstance(item, (list, tuple)):
                    export, label = item
                else:
                    export = label = item
                options.append((str(label), str(export)))
        fields.append(FormField(name, str(kind), flags, value, tuple(options), tuple(map(float, widget["/Rect"]))))
    return fields


def fill_form(source, destination, field, value):
    change_form(source, destination, {field.name: value})


def change_form(source, destination, values):
    reader = reader_for(source)
    check_editable(reader)
    check_form_type(reader)
    writer = PdfWriter(clone_from=reader)
    writer.update_page_form_field_values(None, values, auto_regenerate=False)
    with atomic_output(destination) as temporary:
        writer.write(temporary)
        updated = reader_for(temporary).get_fields() or {}
        for name, value in values.items():
            if updated.get(name, {}).get("/V") != value:
                raise PdfReadError(tr("No se pudo guardar el valor del campo «{0}».").format(name))


def clear_form(source, destination):
    reader = reader_for(source)
    values = {}
    for index in range(len(reader.pages)):
        for field in form_fields(reader, index):
            values[field.name] = "/Off" if field.kind == "/Btn" else [] if field.flags & (1 << 21) else ""
    if not values:
        raise ValueError(tr("No hay campos AcroForm editables para vaciar."))
    change_form(source, destination, values)


def flatten_form(source, destination):
    reader = reader_for(source)
    check_editable(reader)
    check_form_type(reader)
    writer = PdfWriter(clone_from=reader)
    form = writer.root_object.get("/AcroForm")
    if not form or not form.get_object().get("/Fields"):
        raise ValueError(tr("Este PDF no contiene campos de formulario para fijar."))
    form = form.get_object()
    for page in writer.pages:
        remaining = ArrayObject()
        for ref in page.get("/Annots", ()):
            widget = ref.get_object()
            if widget.get("/Subtype") != "/Widget":
                remaining.append(ref)
                continue
            field = widget_field(widget)
            value = field.get("/V")
            if int(widget.get("/F", 0)) & 34:
                if value not in (None, "", "/Off", []):
                    raise ValueError(tr("Un campo rellenado está oculto. No se puede fijar su aspecto."))
                continue
            appearances = widget.get("/AP")
            appearance = appearances.get_object().get("/N") if appearances else None
            appearance = appearance.get_object() if appearance else None
            if isinstance(appearance, DictionaryObject) and not isinstance(appearance, StreamObject):
                state = widget.get("/AS", value or "/Off")
                appearance = appearance.get(state)
                appearance = appearance.get_object() if appearance else None
            if not isinstance(appearance, StreamObject):
                if value not in (None, "", "/Off", []):
                    raise ValueError(tr("Un campo rellenado no tiene aspecto visible. Ábrelo y guarda su valor primero."))
                continue
            place_widget_appearance(writer, page, widget, appearance)
        page[NameObject("/Annots")] = remaining
    writer.root_object.pop(NameObject("/AcroForm"))
    save_writer(writer, destination)


def place_widget_appearance(writer, page, widget, appearance):
    a, b, c, d, e, f = map(float, appearance.get("/Matrix", (1, 0, 0, 1, 0, 0)))
    x1, y1, x2, y2 = map(float, appearance["/BBox"])
    points = [(a*x + c*y + e, b*x + d*y + f) for x in (x1, x2) for y in (y1, y2)]
    xs, ys = zip(*points)
    x1, y1, x2, y2 = map(float, widget["/Rect"])
    if max(xs) == min(xs) or max(ys) == min(ys) or x1 == x2 or y1 == y2:
        raise ValueError(tr("Un campo tiene dimensiones no válidas y no se puede fijar."))
    sx, sy = abs(x2 - x1) / (max(xs) - min(xs)), abs(y2 - y1) / (max(ys) - min(ys))
    tx, ty = min(x1, x2) - sx * min(xs), min(y1, y2) - sy * min(ys)
    resources = DictionaryObject()
    if "/Resources" in page:
        resources.update(page["/Resources"])
    xobjects = DictionaryObject()
    if "/XObject" in resources:
        xobjects.update(resources["/XObject"])
    suffix = len(xobjects)
    name = NameObject(f"/PDFiuField{suffix}")
    while name in xobjects:
        suffix += 1
        name = NameObject(f"/PDFiuField{suffix}")
    xobjects[name] = appearance.indirect_reference or writer._add_object(appearance)
    resources[NameObject("/XObject")] = xobjects
    page[NameObject("/Resources")] = resources
    writer._merge_content_stream_to_page(page, f"q\n{sx:.8f} 0 0 {sy:.8f} {tx:.8f} {ty:.8f} cm\n{name} Do\nQ".encode("ascii"))


@dataclass(frozen=True)
class Coordinates:
    origin: tuple
    right: tuple
    down: tuple

    def at(self, x, y):
        return (
            self.origin[0] + x * self.right[0] + y * self.down[0],
            self.origin[1] + x * self.right[1] + y * self.down[1],
        )

    def box(self, x1, y1, x2, y2):
        points = [self.at(x, y) for x, y in ((x1, y1), (x2, y1), (x1, y2), (x2, y2))]
        xs, ys = zip(*points)
        return round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))

    def device(self, x, y):
        x, y = x - self.origin[0], y - self.origin[1]
        rx, ry = self.right
        dx, dy = self.down
        determinant = rx * dy - ry * dx
        return (x * dy - y * dx) / determinant, (rx * y - ry * x) / determinant


def signature_widgets(page):
    for annotation in page["/Annots"] if "/Annots" in page else ():
        widget = annotation.get_object()
        if widget.get("/Subtype") != "/Widget" or "/Rect" not in widget:
            continue
        field = widget
        kind = value = None
        names = []
        for _ in range(20):
            if kind is None:
                kind = field.get("/FT")
            if value is None:
                value = field.get("/V")
            if field.get("/T"):
                names.append(str(field["/T"]))
            if "/Parent" not in field:
                break
            field = field["/Parent"]
        if kind == "/Sig":
            x1, y1, x2, y2 = (float(value) for value in widget["/Rect"])
            box = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
            yield ".".join(reversed(names)), box, signature_value(value) and not int(widget.get("/F", 0)) & 35


def signature_boxes(page):
    return [box for _, box, _ in signature_widgets(page)]


def overlaps(a, b):
    return max(a[0], b[0]) < min(a[2], b[2]) and max(a[1], b[1]) < min(a[3], b[3])


def validate_signature_box(page, box):
    x1, y1, x2, y2 = box
    sides = (x2 - x1, y2 - y1)
    if min(sides) < 12 or max(sides) < 55:
        raise ValueError(tr("El recuadro es pequeño. Arrastra para dibujar uno más grande."))
    bounds = page.cropbox
    if x1 < float(bounds.left) - 1 or y1 < float(bounds.bottom) - 1 or x2 > float(bounds.right) + 1 or y2 > float(bounds.top) + 1:
        raise ValueError(tr("El recuadro debe quedar dentro de la página."))
    if any(overlaps(box, existing) for existing in signature_boxes(page)):
        raise ValueError(tr("El recuadro se solapa con una firma o un campo existente. Elige otra zona."))


def project_signature_box(source_page, target_page, box):
    left, bottom, right, top = map(float, source_page.cropbox)
    source_rotation = source_page.rotation % 360
    target_rotation = target_page.rotation % 360
    target_left, target_bottom, target_right, target_top = map(float, target_page.cropbox)

    def relative(x, y):
        x = (x - left) / (right - left)
        y = (y - bottom) / (top - bottom)
        return {0: (x, 1-y), 90: (y, x), 180: (1-x, y), 270: (1-y, 1-x)}[source_rotation]

    def target(u, v):
        x, y = {0: (u, 1-v), 90: (v, u), 180: (1-u, v), 270: (1-v, 1-u)}[target_rotation]
        return target_left + x * (target_right - target_left), target_bottom + y * (target_top - target_bottom)

    x1, y1, x2, y2 = box
    xs, ys = zip(*(target(*relative(x, y)) for x in (x1, x2) for y in (y1, y2)))
    return round(min(xs)), round(min(ys)), round(max(xs)), round(max(ys))


def signature_plan(reader, page, box, *, all_pages=False):
    if not 0 <= page < len(reader.pages):
        raise ValueError(tr("El documento no tiene página {0}.").format(page + 1))
    indices = range(len(reader.pages)) if all_pages else (page,)
    positions = {}
    for index in indices:
        other = box if index == page else project_signature_box(reader.pages[page], reader.pages[index], box)
        try:
            validate_signature_box(reader.pages[index], other)
        except ValueError as error:
            raise ValueError(tr("Página {0}: {1}").format(index + 1, error)) from error
        positions[index] = other
    return positions


def render_page(document, index, *, width=None, dpi=None, with_coordinates=False):
    page = document[index]
    try:
        page_width, page_height = page.get_size()
        scale = width / page_width if width else (dpi or 96) / 72
        scale = min(scale, 6000 / max(page_width, page_height))
        bitmap = page.render(scale=scale, draw_annots=True)
        try:
            image = bitmap.to_pil()
            if image.mode != "RGB":
                image = image.convert("RGB")
            if not with_coordinates:
                return image

            def map_point(x, y):
                px, py = c_double(), c_double()
                ok = pdfium.raw.FPDF_DeviceToPage(page.raw, 0, 0, bitmap.width, bitmap.height, 0, x, y, byref(px), byref(py))
                if not ok:
                    raise ValueError(tr("No se pudo localizar el recuadro en la página."))
                return px.value, py.value

            origin = map_point(0, 0)
            right = map_point(bitmap.width, 0)
            down = map_point(0, bitmap.height)
            coordinates = Coordinates(
                origin,
                tuple((value - offset) / bitmap.width for value, offset in zip(right, origin)),
                tuple((value - offset) / bitmap.height for value, offset in zip(down, origin)),
            )
            return image, coordinates
        finally:
            bitmap.close()
    finally:
        page.close()


def render_page_tile(document, index, scale, bounds, *, annotations=True):
    """Render a bounded crop at the screen's pixel density."""
    left, top, right, bottom = bounds
    page = document[index]
    try:
        full_width = ceil(page.get_width() * scale)
        full_height = ceil(page.get_height() * scale)
        trims = (left, full_height - bottom, full_width - right, top)
        crop = tuple(max(0, pixels - .25) / scale for pixels in trims)
        bitmap = page.render(scale=scale, crop=crop, draw_annots=annotations, may_draw_forms=annotations)
        try:
            image = bitmap.to_pil()
            return image if image.mode == "RGB" else image.convert("RGB")
        finally:
            bitmap.close()
    finally:
        page.close()


def save_writer(writer, destination):
    with atomic_output(destination) as temporary:
        with temporary.open("wb") as stream:
            writer.write(stream)
        if len(reader_for(temporary).pages) != len(writer.pages):
            raise ValueError(tr("El PDF guardado no tiene el número de páginas esperado."))


def blank_pdf(destination, width, height):
    writer = PdfWriter()
    writer.add_blank_page(width, height)
    save_writer(writer, destination)


def images_to_pdf(sources, destination, progress):
    from PIL import Image, ImageOps

    with atomic_output(destination) as temporary:
        output = Canvas(str(temporary), pageCompression=1)
        for index, (path, angle) in enumerate(sources):
            progress(index + 1, len(sources))
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original)
                if angle:
                    image = image.rotate(-angle, expand=True)
                landscape = image.width > image.height
                width, height = (842, 595) if landscape else (595, 842)
                scale = min((width - 36) / image.width, (height - 36) / image.height)
                w, h = image.width * scale, image.height * scale
                output.setPageSize((width, height))
                output.drawImage(ImageReader(image.convert("RGBA")), (width - w) / 2, (height - h) / 2,
                                 w, h, mask="auto")
                output.showPage()
        output.save()
        if len(reader_for(temporary).pages) != len(sources):
            raise ValueError(tr("No se pudieron convertir todas las imágenes."))


def reader_for_merge(path, remove_signatures):
    reader = reader_for(path, allow_empty_password=True)
    if remove_signatures:
        if pdf_has_signatures(reader):
            clear_signature_fields(reader)
    else:
        check_editable(reader)
    return reader


def merge(paths, destination, *, with_index=False, names=None, remove_signatures=False):
    writer = PdfWriter()
    for path in paths:
        reader = reader_for_merge(path, remove_signatures)
        label = Path((names or {}).get(str(path), path)).stem
        writer.append(reader, outline_item=label if with_index else None, import_outline=True)
    save_writer(writer, destination)


def edit_pages(source, destination, order, rotate_index=None, *, rotations=None):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter()
    writer.append(reader, pages=order, import_outline=True)
    if rotate_index is not None:
        writer.pages[rotate_index].rotate(90)
    if rotations:
        for index, angle in rotations.items():
            if angle % 360:
                writer.pages[index].rotate(angle % 360)
    if reader.metadata:
        writer.add_metadata({str(key): str(value) for key, value in reader.metadata.items() if value is not None})
    save_writer(writer, destination)


def split_pdf(source, destination_dir, *, every=1, stem=None, password=None, progress=None):
    if every < 1:
        raise ValueError(tr("Indica al menos 1 página por archivo."))
    reader = reader_for(source, password=password)
    total = len(reader.pages)
    if total == 0:
        raise ValueError(tr("El documento no tiene páginas."))
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    base = stem or Path(source).stem
    parts = [list(range(start, min(start + every, total))) for start in range(0, total, every)]
    digits = max(3, len(str(len(parts))))
    created = []
    for idx, pages in enumerate(parts, 1):
        if progress:
            progress(idx, len(parts))
        target = destination_dir / f"{base} - {tr('parte')} {idx:0{digits}d}.pdf"
        serial = 2
        while target.exists():
            target = destination_dir / f"{base} - {tr('parte')} {idx:0{digits}d} ({serial}).pdf"
            serial += 1
        writer = PdfWriter()
        writer.append(reader, pages=pages, import_outline=False)
        save_writer(writer, target)
        created.append(target)
    return created


def pages_per_sheet(source, destination, paper, grid, progress):
    reader = reader_for(source)
    check_editable(reader)
    width, height = paper
    total = len(reader.pages)
    if grid is None:
        columns = ceil(sqrt(total))
        rows = ceil(total / columns)
    else:
        columns, rows = grid
    margin = 18
    gap = min(8, (width - 2 * margin) / (7 * columns), (height - 2 * margin) / (7 * rows))
    cell_width = (width - 2 * margin - (columns - 1) * gap) / columns
    cell_height = (height - 2 * margin - (rows - 1) * gap) / rows
    writer = PdfWriter()
    sheet = None
    for index, page in enumerate(reader.pages):
        progress(index + 1, total)
        row, column = divmod(index % (columns * rows), columns)
        if row == column == 0:
            sheet = writer.add_blank_page(width, height)
        if page.rotation:
            page.transfer_rotation_to_content()
        # The print layout carries the page content. Widgets and other interactive
        # annotations depend on the source document and are not copied to the sheet.
        page.pop(NameObject("/Annots"), None)
        crop = page.cropbox
        source_width, source_height = float(crop.width), float(crop.height)
        if source_width <= 0 or source_height <= 0:
            raise ValueError(tr("La página {0} tiene un tamaño no válido.").format(index + 1))
        scale = min(cell_width / source_width, cell_height / source_height)
        x = margin + column * (cell_width + gap) + (cell_width - scale * source_width) / 2
        y = height - margin - (row + 1) * cell_height - row * gap + (cell_height - scale * source_height) / 2
        transform = Transformation().scale(scale).translate(x - scale * float(crop.left), y - scale * float(crop.bottom))
        sheet.merge_transformed_page(page, transform)
    save_writer(writer, destination)


def insert_pages(target, destination, position, sources, *, remove_signatures=False):
    original = reader_for(target)
    check_editable(original)
    if not 0 <= position <= len(original.pages):
        raise ValueError(tr("El punto de inserción ya no existe."))
    writer = PdfWriter(clone_from=original)
    inserted = 0
    for path, selection in sources:
        try:
            source = reader_for_merge(path, remove_signatures)
            pages = list(range(len(source.pages))) if selection is None else list(selection)
            if not pages or len(set(pages)) != len(pages) or any(not 0 <= page < len(source.pages) for page in pages):
                raise ValueError(tr("La selección de páginas ha cambiado."))
            existing = writer.get_fields() or {}
            incoming = source.get_fields() or {}
            if existing.keys() & incoming.keys():
                counter = 1
                while any(name == f"Insertado_{counter}" or name.startswith(f"Insertado_{counter}.") for name in existing):
                    counter += 1
                source.add_form_topname(f"Insertado_{counter}")
            writer.merge(position + inserted, source, pages=pages, import_outline=True)
            inserted += len(pages)
        except Exception as error:
            raise ValueError(f"{Path(path).name}: {error}") from error
    if not inserted:
        raise ValueError(tr("No hay páginas para insertar."))
    save_writer(writer, destination)
    return inserted


def pdf_image_usage(writer, *, on_image=None, page_indices=None):
    usages = {}
    masks = set()
    protected_images = set()
    can_resize = True
    probe_limit = 256 * 1024

    def protect_resources(resources, seen):
        resources = resources.get_object()
        if id(resources) in seen:
            return
        seen.add(id(resources))
        for kind in ("/XObject", "/Pattern", "/Font"):
            for reference in resources.get(kind, DictionaryObject()).get_object().values():
                obj = reference.get_object()
                if obj.get("/Subtype") == "/Image" and getattr(reference, "idnum", None) is not None:
                    protected_images.add(reference.idnum)
                if "/Resources" in obj:
                    protect_resources(obj["/Resources"], seen)

    def visit(stream, resources, matrix, unit, ancestors, page_index):
        nonlocal can_resize
        if stream is None:
            return
        fonts = resources["/Font"] if "/Font" in resources else {}
        if resources.get("/Pattern") or any(font.get_object().get("/Subtype") == "/Type3" for font in fonts.values()):
            protect_resources(resources, set())
        xobjects = resources.get("/XObject", DictionaryObject()).get_object()
        if not xobjects and on_image is None:
            return
        if on_image is None and b"Do" not in stream.get_data():
            return
        stack = []
        for operands, op in stream.operations:
            if op == b"q":
                stack.append(matrix)
            elif op == b"Q":
                if not stack:
                    can_resize = False
                else:
                    matrix = stack.pop()
            elif op == b"cm":
                matrix = image_matrix(matrix, operands)
            elif op == b"INLINE IMAGE" and on_image:
                settings = operands["settings"]
                width = settings.get("/W", settings.get("/Width"))
                height = settings.get("/H", settings.get("/Height"))
                if width and height and page_index >= 0:
                    a, b, c, d = matrix
                    on_image(page_index, {"/Width": width, "/Height": height},
                             (hypot(a, b) * unit / 72, hypot(c, d) * unit / 72))
            elif op == b"Do":
                reference = xobjects.get(operands[0])
                if reference is None:
                    continue
                obj = reference.get_object()
                kind = obj.get("/Subtype")
                if kind == "/Image" and getattr(reference, "idnum", None) is not None:
                    key = reference.idnum
                    if page_index < 0:
                        protected_images.add(key)
                        continue
                    for name in ("/Mask", "/SMask"):
                        mask = getattr(obj.get(name), "idnum", None)
                        if mask is not None:
                            masks.add(mask)
                    if key not in usages:
                        usages[key] = (obj, [])
                    a, b, c, d = matrix
                    dimensions = hypot(a, b) * unit / 72, hypot(c, d) * unit / 72
                    usages[key][1].append(dimensions)
                    if on_image:
                        on_image(page_index, obj, dimensions)
                elif kind == "/Form":
                    if page_indices is not None and len(obj._data) > probe_limit:
                        continue
                    if id(obj) in ancestors or len(ancestors) >= 20:
                        can_resize = False
                        continue
                    sub_resources = obj["/Resources"] if "/Resources" in obj else resources
                    sub_matrix = image_matrix(matrix, obj.get("/Matrix", (1, 0, 0, 1, 0, 0)))
                    visit(ContentStream(obj, writer), sub_resources, sub_matrix, unit, ancestors | {id(obj)}, page_index)

    def protect_appearance(reference, resources, seen):
        obj = reference.get_object()
        if id(obj) in seen or len(seen) >= 1000:
            return
        seen.add(id(obj))
        if isinstance(obj, StreamObject):
            sub_resources = obj["/Resources"] if "/Resources" in obj else resources
            visit(ContentStream(obj, writer), sub_resources, (1, 0, 0, 1), 1, {id(obj)}, -1)
        elif isinstance(obj, DictionaryObject):
            for value in obj.values():
                protect_appearance(value, resources, seen)

    pages = enumerate(writer.pages) if page_indices is None else ((i, writer.pages[i]) for i in page_indices)
    for page_index, page in pages:
        if page_indices is not None and sum(len(stream._data) for stream in page_content_parts(page)) > probe_limit:
            continue
        resources = page.get("/Resources", DictionaryObject()).get_object()
        for item in page.get("/Annots", ()):
            appearance = item.get_object().get("/AP")
            if appearance:
                try:
                    protect_appearance(appearance, resources, set())
                except (PdfReadError, ValueError, TypeError, KeyError):
                    can_resize = False
        visit(page.get_contents(), resources,
              (1, 0, 0, 1), float(page.get("/UserUnit", 1)), set(), page_index)
    return [value for key, value in usages.items() if key not in masks and key not in protected_images], can_resize


def image_matrix(matrix, operands):
    a, b, c, d = matrix
    e, f, g, h = map(float, operands[:4])
    return (a*e + c*f, b*e + d*f, a*g + c*h, b*g + d*h)


def resolve_image_colorspace(stream):
    color_space = stream.get("/ColorSpace")
    if hasattr(color_space, "get_object"):
        color_space = color_space.get_object()
    if color_space == "/DeviceRGB":
        return "rgb", 3
    if color_space == "/DeviceGray":
        return "gray", 1
    if color_space == "/DeviceCMYK":
        return "cmyk", 4
    if isinstance(color_space, ArrayObject) and len(color_space) >= 2 and color_space[0] == "/ICCBased":
        profile = color_space[1].get_object() if hasattr(color_space[1], "get_object") else color_space[1]
        if isinstance(profile, DictionaryObject):
            channels = int(profile.get("/N", 0))
            if channels == 3:
                return "icc-rgb", 3
            if channels == 1:
                return "icc-gray", 1
            if channels == 4:
                return "icc-cmyk", 4
    return None


def compressible_image_format(stream, dpi, compact, *, grayscale=False):
    filters = stream.get("/Filter", [])
    if isinstance(filters, str):
        filters = [filters]
    if (any(name not in ("/ASCII85Decode", "/ASCIIHexDecode") for name in filters[:-1])
            or any(key in stream for key in ("/Mask", "/SMaskInData", "/ImageMask", "/Alternates", "/F"))):
        return None
    cs_info = resolve_image_colorspace(stream)
    if cs_info is None:
        return None
    cs_kind, channels = cs_info
    if cs_kind in ("cmyk", "icc-cmyk") and not (compact or grayscale):
        return None
    if cs_kind in ("icc-rgb", "icc-gray") and not (dpi or compact or grayscale):
        return None
    if "/Decode" in stream:
        decode = stream["/Decode"]
        if stream.get("/BitsPerComponent") != 8 or not isinstance(decode, ArrayObject) or tuple(decode) != (0, 1) * channels:
            return None
    if filters and filters[-1] == "/DCTDecode" and "/DecodeParms" not in stream:
        return "/DCTDecode"
    if filters and filters[-1] == "/JPXDecode" and (dpi or compact or grayscale):
        return "/JPXDecode"
    if (dpi or compact or grayscale) and (not filters or filters[-1] == "/FlateDecode") and stream.get("/BitsPerComponent") == 8:
        return "/FlateDecode"
    return None


def scaled_image_size(width, height, sizes, dpi):
    if not dpi or not sizes or not all(w > 0 and h > 0 for w, h in sizes):
        return width, height
    min_width = ceil(dpi * max(w for w, _ in sizes))
    min_height = ceil(dpi * max(h for _, h in sizes))
    ratio = min(1, max(min_width / width, min_height / height))
    return (ceil(width * ratio), ceil(height * ratio)) if ratio < 0.98 else (width, height)


@dataclass(frozen=True)
class RasterEncoding:
    payload: bytes
    size: tuple[int, int]
    filter_name: str
    resized: bool
    predictor_colors: int = 0
    color_space: str | None = None


def photographic_image(image):
    from PIL import Image, ImageChops

    # A nearest-neighbour sample keeps flat tones and outlines distinct.
    with image.resize((160, 160), Image.Resampling.NEAREST) as reduced, reduced.convert("L") as sample:
        histogram = sample.histogram()
        dominant_tones = sum(sorted(histogram, reverse=True)[:4])
        if dominant_tones > 0.35 * 160 * 160:
            return False
        with ImageChops.difference(sample.crop((0, 0, 159, 160)), sample.crop((1, 0, 160, 160))) as edges:
            return sum(edges.histogram()[2:50]) > 0.24 * 159 * 160


def jpeg_encoding(image, quality, *, compact=False):
    output = BytesIO()
    image.save(output, "JPEG", quality=quality, optimize=True, subsampling=2 if compact else 0)
    return output.getvalue()


def png_predictor_encoding(image):
    # A PNG's IDAT chunks are a PDF-compatible Flate stream with PNG row predictors.
    output = BytesIO()
    image.save(output, "PNG", compress_level=9)
    raw = output.getbuffer()
    chunks = []
    offset = 8
    while offset < len(raw):
        size = int.from_bytes(raw[offset:offset+4], "big")
        if raw[offset+4:offset+8] == b"IDAT":
            chunks.append(raw[offset+8:offset+8+size])
        offset += size + 12
    return b"".join(chunks)


def recompress_jpeg(stream, sizes, quality, dpi, compact, *, fast=False, grayscale=False):
    from PIL import Image

    try:
        original_bytes = stream.get_data()
        with Image.open(BytesIO(original_bytes)) as original:
            width, height = original.size
            if (width, height) != (stream.get("/Width"), stream.get("/Height")):
                return None
            if original.mode not in ("RGB", "L", "CMYK"):
                return None
            if original.mode == "CMYK" and not (compact or grayscale):
                return None
            if original.info.get("icc_profile") and not (compact or grayscale):
                return None
            picture = original
            converted = False
            target_mode = "L" if grayscale else ("RGB" if original.mode == "CMYK" else original.mode)
            planned = scaled_image_size(width, height, sizes, dpi)
            resized = planned != (width, height)
            if resized:
                if fast and original.mode != "CMYK":
                    original.draft(original.mode, planned)
                picture = original.resize(planned, Image.Resampling.LANCZOS, reducing_gap=3.0 if fast else None)
            if picture.mode != target_mode:
                converted_pic = picture.convert(target_mode)
                if picture is not original:
                    picture.close()
                picture = converted_pic
                converted = True
            try:
                is_photo = photographic_image(picture if (fast or converted) else original)
                encoded = jpeg_encoding(picture, quality, compact=compact and (is_photo or grayscale))
            finally:
                if picture is not original:
                    picture.close()
            is_jpx = stream.get("/Filter") == "/JPXDecode" or (isinstance(stream.get("/Filter"), list) and stream.get("/Filter")[-1] == "/JPXDecode")
            if not resized and not converted and not is_jpx and len(original_bytes) < len(encoded):
                encoded = original_bytes
            if len(encoded) < len(stream._data) * 0.98 or converted:
                new_cs = None
                if target_mode == "L" and stream.get("/ColorSpace") != "/DeviceGray":
                    new_cs = "/DeviceGray"
                elif target_mode == "RGB" and stream.get("/ColorSpace") != "/DeviceRGB":
                    new_cs = "/DeviceRGB"
                if len(encoded) < len(stream._data) * 0.98:
                    return RasterEncoding(encoded, planned, "/DCTDecode", resized, color_space=new_cs)
    except (OSError, ValueError, PdfReadError, Image.DecompressionBombError):
        return None
    return None


def recompress_raster(stream, sizes, quality, dpi, mode, compact, *, fast=False, grayscale=False):
    if mode in ("/DCTDecode", "/JPXDecode"):
        return recompress_jpeg(stream, sizes, quality, dpi, compact, fast=fast, grayscale=grayscale)
    from PIL import Image

    width, height = int(stream["/Width"]), int(stream["/Height"])
    if min(width, height) < 1 or width * height > 50_000_000:
        return None
    cs_info = resolve_image_colorspace(stream)
    if cs_info is None:
        return None
    cs_kind, _ = cs_info
    target = scaled_image_size(width, height, sizes, dpi)
    resized = target != (width, height)
    if not resized and not compact and not grayscale:
        return None
    raw_mode = "L" if cs_kind in ("gray", "icc-gray") else ("CMYK" if cs_kind in ("cmyk", "icc-cmyk") else "RGB")
    target_mode = "L" if grayscale or raw_mode == "L" else "RGB"
    new_cs = "/DeviceGray" if target_mode == "L" else "/DeviceRGB"
    try:
        with Image.frombytes(raw_mode, (width, height), stream.get_data()) as picture:
            work = picture.convert(target_mode) if picture.mode != target_mode else picture
            try:
                smaller = work.resize(target, Image.Resampling.LANCZOS, reducing_gap=3.0 if fast else None) if resized else work
                try:
                    if compact and (photographic_image(work) or grayscale):
                        jpeg = jpeg_encoding(smaller, quality, compact=True)
                        if len(jpeg) < len(stream._data) * 0.98:
                            return RasterEncoding(jpeg, target, "/DCTDecode", resized, color_space=new_cs)
                    payload = png_predictor_encoding(smaller)
                finally:
                    if smaller is not work:
                        smaller.close()
            finally:
                if work is not picture:
                    work.close()
    except (OSError, ValueError, PdfReadError):
        return None
    if len(payload) + 64 < len(stream._data) * 0.98:
        return RasterEncoding(payload, target, "/FlateDecode", resized, len(target_mode), color_space=new_cs)
    return None


def _smask_is_resizable(smask):
    if (not isinstance(smask, StreamObject) or smask.get("/ColorSpace") != "/DeviceGray"
            or smask.get("/BitsPerComponent") != 8):
        return False
    if "/Decode" in smask:
        decode = smask["/Decode"]
        if not isinstance(decode, ArrayObject) or tuple(decode) != (0, 1):
            return False
    return True


def _resize_smask_stream(smask, target, *, fast=False):
    from PIL import Image

    if not _smask_is_resizable(smask):
        return False
    width, height = int(smask.get("/Width", 0)), int(smask.get("/Height", 0))
    if min(width, height) < 1 or width * height > 50_000_000:
        return False
    try:
        with Image.frombytes("L", (width, height), smask.get_data()) as mask_img:
            with mask_img.resize(target, Image.Resampling.LANCZOS, reducing_gap=3.0 if fast else None) as resized_mask:
                payload = png_predictor_encoding(resized_mask)
    except (OSError, ValueError, PdfReadError):
        return False
    smask._data = payload
    smask.decoded_self = None
    smask[NameObject("/Filter")] = NameObject("/FlateDecode")
    smask[NameObject("/DecodeParms")] = DictionaryObject({
        NameObject("/Predictor"): NumberObject(15),
        NameObject("/Colors"): NumberObject(1),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Columns"): NumberObject(target[0]),
    })
    smask[NameObject("/Width")] = NumberObject(target[0])
    smask[NameObject("/Height")] = NumberObject(target[1])
    return True


def optimize_images(writer, quality, dpi, compact, *, fast=False, grayscale=False, progress=None):
    usages, can_resize = pdf_image_usage(writer)
    dpi = dpi if can_resize else None
    smask_refs = {}
    for stream, _ in usages:
        if "/SMask" in stream:
            smask = stream["/SMask"].get_object()
            smask_refs[id(smask)] = smask_refs.get(id(smask), 0) + 1
    updated, resized = set(), 0
    for index, (stream, sizes) in enumerate(usages, 1):
        if progress:
            progress(index, len(usages))
        mode = compressible_image_format(stream, dpi, compact, grayscale=grayscale)
        if not mode:
            continue
        smask = stream["/SMask"].get_object() if "/SMask" in stream else None
        effective_dpi = dpi
        if smask is not None:
            can_resize_smask = smask_refs.get(id(smask), 0) == 1 and _smask_is_resizable(smask)
            if not can_resize_smask:
                effective_dpi = None
        result = recompress_raster(stream, sizes, quality, effective_dpi, mode, compact, fast=fast, grayscale=grayscale)
        if not result:
            continue
        new_width, new_height = result.size
        if smask is not None and result.resized:
            if not _resize_smask_stream(smask, result.size, fast=fast):
                continue
            updated.add(id(smask))
        stream._data = result.payload
        stream.decoded_self = None
        stream[NameObject("/Filter")] = NameObject(result.filter_name)
        stream.pop(NameObject("/DecodeParms"), None)
        if result.color_space is not None:
            stream[NameObject("/ColorSpace")] = NameObject(result.color_space)
        if result.predictor_colors:
            stream[NameObject("/DecodeParms")] = DictionaryObject({
                NameObject("/Predictor"): NumberObject(15),
                NameObject("/Colors"): NumberObject(result.predictor_colors),
                NameObject("/BitsPerComponent"): NumberObject(8),
                NameObject("/Columns"): NumberObject(new_width),
            })
        stream[NameObject("/Width")] = NumberObject(new_width)
        stream[NameObject("/Height")] = NumberObject(new_height)
        updated.add(id(stream))
        resized += result.resized
    return updated, resized


def improve_flate(payload, *, level=9):
    try:
        decoder = decompressobj()
        decoded = decoder.decompress(payload, 32 * 1024 * 1024)
        if decoder.eof and not decoder.unused_data:
            packed = deflate(decoded, level=level)
            return packed if len(packed) < len(payload) else None
    except ZlibError:
        pass
    return None


def single_flate(stream):
    filters = stream.get("/Filter")
    return filters == "/FlateDecode" or filters == ["/FlateDecode"]


def page_content_parts(page):
    contents = page.get("/Contents")
    if contents is None:
        return
    parts = contents.get_object()
    for ref in parts if isinstance(parts, list) else (contents,):
        stream = ref.get_object()
        if isinstance(stream, StreamObject):
            yield stream


def page_streams(pages):
    streams = {}
    for page in pages:
        for stream in page_content_parts(page):
            if not stream.get("/Filter"):
                streams[id(stream)] = stream
    return streams.values()


def estimated_image_size(stream, sizes, quality, dpi, mode, compact):
    width, height = int(stream["/Width"]), int(stream["/Height"])
    size = len(stream._data)
    if min(width, height) < 1 or not sizes:
        return size
    w, h = scaled_image_size(width, height, sizes, dpi)
    pixel_ratio = (w * h) / (width * height)
    density = size / (width * height)
    # Downsampling often smooths detailed photographs, which further reduces JPEG size.
    tonal_density = (0.09 + 0.72 * (quality / 100) ** 3) * (0.35 + 0.65 * pixel_ratio ** 0.5)
    if mode == "/DCTDecode":
        jpeg_ratio = 0.62 + 0.38 * (quality / 100) ** 2
        projected = size * pixel_ratio ** 0.86 * jpeg_ratio
        if compact and density >= 0.30 and pixel_ratio < 0.67:
            projected = min(projected, w * h * tonal_density)
        return min(size, round(projected + 500))
    # Detailed images usually occupy more bytes per pixel than line art in a Flate stream.
    if compact and density >= 0.35:
        return min(size, round(w * h * tonal_density + 500))
    if pixel_ratio < 1:
        return min(size, round(size * pixel_ratio ** 0.78 + 100))
    return size


def compression_resource_images(resources, dpi, compact, cache, ancestors=(), *, grayscale=False):
    resources = resources.get_object()
    identity = id(resources)
    if identity in ancestors or len(ancestors) >= 20:
        return {}
    if identity in cache:
        return cache[identity]
    fonts = resources.get("/Font", DictionaryObject()).get_object()
    if resources.get("/Pattern") or any(font.get_object().get("/Subtype") == "/Type3" for font in fonts.values()):
        return {}
    images = {}
    for ref in resources.get("/XObject", DictionaryObject()).get_object().values():
        obj = ref.get_object()
        subtype = obj.get("/Subtype")
        if subtype == "/Image" and getattr(ref, "idnum", None) is not None:
            mode = compressible_image_format(obj, dpi, compact, grayscale=grayscale)
            if mode:
                images[ref.idnum] = obj, mode
        elif subtype == "/Form" and "/Resources" in obj:
            images.update(compression_resource_images(obj["/Resources"], dpi, compact, cache, (*ancestors, identity), grayscale=grayscale))
    cache[identity] = images
    return images


def estimate_image_reduction(reader, indices, quality, dpi, compact, *, grayscale=False):
    resources_cache = {}
    candidates = {}
    weights = []
    for index, page in enumerate(reader.pages):
        images = compression_resource_images(page.get("/Resources", DictionaryObject()), dpi, compact, resources_cache, grayscale=grayscale)
        if not images:
            continue
        box = page.mediabox
        unit = float(page.get("/UserUnit", 1)) / 72
        footprint = (float(box.width) * unit, float(box.height) * unit)
        weight = 0
        for key, (stream, mode) in images.items():
            if key not in candidates:
                candidates[key] = stream, mode, {}
            candidates[key][2][index] = footprint
            weight += len(stream._data)
        weights.append((weight, index))
    if not candidates:
        return 0

    largest = [index for _, index in sorted(weights, reverse=True)[:4]]
    probes = list(dict.fromkeys([*largest, *indices]))[:len(indices)]
    usage, can_resize = pdf_image_usage(reader, page_indices=probes)
    observed = {stream.indirect_reference.idnum: sizes for stream, sizes in usage}
    gain = 0
    for key, (stream, mode, footprints) in candidates.items():
        sizes = observed[key] if len(footprints) == 1 and key in observed else list(footprints.values())
        projected = estimated_image_size(stream, sizes, quality, dpi if can_resize else None, mode, compact)
        if grayscale and resolve_image_colorspace(stream) not in (None, ("gray", 1), ("icc-gray", 1)):
            projected = round(projected * 0.65)
        gain += len(stream._data) - projected
    return gain


def _stream_payload_size(value):
    obj = value.get_object() if hasattr(value, "get_object") else value
    if isinstance(obj, StreamObject):
        return len(obj._data)
    if isinstance(obj, DictionaryObject):
        return sum(_stream_payload_size(item) for item in obj.values())
    if isinstance(obj, ArrayObject):
        return sum(_stream_payload_size(item) for item in obj)
    return 0


def strip_pdf_bloat(writer, *, strip_bloat=True, clean_metadata=False):
    if strip_bloat:
        for key in ("/PieceInfo", "/SpiderInfo"):
            writer.root_object.pop(NameObject(key), None)
        for page in writer.pages:
            for key in ("/PieceInfo", "/Thumb", "/LastModified"):
                page.pop(NameObject(key), None)
    if clean_metadata:
        writer.root_object.pop(NameObject("/Metadata"), None)
        for page in writer.pages:
            page.pop(NameObject("/Metadata"), None)
        for obj in writer._objects:
            if isinstance(obj, StreamObject) and "/Metadata" in obj:
                obj.pop(NameObject("/Metadata"), None)
        if hasattr(writer, "_info") and writer._info is not None:
            info = writer._info.get_object() if hasattr(writer._info, "get_object") else writer._info
            if isinstance(info, DictionaryObject):
                info.clear()


@contextmanager
def compression_reader(source, *, allow_empty_password=False, password=None, read_only=False):
    with Path(source).open("rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        # A stored stream cannot exceed the file itself. Bound memory use for very large files.
        with apply_configuration(maximum_declared_stream_length=min(size, 256 * 1024 * 1024)):
            reader = PdfReader(handle)
            if reader.is_encrypted:
                supplied = password if password is not None else "" if allow_empty_password else None
                if supplied is None or not reader.decrypt(supplied):
                    raise ProtectedPdf(tr("Este PDF está protegido. Usa Proteger → Desbloquear PDF para crear una copia editable."))
            if not read_only:
                check_editable(reader)
            if not reader.pages:
                raise ValueError(tr("El documento no contiene páginas."))
            yield reader, size


def estimate_compression(source, *, quality=None, dpi=None, compact=False, grayscale=False,
                         clean_metadata=False, strip_bloat=True, password=None):
    with compression_reader(source, allow_empty_password=True, password=password, read_only=True) as (reader, before):
        total = len(reader.pages)
        count = min(total, 8)
        indices = [index * (total - 1) // (count - 1) for index in range(count)] if count > 1 else [0]
        scale = total / count
        structure_gain = 0.55 * scale * sum(len(stream._data) for stream in page_streams(reader.pages[i] for i in indices))
        bloat_gain = 0
        if strip_bloat:
            for key in ("/PieceInfo", "/SpiderInfo"):
                if key in reader.root_object:
                    bloat_gain += _stream_payload_size(reader.root_object[key])
            bloat_gain += scale * sum(
                _stream_payload_size(reader.pages[i][key])
                for i in indices for key in ("/PieceInfo", "/Thumb") if key in reader.pages[i]
            )
        if clean_metadata and "/Metadata" in reader.root_object:
            bloat_gain += _stream_payload_size(reader.root_object["/Metadata"])
        image_gain = estimate_image_reduction(reader, indices, quality, dpi, compact, grayscale=grayscale) if quality is not None else 0
        gain = round(structure_gain + bloat_gain + image_gain)
        minimum = min(before, 1024 + 96 * total)
        return before, max(minimum, before - gain), count, total


def compress_copy(source, destination, *, quality=None, dpi=None, compact=False, fast=False,
                  allow_larger=False, progress=None, grayscale=False, clean_metadata=False, strip_bloat=True):
    destination = Path(destination)
    if Path(source).resolve() == destination.resolve():
        raise ValueError(tr("Guarda la compresión en un archivo distinto para conservar el original."))
    with compression_reader(source) as (reader, before):
        return write_compressed_copy(
            reader, before, destination, quality, dpi, compact, fast, allow_larger, progress,
            grayscale=grayscale, clean_metadata=clean_metadata, strip_bloat=strip_bloat,
        )


def write_compressed_copy(reader, before, destination, quality, dpi, compact, fast, allow_larger, progress=None,
                          *, grayscale=False, clean_metadata=False, strip_bloat=True):
    writer = PdfWriter(clone_from=reader)
    strip_pdf_bloat(writer, strip_bloat=strip_bloat, clean_metadata=clean_metadata)
    image_count = 0
    object_count = len(writer._objects)

    def report_images(step, count):
        nonlocal image_count
        image_count = count
        progress(step, count + object_count)

    image_progress = report_images if progress else None
    optimized, resized = (
        optimize_images(writer, quality, dpi, compact, fast=fast, grayscale=grayscale, progress=image_progress)
        if quality is not None else (set(), 0)
    )
    flate_level = 6 if fast else 9
    for index, stream in enumerate(writer._objects):
        if progress and index % 32 == 0:
            progress(image_count + index, image_count + object_count)
        if (not isinstance(stream, StreamObject) or id(stream) in optimized or "/F" in stream
                or stream.get("/Type") in ("/Metadata", "/XRef", "/ObjStm") or len(stream._data) <= 30):
            continue
        if single_flate(stream):
            packed = improve_flate(stream._data, level=flate_level)
            if packed:
                stream._data = packed
                stream.decoded_self = None
            continue
        if stream.get("/Filter"):
            continue
        reference = getattr(stream, "indirect_reference", None)
        if reference is None:
            continue
        encoded = stream.flate_encode(level=flate_level)
        if len(encoded._data) + 30 < len(stream._data):
            encoded.indirect_reference = reference
            writer._objects[index] = encoded
    # pypdf hashes the decoded streams during this pass, even when only removing orphans.
    if before <= 150_000_000:
        # Separate optional-content groups can have identical dictionaries and still be distinct layers.
        writer.compress_identical_objects(remove_identicals="/OCProperties" not in writer.root_object, remove_orphans=True)
    if progress:
        progress(image_count + object_count, image_count + object_count)
    with TemporaryDirectory(prefix=".pdfiu-compresion-", dir=destination.parent) as folder:
        temporary = Path(folder) / "candidato.pdf"
        writer.write(temporary)
        after = temporary.stat().st_size
        if after >= before:
            if allow_larger:
                return before, before, len(optimized), resized
            raise ValueError(tr("Este perfil no reduce el tamaño del PDF original."))
        if len(reader_for(temporary).pages) != len(reader.pages):
            raise ValueError(tr("No se pudo conservar el número de páginas."))
        temporary.replace(destination)
    return before, after, len(optimized), resized


def protect_copy(source, destination, password):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    writer.encrypt(password, algorithm="AES-256")
    with atomic_output(destination) as temporary:
        writer.write(temporary)
        result = PdfReader(temporary)
        if not result.is_encrypted or not result.decrypt(password) or len(result.pages) != len(reader.pages):
            raise ValueError(tr("No se pudo comprobar la copia protegida."))


def load_stamp_image(stamp_path, *, remove_white=True):
    from PIL import Image

    stamp_path = Path(stamp_path)
    if not stamp_path.is_file():
        raise ValueError(tr("No se encontró el archivo de firma."))
    if stamp_path.suffix.casefold() == ".pdf":
        with pdfium_reader(stamp_path) as document:
            if len(document) < 1:
                raise ValueError(tr("El PDF de firma no contiene páginas."))
            image = render_page(document, 0, dpi=300)
        image = image.convert("RGBA")
    else:
        with Image.open(stamp_path) as opened:
            image = opened.convert("RGBA")
    if remove_white:
        cleaned = []
        pixels = image.get_flattened_data() if hasattr(image, "get_flattened_data") else image.getdata()
        for r, g, b, a in pixels:
            if a == 0:
                cleaned.append((r, g, b, 0))
                continue
            lum = (r * 299 + g * 587 + b * 114) // 1000
            if lum >= 242:
                cleaned.append((r, g, b, 0))
            elif lum >= 215:
                cleaned.append((r, g, b, int(a * (242 - lum) / 27)))
            else:
                cleaned.append((r, g, b, a))
        image.putdata(cleaned)
    bbox = image.getbbox()
    if bbox:
        image = image.crop(bbox)
    if image.width < 1 or image.height < 1:
        raise ValueError(tr("La imagen de firma está vacía."))
    return image


def add_signature_stamp(source, destination, page_index, box, stamp_path, *, remove_white=True):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    page = writer.pages[page_index]
    left, bottom, right, top = box
    box_w, box_h = max(1.0, right - left), max(1.0, top - bottom)
    image = load_stamp_image(stamp_path, remove_white=remove_white)
    scale = min(box_w / image.width, box_h / image.height)
    draw_w, draw_h = image.width * scale, image.height * scale
    draw_x = left + (box_w - draw_w) / 2
    draw_y = bottom + (box_h - draw_h) / 2

    page_w = float(page.mediabox.width)
    page_h = float(page.mediabox.height)
    overlay = BytesIO()
    canvas = Canvas(overlay, pagesize=(page_w, page_h), pageCompression=1)
    canvas.drawImage(ImageReader(image), draw_x, draw_y, width=draw_w, height=draw_h, mask="auto")
    canvas.save()
    overlay.seek(0)
    stamp_page = PdfReader(overlay).pages[0]
    page.merge_page(stamp_page)
    save_writer(writer, destination)


def redact_copy(source, destination, page_boxes, progress):
    from PIL import ImageDraw

    if not any(page_boxes.values()):
        raise ValueError(tr("Marca al menos una zona para censurar."))
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter()
    # Rebuild the page tree without document attachments, forms, or links to replaced pages.
    excluded = ("/Annots", "/AA", "/B", "/Metadata", "/PieceInfo", "/StructParents", "/AF", "/Thumb")
    with pdfium_reader(source) as document:
        for index, page in enumerate(reader.pages):
            progress(index + 1, len(reader.pages))
            boxes = page_boxes.get(index)
            if not boxes:
                writer.add_page(page, excluded_keys=excluded)
                continue
            image, coords = render_page(document, index, dpi=200, with_coordinates=True)
            brush = ImageDraw.Draw(image)
            for left, bottom, right, top in boxes:
                x, y = zip(*(coords.device(px, py) for px in (left, right) for py in (bottom, top)))
                brush.rectangle((floor(min(x)), floor(min(y)), ceil(max(x)), ceil(max(y))), fill="black")
            width, height = image.width * hypot(*coords.right), image.height * hypot(*coords.down)
            flattened = BytesIO()
            canvas = Canvas(flattened, pagesize=(width, height), pageCompression=1)
            canvas.drawImage(ImageReader(image), 0, 0, width, height)
            canvas.save()
            replacement = PdfReader(flattened)
            writer.add_page(replacement.pages[0])
            writer.reset_translation(replacement)
    save_writer(writer, destination)


def redact_searchable_copy(source, destination, page_boxes, tessdata, languages, progress):
    from shutil import copyfile

    total = len(reader_for(source).pages)
    marked = [index for index, boxes in page_boxes.items() if boxes]
    final_total = total + len(marked)
    with TemporaryDirectory(prefix=".pdfiu-censura-", dir=Path(destination).parent) as folder:
        raster = Path(folder) / "censurado.pdf"
        redact_copy(source, raster, page_boxes, lambda current, _: progress(current, final_total))
        recognized = ocr_document(
            raster, destination, tessdata, languages, lambda current, _: progress(total + current, final_total), indices=marked,
        )
        if not recognized:
            with atomic_output(destination) as temporary:
                copyfile(raster, temporary)
    return recognized


def annotation_overlay(page, draw):
    stream = BytesIO()
    canvas = Canvas(stream)
    draw(canvas)
    canvas.showPage()
    canvas.save()
    stream.seek(0)
    overlay = PdfReader(stream).pages[0]
    overlay.mediabox = RectangleObject(page.mediabox)
    overlay.cropbox = RectangleObject(page.cropbox)
    page.merge_page(overlay, over=True, expand=False)


def add_text(source, destination, index, coordinates, position, text, font_size):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    x, y = coordinates.at(*position)
    rx, ry = coordinates.right
    length = (rx * rx + ry * ry) ** 0.5
    rx, ry = rx / length, ry / length

    def draw(canvas):
        canvas.transform(rx, ry, -ry, rx, x, y)
        canvas.setFont("Helvetica", font_size)
        canvas.setFillColorRGB(0.08, 0.15, 0.21)
        for row, line in enumerate(text.splitlines()):
            canvas.drawString(0, -row * font_size * 1.25, line)

    annotation_overlay(writer.pages[index], draw)
    save_writer(writer, destination)


@dataclass(frozen=True)
class TextBlock:
    index: int
    value: str
    box: tuple


def text_block_at(source, index, x, y, *, password=None):
    with pdfium_reader(source, password=password) as document:
        page = document[index]
        try:
            with document_text_on_page(page) as textpage:
                char_index = textpage.get_index(x, y, 6, 6)
                picked = textpage.get_textobj(char_index) if char_index is not None else None
                if picked is None:
                    return None
                if pdfium.raw.FPDFTextObj_GetTextRenderMode(picked) in (3, 7):
                    raise ValueError(tr("Este texto es una capa OCR invisible. Editarlo no cambiaría la imagen de la página."))
                address = cast(picked.raw, c_void_p).value
                for position, item in enumerate(page.get_objects(max_depth=0, textpage=textpage)):
                    if cast(item.raw, c_void_p).value == address:
                        return TextBlock(position, item.extract(), item.get_bounds())
                raise ValueError(tr("Este texto forma parte de un objeto reutilizado. Abre el archivo de origen para editarlo."))
        finally:
            page.close()


@contextmanager
def document_text_on_page(page):
    content = page.get_textpage()
    try:
        yield content
    finally:
        content.close()


def replace_text_block(source, destination, index, block, replacement):
    reader = reader_for(source)
    check_editable(reader)
    if has_xfa(reader):
        raise ValueError(tr("Prepara primero una copia editable del formulario XFA."))
    replacement = replacement.strip("\r\n")
    with atomic_output(destination) as temporary:
        with pdfium_reader(source) as document:
            page = document[index]
            try:
                with document_text_on_page(page) as textpage:
                    objects = list(page.get_objects(max_depth=0, textpage=textpage))
                    item = objects[block.index]
                    if item.type != pdfium.raw.FPDF_PAGEOBJ_TEXT or item.extract() != block.value:
                        raise ValueError(tr("El bloque de texto cambió. Vuelve a seleccionarlo."))
                    if replacement:
                        origin = item.get_matrix()
                        encoded = (replacement + "\x00").encode("utf-16-le")
                        buffer = (pdfium.raw.FPDF_WCHAR * (len(encoded) // 2)).from_buffer_copy(encoded)
                        if not pdfium.raw.FPDFText_SetText(item, buffer):
                            raise ValueError(tr("La fuente de este PDF no admite el texto nuevo."))
                    else:
                        original_count = sum(obj.extract() == block.value for obj in objects
                                             if obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT)
                        page.remove_obj(item)
                page.gen_content()
                document.save(temporary)
            finally:
                page.close()
        result = reader_for(temporary)
        if len(result.pages) != len(reader.pages) or set(result.get_fields() or {}) != set(reader.get_fields() or {}):
            raise ValueError(tr("PDFiu no pudo conservar las páginas y los campos del documento."))
        with pdfium_reader(temporary) as document:
            page = document[index]
            try:
                with document_text_on_page(page) as textpage:
                    objects = [obj for obj in page.get_objects(max_depth=0, textpage=textpage)
                               if obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT]
                    if replacement:
                        matches = [obj.get_matrix() for obj in objects if obj.extract() == replacement]
                        if not any(abs(pos.e-origin.e) < 0.1 and abs(pos.f-origin.f) < 0.1 for pos in matches):
                            raise ValueError(tr("La fuente no pudo guardar ese texto. Prueba con otros caracteres."))
                    elif sum(obj.extract() == block.value for obj in objects) != original_count - 1:
                        raise ValueError(tr("No se pudo eliminar el bloque de texto."))
            finally:
                page.close()


def page_range(expression, count):
    if not expression.strip():
        return range(count)
    pages = set()
    for part in expression.split(","):
        ends = part.strip().split("-")
        if len(ends) > 2 or any(not end.strip().isdecimal() for end in ends):
            raise ValueError(tr("Indica páginas o rangos separados por comas, como 1,3-5,8."))
        start, stop = int(ends[0]), int(ends[-1])
        if not 1 <= start <= stop <= count:
            raise ValueError(tr("El intervalo {0} debe estar entre 1 y {1}.").format(part.strip(), count))
        pages.update(range(start - 1, stop))
    return sorted(pages)


HEADER_FAMILIES = {
    "Helvetica": ("Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"),
    "Times": ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic"),
    "Courier": ("Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique"),
}


@dataclass(frozen=True)
class HeaderRun:
    text: str
    family: str = "Helvetica"
    bold: bool = False
    italic: bool = False
    underline: bool = False

    @property
    def font(self):
        return HEADER_FAMILIES[self.family][int(self.bold) + 2 * int(self.italic)]


def expand_header_line(line, variables):
    value = "".join(run.text for run in line)
    styles = [run for run in line for _ in run.text]
    result = []

    def append(text, style):
        if not text:
            return
        font, underline = style.font, style.underline
        if result and result[-1][1:] == (font, underline):
            earlier, _, _ = result[-1]
            result[-1] = (earlier + text, font, underline)
        else:
            result.append((text, font, underline))

    offset = 0
    for match in re.finditer(r"\{(página|total|archivo)\}", value):
        for index in range(offset, match.start()):
            append(value[index], styles[index])
        append(variables[match[1]], styles[match.start()])
        offset = match.end()
    for index in range(offset, len(value)):
        append(value[index], styles[index])
    return result


def add_header_footer(source, destination, indices, text, header, alignment, margin_x, margin_y, size,
                      display_name=None, start_number=None):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    if isinstance(text, str):
        text = tuple((HeaderRun(line),) for line in text.split("\n"))
    for step, index in enumerate(indices):
        page = writer.pages[index]
        left, bottom, right, top = map(float, page.cropbox)
        rotation = page.rotation % 360
        transforms = {0: (1, 0, 0, 1, left, bottom), 90: (0, 1, -1, 0, right, bottom),
                      180: (-1, 0, 0, -1, right, top), 270: (0, -1, 1, 0, left, top)}
        width, height = (top-bottom, right-left) if rotation in (90, 270) else (right-left, top-bottom)
        variables = {
            "página": str(index + 1 if start_number is None else start_number + step),
            "total": str(len(writer.pages)),
            "archivo": Path(display_name or source).stem,
        }
        lines = [expand_header_line(line, variables) for line in text]
        widths = [sum(stringWidth(label, font, size) for label, font, _ in line) for line in lines]
        leading = size * 1.3
        block_height = size + (len(lines)-1) * leading
        margin = margin_x if alignment != "center" else 0
        if max(widths, default=0) + 2 * margin > width or margin_y + block_height > height:
            raise ValueError(tr("El texto o los márgenes no caben en la página {0}.").format(index + 1))

        def draw(canvas):
            canvas.transform(*transforms[rotation])
            first_y = height - margin_y - size if header else margin_y + (len(lines)-1) * leading
            for row, (line, line_width) in enumerate(zip(lines, widths)):
                y = first_y - row * leading
                x = {"left": margin_x, "center": (width-line_width)/2, "right": width-margin_x-line_width}[alignment]
                for label, font, underlined in line:
                    canvas.setFont(font, size)
                    canvas.drawString(x, y, label)
                    length = stringWidth(label, font, size)
                    if underlined:
                        canvas.setLineWidth(max(0.4, size * 0.055))
                        canvas.line(x, y - size*0.13, x + length, y - size*0.13)
                    x += length

        annotation_overlay(page, draw)
    save_writer(writer, destination)


def add_review_annotation(source, destination, index, boxes, note=None, *, underline=False):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    if note is not None:
        annotation = Text(rect=boxes[0], text=note, open=False)
    else:
        rect = (min(box[0] for box in boxes), min(box[1] for box in boxes),
                max(box[2] for box in boxes), max(box[3] for box in boxes))
        quad_points = ArrayObject(FloatObject(value) for l, b, r, t in boxes for value in (l, t, r, t, l, b, r, b))
        annotation = Highlight(rect=rect, quad_points=quad_points,
                               highlight_color="317f72" if underline else "ffe36e", printing=True)
        if underline:
            annotation[NameObject("/Subtype")] = NameObject("/Underline")
    writer.add_annotation(index, annotation)
    save_writer(writer, destination)


def add_batch_note(source, destination, pages, note):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    for index in page_range(pages, len(writer.pages)):
        crop = writer.pages[index].cropbox
        left, bottom, right, top = map(float, crop)
        width, height = min(18, (right - left) / 3), min(18, (top - bottom) / 3)
        box = (right - 2 * width, top - 2 * height, right - width, top - height)
        writer.add_annotation(index, Text(rect=box, text=note, open=False))
    save_writer(writer, destination)


REVIEW_TYPES = {"/Text": "Nota", "/Highlight": "Resaltado", "/Underline": "Subrayado",
                "/StrikeOut": "Tachado", "/Squiggly": "Subrayado ondulado", "/FreeText": "Texto",
                "/Ink": "Dibujo", "/Square": "Rectángulo", "/Circle": "Óvalo", "/Line": "Línea",
                "/Polygon": "Polígono"}


def add_surface_annotation(source, destination, page, points, label, measured, unit, color, opacity):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    xs, ys = zip(*points)
    left, bottom, right, top = min(xs)-1, min(ys)-1, max(xs)+1, max(ys)+1
    if len(points) < 3 or measured <= 0:
        raise ValueError(tr("Marca al menos tres vértices que formen una superficie."))
    annotation = Polygon(points)
    annotation.pop(NameObject("/IT"), None)
    annotation[NameObject("/Rect")] = RectangleObject((left, bottom, right, top))
    annotation[NameObject("/Vertices")] = ArrayObject(FloatObject(value) for point in points for value in point)
    annotation[NameObject("/C")] = ArrayObject(FloatObject(value) for value in color)
    annotation[NameObject("/IC")] = ArrayObject(FloatObject(value) for value in color)
    annotation[NameObject("/F")] = NumberObject(4)
    annotation[NameObject("/Contents")] = TextStringObject(f"{label} · {measured:.3f} {unit}")
    annotation[NameObject("/PDFiuSurface")] = DictionaryObject({
        NameObject("/Name"): TextStringObject(label),
        NameObject("/Area"): FloatObject(measured),
        NameObject("/Unit"): TextStringObject(unit),
    })
    vertices = [f"{x-left:.6f} {y-bottom:.6f}" for x, y in points]
    commands = vertices[0] + " m " + " ".join(vertex + " l" for vertex in vertices[1:])
    paint = " ".join(f"{channel:.5f}" for channel in color)
    graphics_state = DictionaryObject({NameObject("/CA"): FloatObject(0.8), NameObject("/ca"): FloatObject(opacity)})
    appearance = DecodedStreamObject()
    appearance.set_data(f"q /Transparencia gs {paint} RG {paint} rg 1.4 w {commands} h B Q".encode("ascii"))
    appearance.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): RectangleObject((0, 0, right-left, top-bottom)),
        NameObject("/Resources"): DictionaryObject({
            NameObject("/ExtGState"): DictionaryObject({NameObject("/Transparencia"): graphics_state}),
        }),
    })
    annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): writer._add_object(appearance)})
    writer.add_annotation(page, annotation)
    save_writer(writer, destination)


def surface_records(reader):
    for page, sheet in enumerate(reader.pages):
        for position, reference in enumerate(sheet.get("/Annots", ())):
            mark = reference.get_object()
            data = mark.get("/PDFiuSurface", mark.get("/FolioSurface"))
            if data is None:
                continue
            data = data.get_object()
            try:
                yield page, position, str(data["/Name"]), float(data["/Area"]), str(data["/Unit"]), tuple(
                    map(float, mark.get("/C", (0.2, 0.4, 0.7))),
                )
            except (KeyError, TypeError, ValueError):
                continue


def add_shape(source, destination, index, kind, start, end, color, *, stroke=2, opacity=1, dashed=False, filled=False):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    xs, ys = zip(start, end)
    pad = max(12 if kind == "arrow" else 2, stroke / 2 + 2)
    rect = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    if kind == "rectangle":
        annotation = Rectangle(rect)
    elif kind == "ellipse":
        annotation = Ellipse(rect)
    else:
        annotation = Line(start, end, rect)
        if kind == "arrow":
            annotation[NameObject("/LE")] = ArrayObject([NameObject("/None"), NameObject("/OpenArrow")])
    annotation[NameObject("/C")] = ArrayObject(FloatObject(value) for value in color)
    filled = filled and kind in ("rectangle", "ellipse")
    if filled:
        annotation[NameObject("/IC")] = ArrayObject(FloatObject(value) for value in color)
    border = DictionaryObject({NameObject("/W"): FloatObject(stroke)})
    if dashed:
        border[NameObject("/S")] = NameObject("/D")
        border[NameObject("/D")] = ArrayObject([FloatObject(stroke*3), FloatObject(stroke*2)])
    annotation[NameObject("/BS")] = border
    annotation[NameObject("/CA")] = FloatObject(opacity)
    annotation[NameObject("/F")] = NumberObject(4)
    shape_appearance(writer, annotation, kind, rect, start, end, color, stroke, pad, opacity, dashed, filled)
    writer.add_annotation(index, annotation)
    save_writer(writer, destination)


def shape_appearance(writer, annotation, kind, rect, start, end, color, stroke, pad, opacity, dashed, filled):
    left, bottom, right, top = rect
    width, height = right - left, top - bottom
    red, green, blue = color
    if kind == "rectangle":
        path = f"{pad} {pad} {width-2*pad} {height-2*pad} re"
    elif kind == "ellipse":
        cx, cy = width/2, height/2
        rx, ry = cx-pad, cy-pad
        kx, ky = rx*0.552285, ry*0.552285
        path = (f"{cx+rx} {cy} m {cx+rx} {cy+ky} {cx+kx} {cy+ry} {cx} {cy+ry} c "
                f"{cx-kx} {cy+ry} {cx-rx} {cy+ky} {cx-rx} {cy} c "
                f"{cx-rx} {cy-ky} {cx-kx} {cy-ry} {cx} {cy-ry} c "
                f"{cx+kx} {cy-ry} {cx+rx} {cy-ky} {cx+rx} {cy} c h")
    else:
        x1, y1 = start[0]-left, start[1]-bottom
        x2, y2 = end[0]-left, end[1]-bottom
        path = f"{x1} {y1} m {x2} {y2} l"
        if kind == "arrow":
            length = hypot(x2-x1, y2-y1)
            if length > 0:
                ux, uy = (x2-x1)/length, (y2-y1)/length
                size = min(10, length/2)
                bx, by = x2-size*ux, y2-size*uy
                path += f" {bx-size*0.5*uy} {by+size*0.5*ux} m {x2} {y2} l {bx+size*0.5*uy} {by-size*0.5*ux} l"
    appearance = DecodedStreamObject()
    dash = f"[{stroke*3} {stroke*2}] 0 d" if dashed else ""
    fill_color = f"{red} {green} {blue} rg" if filled else ""
    appearance.set_data(
        f"q /PDFiuOpacity gs {red} {green} {blue} RG {fill_color} {stroke} w 1 J 1 j {dash} {path} {'B' if filled else 'S'} Q".encode("ascii")
    )
    graphics_state = DictionaryObject({NameObject("/Type"): NameObject("/ExtGState"),
                                       NameObject("/CA"): FloatObject(opacity),
                                       NameObject("/ca"): FloatObject(opacity * 0.24)})
    resources = DictionaryObject({NameObject("/ExtGState"): DictionaryObject({NameObject("/PDFiuOpacity"): graphics_state})})
    appearance.update({NameObject("/Type"): NameObject("/XObject"), NameObject("/Subtype"): NameObject("/Form"),
                       NameObject("/BBox"): RectangleObject((0, 0, width, height)),
                       NameObject("/Resources"): resources})
    annotation[NameObject("/AP")] = DictionaryObject({NameObject("/N"): writer._add_object(appearance)})


def review_annotations(path, *, password=None):
    reader = reader_for(path, allow_empty_password=True, password=password)
    for index, page in enumerate(reader.pages):
        for position, ref in enumerate(page.get("/Annots", ())):
            annotation = ref.get_object()
            kind = REVIEW_TYPES.get(annotation.get("/Subtype"))
            if kind:
                if kind == "Línea" and "/OpenArrow" in annotation.get("/LE", ()):
                    kind = "Flecha"
                yield index, position, tr(kind), str(annotation.get("/Contents") or "")


def remove_review_annotation(source, destination, index, position):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    annotations = writer.pages[index]["/Annots"]
    target = annotations[position]
    if target.get_object().get("/Subtype") not in REVIEW_TYPES:
        raise ValueError(tr("La anotación seleccionada no se puede eliminar desde este panel."))
    related = [target]
    for ref in annotations:
        annotation = ref.get_object()
        if annotation.get("/Parent") == target or annotation.get("/IRT") == target:
            related.append(ref)
    writer.pages[index][NameObject("/Annots")] = ArrayObject(ref for ref in annotations if ref not in related)
    writer.compress_identical_objects(remove_identicals=False, remove_orphans=True)
    save_writer(writer, destination)


def change_annotation_box(source, destination, index, position, *, center=None, rect=None):
    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    page = writer.pages[index]
    annotation = page["/Annots"][position].get_object()
    kind = annotation.get("/Subtype")
    if kind not in ("/Line", "/Square", "/Circle", "/Text") or (rect and kind == "/Text"):
        raise ValueError(tr("Esta operación se aplica a notas y formas. Solo las formas se pueden redimensionar."))
    x1, y1, x2, y2 = map(float, annotation["/Rect"])
    if center is not None:
        x, y = center
        rect = (x - (x2-x1)/2, y - (y2-y1)/2, x + (x2-x1)/2, y + (y2-y1)/2)
    left, bottom, right, top = map(float, rect)
    crop = page.cropbox
    if (min(right-left, top-bottom, x2-x1, y2-y1) <= 0
            or left < float(crop.left) or bottom < float(crop.bottom)
            or right > float(crop.right) or top > float(crop.top)):
        raise ValueError(tr("La anotación debe caber dentro de la página."))
    annotation[NameObject("/Rect")] = RectangleObject(rect)
    if "/L" in annotation:
        line = list(map(float, annotation["/L"]))
        for i in (0, 2):
            line[i] = left + (line[i]-x1)/(x2-x1)*(right-left)
            line[i+1] = bottom + (line[i+1]-y1)/(y2-y1)*(top-bottom)
        annotation[NameObject("/L")] = ArrayObject(FloatObject(value) for value in line)
    save_writer(writer, destination)


def batch_header_footer(sources, directory, expression, settings, progress):
    directory = Path(directory)
    jobs = []
    reserved = {path.name.casefold() for path in directory.iterdir()}
    for source in sources:
        source = Path(source)
        try:
            reader = reader_for(source)
            check_editable(reader)
            indices = page_range(expression, len(reader.pages))
        except Exception as error:
            raise ValueError(f"{source.name}: {error}") from error
        stem = tr("{0} - con encabezado o pie").format(source.stem)
        name = f"{stem}.pdf"
        suffix = 2
        while name.casefold() in reserved:
            name = f"{stem} ({suffix}).pdf"
            suffix += 1
        reserved.add(name.casefold())
        jobs.append((source, indices, name))
    with TemporaryDirectory(prefix=".pdfiu-lote-", dir=directory) as staging:
        staging = Path(staging)
        for index, (source, indices, name) in enumerate(jobs, 1):
            progress(index, len(jobs))
            try:
                add_header_footer(source, staging / name, indices, *settings)
            except Exception as error:
                raise ValueError(f"{source.name}: {error}") from error
        saved = []
        for _, _, name in jobs:
            try:
                (staging / name).rename(directory / name)
            except OSError as error:
                raise ValueError(tr("Se guardaron {0} de {1} copias: {2}").format(len(saved), len(jobs), error)) from error
            saved.append(directory / name)
    return saved


def workspace_batch_copies(entries, directory, suffix, process, progress, *, extension="pdf"):
    directory = Path(directory)
    saved, skipped, failures, cancelled = [], [], [], []
    reserved = {path.name.casefold() for path in directory.iterdir()}
    with TemporaryDirectory(prefix=".pdfiu-lote-", dir=directory) as staging:
        for index, (source, name) in enumerate(entries, 1):
            pending = Path(staging) / f"{index}.{extension}"
            try:
                progress(index, len(entries))
                outputs = process(source, pending, name)
                if outputs is None and pending.is_file():
                    separator = "" if suffix.startswith("_") else " - "
                    outputs = [(pending, f"{Path(name).stem}{separator}{suffix}.{extension}")]
                if not outputs:
                    skipped.append(name)
                    continue
                for staged, filename in outputs:
                    destination = directory / filename
                    counter = 2
                    stem, ext = destination.stem, destination.suffix
                    while True:
                        if destination.name.casefold() not in reserved:
                            try:
                                with destination.open("xb"):
                                    pass
                            except FileExistsError:
                                pass
                            else:
                                break
                        destination = directory / f"{stem} ({counter}){ext}"
                        counter += 1
                    try:
                        os.replace(staged, destination)
                    except OSError:
                        destination.unlink(missing_ok=True)
                        raise
                    reserved.add(destination.name.casefold())
                    saved.append(destination)
            except OperationCancelled:
                cancelled.extend(name for _, name in entries[index - 1:])
                break
            except Exception as error:
                failures.append((name, str(error) or type(error).__name__))
    return saved, skipped, failures, cancelled


def ocr_document(source, destination, tessdata, languages, progress, *, indices=None):
    import csv
    import tesserocr

    reader = reader_for(source)
    check_editable(reader)
    writer = PdfWriter(clone_from=reader)
    covered = 0
    indices = range(len(writer.pages)) if indices is None else indices
    with pdfium_reader(source) as document, tesserocr.PyTessBaseAPI(path=str(tessdata), lang=languages) as api:
        for done, index in enumerate(indices, 1):
            target = writer.pages[index]
            progress(done, len(indices))
            if (reader.pages[index].extract_text() or "").strip():
                continue
            image, coords = render_page(document, index, dpi=240, with_coordinates=True)
            api.SetImage(image)
            if not api.Recognize():
                raise ValueError(tr("No se pudo reconocer la página {0}.").format(index + 1))
            columns = ("level", "page", "block", "paragraph", "line", "word", "left", "top", "width", "height", "confidence", "text")
            rows = csv.DictReader(api.GetTSVText(0).splitlines(), fieldnames=columns, delimiter="\t", quoting=csv.QUOTE_NONE)
            words = [row for row in rows if row.get("level") == "5" and (row.get("text") or "").strip()]
            if not words:
                continue

            def draw(canvas):
                rx, ry = coords.right
                dx, dy = coords.down
                base_scale = (rx * rx + ry * ry) ** 0.5
                size_scale = (dx * dx + dy * dy) ** 0.5
                rx, ry = rx / base_scale, ry / base_scale
                for row in words:
                    word = row["text"].strip()
                    left, top, width, height = (int(row[key]) for key in ("left", "top", "width", "height"))
                    x, y = coords.at(left, top + height * 0.85)
                    size = max(height * size_scale, 1)
                    measured = stringWidth(word, "Helvetica", size)
                    if measured <= 0 or width <= 0:
                        continue
                    canvas.saveState()
                    canvas.transform(rx, ry, -ry, rx, x, y)
                    line = canvas.beginText(0, 0)
                    line.setTextRenderMode(3)
                    line.setFont("Helvetica", size)
                    line.setHorizScale(width * base_scale / measured * 100)
                    line.textOut(word)
                    canvas.drawText(line)
                    canvas.restoreState()

            annotation_overlay(target, draw)
            covered += 1
    if covered:
        save_writer(writer, destination)
    return covered
