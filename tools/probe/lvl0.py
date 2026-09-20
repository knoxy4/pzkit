"""Every craftRecipe that awards XP with NO skill requirement = a level-0 entry point."""
import collections
import pathlib
import re

root = pathlib.Path.home() / "pzserver/media/scripts"
blocks = []
for f in root.rglob("*.txt"):
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    # split on craftRecipe headers, keep the name
    parts = re.split(r'\n\s*craftRecipe\s+(\w+)', t)
    for i in range(1, len(parts) - 1, 2):
        blocks.append((f.name, parts[i], parts[i + 1][:1200]))

entry = collections.defaultdict(list)
gated = collections.Counter()
for fname, name, body in blocks:
    body = body.split("craftRecipe")[0]
    awards = re.findall(r'xpAward\s*=\s*([\w:,\s]+),', body)
    reqs = re.findall(r'SkillRequired\s*=\s*([\w:,\s]+),', body)
    if not awards:
        continue
    req_skills = set()
    for r in reqs:
        for pair in r.split(","):
            if ":" in pair:
                s, lvl = pair.split(":")[:2]
                if lvl.strip().isdigit() and int(lvl.strip()) > 0:
                    req_skills.add(s.strip())
    for a in awards:
        for pair in a.split(","):
            if ":" not in pair:
                continue
            skill, amt = pair.split(":")[:2]
            skill, amt = skill.strip(), amt.strip()
            if not amt.isdigit():
                continue
            if skill in req_skills or req_skills:
                gated[skill] += 1
            else:
                entry[skill].append((name, int(amt)))

print("=== LEVEL-0 ENTRY POINTS (no skill requirement, awards XP) ===\n")
for skill in sorted(entry, key=lambda s: -len(entry[s])):
    rows = sorted(set(entry[skill]), key=lambda r: -r[1])
    print(f"{skill}  ({len(rows)} recipes, best {rows[0][1]} xp)")
    for name, amt in rows[:6]:
        print(f"    {amt:4} xp  {name}")
    print()

print("=== SKILLS WITH NO ZERO-REQ RECIPE (gated behind something) ===")
print(sorted(set(gated) - set(entry)))
