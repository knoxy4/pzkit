"""64->32 nearest-neighbour downscale for ikag_mycology icons. Masters preserved."""
import os
import pathlib
import shutil
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("PIL missing: pip install --break-system-packages pillow")

d = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PZ_TEXTURES_DIR", "")
)
if not d.is_dir():
    sys.exit(
        f"usage: {pathlib.Path(sys.argv[0]).name} <textures-dir>\n"
        "   or: set PZ_TEXTURES_DIR to your mod's 42/media/textures directory"
    )
masters = d / "_masters_64"
masters.mkdir(exist_ok=True)

done, skipped = [], []
for p in sorted(d.glob("Item_*.png")):
    im = Image.open(p).convert("RGBA")
    if im.size != (64, 64):
        skipped.append((p.name, im.size))
        continue
    shutil.copy2(p, masters / p.name)          # keep the 64 master
    im.resize((32, 32), Image.NEAREST).save(p, optimize=True)
    done.append(p.name)

print(f"downscaled {len(done)} icons 64->32 (NEAREST)")
print(f"masters kept in {masters.name}/")
if skipped:
    print("skipped (not 64x64):", skipped)

print("\nverify:")
for p in sorted(d.glob("Item_*.png")):
    im = Image.open(p)
    print(f"  {p.name:36} {im.size[0]}x{im.size[1]}  {im.mode}  {p.stat().st_size}B")
