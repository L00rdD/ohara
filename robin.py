"""Robin, Ohara's librarian: reads the cover of each volume that comes in and keeps
what its spine needs, since scans hardly ever hold the real spine: the colours of
the cover's left edge (where a cover meets its spine), its main and accent colours,
an ink that reads on them, and the liveliest square of the illustration for the
top of the spine. Pillow only."""

import colorsys
import io

from PIL import Image, ImageFilter, ImageStat

CROP = 112  # side of the illustration kept for the top of the spine, in pixels


def hex_of(rgb):
    return "#%02x%02x%02x" % tuple(int(c) for c in rgb[:3])


def luminance(rgb):
    r, g, b = (c / 255 for c in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def edge(img):
    """The mean colour of the cover's left edge, a tenth of its width."""
    strip = img.crop((0, 0, max(1, img.width // 10), img.height))
    return ImageStat.Stat(strip).mean


def palette(img, n=6):
    """The cover's colours, the most used first: [(count, (r, g, b)), …]."""
    small = img.copy()
    small.thumbnail((80, 120))
    q = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    return [(count, tuple(pal[i * 3:i * 3 + 3])) for count, i in counts]


def saturation(rgb):
    return colorsys.rgb_to_hsv(*(c / 255 for c in rgb[:3]))[1]


def accent(colours, main):
    """The most saturated colour that is not the main one, else the main one."""
    others = [c for _, c in colours if c != main]
    return max(others, key=saturation) if others else main


def liveliest(img):
    """The square of the illustration's upper part where the most is going on
    (edges and colour), for the top of the spine."""
    side = max(1, min(img.width, img.height) // 3)
    work = img.copy()
    work.thumbnail((180, 270))
    scale = img.width / work.width
    side_w = max(1, int(side / scale))
    edges = work.convert("L").filter(ImageFilter.FIND_EDGES)
    hsv = work.convert("HSV")
    best, best_at = -1, (0, 0)
    step = max(1, side_w // 4)
    for y in range(0, max(1, int(work.height * 0.7) - side_w + 1), step):
        for x in range(0, max(1, work.width - side_w + 1), step):
            box = (x, y, x + side_w, y + side_w)
            score = ImageStat.Stat(edges.crop(box)).mean[0] + ImageStat.Stat(hsv.crop(box)).mean[1] * 0.5
            if score > best:
                best, best_at = score, (x, y)
    x, y = (int(v * scale) for v in best_at)
    return img.crop((x, y, x + side, y + side)).resize((CROP, CROP))


def read_cover(data):
    """What a spine needs, from a cover's bytes: colours and the illustration's
    square (JPEG bytes)."""
    img = Image.open(io.BytesIO(data)).convert("RGB")
    colours = palette(img)
    main = colours[0][1]
    left = edge(img)
    out = io.BytesIO()
    liveliest(img).save(out, "JPEG", quality=82)
    return {
        "edge": hex_of(left),
        "main": hex_of(main),
        "accent": hex_of(accent(colours, main)),
        "ink": "#1b130b" if luminance(left) > 0.55 else "#fdf6e6",
    }, out.getvalue()
