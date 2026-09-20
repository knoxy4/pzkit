import collections
import pathlib
import re

p = pathlib.Path.home() / "pzserver/media/radio/RadioData.xml"
t = p.read_text(encoding="utf-8", errors="replace")
print("file:", p, len(t), "chars")

codes = collections.Counter()
for m in re.finditer(r'codes="([^"]*)"', t):
    for c in m.group(1).split(","):
        c = c.strip()
        if c:
            codes[c] += 1

print("\n=== UNIQUE codes= VALUES ===")
for c, n in codes.most_common():
    print(f"{n:6}  {c}")

print("\n=== SAMPLE LineEntry WITH codes ===")
for m in list(re.finditer(r'<LineEntry[^>]*codes="[^"]*"[^>]*>', t))[:4]:
    print(m.group(0)[:220])

print("\n=== ATTRIBUTE NAMES ON LineEntry ===")
attrs = collections.Counter()
for m in re.finditer(r'<LineEntry([^>]*)>', t):
    for a in re.finditer(r'(\w+)=', m.group(1)):
        attrs[a.group(1)] += 1
print(dict(attrs))
