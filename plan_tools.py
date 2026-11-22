from translations import tr

from math import hypot
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject

from pdf_ops import add_header_footer, check_editable, ocr_document, pdf_image_usage, reader_for, save_writer


def measured_value(points, kind, meters_per_point):
    if kind == "distance":
        start, end = points
        return hypot(end[0] - start[0], end[1] - start[1]) * meters_per_point
    sides = zip(points, points[1:] + points[:1])
    if kind == "perimeter":
        return sum(hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in sides) * meters_per_point
    return abs(sum(x1*y2 - x2*y1 for (x1, y1), (x2, y2) in sides)) * meters_per_point**2 / 2


def inspect_document(path, progress):
    reader = reader_for(path)
    pages = []
    for index, page in enumerate(reader.pages):
        progress(index + 1, len(reader.pages))
        crop = page.cropbox
        unit = float(page.get("/UserUnit", 1)) * 25.4 / 72
        width, height = float(crop.width)*unit, float(crop.height)*unit
        if page.rotation % 180:
            width, height = height, width
        pages.append({"size": (width, height), "images": [], "fonts": page_fonts(page)})

    def report(page, stream, inches):
        width, height = int(stream["/Width"]), int(stream["/Height"])
        x, y = inches
        if x > 0 and y > 0:
            pages[page]["images"].append((width, height, width/x, height/y))

    pdf_image_usage(reader, on_image=report)
    return pages


def page_fonts(page):
    found = {}
    seen = set()

    def visit(resources):
        if id(resources) in seen or len(seen) >= 1000:
            return
        seen.add(id(resources))
        for reference in resources.get("/Font", DictionaryObject()).get_object().values():
            font = reference.get_object()
            descendants = font.get("/DescendantFonts")
            family = str(font.get("/BaseFont") or font.get("/Name") or tr("Sin nombre")).lstrip("/")
            descriptor = (descendants[0].get_object() if descendants else font).get("/FontDescriptor")
            embedded = (font.get("/Subtype") == "/Type3" or bool(
                descriptor and any(key in descriptor.get_object() for key in ("/FontFile", "/FontFile2", "/FontFile3"))
            ))
            found[family] = found.get(family, True) and embedded
        for reference in resources.get("/XObject", DictionaryObject()).get_object().values():
            obj = reference.get_object()
            if obj.get("/Subtype") == "/Form" and "/Resources" in obj:
                visit(obj["/Resources"])

    visit(page.get("/Resources", DictionaryObject()).get_object())
    return sorted(found.items())


def layer_list(path, *, password=None):
    reader = reader_for(path, allow_empty_password=True, password=password)
    catalog = reader.root_object.get("/OCProperties")
    if not catalog:
        return []
    catalog = catalog.get_object()
    configuration = catalog.get("/D", DictionaryObject()).get_object()
    active = set(ref.idnum for ref in configuration.get("/ON", ()) if hasattr(ref, "idnum"))
    inactive = set(ref.idnum for ref in configuration.get("/OFF", ()) if hasattr(ref, "idnum"))
    locked = set(ref.idnum for ref in configuration.get("/Locked", ()) if hasattr(ref, "idnum"))
    initial = configuration.get("/BaseState") != "/OFF"
    return [(str(ref.get_object().get("/Name") or f"Capa {index + 1}"),
             ref.idnum in active or (initial and ref.idnum not in inactive), ref.idnum in locked)
            for index, ref in enumerate(catalog.get("/OCGs", ())) if hasattr(ref, "idnum")]


def layer_preview(source, destination, visibility, *, password=None):
    writer = PdfWriter(clone_from=reader_for(source, allow_empty_password=True, password=password))
    catalog = writer.root_object["/OCProperties"]
    configuration = catalog.get("/D", DictionaryObject()).get_object()
    catalog[NameObject("/D")] = configuration
    pages = [ref for ref in catalog.get("/OCGs", ()) if hasattr(ref, "idnum")]
    configuration[NameObject("/BaseState")] = NameObject("/OFF")
    configuration[NameObject("/ON")] = ArrayObject(ref for ref, checked in zip(pages, visibility) if checked)
    configuration[NameObject("/OFF")] = ArrayObject(ref for ref, checked in zip(pages, visibility) if not checked)
    save_writer(writer, destination)


def prepare_recipe(inputs, folder, tessdata, languages, ocr, numbering, progress):
    folder = Path(folder)
    used = {file.name.casefold() for file in folder.iterdir()}
    with TemporaryDirectory(prefix=".folio-proceso-", dir=folder) as directory:
        staging = Path(directory)
        outputs = []
        for index, (source, display_name) in enumerate(inputs):
            progress(index + 1, len(inputs))
            stem = f"{Path(display_name).stem} - preparado"
            name = f"{stem}.pdf"
            count = 2
            while name.casefold() in used:
                name = f"{stem} ({count}).pdf"
                count += 1
            used.add(name.casefold())
            try:
                document = reader_for(source)
                check_editable(document)
                count = len(document.pages)
                scanned = staging / f"ocr-{index}.pdf"
                prepared = staging / name
                current = source
                if ocr and ocr_document(source, scanned, tessdata, languages, lambda *_: None):
                    current = scanned
                if numbering:
                    add_header_footer(current, prepared, range(count), "{página}", False, "center", 24, 24, 10)
                else:
                    copyfile(current, prepared)
                outputs.append(prepared)
            except Exception as error:
                raise ValueError(f"{display_name}: {error}") from error
        saved = []
        for output in outputs:
            final = folder / output.name
            try:
                if final.exists():
                    raise FileExistsError(final.name)
                output.rename(final)
            except OSError as error:
                raise ValueError(tr("Se publicaron {0} de {1} archivos: {2}").format(len(saved), len(outputs), error)) from error
            saved.append(final)
        return saved
