"""Minimal SVG canvas with the subset of the PIL ImageDraw API the plan scripts use (polygon, line, rectangle,
rounded_rectangle, ellipse, text, textlength). Lets the same drawing code emit a vector plan: flat footprints and
labels stay sharp at any zoom and are far smaller than a raster. Text widths are measured with the PIL font, so
label-collision layout is identical to the raster output."""
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr


def _num(v):
    return f"{float(v):.1f}".rstrip("0").rstrip(".")


def _pts(xy):
    flat = list(xy)
    if flat and not isinstance(flat[0], (list, tuple)):   # (x0, y0, x1, y1, ...) form
        flat = list(zip(flat[0::2], flat[1::2]))
    return " ".join(f"{_num(x)},{_num(y)}" for x, y in flat)


def _paint(fill, outline=None, width=1):
    s = f' fill={quoteattr(fill) if fill else chr(34) + "none" + chr(34)}'
    if outline:
        s += f" stroke={quoteattr(outline)} stroke-width={quoteattr(_num(width))}"
    return s


def _font_attrs(font):
    path = str(getattr(font, "path", "") or "").lower()
    size = getattr(font, "size", 11)
    family = "Segoe UI, Arial, sans-serif" if "segoe" in path or not path else "sans-serif"
    weight = ' font-weight="bold"' if path.endswith("b.ttf") or "bold" in path else ""
    return f' font-family="{family}" font-size="{_num(size)}"{weight}'


class SvgCanvas:
    def __init__(self, width, height, background="#FFFFFF"):
        self.width, self.height = int(width), int(height)
        self.items = [f'<rect x="0" y="0" width="{self.width}" height="{self.height}" fill={quoteattr(background)}/>']

    def polygon(self, xy, fill=None, outline=None, width=1):
        self.items.append(f'<polygon points="{_pts(xy)}"{_paint(fill, outline, width)} stroke-linejoin="miter"/>')

    def line(self, xy, fill=None, width=1, joint=None):
        self.items.append(f'<polyline points="{_pts(xy)}" fill="none" stroke={quoteattr(fill or "#000000")} '
                          f'stroke-width="{_num(width)}" stroke-linecap="square"/>')

    def rectangle(self, box, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.items.append(f'<rect x="{_num(x0)}" y="{_num(y0)}" width="{_num(x1 - x0)}" height="{_num(y1 - y0)}"{_paint(fill, outline, width)}/>')

    def rounded_rectangle(self, box, radius=0, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.items.append(f'<rect x="{_num(x0)}" y="{_num(y0)}" width="{_num(x1 - x0)}" height="{_num(y1 - y0)}" '
                          f'rx="{_num(radius)}"{_paint(fill, outline, width)}/>')

    def ellipse(self, box, fill=None, outline=None, width=1):
        x0, y0, x1, y1 = box
        self.items.append(f'<ellipse cx="{_num((x0 + x1) / 2)}" cy="{_num((y0 + y1) / 2)}" rx="{_num((x1 - x0) / 2)}" '
                          f'ry="{_num((y1 - y0) / 2)}"{_paint(fill, outline, width)}/>')

    def text(self, xy, text, font=None, fill="#000000", **_):
        # PIL anchors text at the top of the ascender; SVG at the baseline.
        ascent = font.getmetrics()[0] if font is not None and hasattr(font, "getmetrics") else 0
        self.items.append(f'<text x="{_num(xy[0])}" y="{_num(xy[1] + ascent)}"{_font_attrs(font)} fill={quoteattr(fill)} '
                          f'xml:space="preserve">{escape(str(text))}</text>')

    def textlength(self, text, font=None):
        return font.getlength(text) if font is not None else 6.0 * len(text)

    def tostring(self):
        body = "\n".join(self.items)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                f'viewBox="0 0 {self.width} {self.height}">\n{body}\n</svg>\n')

    def save(self, path):
        Path(path).write_text(self.tostring(), encoding="utf-8")
