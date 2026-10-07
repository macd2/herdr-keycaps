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


def make_cheatsheet(path: Path):
    """The keymap as a printed reference card, not a photograph of a terminal.

    Typeset from keycaps.entries(), the same rows the popup formats, so the
    card cannot drift from the plugin. Column widths are measured from the
    longest string in each column rather than guessed, and the page is sized
    to fit them.
    """
    rows, prefix_key = keycaps.entries(keycaps.config_path())

    key_font = data(18)
    pre_font = data(18)
    txt_font = display(18, 500)
    sec_font = display(17, 700)
    legend_font = data(14)

    pad = 26
    key_w = max([key_font.getlength(r[1]) for r in rows] + [legend_font.getlength("DIRECT")])
    pre_w = max([pre_font.getlength(r[2]) for r in rows] + [legend_font.getlength("VIA PREFIX")])
    txt_w = max(txt_font.getlength(r[3]) for r in rows)
    col_w = int(key_w + pad + pre_w + pad + txt_w)
    key_x, pre_x, txt_x = 0, int(key_w + pad), int(key_w + pad + pre_w + pad)

    m, gutter = 64, 76
    w = m * 2 + col_w * 2 + gutter
    line_h, head_h, top = 30, 46, 250

    # Whole sections only: a group split across columns is harder to scan.
    blocks, current = [], None
    for section, direct, leader, text in rows:
        if current is None or current[0] != section:
            current = (section, [])
            blocks.append(current)
        current[1].append((direct, leader, text))

    def block_h(b):
        return head_h + len(b[1]) * line_h + 20

    # Pick the split that makes the two columns most even.
    heights = [block_h(b) for b in blocks]
    best = min(range(1, len(blocks)),
               key=lambda i: abs(sum(heights[:i]) - sum(heights[i:])))
    left, right = blocks[:best], blocks[best:]
    body_h = max(sum(heights[:best]), sum(heights[best:]))
    h = top + body_h + 92

    img = Image.new("RGB", (w, h), PAPER)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 11], fill=RED)

    tracked(d, (m, 66), "Keycaps", display(62, 800), INK, -1.4)
    d.text((m + 3, 150), "Keymap reference", font=display(22, 600), fill=INK)
    trigger = data(16)
    label = f"press  alt+h  /  prefix is {prefix_key}"
    d.text((w - m - trigger.getlength(label), 156), label, font=trigger, fill=GREY)
    d.line([(m, 196), (w - m, 196)], fill=INK, width=2)

    for x in (m, m + col_w + gutter):
        d.text((x + key_x, 212), "DIRECT", font=legend_font, fill=GREY)
        d.text((x + pre_x, 212), "VIA PREFIX", font=legend_font, fill=GREY)

    def draw_column(x, blocks_):
        y = top
        for section, items in blocks_:
            tracked(d, (x, y), section, sec_font, INK, 1.4)
            d.line([(x, y + 27), (x + col_w, y + 27)], fill=RULE, width=1)
            y += head_h
            for direct, leader, text in items:
                if direct:
                    d.text((x + key_x, y), direct, font=key_font, fill=INK)
                if leader:
                    d.text((x + pre_x, y), leader, font=pre_font, fill=GREY)
                d.text((x + txt_x, y), text, font=txt_font, fill=INK)
                y += line_h
            y += 20

    draw_column(m, left)
    draw_column(m + col_w + gutter, right)

    fy = h - 56
    d.line([(m, fy), (w - m, fy)], fill=RULE, width=1)
    foot = data(15)
    tracked(d, (m, fy + 20), "KEYCAPS", foot, INK, 1.6)
    d.text((m + 150, fy + 20), "built from herdr --default-config + config.toml",
           font=foot, fill=GREY)
    tail = f"{len(rows)} rows"
    d.text((w - m - foot.getlength(tail), fy + 20), tail, font=foot, fill=GREY)

    img.save(path)
    return path


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    for made in (make_logo(here / "logo.png"),
                 make_banner(here / "banner.png"),
                 make_cheatsheet(here / "cheatsheet.png")):
        img = Image.open(made)
        print(f"{made.name:16} {img.width}x{img.height}")
