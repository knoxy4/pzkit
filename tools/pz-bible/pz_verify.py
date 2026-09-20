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
NOT FOUND + nearest candidates (ranked by similarity to the name's
last segment; empty when nothing is close enough to be a plausible typo).

Rules: NOT FOUND is a hard stop - use a suggestion or redesign, never ship
the name with a caveat. CASE MISMATCH is an error - PZ names are
case-sensitive. `tile` accepts a sheet name or sheet_N (index range NOT
validated). See README.md for provenance and what is not covered.
"""
import difflib
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
# NOT FOUND suggestion tuning. EDIT_BUDGET is roughly how many typos a
# candidate may be away, scaled by name length; MIN_SIM keeps very short
# names from accepting anything. Below the floor we print nothing.
MIN_SIM = float(os.environ.get("PZ_BIBLE_MIN_SIM") or 0.62)
EDIT_BUDGET = 1.5
PREFIX_BONUS = 0.05


def list_path(kind):
    return os.path.join(REFS, KINDS[kind])


def have_list(kind):
    return os.path.exists(list_path(kind))


def _missing_hint(path):
    builder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_refs.py")
    return (f"missing reference list: {path}\n"
            "Generate the lists first:\n"
            f"  python3 {builder} --game <ProjectZomboid dir>\n"
            "Or set PZ_BIBLE_REFS to a directory that already has them.")


def load(kind):
    path = list_path(kind)
    if not os.path.exists(path):
        print(_missing_hint(path))
        sys.exit(2)
    with open(path, encoding="utf-8", errors="replace") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip()]


def split_id(name):
    """PZ ids are Module.Item, Class:method or Enum.VALUE - the discriminating
    part is the tail. Returns (prefix, leaf); prefix is "" if undivided."""
    for sep in (":", "."):
        if sep in name:
            head, _, tail = name.rpartition(sep)
            return head, tail
    return "", name


def common_prefix_len(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def nearest(names, target, limit=8):
    """Best `limit` candidates, ranked by similarity to the leaf of `target`.

    Compares leaf to leaf (Base.Nonsense is scored against the Axe in
    Base.Axe), nudges candidates sharing the target's module/class prefix up,
    and puts names that literally contain the typed leaf on top. The floor is
    an edit budget: a long name has to match far more closely than a short one
    to count as a typo. Returns [] when nothing clears it - no suggestion at
    all beats eight wrong ones."""
    prefix, leaf = split_id(target)
    prefix, leaf = prefix.lower(), leaf.lower()
    floor = max(MIN_SIM, 1.0 - EDIT_BUDGET / max(len(leaf), 1))
    m = difflib.SequenceMatcher()
    m.set_seq2(leaf)
    scored = []
    for n in names:
        npre, cand = split_id(n)
        cand = cand.lower()
        bonus = PREFIX_BONUS if prefix and npre.lower() == prefix else 0.0
        # Containment only means something once the leaf is long enough to be
        # distinctive: a one- or two-character leaf is inside half the list,
        # which is the file-order noise this ranking exists to remove.
        if len(leaf) >= 3 and leaf in cand:
            scored.append((1, 1.0, 0, abs(len(cand) - len(leaf)), n))
            continue
        m.set_seq1(cand)
        # length bound, then cheap upper bound, before the real O(n*m) ratio
        if m.real_quick_ratio() < floor or m.quick_ratio() < floor:
            continue
        r = m.ratio()
        if r >= floor:
            scored.append((0, r + bonus, common_prefix_len(cand, leaf), 0, n))
    scored.sort(key=lambda s: (-s[0], -s[1], -s[2], s[3], s[4]))
    return [s[-1] for s in scored[:limit]]


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
        present = [k for k in sorted(KINDS) if have_list(k)]
        absent = [k for k in sorted(KINDS) if not have_list(k)]
        if not present:
            print(_missing_hint(list_path(sorted(KINDS)[0])))
            return 2
        ok = any([verify(k, rest[0], quiet_miss=True) for k in present])
        if not ok:
            print(f"NOT FOUND [any] {rest[0]}")
            if absent:
                # Say so: an unchecked kind is not the same as a verified miss,
                # and NOT FOUND is documented as a hard stop.
                print(f"  note: {len(absent)} kind(s) not checked - no list built: "
                      + ", ".join(absent))
        return 0 if ok else 1
    if cmd not in KINDS:
        print(f"unknown kind: {cmd} | kinds: any, list, search, "
              + ", ".join(sorted(KINDS)))
        return 2
    return 0 if verify(cmd, rest[0]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
