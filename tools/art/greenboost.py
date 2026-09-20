"""Push the contamination green so it survives the 64->32 downscale. Compare, don't commit."""
import os
import sys
import colorsys
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
master = d / "_masters_64" / "Item_MonotubContaminated.png"
im = Image.open(master).convert("RGBA")
px = im.load()

boosted = im.copy()
bp = boosted.load()
touched = 0
for y in range(im.height):
    for x in range(im.width):
        r, g, b, a = px[x, y]
        if a < 40:
            continue
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        # green-ish hue band, any saturation above trace
        if 0.18 < h < 0.45 and s > 0.10:
            s = min(1.0, s * 2.6)
            v = min(1.0, v * 1.25)
            nr, ng, nb = colorsys.hsv_to_rgb(h, s, v)
            bp[x, y] = (int(nr * 255), int(ng * 255), int(nb * 255), a)
            touched += 1
print(f"green pixels boosted: {touched}")

Z = 8
old32 = Image.open(d / "Item_MonotubContaminated.png").convert("RGBA")
new32 = boosted.resize((32, 32), Image.NEAREST)
spent32 = Image.open(d / "Item_MonotubSpent.png").convert("RGBA")

cell = 32 * Z + 10
sheet = Image.new("RGBA", (cell * 3, cell), (28, 28, 30, 255))
for i, img in enumerate([old32, new32, spent32]):
    sheet.alpha_composite(img.resize((32 * Z, 32 * Z), Image.NEAREST), (i * cell + 5, 5))
sheet.save(d / "_green_compare.png")
boosted.save(d / "_contaminated_boosted64.png")
print("wrote _green_compare.png  (old32 | boosted32 | spent32)")
