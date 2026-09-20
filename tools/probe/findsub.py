import pathlib
import re

sc = pathlib.Path.home() / "pzserver/media/scripts"
pat = re.compile(r'\n\s*item\s+(\w*(?:Saw|Wood|Straw|Hay|Shaving|Chip|Grain|Compost|Manure|Dung|Mulch|Peat)\w*)')
hits = set()
for f in sc.rglob("*.txt"):
    for m in pat.finditer(f.read_text(errors="replace")):
        hits.add(m.group(1))
for h in sorted(hits):
    print(" ", h)
