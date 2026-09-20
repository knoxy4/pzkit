"""The only test that matters: all 7 tub states at TRUE 32px on a dark inventory panel."""
import os
import sys
import pathlib
from PIL import Image

d = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PZ_TEXTURES_DIR", "")
)
if not d.is_dir():
    sys.exit(
        f"usage: {pathlib.Path(sys.argv[0]).name} <textures-dir>\n"
        "   or: set PZ_TEXTURES_DIR to your mod's 42/media/textures directory"
    )
order = ["Item_Monotub", "Item_MonotubLoaded", "Item_MonotubInoculated",
         "Item_MonotubColonized", "Item_MonotubFruiting", "Item_MonotubSpent",
         "Item_MonotubContaminated"]

# true size row, then 4x row for detail
pad, gap = 6, 4
w = len(order) * (32 + gap) + pad * 2
sheet = Image.new("RGBA", (w, 32 + 128 + gap * 3 + pad * 2), (30, 30, 32, 255))
for i, n in enumerate(order):
    im = Image.open(d / f"{n}.png").convert("RGBA")
    sheet.alpha_composite(im, (pad + i * (32 + gap), pad))

big = Image.new("RGBA", (len(order) * (128 + gap), 128), (30, 30, 32, 255))
for i, n in enumerate(order):
    im = Image.open(d / f"{n}.png").convert("RGBA").resize((128, 128), Image.NEAREST)
    big.alpha_composite(im, (i * (128 + gap), 0))
big = big.resize((w - pad * 2, int(128 * (w - pad * 2) / big.width)), Image.LANCZOS)
sheet.alpha_composite(big, (pad, pad + 32 + gap * 2))
sheet.save(d / "_truesize.png")
print("wrote _truesize.png — top row is ACTUAL 32px, bottom is zoomed")
