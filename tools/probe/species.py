import pathlib
import re

home = pathlib.Path.home()
sc = home / "pzserver/media/scripts"
tex = pathlib.Path("/mnt/x/SteamLibrary/steamapps/common/ProjectZomboid/media/textures")

print("=== MUSHROOM *ITEMS* defined in scripts ===")
items = set()
for f in sc.rglob("*.txt"):
    t = f.read_text(errors="replace")
    for m in re.finditer(r'\n\s*item\s+(\w*[Mm]ushroom\w*)', t):
        items.add(m.group(1))
print("  " + (", ".join(sorted(items)) if items else "NONE"))

print("\n=== MUSHROOM *TEXTURES* (named species art) ===")
arts = sorted(p.stem for p in tex.rglob("*ushroom*.png"))
print("  " + ", ".join(arts))

print("\n=== POISON MECHANIC in the forage system ===")
fg = home / "pzserver/media/lua/shared/Foraging"
for kw in ("poisonChance", "poisonPowerMin", "poisonPowerMax", "poisonDetectionLevel",
           "doPoisonItemSpawn", "isItemPoisonous", "poison"):
    for p in fg.rglob("*.lua"):
        s = p.read_text(errors="replace")
        m = re.search(rf'^.*\b{kw}\b.*$', s, re.M)
        if m and len(m.group(0)) < 130:
            print(f"  [{p.name}] {m.group(0).strip()}")
            break

print("\n=== forageSkills: what levels gate ===")
fs = (fg / "forageSkills.lua").read_text(errors="replace")
for m in re.finditer(r'^\s*(\w+)\s*=\s*\{', fs, re.M):
    print("  profession/trait:", m.group(1))
