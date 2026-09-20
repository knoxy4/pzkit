"""Rebuild a contact sheet from the downscaled 32px icons, on a dark panel, 4x zoom."""
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
         "Item_MonotubContaminated", "Item_SporePrint", "Item_SporeSlurry",
         "Item_SubstrateRaw", "Item_SubstrateMixed", "Item_SubstratePrepared",
         "Item_MushroomFresh", "Item_MushroomDried"]

Z, COLS, PAD = 4, 7, 4
cell = 32 * Z + PAD * 2
rows = (len(order) + COLS - 1) // COLS
sheet = Image.new("RGBA", (COLS * cell, rows * cell), (28, 28, 30, 255))

for i, name in enumerate(order):
    p = d / f"{name}.png"
    if not p.exists():
        continue
    im = Image.open(p).convert("RGBA").resize((32 * Z, 32 * Z), Image.NEAREST)
    x = (i % COLS) * cell + PAD
    y = (i // COLS) * cell + PAD
    sheet.alpha_composite(im, (x, y))

out = d / "ContactSheet32.png"
sheet.save(out)
print("wrote", out, sheet.size)
print("row1:", ", ".join(o.replace("Item_", "") for o in order[:7]))
print("row2:", ", ".join(o.replace("Item_", "") for o in order[7:]))
