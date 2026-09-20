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
p = d / "Item_MonotubFruiting.png"
im = Image.open(p).convert("RGBA")
w, h = im.size
px = im.load()
print(f"{p.name}: {w}x{h}  {p.stat().st_size}B")

# halo check: near-white pixels sitting next to transparency
halo = 0
for y in range(h):
    for x in range(w):
        r, g, b, a = px[x, y]
        if a < 200:
            continue
        if r > 235 and g > 235 and b > 235:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and px[nx, ny][3] < 60:
                    halo += 1
                    break
print(f"white-on-edge pixels (halo suspects): {halo}")

# rim break: how far up the opaque content reaches, column by column
cols = []
for x in range(w):
    top = next((y for y in range(h) if px[x, y][3] > 60), None)
    cols.append(top)
solid = [c for c in cols if c is not None]
print(f"topmost opaque row: {min(solid)} of {h}")
print(f"content spans cols {cols.index(next(c for c in cols if c is not None))}..{w - 1 - cols[::-1].index(next(c for c in cols[::-1] if c is not None))}")

# side-by-side vs spent + contaminated at 8x on dark
Z = 8
names = ["Item_MonotubColonized", "Item_MonotubFruiting", "Item_MonotubSpent", "Item_MonotubContaminated"]
cell = 32 * Z + 10
sheet = Image.new("RGBA", (cell * len(names), cell), (28, 28, 30, 255))
for i, n in enumerate(names):
    q = Image.open(d / f"{n}.png").convert("RGBA").resize((32 * Z, 32 * Z), Image.NEAREST)
    sheet.alpha_composite(q, (i * cell + 5, 5))
sheet.save(d / "_final_check.png")
print("wrote _final_check.png:", " | ".join(n.replace("Item_Monotub", "") for n in names))
