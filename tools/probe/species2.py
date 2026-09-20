import pathlib
import re

home = pathlib.Path.home()
sc = home / "pzserver/media/scripts"
lua = home / "pzserver/media/lua"

SPECIES = ["Chanterelle", "Morel", "Oyster", "KingOyster", "Enoki", "Shitake",
           "Portabello", "Henofthewoods", "TurkeyTail", "CommonPuffball",
           "GiantPuffball", "FlyAgaric", "Deathcap", "DestroyingAngel"]

# every item name in the game, regardless of spelling
all_items = set()
for f in sc.rglob("*.txt"):
    all_items |= set(re.findall(r'\n\s*item\s+(\w+)', f.read_text(errors="replace")))
print(f"total items in B42: {len(all_items)}")

print("\n=== is each species an ITEM? ===")
for sp in SPECIES:
    hit = [i for i in all_items if sp.lower() in i.lower()]
    print(f"  {sp:18} {'ITEM: ' + ', '.join(hit) if hit else 'no item'}")

print("\n=== does anything REFERENCE the texture names? ===")
for sp in ["Chanterelle", "Deathcap", "DestroyingAngel", "FlyAgaric", "Morel"]:
    found = []
    for d in (sc, lua):
        for f in d.rglob("*"):
            if f.is_file() and f.suffix in (".txt", ".lua"):
                if sp.lower() in f.read_text(errors="replace").lower():
                    found.append(f"{f.parent.name}/{f.name}")
                    break
        if found:
            break
    print(f"  {sp:18} {found or 'NOT referenced anywhere in scripts or lua'}")

print("\n=== poison config actually shipped on generic mushrooms ===")
mm = (lua / "shared/Foraging/Categories/Mushrooms.lua").read_text(errors="replace")
for k in ("chance", "poisonChance", "poisonPowerMin", "poisonPowerMax", "poisonDetectionLevel"):
    m = re.search(rf'^\s*{k}\s*=.*$', mm, re.M)
    if m:
        print("  " + m.group(0).strip())
