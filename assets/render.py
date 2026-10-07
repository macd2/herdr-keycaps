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

BASE = (30, 30, 46)        # #1e1e2e
MANTLE = (24, 24, 37)      # #181825
SURFACE = (49, 50, 68)     # #313244
TEXT = (205, 214, 244)     # #cdd6f4
SUBTEXT = (108, 112, 134)  # #6c7086
TEAL = (148, 226, 213)     # #94e2d5
MAUVE = (203, 166, 247)    # #cba6f7

MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
MONO_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
# Vendored so the assets rebuild anywhere; OFL licence sits beside it. The
# wordmark is the one place a display face earns its weight - mono stays mono
# everywhere the terminal is being shown.
SANS = str(Path(__file__).resolve().parent / "fonts" / "IBMPlexSans[wdth,wght].ttf")


def sans(size: int, weight: int = 700):
    font = ImageFont.truetype(SANS, size)
    font.set_variation_by_axes([weight, 100])   # axes are (Weight, Width)
    return font


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


def vgradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)],
               fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    return img


def glow(size, centre, radius, colour, strength=90):
    """A soft radial wash, for depth behind the keys."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = centre
    d.ellipse([x - radius, y - radius, x + radius, y + radius],
              fill=(*colour, strength))
    return layer.filter(ImageFilter.GaussianBlur(radius // 2))


def keycap(draw, x, y, w, h=None, face=SURFACE, top=TEAL, glyph=None, font=None,
           label=TEXT):
    """A keycap with a skirt, a lifted top face and a glyph."""
    h = h or w
    r = max(6, min(w, h) // 6)
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=face)
    # Lip: a lighter edge along the top of the skirt.
    draw.rounded_rectangle([x, y, x + w, y + h - max(4, h // 9)], radius=r,
                           fill=tuple(min(255, c + 16) for c in face))
    inset, lift = max(5, w // 14), max(5, h // 8)
    tx0, ty0 = x + inset, y + inset - lift // 3
    tx1, ty1 = x + w - inset, y + h - inset - lift
    # A vertical sheen across the top face: light catches the near edge.
    fw, fh = int(tx1 - tx0), int(ty1 - ty0)
    if fw > 0 and fh > 0:
        face_img = vgradient((fw, fh),
                             tuple(min(255, c + 26) for c in top),
                             tuple(max(0, c - 18) for c in top))
        face_mask = Image.new("L", (fw, fh), 0)
        ImageDraw.Draw(face_mask).rounded_rectangle(
            [0, 0, fw - 1, fh - 1], radius=max(2, r // 2), fill=255)
        draw._image.paste(face_img, (int(tx0), int(ty0)), face_mask)
    if glyph and font:
        box = draw.textbbox((0, 0), glyph, font=font)
        draw.text(((tx0 + tx1) / 2 - (box[2] - box[0]) / 2 - box[0],
                   (ty0 + ty1) / 2 - (box[3] - box[1]) / 2 - box[1]),
                  glyph, font=font, fill=label)


def shadowed_keycap(img, x, y, w, h=None, **kw):
    """Keycap with a soft drop shadow, composited onto img."""
    h = h or w
    pad = 40
    layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([pad + 4, pad + 12, pad + w + 4, pad + h + 14],
                        radius=max(6, min(w, h) // 6), fill=(0, 0, 0, 150))
    layer = layer.filter(ImageFilter.GaussianBlur(14))
    keycap(ImageDraw.Draw(layer), pad, pad, w, h, **kw)
    img.paste(layer, (x - pad, y - pad), layer)


def make_logo(path: Path, size: int = 512):
    """One key, filling the frame.

    Everything is drawn opaque and masked at the end: a glow composited over a
    transparent canvas leaves a tinted haze outside the rounded square, which
    reads as grime on a light background.
    """
    img = Image.new("RGBA", (size, size), (*BASE, 255))
    img.alpha_composite(glow((size, size), (size // 2, size // 2),
                             int(size * 0.42), TEAL, 40))

    cap = int(size * 0.56)
    shadowed_keycap(img, (size - cap) // 2, (size - cap) // 2 - int(size * 0.02),
                    cap, cap, glyph="K", label=BASE,
                    font=ImageFont.truetype(MONO_BOLD, int(cap * 0.58)))

    mask = Image.new("L", (size, size), 0)
    o = int(size * 0.06)
    ImageDraw.Draw(mask).rounded_rectangle([o, o, size - o, size - o],
                                           radius=int(size * 0.21), fill=255)
    img.putalpha(mask)
    img.save(path)
    return path


def flat_key(draw, x, y, w, h, face, top, glyph=None, font=None, label=BASE):
    """A key drawn flat enough to sit in a layout rather than shout in it.

    Distinct from keycap() above, which carries the logo's lift and sheen.
    """
    r = max(5, int(min(w, h) * 0.17))
    draw.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=face)
    lip = max(3, int(h * 0.16))
    draw.rounded_rectangle([x + int(w * 0.07), y + int(h * 0.06),
                            x + w - int(w * 0.07), y + h - lip],
                           radius=max(3, r - 2), fill=top)
    if glyph and font:
        box = draw.textbbox((0, 0), glyph, font=font)
        draw.text((x + w / 2 - (box[2] - box[0]) / 2 - box[0],
                   y + (h - lip) / 2 - (box[3] - box[1]) / 2 - box[1]),
                  glyph, font=font, fill=label)


def make_banner(path: Path, w: int = 1200, h: int = 630):
    """Two columns, ruled: what it is on the left, what it shows on the right.

    1200x630 is the format herdr uses for its own card. The chord appears as
    the keys you actually press, and the panel holds the real list rather than
    a mock-up of one.
    """
    keycaps.colour_enabled = lambda: True
    lines = keycaps.document(keycaps.config_path()).split("\n")

    img = vgradient((w, h), MANTLE, BASE).convert("RGBA")
    d = ImageDraw.Draw(img)
    rail = 430
    d.rectangle([0, 0, rail, h], fill=BASE)
    d.line([(rail, 0), (rail, h)], fill=SURFACE, width=1)

    tracked(d, (64, 168), "Keycaps", sans(62), TEXT, -0.5)
    d.rounded_rectangle([66, 248, 66 + 56, 253], radius=3, fill=TEAL)
    tag = ImageFont.truetype(MONO, 17)
    for i, line in enumerate(("the faster way",
                              "to drive herdr")):
        d.text((66, 282 + i * 26), line, font=tag, fill=SUBTEXT)

    kf = ImageFont.truetype(MONO_BOLD, 20)
    flat_key(d, 66, 392, 104, 60, face=SURFACE, top=(58, 60, 82), glyph="alt",
           font=kf, label=TEXT)
    d.text((182, 410), "+", font=ImageFont.truetype(MONO, 26), fill=SUBTEXT)
    flat_key(d, 214, 392, 60, 60, face=SURFACE, top=TEAL, glyph="h", font=kf)

    px, py = 486, 64
    pw, ph = w - px - 56, h - py * 2
    d.rounded_rectangle([px, py, px + pw, py + ph], radius=10,
                        fill=MANTLE, outline=SURFACE, width=1)
    font = ImageFont.truetype(MONO, 13)
    bold = ImageFont.truetype(MONO_BOLD, 13)
    y = py + 26
    for line in lines:
        x = px + 26
        for run, is_bold, colour in spans(line):
            d.text((x, y), run, font=bold if is_bold else font, fill=colour)
            x += font.getlength(run)
        y += 21
        if y > py + ph - 30:
            break

    # The list outruns any banner, so it dissolves inside the panel: a hard
    # edge reads as broken, a fade reads as "there is more".
    fade = 150
    veil = Image.new("RGBA", (pw - 2, fade), (*MANTLE, 0))
    vd = ImageDraw.Draw(veil)
    for i in range(fade):
        vd.line([(0, i), (pw, i)],
                fill=(*MANTLE, min(255, int(255 * (i / (fade * 0.74)) ** 1.4))))
    img.alpha_composite(veil, (px + 1, py + ph - fade))

    img.convert("RGB").save(path)
    return path


def make_screenshot(path: Path, pad: int = 28, fs: int = 21):
    keycaps.colour_enabled = lambda: True  # draw it the way the popup shows it
    text = keycaps.document(keycaps.config_path()).rstrip("\n")
    lines = text.split("\n")

    font = ImageFont.truetype(MONO, fs)
    bold = ImageFont.truetype(MONO_BOLD, fs)
    cw = font.getlength("M")
    lh = int(fs * 1.55)
    cols = max(len(ANSI.sub("", l)) for l in lines)
    chrome = 46
    w = int(cols * cw) + pad * 2
    h = lh * len(lines) + pad * 2 + chrome

    img = Image.new("RGB", (w, h), BASE)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, chrome], fill=MANTLE)
    for i, colour in enumerate(((243, 139, 168), (249, 226, 175), (166, 227, 161))):
        d.ellipse([pad + i * 26, chrome // 2 - 7, pad + i * 26 + 14, chrome // 2 + 7],
                  fill=colour)
    d.text((w / 2 - 44, chrome // 2 - fs // 2), "Keycaps",
           font=ImageFont.truetype(MONO, fs - 4), fill=SUBTEXT)

    y = chrome + pad
    for line in lines:
        x = pad
        for run, is_bold, colour in spans(line):
            d.text((x, y), run, font=bold if is_bold else font, fill=colour)
            x += font.getlength(run)
        y += lh
    img.save(path)
    return path


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    for made in (make_logo(here / "logo.png"),
                 make_banner(here / "banner.png"),
                 make_screenshot(here / "screenshot.png")):
        img = Image.open(made)
        print(f"{made.name:16} {img.width}x{img.height}")
