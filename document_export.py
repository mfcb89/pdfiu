from translations import tr

import csv
import re
from collections import Counter
from contextlib import ExitStack, closing

from pdf_ops import atomic_output, pdfium_reader, render_page


def export_document(source, destination, kind, indices, progress, *, tessdata=None, language="spa+eng",
                    unruled=False, formatted=False):
    if kind in ("xlsx", "csv"):
        return export_tables(source, destination, kind, indices, progress, unruled)
    if kind == "docx" and formatted:
        from word_export import export_formatted_word

        return export_formatted_word(source, destination, indices, progress)
    return export_text(source, destination, kind, indices, progress, tessdata, language)


def export_text(source, destination, kind, indices, progress, tessdata, language):
    word = None
    if kind == "docx":
        from docx import Document

        word = Document()
    text_pages, skipped = [], []
    pages = text_blocks(source, indices, progress, structured=word is not None, tessdata=tessdata, language=language)
    with closing(pages), atomic_output(destination) as temporary:
        for done, (index, blocks) in enumerate(pages, 1):
            if not blocks:
                skipped.append(index + 1)
                continue
            if word is None:
                text_pages.append("\n\n".join(content for _, content in blocks))
            else:
                if done - len(skipped) > 1:
                    word.add_page_break()
                for _, content in blocks:
                    if isinstance(content, str):
                        word.add_paragraph(xml_text(content))
                    else:
                        table = word.add_table(rows=0, cols=max(map(len, content)))
                        table.style = "Table Grid"
                        for values in content:
                            for cell, value in zip(table.add_row().cells, values):
                                cell.text = xml_text(value or "")
        if len(skipped) == len(indices):
            raise ValueError(tr("No se encontró texto en las páginas seleccionadas. Prueba el OCR o elige otras páginas."))
        if word is None:
            temporary.write_text("\n\n".join(text_pages) + "\n", encoding="utf-8")
        else:
            word.save(temporary)
    return skipped


def text_blocks(source, indices, progress, *, structured, tessdata, language, markdown=False):
    import pdfplumber

    with ExitStack() as stack:
        pdf = stack.enter_context(pdfplumber.open(source))
        ocr = None
        for done, index in enumerate(indices, 1):
            progress(done, len(indices))
            original = pdf.pages[index]
            try:
                page = original.dedupe_chars()
                if structured:
                    blocks = structured_blocks(page, markdown=markdown)
                else:
                    plain_text = (page.extract_text() or "").strip()
                    blocks = [(0, plain_text)] if plain_text else []
                if not blocks and tessdata is not None:
                    if ocr is None:
                        import tesserocr

                        rendered = stack.enter_context(pdfium_reader(source))
                        ocr = stack.enter_context(tesserocr.PyTessBaseAPI(path=str(tessdata), lang=language))
                    ocr.SetImage(render_page(rendered, index, dpi=240))
                    blocks = split_paragraphs((ocr.GetUTF8Text() or "").strip())
                    if markdown:
                        blocks = [(top, markdown_paragraph(content.splitlines())) for top, content in blocks]
            finally:
                original.close()
            yield index, blocks


def markdown_from_pdf(source, title, indices, progress, *, tessdata=None, language="spa+eng"):
    sections, skipped = [], []
    pages = text_blocks(source, indices, progress, structured=True, tessdata=tessdata, language=language, markdown=True)
    with closing(pages):
        for index, blocks in pages:
            if not blocks:
                skipped.append(index + 1)
                continue
            sections.append(f"## Página {index + 1}")
            sections.extend(content if isinstance(content, str) else markdown_table(content)
                            for _, content in blocks)
    if not sections:
        raise ValueError(tr("No se encontró texto en las páginas seleccionadas. Prueba el OCR o elige otras páginas."))
    return "\n\n".join([f"# {markdown_text(title)}", *sections]) + "\n", skipped


def markdown_text(value):
    value = " ".join(xml_text(value).split())
    value = re.sub(r"([\\`*_{}\[\]<>#|~!&])", r"\\\1", value)
    return re.sub(r"^([0-9]{1,9})([.)])(?= )|^([-+=])(?= |$)", r"\1\\\2\3", value)


def markdown_table(rows):
    width = max(map(len, rows))

    def line(values):
        return "| " + " | ".join(values + [""] * (width - len(values))) + " |"

    header, *body = ([markdown_text(value or "") for value in row] for row in rows)
    return "\n".join([line(header), line(["---"] * width), *(line(row) for row in body)])


LIST_ITEM = re.compile(r"^([-+*•▪]|[0-9]{1,9}[.)]|[a-zA-Z]\))\s+(\S.*)")
BOLD_FONT = re.compile(r"bold|black|demi|heavy", re.I)


def markdown_paragraph(lines):
    if not any(LIST_ITEM.match(line.strip()) for line in lines):
        return markdown_text(" ".join(lines))
    result = []
    for line in lines:
        item = LIST_ITEM.match(line.strip())
        if item:
            marker, content = item.groups()
            if marker in ("•", "▪", "*", "+", "-"):
                result.append(f"- {markdown_text(content)}")
            elif marker[0].isdecimal():
                result.append(f"{marker} {markdown_text(content)}")
            else:
                result.append(f"- {marker} {markdown_text(content)}")
        elif line.strip():
            if result:
                result[-1] += " " + markdown_text(line)
            else:
                result.append(markdown_text(line))
    return "\n".join(result)


def heading_level(line, body_size):
    chars = [char for char in line["chars"] if char["text"].strip()]
    if not chars or len(line["text"]) > 110 or LIST_ITEM.match(line["text"]):
        return 0
    size = Counter(round(char["size"], 1) for char in chars).most_common(1)[0][0]
    if size >= body_size * 1.38:
        return 3
    bold = sum(bool(BOLD_FONT.search(char["fontname"] or "")) for char in chars)
    return 4 if size >= body_size * 1.16 and bold > len(chars) * 0.8 else 0


def split_paragraphs(text):
    return [(0, part.strip()) for part in re.split(r"\n\s*\n", text) if part.strip()]


def structured_blocks(page, *, markdown=False):
    tables = [(table.bbox, table.extract()) for table in page.find_tables()]
    tables = [(box, rows) for box, rows in tables if any(value for row in rows for value in row)]

    def outside_tables(obj):
        if obj["object_type"] != "char":
            return True
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(left <= x <= right and top <= y <= bottom for (left, top, right, bottom), _ in tables)

    blocks = [(box[1], rows) for box, rows in tables]
    lines = page.filter(outside_tables).extract_text_lines(return_chars=markdown)
    body_sizes = Counter(round(char["size"], 1) for char in page.chars if char["text"].strip()) if markdown else {}
    body_size = body_sizes.most_common(1)[0][0] if body_sizes else 0
    paragraph, previous = [], None

    def append_paragraph():
        blocks.append((top, markdown_paragraph(paragraph) if markdown else " ".join(paragraph)))
        paragraph.clear()

    for line in lines:
        level = heading_level(line, body_size) if body_size else 0
        if level:
            if paragraph:
                append_paragraph()
            blocks.append((line["top"], f"{'#' * level} {markdown_text(line['text'])}"))
            previous = None
            continue
        if previous:
            gap = line["top"] - previous["bottom"]
            height = previous["bottom"] - previous["top"]
            if gap > max(4, height * 0.6) or abs(line["x0"] - previous["x0"]) > 15:
                append_paragraph()
        if not paragraph:
            top = line["top"]
        paragraph.append(line["text"])
        previous = line
    if paragraph:
        append_paragraph()
    return sorted(blocks, key=lambda block: block[0])


def export_tables(source, destination, kind, indices, progress, unruled):
    import pdfplumber

    workbook = None
    if kind == "xlsx":
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell

        workbook = Workbook(write_only=True)
    skipped = []
    with pdfplumber.open(source) as pdf, atomic_output(destination) as temporary, ExitStack() as stack:
        if workbook is None:
            stream = stack.enter_context(temporary.open("w", encoding="utf-8-sig", newline=""))
            csv_writer = csv.writer(stream, delimiter=";")
        table_count = 0
        for done, index in enumerate(indices, 1):
            progress(done, len(indices))
            original = pdf.pages[index]
            try:
                page = original.dedupe_chars()
                tables = [rows for rows in page.extract_tables() if any(value for row in rows for value in row)]
                if not tables and unruled:
                    aligned = page.extract_tables({
                        "vertical_strategy": "text", "horizontal_strategy": "text",
                        "min_words_vertical": 3, "min_words_horizontal": 2,
                    })
                    tables = [[row for row in rows if any(row)] for rows in aligned if meaningful_table(rows)]
            finally:
                original.close()
            if not tables:
                skipped.append(index + 1)
            for position, rows in enumerate(tables, 1):
                table_count += 1
                if workbook is None:
                    if table_count > 1:
                        csv_writer.writerow([])
                    csv_writer.writerows([csv_value(value) for value in row] for row in rows)
                    continue
                sheet = workbook.create_sheet(tr("Página {0} tabla {1}").format(index + 1, position))
                for row in rows:
                    cells = []
                    for value in row:
                        if value is None:
                            cells.append(None)
                            continue
                        numeric = number(value)
                        if numeric is not None:
                            cells.append(numeric)
                        else:
                            cell = WriteOnlyCell(sheet, value=xml_text(value))
                            cell.data_type = "s"
                            cells.append(cell)
                    sheet.append(cells)
        if not table_count:
            raise ValueError(tr("No se detectaron tablas. Prueba con tablas sin bordes o aplica OCR si el PDF está escaneado."))
        if workbook is not None:
            workbook.save(temporary)
    return skipped


def meaningful_table(rows):
    return sum(sum(bool(value and value.strip()) for value in row) >= 2 for row in rows) >= 2


def number(value):
    text = value.strip()
    if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:[,.][0-9]+)?", text):
        return None
    integer, point, fraction = text.replace(",", ".").partition(".")
    if len(integer.lstrip("-") + fraction) > 15 or (len(fraction) == 3 and integer.lstrip("-") != "0"):
        return None
    return float(f"{integer}.{fraction}") if point else int(integer)


def csv_value(value):
    if value and value.lstrip().startswith(("=", "+", "-", "@")) and number(value) is None:
        return "'" + value
    return value


def xml_text(value):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "", value)
