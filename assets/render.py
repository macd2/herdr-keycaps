#!/usr/bin/env python3
"""Draw the release assets: logo, banner, screenshot.

The screenshot is rendered from keycaps.document(), the same string the popup
pages, so a published image cannot drift from what the plugin actually shows.
Palette is Catppuccin Mocha, matching the herdr theme this was built against.

    python3 assets/render.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import keycaps  # noqa: E402

# Instrument: a Swiss technical system. Paper ground, hairlines, one red that
# only ever marks a measurement. Neutrals are warm-grey, never pure.
PAPER = (242, 241, 238)
INK = (17, 17, 17)
GREY = (139, 139, 134)
RED = (212, 35, 30)
RULE = (203, 202, 197)

# The terminal keeps its own colours: the screenshot documents what the popup
# actually looks like, so the brand frames it rather than repainting it.
BASE = (30, 30, 46)
TEXT = (205, 214, 244)
SUBTEXT = (108, 112, 134)
TEAL = (148, 226, 213)

FONTS = Path(__file__).resolve().parent / "fonts"
DISPLAY = str(FONTS / "Archivo[wdth,wght].ttf")
DATA = str(FONTS / "IBMPlexMono-Regular.ttf")
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"


def display(size: int, weight: int = 800):
    font = ImageFont.truetype(DISPLAY, size)
    font.set_variation_by_axes([weight, 100])   # axes are (Weight, Width)
    return font


def data(size: int):
    return ImageFont.truetype(DATA, size)


def tracked(draw, xy, text, font, fill, spacing=0.0):
    """Draw with letter-spacing, which Pillow has no setting for."""
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        x += font.getlength(char) + spacing
    return x


ANSI = re.compile(r"\033\[([0-9;]*)m")


def spans(line: str):
    """Split an ANSI line into (text, bold, colour) runs."""
    out, pos, bold, colour = [], 0, False, TEXT
    for m in ANSI.finditer(line):
        if m.start() > pos:
            out.append((line[pos:m.start()], bold, colour))
        for code in (m.group(1) or "0").split(";"):
            if code in ("", "0"):
                bold, colour = False, TEXT
            elif code == "1":
                bold = True
            elif code == "2":
                colour = SUBTEXT
            elif code == "36":
                colour = TEAL
        pos = m.end()
    if pos < len(line):
        out.append((line[pos:], bold, colour))
    return out


def cap_diagram(d, x, y, size, glyph="K", stroke=3, inner=None, label_font=None):
    """The keycap as an orthographic drawing: outer wall, inner face, legend.

    Two concentric squares is the whole mark. A keycap seen straight down is
    exactly that, so the drawing is literal rather than stylised.
    """
    d.rectangle([x, y, x + size, y + size], outline=INK, width=stroke)
    pad = inner if inner is not None else int(size * 0.13)
    d.rectangle([x + pad, y + pad, x + size - pad, y + size - pad],
                outline=INK, width=max(1, stroke // 2))
    if glyph and label_font:
        box = d.textbbox((0, 0), glyph, font=label_font)
        d.text((x + size / 2 - (box[2] - box[0]) / 2 - box[0],
                y + size / 2 - (box[3] - box[1]) / 2 - box[1]),
               glyph, font=label_font, fill=INK)


def dimension(d, x, y0, y1, text, font, gap=10):
    """A measurement line with ticks and a label. Red, because it measures."""
    d.line([(x, y0), (x, y1)], fill=RED, width=2)
    for yy in (y0, y1):
        d.line([(x - 7, yy), (x + 7, yy)], fill=RED, width=2)
    box = d.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    cx, cy = x + gap + th, (y0 + y1) / 2
    strip = Image.new("RGBA", (tw + 8, th + 8), (0, 0, 0, 0))
    ImageDraw.Draw(strip).text((4 - box[0], 4 - box[1]), text, font=font, fill=RED)
    strip = strip.rotate(90, expand=True)
    d._image.paste(strip, (int(cx - strip.width / 2), int(cy - strip.height / 2)), strip)


def make_logo(path: Path, size: int = 512):
    """The keycap drawn, not rendered. Paper ground, hairlines, no shadow."""
    img = Image.new("RGB", (size, size), PAPER)
    d = ImageDraw.Draw(img)

    cap = int(size * 0.56)
    o = (size - cap) // 2
    stroke = max(3, int(size * 0.018))
    cap_diagram(d, o, o, cap, glyph="K", stroke=stroke,
                inner=int(cap * 0.14), label_font=display(int(cap * 0.46)))

    # One red tick at the top-left corner: the datum the drawing is set from.
    t = int(size * 0.055)
    d.line([(o, o - t), (o, o)], fill=RED, width=stroke)
    d.line([(o - t, o), (o, o)], fill=RED, width=stroke)

    img.save(path)
    return path


def make_banner(path: Path, w: int = 1200, h: int = 630):
    """Specification sheet, not a poster.

    1200x630 is the format herdr uses for its own card. The left column states
    what the thing is, the spec block states what is measurably true, and the
    drawing on the right is dimensioned like any other part.
    """
    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)

    d.rectangle([0, 0, w, 11], fill=RED)

    m = 72
    tracked(d, (m, 150), "Keycaps", display(104, 800), INK, -2.5)
    d.text((m + 4, 292), "The faster way to drive herdr.", font=display(30, 600), fill=INK)

    # Spec block: every row is a fact the plugin can be held to.
    sy = 388
    d.line([(m + 4, sy), (m + 4 + 470, sy)], fill=GREY, width=1)
    rows = (
        ("BINDINGS", "44 rows, read from your own config"),
        ("TRIGGER", "alt+h"),
        ("SOURCE", "herdr --default-config + config.toml"),
    )
    f = data(17)
    for i, (k, v) in enumerate(rows):
        y = sy + 22 + i * 30
        d.text((m + 4, y), k, font=f, fill=GREY)
        d.text((m + 4 + 130, y), v, font=f, fill=GREY)

    # The drawing, dimensioned.
    cap = 232
    cx = w - 384
    cy = (h - cap) // 2 - 6
    cap_diagram(d, cx, cy, cap, glyph="K", stroke=5,
                inner=int(cap * 0.13), label_font=display(104, 800))
    dimension(d, cx + cap + 44, cy, cy + cap, "1U", data(16))

    # Footer rule: a spec sheet states its own provenance at the foot.
    fy = h - 86
    d.line([(m, fy), (w - m, fy)], fill=RULE, width=1)
    foot = data(16)
    tracked(d, (m, fy + 22), "KEYCAPS", foot, INK, 1.6)
    d.text((m + 150, fy + 22), "herdr plugin", font=foot, fill=GREY)
    right = "v1.0.0 / MIT"
    d.text((w - m - foot.getlength(right), fy + 22), right, font=foot, fill=GREY)

    img.save(path)
    return path


def make_screenshot(path: Path, pad: int = 30, fs: int = 21):
    """The popup as a figure on the page.

    The terminal keeps its own colours, because this documents what the plugin
    actually shows. Everything around it belongs to the brand: paper margin,
    hairline frame, a numbered caption the way a manual carries one.
    """
    keycaps.colour_enabled = lambda: True
    text = keycaps.document(keycaps.config_path()).rstrip("\n")
    lines = text.split("\n")

    font = ImageFont.truetype(MONO, fs)
    bold = ImageFont.truetype(MONO_BOLD, fs)
    cw = font.getlength("M")
    lh = int(fs * 1.55)
    cols = max(len(ANSI.sub("", l)) for l in lines)

    inner_w = int(cols * cw) + pad * 2
    inner_h = lh * len(lines) + pad * 2
    margin = 46
    caption = 54
    w = inner_w + margin * 2
    h = inner_h + margin * 2 + caption

    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)

    # Hairline frame, one red tick at the datum corner.
    d.rectangle([margin - 1, margin - 1, margin + inner_w, margin + inner_h],
                fill=BASE, outline=INK, width=1)
    d.line([(margin - 1, margin - 15), (margin - 1, margin - 1)], fill=RED, width=2)
    d.line([(margin - 15, margin - 1), (margin - 1, margin - 1)], fill=RED, width=2)

    y = margin + pad
    for line in lines:
        x = margin + pad
        for run, is_bold, colour in spans(line):
            d.text((x, y), run, font=bold if is_bold else font, fill=colour)
            x += font.getlength(run)
        y += lh

    cap_font = data(17)
    cy = margin + inner_h + 20
    d.text((margin, cy), "Fig. 1", font=cap_font, fill=RED)
    d.text((margin + 70, cy), "alt+h, every binding in effect", font=cap_font, fill=GREY)

    img.save(path)
    return path


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    for made in (make_logo(here / "logo.png"),
                 make_banner(here / "banner.png"),
                 make_screenshot(here / "screenshot.png")):
        img = Image.open(made)
        print(f"{made.name:16} {img.width}x{img.height}")
