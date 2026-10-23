"""Collect only the Pillow codecs Raze actually opens.

Pillow's own hook gathers every image plugin it ships, and each plugin pulls
its codec library in with it - AVIF alone is 7.7 MB, and a onefile build
unpacks the whole payload to a temporary folder on **every** launch.  Raze
loads exactly one kind of image (a PNG emblem) and draws its text with
FreeType, so collecting everything else was nine megabytes of dead weight
paid for on each start.
"""

hiddenimports = [
    "PIL.PngImagePlugin",   # the only format the app ever opens
    "PIL.ImageTk",          # PhotoImage, for the baked text
    "PIL.ImageDraw",        # the text engine draws glyphs with this
    "PIL.ImageFont",        # FreeType, for the bundled Inter faces
    "PIL.ImageColor",
    "PIL.ImageMode",
    "PIL.ImageOps",
]
