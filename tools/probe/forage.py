import pathlib
import re

f = pathlib.Path.home() / "pzserver/media/lua/shared/Foraging"

print("=== Mushrooms.lua — first entry, full schema ===")
t = (f / "Categories/Mushrooms.lua").read_text(errors="replace")
print(t[:1400])

print("\n=== WEATHER / RAIN HOOKS across the forage system ===")
for p in f.rglob("*.lua"):
    s = p.read_text(errors="replace")
    for kw in ("rain", "Rain", "weather", "Weather", "snow", "Snow"):
        for m in re.finditer(rf'^.*{kw}.*$', s, re.M):
            line = m.group(0).strip()
            if len(line) < 110 and "--" not in line[:3]:
                print(f"  [{p.name}] {line}")
                break
        break
