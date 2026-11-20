"""
Generates every visual asset for Auto Typer.

What it writes: assets/bg.png as flat black artwork, assets/bg_view.png
cropped from y=96 down, assets/raze_emblem.png, app_icon.png beside this
script and a multi-size assets/raze.ico.

The background once followed the original recipe - three desaturated
lavender/white radial glows (top shaft + two soft bands), a flowing
halftone mesh band that rides a wave curve, a stack of thin,
gradient-stroked wave lines, a sparse star field and display type
rendered straight into the pixels.  None of it is drawn any more: the
artwork has been flat black since the hero was removed, and the constants
below are what is left of that recipe.
"""
import json
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
os.makedirs(ASSETS, exist_ok=True)

WIN_W = 1060
WIN_H = 860
NAV_H = 68

# --- design tokens ---------------------------------------------------- #
BG = (6, 6, 7)
TEXT = (246, 246, 248)
MUTED = (161, 161, 170)
FAINT = (113, 113, 122)
BORDER = (30, 30, 35)

# raze's overlay gradients (desaturated lavender / silver)
GLOW_TOP = (170, 178, 230)      # rgba(170,178,230,.20) at 50% -4%
GLOW_MID = (210, 214, 230)      # rgba(210,214,230,.10) at 60% 62%
GLOW_LOW = (200, 204, 225)      # rgba(200,204,225,.07) at 30% 74%

FONT_DIR = os.path.join(ASSETS, "fonts")

# weight name -> file.  Geist has no optical-size cut, so the weight name is
# the whole name.  Only the faces Raze actually renders with are listed,
# because a onefile build unpacks every bundled byte to disk on every launch,
# and a weight that is not here falls back to Regular instead of crashing.
FONT_FILES = {
    "Regular": "Geist-Regular.ttf",
    "Medium": "Geist-Medium.ttf",
    "SemiBold": "Geist-SemiBold.ttf",
    "Bold": "Geist-Bold.ttf",
    "ExtraBold": "Geist-ExtraBold.ttf",
}


def font(size, weight="Regular"):
    path = os.path.join(FONT_DIR, FONT_FILES.get(weight, "Geist-Regular.ttf"))
    return ImageFont.truetype(path, size)

HEADLINE_X, HEADLINE_Y = 44, 108
HEADLINE_SIZE = 46
HEADLINE_LEAD = 52
HEADLINE_TRACK = -2.2
SUBTITLE_X, SUBTITLE_Y = 44, 232
SUBTITLE_SIZE = 13

# the hero band - window rows 96..300
HERO_Y = 96
HERO_H = 204

# the floating nav island
ISLAND_X, ISLAND_Y = 180, 18
ISLAND_W, ISLAND_H = 700, 56
# --- the wave system ------------------------------------------------------ #
# (base y, amplitude, frequency, phase, stroke width, stroke shade)
WAVES = [
    (238, 13, 2.35, 2.55, 1, 26),
    (248, 17, 1.95, 0.90, 1, 30),
    (257, 21, 1.70, 0.00, 1, 34),
    (266, 22, 1.45, 1.30, 1, 40),
    (275, 19, 1.80, 2.20, 1, 32),
    (284, 15, 2.10, 0.55, 1, 28),
    (293, 11, 2.55, 1.80, 1, 24),
]
MESH = {"base": 266, "amp": 22, "freq": 1.45, "phase": 1.30, "half": 26, "step": 2}


def font(size, weight="Regular"):
    path = os.path.join(FONT_DIR, FONT_FILES.get(weight, "Geist-Regular.ttf"))
    return ImageFont.truetype(path, size)


def draw_tracked(draw, xy, text, fnt, fill, tracking=0.0):
    """Draw text with letter spacing while keeping the font's own kerning."""
    x, y = xy
    for i, ch in enumerate(text):
        dx = draw.textlength(text[:i], font=fnt) + tracking * i
        draw.text((x + dx, y), ch, font=fnt, fill=fill)
    return x + draw.textlength(text, font=fnt) + tracking * max(0, len(text) - 1)


def tracked_width(draw, text, fnt, tracking=0.0):
    return draw.textlength(text, font=fnt) + tracking * max(0, len(text) - 1)


SS = 3  # supersampling factor for crisp small type


def bake_text(text, size, weight, color, tracking=0.0, pad=2):
    """Render text to a transparent PNG at 3x then downsample -> razor sharp."""
    fnt = font(size * SS, weight)
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    w = int(tracked_width(probe, text, fnt, tracking * SS)) + pad * 2 * SS
    asc, desc = fnt.getmetrics()
    h = int(asc + desc) + pad * 2 * SS
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_tracked(d, (pad * SS, pad * SS), text, fnt, color + (255,), tracking=tracking * SS)
    return img.resize((max(1, w // SS), max(1, h // SS)), Image.Resampling.LANCZOS)


# --------------------------------------------------------------------------- #
#  Background
# --------------------------------------------------------------------------- #
def elliptical_glow(size, center, rx, ry, color, alpha):
    """Soft elliptical radial gradient (like a CSS radial-gradient)."""
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    steps = 56
    for i in range(steps, 0, -1):
        t = i / steps
        a = int(alpha * (1 - t) ** 2.1)
        if a <= 0:
            continue
        d.ellipse([center[0] - rx * t, center[1] - ry * t,
                   center[0] + rx * t, center[1] + ry * t],
                  fill=color + (a,))
    return layer.filter(ImageFilter.GaussianBlur(26))


def wave_y(spec, x):
    base, amp, freq, phase = spec[0], spec[1], spec[2], spec[3]
    return base + amp * math.sin((x / WIN_W) * freq * math.pi + phase)


def build_background():
    """Pure black artwork - the hero and its display type are gone."""
    base = Image.new("RGBA", (WIN_W, WIN_H), (0, 0, 0, 255))

    # --- (no display type: the hero was removed, the artwork stays pure black)

    base.convert("RGB").save(os.path.join(ASSETS, "bg.png"))
    # the view background starts below the floating nav island
    base.crop((0, 96, WIN_W, WIN_H)).convert("RGB").save(
        os.path.join(ASSETS, "bg_view.png"))
    print("bg.png + bg_view.png")


# --------------------------------------------------------------------------- #
#  App icon
# --------------------------------------------------------------------------- #
def build_logo():
    """The raze emblem -> UI crops + the .ico / exe icon."""
    src = os.path.join(HERE, "raze_emblem_src.png")
    if not os.path.exists(src):
        print("no raze_emblem_src.png")
        return
    im = Image.open(src).convert("RGBA")
    bbox = im.getbbox()
    if bbox:
        im = im.crop(bbox)

    # the master artwork ships with the app - it re-cuts the emblem at the
    # display's native resolution at runtime
    im.save(os.path.join(ASSETS, "raze_emblem.png"))

    # exe icon: white emblem on a near-black rounded tile
    tile = 512
    canvas = Image.new("RGBA", (tile, tile), (0, 0, 0, 0))
    mask = Image.new("L", (tile, tile), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tile - 1, tile - 1], radius=112, fill=255)
    plate = Image.new("RGBA", (tile, tile), (9, 9, 11, 255))
    canvas.paste(plate, (0, 0), mask)
    mark = im.resize((340, 340), Image.Resampling.LANCZOS)
    mark = mark.filter(ImageFilter.UnsharpMask(radius=1.3, percent=130, threshold=2))
    canvas.alpha_composite(mark, ((tile - 340) // 2, (tile - 340) // 2))
    canvas.save(os.path.join(HERE, "app_icon.png"))

    # a multi-size .ico for the window/taskbar icon
    ico = im.resize((256, 256), Image.Resampling.LANCZOS)
    ico.save(os.path.join(ASSETS, "raze.ico"),
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                    (128, 128), (256, 256)])
    print("logo + app_icon + raze.ico")


if __name__ == "__main__":
    build_background()
    build_logo()
