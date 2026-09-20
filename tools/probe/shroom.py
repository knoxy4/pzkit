import pathlib
import re

m = pathlib.Path.home() / "pzserver/media"

print("=== VANILLA MUSHROOM / FUNGI ITEMS ===")
hits = set()
for f in (m / "scripts").rglob("*.txt"):
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for mm in re.finditer(r'\n\s*item\s+(\w*(?:[Mm]ushroom|[Ss]hroom|Fungi|Cap)\w*)', t):
        hits.add(mm.group(1))
for h in sorted(hits):
    print("  ", h)

print("\n=== FORAGING Mushrooms.lua ENTRIES ===")
p = m / "lua/shared/Foraging/Categories/Mushrooms.lua"
if p.exists():
    for mm in sorted(set(re.findall(r'^\s*(\w+)\s*=\s*\{', p.read_text(errors="replace"), re.M))):
        print("  ", mm)

print("\n=== CONTAINER / TUB / BUCKET CANDIDATES ===")
cand = set()
for f in (m / "scripts").rglob("*.txt"):
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for mm in re.finditer(r'\n\s*item\s+(\w*(?:Bucket|Tub|Crate|Bin|Tray|Planter|Box)\w*)', t):
        cand.add(mm.group(1))
print("  ", ", ".join(sorted(cand)[:40]))

print("\n=== FARMING / GROW SYSTEM FILES ===")
for d in ["lua/shared/Farming", "lua/server/Farming", "lua/client/Farming"]:
    dd = m / d
    if dd.is_dir():
        print(f"  {d}: " + ", ".join(sorted(x.name for x in dd.iterdir())[:14]))
