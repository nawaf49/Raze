"""High quality text rasteriser for Raze.

Why this exists
---------------
Windows renders text with ClearType, which paints blue/orange fringes around
the glyphs - ugly on a pure black background.  Raze renders its own text
instead, but the first implementation rasterised at 3x and downscaled the
RGBA image.  That is what made everything look soft: the resize mixed the
colour of the transparent pixels (black) into the edges of the glyphs, so
every letter came out thinner and blurrier than it should be.

How this works
--------------
1.  The glyph coverage is rendered by FreeType **at the exact pixel size the
    text will be displayed at**, with the same hinting the OS uses.  Every
    stem therefore lands on whole pixels - the crispness of native text.
2.  Small text gets *stem darkening*.  Below roughly 12 pixels a stem of
    Inter is thinner than one pixel, so it smears across two of them and
    turns into grey mush - measurably, only two pixels of a 9px line came
    out fully opaque.  The coverage of small type is therefore pushed
    towards solid, which is exactly what Windows does with its own stem
    darkening.  The letterforms keep their shape, they only gain weight.
3.  The coverage is kept in a grayscale mask.  Colour is applied afterwards,
    so the antialiasing is perfectly neutral: no coloured fringes, no dark
    halo, and the text keeps its full brightness at the edges.
4.  Letter spacing (tracking) is applied per glyph on integer positions, so
    tracked type stays pixel aligned instead of drifting into blur.

The result is text that is as sharp as the operating system's own, on any
display, at any scale factor.
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

# Only the faces the app renders with are listed.  Dropping the two unused
# InterDisplay cuts keeps a missing file from silently rendering the wrong
# weight - a request for a weight that is not here falls back to Regular.
FONT_FILES = {
    "Regular": "Inter-Regular.ttf",
    "Medium": "Inter-Medium.ttf",
    "SemiBold": "Inter-SemiBold.ttf",
    "Bold": "Inter-Bold.ttf",
    "DisplaySemiBold": "InterDisplay-SemiBold.ttf",
    "DisplayBold": "InterDisplay-Bold.ttf",
    "DisplayExtraBold": "InterDisplay-ExtraBold.ttf",
}

# Below this size a stem of Inter is thinner than a pixel and needs to be
# darkened, otherwise the text reads as grey mush instead of letters.
SMALL_TEXT_MAX = 12
# How hard the coverage of small type is pushed towards solid.
SMALL_GAMMA = 0.45

_font_cache = {}
_lut_cache = {}


def _gamma_lut(gamma):
    """LUT that pushes partial coverage towards solid (stem darkening)."""
    if gamma not in _lut_cache:
        _lut_cache[gamma] = [
            min(255, int(round(255 * ((v / 255.0) ** gamma)))) for v in range(256)
        ]
    return _lut_cache[gamma]


def font(font_dir, weight, px_size, path=None):
    """A hinted FreeType face at the requested pixel size (cached)."""
    key = (path or font_dir, weight, int(px_size))
    if key not in _font_cache:
        if path:
            file_path = path
        else:
            file_path = os.path.join(font_dir,
                                     FONT_FILES.get(weight, FONT_FILES["Regular"]))
            if not os.path.exists(file_path):
                file_path = os.path.join(font_dir, "Inter-Regular.ttf")
        _font_cache[key] = ImageFont.truetype(file_path, max(1, int(px_size)))
    return _font_cache[key]


def render(text, px_size, font_dir, weight="Regular", color="#ffffff",
           tracking=0.0, pad=1, path=None, darken=True, min_px=None, max_px=None):
    """Rasterise `text` into an RGBA image of exactly the target pixel size.

    px_size  - the em size in *device* pixels
    tracking - extra letter spacing in device pixels
    path     - optional explicit font file (used for the monospaced log)
    """
    if not text:
        text = " "

    fnt = font(font_dir, weight, px_size, path)
    probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))
    ascent, descent = fnt.getmetrics()

    def _advance(value):
        if tracking:
            return probe.textlength(value, font=fnt) + tracking * max(0, len(value) - 1)
        return probe.textlength(value, font=fnt)

    advance = _advance(text)

    # A box that never changes its size: the text is clipped to fit and the
    # artwork is padded to a fixed width, so a counter going from 9 to 10
    # cannot push the layout around.
    if max_px:
        limit = max_px - pad * 2
        if advance > limit:
            cut = text
            while cut and _advance(cut + "\u2026") > limit:
                cut = cut[:-1]
            text = cut + "\u2026"
            advance = _advance(text)

    width = int(math.ceil(advance))
    if min_px:
        width = max(width, int(min_px))

    w = max(1, width + pad * 2)
    h = ascent + descent + pad * 2
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)

    # the text hugs the right edge of a fixed box
    offset = pad + max(0, width - int(math.ceil(advance)))

    if tracking:
        # per glyph placement: keeps the font's own kerning for the positions
        # while giving every glyph an exact integer slot.
        for i, ch in enumerate(text):
            x = offset + int(round(probe.textlength(text[:i], font=fnt) + tracking * i))
            draw.text((x, pad), ch, font=fnt, fill=255)
    else:
        # one pass: kerning and ligatures are kept exactly as designed
        draw.text((offset, pad), text, font=fnt, fill=255)

    # Stem darkening: at small sizes the stems are thinner than a pixel and
    # spread across two of them.  Pushing the coverage towards solid gives
    # them the weight Windows gives them.
    #
    # It is only done for light text on a dark background: there the extra
    # coverage reads as brightness and the letter sharpens.  On dark text over
    # a light button the very same boost would fatten the strokes and close
    # the counters, so it is left alone there.
    if darken and px_size <= SMALL_TEXT_MAX:
        mask = mask.point(_gamma_lut(SMALL_GAMMA))

    # colourise last: the mask carries the antialiasing, the pixels keep the
    # exact text colour, so nothing is darkened or tinted on the way out.
    out = Image.new("RGBA", mask.size, color)
    out.putalpha(mask)
    return out
