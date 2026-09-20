import pathlib
import struct
from collections import Counter

root = pathlib.Path("/mnt/x/SteamLibrary/steamapps/workshop/content/108600")


def png_size(p):
    try:
        with open(p, "rb") as f:
            h = f.read(26)
        if h[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", h[16:24])
    except Exception:
        return None


c, n, examples = Counter(), 0, []
for p in root.rglob("Item_*.png"):
    s = png_size(p)
    if s:
        c[s] += 1
        n += 1
        if len(examples) < 6 and s == (64, 64):
            examples.append(p.name)
    if n > 6000:
        break

print("=== ITEM ICON SIZES IN REAL WORKSHOP MODS ===")
for size, k in c.most_common(8):
    pct = 100 * k / max(n, 1)
    print(f"  {size[0]:>3}x{size[1]:<3}  {k:>5} icons  ({pct:.1f}%)")
print(f"\n  sampled: {n}")
print("  examples:", ", ".join(examples))
