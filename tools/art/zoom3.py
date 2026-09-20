"""Zoomed look at the three problem icons, from the 64px masters, on a dark panel."""
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
src = d / "_masters_64"
names = ["Item_MonotubColonized", "Item_MonotubFruiting",
         "Item_MonotubSpent", "Item_MonotubContaminated"]

Z, PAD = 6, 8
cell = 64 * Z + PAD * 2
sheet = Image.new("RGBA", (len(names) * cell, cell), (28, 28, 30, 255))
for i, n in enumerate(names):
    p = src / f"{n}.png"
    if not p.exists():
        p = d / f"{n}.png"
    im = Image.open(p).convert("RGBA")
    im = im.resize((64 * Z, 64 * Z), Image.NEAREST)
    sheet.alpha_composite(im, (i * cell + PAD, PAD))
out = d / "_review_trio.png"
sheet.save(out)
print("wrote", out, sheet.size)
print("order:", " | ".join(n.replace("Item_Monotub", "") for n in names))
