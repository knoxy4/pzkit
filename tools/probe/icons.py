import pathlib
import struct

m = pathlib.Path.home() / "pzserver/media/textures"


def png_size(p):
    try:
        with open(p, "rb") as f:
            h = f.read(26)
        if h[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", h[16:24])
    except Exception:
        return None


names = ["Item_MushroomGeneric1", "Item_MushroomsButton", "Item_Bucket",
         "Item_Water", "Item_BakingTray", "Item_Jar"]
print("=== REFERENCE ICONS ===")
for n in names:
    p = m / f"{n}.png"
    print(f"  {n+'.png':32} {'MISSING' if not p.exists() else str(png_size(p)) + f'  {p.stat().st_size}B'}")

print("\n=== SIZE DISTRIBUTION across Item_*.png ===")
from collections import Counter
c = Counter()
for p in list(m.glob("Item_*.png"))[:4000]:
    s = png_size(p)
    if s:
        c[s] += 1
for size, n in c.most_common(8):
    print(f"  {size[0]}x{size[1]}  ->  {n} icons")
print(f"\n  total Item_*.png sampled: {sum(c.values())}")
