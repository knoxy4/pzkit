import pathlib
import re

f = pathlib.Path.home() / "pzserver/media/lua/shared/Foraging"

print("=== addForageDef signature + how defs get registered ===")
s = (f / "forageSystem.lua").read_text(errors="replace")
m = re.search(r'function forageSystem\.addForageDef.*?\n(?:.*\n){0,25}', s)
print(m.group(0) if m else "not found")

print("=== months / bonusMonths keys in forageDefinitions ===")
d = (f / "forageDefinitions.lua").read_text(errors="replace")
for kw in ("months", "bonusMonths", "malusMonths", "snowChance", "dayChance", "nightChance", "minCount", "maxCount"):
    mm = re.search(rf'^\s*{kw}\s*=.*$', d, re.M)
    if mm:
        print("  " + mm.group(0).strip())

print("\n=== bucket-ish item names in vanilla ===")
sc = pathlib.Path.home() / "pzserver/media/scripts"
names = set()
for p in sc.rglob("*.txt"):
    for mm in re.finditer(r'\n\s*item\s+(Bucket\w*|Plastic\w*|Sheet)\b', p.read_text(errors="replace")):
        names.add(mm.group(1))
print("  " + ", ".join(sorted(names)))
