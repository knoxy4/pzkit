import os
import sys
import pathlib
import struct

d = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PZ_TEXTURES_DIR", "")
)
if not d.is_dir():
    sys.exit(
        f"usage: {pathlib.Path(sys.argv[0]).name} <textures-dir>\n"
        "   or: set PZ_TEXTURES_DIR to your mod's 42/media/textures directory"
    )

COLOR = {0: "gray", 2: "RGB", 3: "palette", 4: "gray+A", 6: "RGBA"}
print(f"{'file':38} {'size':>9}  {'bits':>4} {'type':<8} alpha")
print("-" * 78)
bad = []
for p in sorted(d.glob("*.png")):
    raw = p.read_bytes()
    w, h = struct.unpack(">II", raw[16:24])
    depth, ctype = raw[24], raw[25]
    has_trns = b"tRNS" in raw[:2000]
    alpha = "yes" if ctype in (4, 6) else ("tRNS" if has_trns else "NO")
    flag = ""
    if p.name != "ContactSheet.png":
        if not (28 <= w <= 34 and 28 <= h <= 34):
            flag = "  <-- SIZE"
            bad.append(p.name)
        if alpha == "NO":
            flag += "  <-- NO ALPHA"
            bad.append(p.name)
    print(f"{p.name:38} {w:>4}x{h:<4} {depth:>4} {COLOR.get(ctype,'?'):<8} {alpha}{flag}")

print("\nissues:", bad or "none")
