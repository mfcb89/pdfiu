"""Render and compare plans on a common physical scale."""

from PIL import Image, ImageChops, ImageOps

from pdf_ops import pdfium_reader, render_page
from translations import tr


def render_revision_pair(paths, passwords, pages, units):
    from contextlib import ExitStack
    with ExitStack() as stack:
        readers = []
        sizes = []
        for path, password, index, unit in zip(paths, passwords, pages, units):
            try:
                document = stack.enter_context(pdfium_reader(path, password=password))
                sizes.append(tuple(side * unit for side in document.get_page_size(index)))
                readers.append(document)
            except Exception as error:
                raise ValueError(tr("{0} · página {1}: {2}").format(path.name, index + 1, error)) from error
        pixels_per_point = min(3.0, 4600 / max(max(size) for size in sizes))
        images = []
        for path, document, index, size in zip(paths, readers, pages, sizes):
            try:
                images.append(render_page(document, index, width=max(1, round(size[0] * pixels_per_point))))
            except Exception as error:
                raise ValueError(tr("{0} · página {1}: {2}").format(path.name, index + 1, error)) from error
        return images, pixels_per_point


def alignment(images, offset_mm, pixels_per_point):
    original, revision = images
    dx, dy = (round(value * 72 * pixels_per_point / 25.4) for value in offset_mm)
    left, top = min(0, dx), min(0, dy)
    width, height = max(original.width, dx + revision.width) - left, max(original.height, dy + revision.height) - top
    if width * height > 42_000_000:
        raise ValueError(tr("Reduce el desplazamiento para superponer estas páginas."))
    return (width, height), (-left, -top), (dx - left, dy - top)


def max_channel(image):
    red, green, blue = image.split()
    return ImageChops.lighter(ImageChops.lighter(red, green), blue)


def overlay_revision(images, color, opacity, offset_mm, pixels_per_point):
    original, revision = images
    size, first, second = alignment(images, offset_mm, pixels_per_point)
    combined = Image.new("RGB", size, "white")
    combined.paste(original, first)
    ink = max_channel(ImageOps.invert(revision))
    mask = ink.point(lambda value: round(value * opacity / 100))
    x, y = second
    combined.paste(color, (x, y, x + revision.width, y + revision.height), mask)
    return combined


def highlight_differences(images, tolerance, offset_mm, pixels_per_point):
    size, first, second = alignment(images, offset_mm, pixels_per_point)
    if size[0] * size[1] > 24_000_000:
        raise ValueError(tr("Reduce el desplazamiento para superponer estas páginas."))
    a = Image.new("RGB", size, "white")
    b = Image.new("RGB", size, "white")
    a.paste(images[0], first)
    b.paste(images[1], second)
    changed = max_channel(ImageChops.difference(a, b)).point(lambda value: 255 if value > tolerance else 0)
    old_ink = max_channel(ImageOps.invert(a))
    new_ink = max_channel(ImageOps.invert(b))
    del a, b
    background = ImageChops.lighter(old_ink, new_ink).point(lambda value: 255 - round(value * .33))
    result = background.convert("RGB")
    occupied = [ink.point(lambda value: 255 if value > tolerance else 0) for ink in (old_ink, new_ink)]
    additions = ImageChops.darker(changed, ImageChops.subtract(occupied[1], occupied[0]))
    removals = ImageChops.darker(changed, ImageChops.subtract(occupied[0], occupied[1]))
    remainders = ImageChops.subtract(changed, ImageChops.lighter(additions, removals))
    result.paste("#a25c00", (0, 0, *size), remainders)
    result.paste("#bb2535", (0, 0, *size), removals)
    result.paste("#007d73", (0, 0, *size), additions)
    return result, changed.getbbox() is not None
