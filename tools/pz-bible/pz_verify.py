#!/usr/bin/env python3
"""pz-bible verifier - Project Zomboid B42 ground-truth name checks.

Portable, stdlib-only. Reference lists live in refs/ next to this script
(or wherever PZ_BIBLE_REFS points). Generate them with build_refs.py.

Usage:
  pz_verify.py <kind> <name>            verify one name (exit 0 ok / 1 miss)
  pz_verify.py any <name>               check across every kind
  pz_verify.py list <kind>              dump a reference list
  pz_verify.py search <kind> <substr>   substring search, max 40 hits

Output: OK | CASE MISMATCH (real spelling returned) | NOT ON THAT CLASS
(api only - method exists on listed classes; fine if one is a parent) |
NOT FOUND + nearest candidates.

Rules: NOT FOUND is a hard stop - use a suggestion or redesign, never ship
the name with a caveat. CASE MISMATCH is an error - PZ names are
case-sensitive. `tile` accepts a sheet name or sheet_N (index range NOT
validated). See README.md for provenance and what is not covered.
"""
import os
import sys

KINDS = {
    "room": "rooms.txt", "containerdist": "containerdists.txt",
    "proclist": "proclists.txt", "item": "items.txt",
    "itemtype": "itemtypes.txt", "category": "displaycategories.txt",
    "tag": "tags.txt", "icon": "icons.txt", "event": "events.txt",
    "sound": "sounds.txt", "model": "models.txt", "recipe": "recipes.txt",
    "perk": "perks.txt", "vehicle": "vehicles.txt", "fixing": "fixings.txt",
    "luaclass": "luaclasses.txt", "luafunc": "luafunctions.txt",
    "sandboxvar": "sandboxvars.txt", "api": "api.txt",
    "translation": "translations.txt", "enum": "enums.txt",
    "evolvedrecipe": "evolvedrecipes.txt", "fluid": "fluids.txt",
    "energy": "energies.txt", "attachment": "attachments.txt",
    "timedaction": "timedactions.txt", "animscript": "animscripts.txt",
    "vehiclepart": "vehicleparts.txt", "outfit": "outfits.txt",
    "clothingitem": "clothingitems.txt", "foragecat": "foragecats.txt",
    "animset": "animsets.txt", "tile": "tilesheets.txt",
}
# Generated lists are never committed; build them with build_refs.py. Defaults
# to refs/ beside this script, overridable so one set can serve several trees.
REFS = os.environ.get("PZ_BIBLE_REFS") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "refs"
)


def load(kind):
    path = os.path.join(REFS, KINDS[kind])
    if not os.path.exists(path):
        print(f"missing reference {path} - regenerate on the KNX box")
        sys.exit(2)
    with open(path, encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def nearest(names, target):
    t = target.lower()
    hits = [n for n in names if t in n.lower()][:8]
    if not hits and len(target) >= 4:
        frag = t[:4]
        hits = [n for n in names if frag in n.lower()][:8]
    return hits


def verify(kind, name, quiet_miss=False):
    """Returns True on a pass. quiet_miss suppresses NOT FOUND detail (any-mode)."""
    names = load(kind)
    if name in names:
        print(f"OK [{kind}] {name}")
        return True
    ci = next((n for n in names if n.lower() == name.lower()), None)
    if ci:
        print(f'CASE MISMATCH [{kind}] you wrote "{name}" real name is "{ci}"')
        return False
    if kind == "tile" and "_" in name:
        base, _, idx = name.rpartition("_")
        if idx.isdigit() and base in names:
            print(f"OK [tile] {name} (sprite index {idx} on known sheet {base}"
                  " - index range not validated)")
            return True
    if kind == "api" and ":" in name:
        method = name.split(":", 1)[1]
        owners = [n for n in names if n.endswith(":" + method)][:10]
        if owners:
            print(f"NOT ON THAT CLASS [api] {name} - but the method exists"
                  " (check inheritance):")
            for o in owners:
                print("  " + o)
            return True
    if not quiet_miss:
        print(f"NOT FOUND [{kind}] {name}")
        near = nearest(names, name)
        if near:
            print("nearest:")
            for n in near:
                print("  " + n)
    return False


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        if rest[0] not in KINDS:
            print(f"unknown kind: {rest[0]} | kinds: {', '.join(sorted(KINDS))}")
            return 2
        print("\n".join(load(rest[0])))
        return 0
    if cmd == "search":
        if len(rest) < 2 or rest[0] not in KINDS:
            print("usage: search <kind> <substr>")
            return 2
        hits = [n for n in load(rest[0]) if rest[1].lower() in n.lower()][:40]
        if hits:
            print("\n".join(hits))
            return 0
        print(f"no matches in [{rest[0]}] for {rest[1]}")
        return 1
    if cmd == "any":
        ok = any([verify(k, rest[0], quiet_miss=True) for k in sorted(KINDS)])
        if not ok:
            print(f"NOT FOUND [any] {rest[0]}")
        return 0 if ok else 1
    if cmd not in KINDS:
        print(f"unknown kind: {cmd} | kinds: any, list, search, "
              + ", ".join(sorted(KINDS)))
        return 2
    return 0 if verify(cmd, rest[0]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
