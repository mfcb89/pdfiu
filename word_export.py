from contextlib import closing
from io import BytesIO
import re

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from pdfplumber import open as open_pdf

from document_export import xml_text
from pdf_ops import atomic_output, pdfium_reader


def export_formatted_word(source, destination, indices, progress):
    word = Document()
    normal = word.styles["Normal"]
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    normal.paragraph_format.keep_together = False
    with open_pdf(source) as pdf, pdfium_reader(source) as renderer, atomic_output(destination) as output:
        for done, index in enumerate(indices, 1):
            progress(done, len(indices))
            page = pdf.pages[index]
            with closing(renderer[index]) as visual:
                section = word.sections[0] if done == 1 else word.add_section(WD_SECTION.NEW_PAGE)
                write_page(word, section, page, visual)
            page.close()
        word.save(output)
    return []


def box_of(obj):
    return tuple(obj[edge] for edge in ("x0", "top", "x1", "bottom"))


def intersection(a, b):
    return max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def includes(box, char):
    x, y = (char["x0"] + char["x1"]) / 2, (char["top"] + char["bottom"]) / 2
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def background_for(rectangles, box):
    box_area = area(box)
    for rect_box, color in rectangles:
        if area(intersection(rect_box, box)) >= box_area * 0.95:
            return color
    return None


def shade(properties, color, *before):
    if color is not None:
        element = OxmlElement("w:shd")
        element.set(qn("w:fill"), str(color))
        properties.insert_element_before(element, *before)


def write_page(word, section, original, visual):
    bounds = intersection(original.bbox, original.cropbox or original.bbox)
    if not area(bounds):
        bounds = original.bbox
    page = original.crop(bounds).dedupe_chars()
    left, top, right, bottom = bounds
    width, height = right - left, bottom - top
    # Word's page dimension limit is 22 inches. Scale oversized plans proportionally.
    factor = min(1, 22 * 72 / max(width, height))
    section.page_width, section.page_height = Pt(width * factor), Pt(height * factor)
    tables = [table for table in page.find_tables() if any(value for row in table.extract() for value in row)]
    prose = page.filter(lambda obj: obj["object_type"] != "char"
                        or not any(includes(table.bbox, obj) for table in tables))
    lines = [line for line in prose.extract_text_lines() if line["text"].strip()]
    images = sorted({box_of(image) for image in page.images if area(box_of(image)) >= 16})
    rectangles = [(box_of(rect), color) for rect in reversed(page.rects)
                  if rect.get("fill") and (color := rgb(rect.get("non_stroking_color"))) is not None]
    if not lines and not tables:
        # Keep scans and drawings as a complete image when there's no native editable content.
        section.left_margin = section.right_margin = section.top_margin = section.bottom_margin = Pt(0)
        add_picture(word, visual, bounds, bounds, width * factor * max(0.5, 1 - 4 / height))
        return

    blocks = [(box_of(line), "line", line) for line in lines]
    blocks.extend((table.bbox, "table", table) for table in tables)
    blocks.extend((image, "image", image) for image in images
                  if area(image) < width * height * 0.92 and
                  not any(area(intersection(image, table.bbox)) >= area(image) * 0.8 for table in tables))
    margin_left = min(60, max(0, min(box[0] for box, _, _ in blocks) - left))
    margin_right = min(60, max(0, right - max(box[2] for box, _, _ in blocks)))
    margin_top = min(72, max(0, min(box[1] for box, _, _ in blocks) - top))
    margin_bottom = min(48, max(0, bottom - max(box[3] for box, _, _ in blocks) - 8))
    section.left_margin, section.right_margin = Pt(margin_left * factor), Pt(margin_right * factor)
    section.top_margin, section.bottom_margin = Pt(margin_top * factor), Pt(margin_bottom * factor)
    origin = left + margin_left

    previous = (origin, top + margin_top, origin, top + margin_top)
    for box, kind, content in sorted(blocks, key=lambda block: (block[0][1], block[0][0])):
        indent = max(0, box[0] - origin) * factor
        before = min(144, max(0, box[1] - previous[3])) * factor
        available = max(1, (right - margin_right - box[0]) * factor)
        if kind == "line":
            paragraph = word.add_paragraph()
            paragraph.paragraph_format.space_before = Pt(before)
            paragraph.paragraph_format.left_indent = Pt(indent)
            paragraph.paragraph_format.line_spacing = Pt(max(1, (box[3] - box[1]) * factor * 1.06))
            shade(paragraph._p.get_or_add_pPr(), background_for(rectangles, box),
                  "w:tabs", "w:spacing", "w:ind", "w:jc")
            styled_runs(paragraph, content["chars"], factor)
        elif kind == "image":
            paragraph = add_picture(word, visual, bounds, box, min((box[2] - box[0]) * factor, available))
            paragraph.paragraph_format.left_indent = Pt(indent)
            paragraph.paragraph_format.space_before = Pt(before)
        else:
            if before > 5:
                spacer = word.add_paragraph()
                spacer.paragraph_format.line_spacing = Pt(before)
            add_table(word, page, content, indent, factor, rectangles)
        previous = box


def add_picture(word, visual, bounds, box, width):
    x0, y0, x1, y1 = bounds
    left, top, right, bottom = box
    scale = min(2, 3600 / max(x1 - x0, y1 - y0))
    crop = left - x0, y1 - bottom, x1 - right, top - y0
    with closing(visual.render(scale=scale, crop=crop, draw_annots=False)) as bitmap:
        pixels = bitmap.to_pil().convert("RGB")
        data = BytesIO()
        pixels.save(data, "PNG")
    paragraph = word.add_paragraph()
    paragraph.add_run().add_picture(data, width=Pt(width))
    return paragraph


def add_table(word, page, source, indent, factor, rectangles):
    positions = sorted({round(edge, 1) for cell in source.cells for edge in (cell[0], cell[2])})
    table = word.add_table(rows=len(source.rows), cols=len(positions) - 1)
    table.style = "Table Grid"
    table.autofit = False
    indent_node = OxmlElement("w:tblInd")
    indent_node.set(qn("w:w"), str(round(indent * 20)))
    indent_node.set(qn("w:type"), "dxa")
    table._tbl.tblPr.insert_element_before(indent_node, "w:tblBorders", "w:tblLayout", "w:tblLook")
    for col, (left, right) in zip(table.columns, zip(positions, positions[1:])):
        col.width = Pt((right - left) * factor)
        for cell in col.cells:
            cell.width = col.width
    for row, source_row in enumerate(source.rows):
        for box in filter(None, source_row.cells):
            start, end = (positions.index(round(edge, 1)) for edge in (box[0], box[2]))
            if start == end:
                continue
            cell = table.cell(row, start)
            if end > start + 1:
                cell = cell.merge(table.cell(row, end - 1))
            content = page.crop(box).extract_text_lines()
            for index, line in enumerate(content):
                paragraph = cell.add_paragraph() if index else cell.paragraphs[0]
                styled_runs(paragraph, [char for char in line["chars"] if includes(box, char)], factor)
                if line["x0"] - box[0] > 4 and box[2] - line["x1"] <= 4:
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            shade(cell._tc.get_or_add_tcPr(), background_for(rectangles, box),
                  "w:noWrap", "w:tcMar", "w:textDirection", "w:vAlign")


FONT_FAMILIES = {"helvetica": "Arial", "times": "Times New Roman", "courier": "Courier New"}


def rgb(color):
    if isinstance(color, (float, int)):
        color = (color,)
    if not isinstance(color, (tuple, list)) or not all(isinstance(v, (int, float)) for v in color):
        return None
    if len(color) == 1:
        color *= 3
    elif len(color) == 4:
        c, m, y, k = color
        color = tuple((1 - value) * (1 - k) for value in (c, m, y))
    if len(color) == 3:
        return RGBColor(*(round(255 * min(1, max(0, value))) for value in color))
    return None


def style_of(char, factor):
    name = (char.get("fontname") or "").split("+")[-1]
    name = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", name)
    bold = bool(re.search("bold|black|demi|heavy", name, re.I))
    italic = bool(re.search("italic|oblique", name, re.I))
    family = re.sub(r"(?:[-, ]*(?:regular|roman|bold|italic|oblique|black|demi|heavy|mt|ps))+$",
                    "", name, flags=re.I).strip()
    family = FONT_FAMILIES.get(family.lower(), family or "Arial")
    return family, round(max(1, char["size"] * factor) * 2) / 2, bold, italic, rgb(char.get("non_stroking_color"))


def styled_runs(paragraph, chars, factor):
    style, buffer, previous = None, [], None

    def flush():
        if buffer:
            run = paragraph.add_run(xml_text("".join(buffer)))
            name, size, bold, italic, color = style
            run.font.name, run.font.size, run.bold, run.italic = name, Pt(size), bold, italic
            if color is not None:
                run.font.color.rgb = color
            buffer.clear()

    for char in chars:
        text = char["text"]
        if previous and text.strip() and previous["text"].strip():
            if char["x0"] - previous["x1"] > max(1.5, char["size"] * 0.18):
                buffer.append(" ")
        current = style_of(char, factor)
        if current != style:
            flush()
            style = current
        buffer.append(text)
        previous = char
    flush()
