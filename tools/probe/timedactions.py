import collections
import pathlib
import re

m = pathlib.Path.home() / "pzserver/media/scripts"

used = collections.Counter()
for f in m.rglob("*.txt"):
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for mm in re.finditer(r'timedAction\s*=\s*(\w+)', t):
        used[mm.group(1)] += 1

print("=== timedAction VALUES USED IN VANILLA RECIPES ===")
for k, n in used.most_common():
    print(f"  {n:>5}  {k}")

decl = collections.Counter()
for f in m.rglob("*.txt"):
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    for mm in re.finditer(r'\n\s*timedAction\s+(\w+)', t):
        decl[mm.group(1)] += 1
print("\n=== DECLARED TimedActionScript BLOCKS ===")
print("  " + ", ".join(sorted(decl)) if decl else "  none found in scripts/")
