"""Franky, Ohara's shipwright: rebuilds each volume lighter. Its JPEG and PNG pages are
made again in WebP at QUALITY, at their own size (black and white ones without their
stray colours); a page that would not come out at least a tenth lighter stays as it
is, and a whole volume is left untouched (a few of its pages tried first tell). The new volume is written beside the old one
under a hidden name, checked (it opens, with the same entries, every page whole), and
only then takes its place: the original is gone. Pillow only."""

import io
import os
import re
import zipfile

from PIL import Image

QUALITY = 85
MARK = b"ohara:franky:webp85"  # the comment of a volume rebuilt
WORTH = 0.9  # a page or a volume is rebuilt only when it comes out under this share
REMADE = re.compile(r"\.(jpe?g|png)$", re.I)
TRIED = 8  # pages tried across a volume before rebuilding it all


def looks_grey(img):
    """Black and white, even when kept in colour (most scans are): no dot of a small
    copy strays far from grey."""
    if img.mode in ("1", "L", "LA"):
        return True
    dots = img.convert("RGB").resize((40, 60)).tobytes()
    return all(max(dots[i:i + 3]) - min(dots[i:i + 3]) < 28 for i in range(0, len(dots), 3))


def done(path):
    """Whether a volume was already rebuilt by Franky."""
    with zipfile.ZipFile(path) as z:
        return z.comment == MARK


def page(data):
    """A page in WebP, or None when it would not be lighter enough."""
    img = Image.open(io.BytesIO(data))
    alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info
    img = img.convert("RGBA" if alpha else "L" if looks_grey(img) else "RGB")
    out = io.BytesIO()
    img.save(out, "WEBP", quality=QUALITY, method=4)
    return out.getvalue() if len(out.getvalue()) < len(data) * WORTH else None


def rebuild(path):
    """Rebuilds a .cbz lighter, in place. Returns its sizes before and after: the same
    when it was not worth it, the volume then left as it was."""
    before = path.stat().st_size
    if not promising(path):
        return {"before": before, "after": before}
    part = path.with_name(f".{path.name}.franky")
    try:
        names = write(path, part)
        if part.stat().st_size >= before * WORTH:
            return {"before": before, "after": before}
        check(part, names)
        stat = path.stat()
        os.utime(part, (stat.st_atime, stat.st_mtime))  # a volume rebuilt is not a new one
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)
    return {"before": before, "after": path.stat().st_size}


def promising(path):
    """Whether a volume is worth rebuilding, from TRIED of its pages spread across it:
    some series are already so well squeezed that WebP saves next to nothing."""
    with zipfile.ZipFile(path) as z:
        pages = [i for i in z.infolist() if REMADE.search(i.filename)]
        tried = pages[:: max(1, len(pages) // TRIED)][:TRIED]
        before = after = 0
        for info in tried:
            data = z.read(info)
            before += len(data)
            after += len(page(data) or data)
    return bool(tried) and after < before * WORTH


def write(path, part):
    """Writes the volume to part, its pages in WebP when that makes them lighter;
    returns the names it holds, in order."""
    names = []
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(part, "w", zipfile.ZIP_STORED) as dst:
        for info in src.infolist():
            if info.is_dir():
                continue
            data = src.read(info)
            name, smaller = info.filename, REMADE.search(info.filename) and page(data)
            if smaller:
                name, data = REMADE.sub(".webp", name), smaller
            dst.writestr(name, data)
            names.append(name)
        dst.comment = MARK
    return names


def check(part, names):
    """The volume written opens, holds what it should, and every page reads whole."""
    with zipfile.ZipFile(part) as z:
        if z.namelist() != names or z.testzip() is not None:
            raise ValueError(f"{part.name}: not as written")
        for name in names:
            if re.search(r"\.(webp|jpe?g|png)$", name, re.I):
                Image.open(io.BytesIO(z.read(name))).load()
