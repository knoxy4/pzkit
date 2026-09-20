#!/usr/bin/env python3
"""Key-aware reference sweep: find script references to things that don't exist.

pzkit's validator only checks module-qualified refs (`Base.Foo`) on non-recipe
blocks, so bare-name references in GrantedRecipes / XPBoosts / trait lists are
invisible to it — which is how a phantom recipe name passes validation GREEN
and then silently does nothing in game.

Truth comes from the vanilla index (pzkit/data/vanilla.db) plus every name the
scanned mods define themselves. Perk names are derived from vanilla's own
xpAward/SkillRequired props, not from a hardcoded list.

    python3 tools/hallucination_sweep.py path/to/mods/
    python3 tools/hallucination_sweep.py --git-ref some-branch
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _default_db():
    """Use pzkit's own answer so the two never drift apart again.

    This script recomputed the path independently and silently stopped finding
    the database when the package layout changed.
    """
    try:
        sys.path.insert(0, str(REPO))
        from pzkit.vanilla_index import default_db_path
        return default_db_path()
    except Exception:
        env = os.environ.get("PZKIT_DB")
        return Path(env) if env else REPO / "data" / "vanilla.db"


DB = _default_db()

RECIPE_KEYS = {"GrantedRecipes", "LearnedRecipes", "TeachedRecipes", "RecipeList"}
PERK_KEYS = {"XPBoosts", "xpAward", "SkillRequired", "AutoLearnAll", "AutoLearnAny"}
TRAIT_KEYS = {"MutuallyExclusiveTraits", "GrantedTraits", "FreeTraits", "RemoveTraits"}
MODEL_KEYS = {"StaticModel", "WorldStaticModel"}

DEPRECATED = {
    "TeachedRecipes": "renamed to LearnedRecipes in B42",
    "Type": "replaced by ItemType at 42.13.0",
    "DisplayName": "removed at 42.12.0 - use ItemName translations",
}

BLOCK_RE = re.compile(r"^\s*(\w+)\s+([\w:.\-]+)\s*$")
PROP_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?),?\s*$")


def vanilla_sets(db: Path) -> dict[str, set[str]]:
    if not db.is_file():
        sys.exit(f"no vanilla index at {db} - run `pzkit index build`")
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out: dict[str, set[str]] = defaultdict(set)
    for bt, key in (
        ("craftRecipe", "recipe"),
        ("character_trait_definition", "trait"),
        ("character_profession_definition", "profession"),
        ("item", "item"),
        ("model", "model"),
    ):
        for r in con.execute("SELECT name FROM blocks WHERE btype=? AND name IS NOT NULL", (bt,)):
            out[key].add(r["name"])
            if ":" in r["name"]:
                out[key].add(r["name"].split(":", 1)[1])

    perks: set[str] = set()
    for r in con.execute(
        "SELECT value FROM props WHERE key IN ('xpAward','SkillRequired','XPBoosts')"
    ):
        for seg in re.split(r"[;,]", r["value"] or ""):
            name = re.split(r"[:=]", seg.strip())[0].strip()
            if name and name.isidentifier():
                perks.add(name)
    out["perk"] = perks
    return out


def scan_file(path: Path, text: str) -> list[tuple[int, str, str, str]]:
    """-> [(line, key, value, blocktype)]"""
    found, stack = [], []
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.split("//")[0].rstrip()
        if not line.strip():
            continue
        m = BLOCK_RE.match(line)
        if m and not line.strip().endswith(","):
            stack.append(m.group(1))
            continue
        if line.strip() == "}":
            if stack:
                stack.pop()
            continue
        p = PROP_RE.match(line)
        if p:
            found.append((i, p.group(1), p.group(2), stack[-1] if stack else ""))
    return found


def own_names(files: list[tuple[str, str]]) -> set[str]:
    names: set[str] = set()
    for _rel, text in files:
        for raw in text.splitlines():
            m = BLOCK_RE.match(raw.split("//")[0].rstrip())
            if m and m.group(1) in (
                "craftRecipe",
                "item",
                "character_trait_definition",
                "character_profession_definition",
            ):
                n = m.group(2)
                names.add(n)
                if ":" in n:
                    names.add(n.split(":", 1)[1])
    return names


def check(files: list[tuple[str, str]], V: dict[str, set[str]]) -> list[str]:
    mine = own_names(files)
    problems: list[str] = []

    def unknown(val: str, ns: str) -> bool:
        v = val.strip().lstrip("\\/")
        if not v or v in mine:
            return False
        if ":" in v and v.split(":", 1)[1] in mine:
            return False
        pool = V[ns]
        return v not in pool and (v.split(":", 1)[-1] not in pool)

    for rel, text in files:
        for line, key, value, btype in scan_file(rel and Path(rel) or Path("."), text):
            if key in DEPRECATED:
                problems.append(f"DEPRECATED {rel}:{line}  {key} - {DEPRECATED[key]}")
            ns = (
                "recipe" if key in RECIPE_KEYS
                else "perk" if key in PERK_KEYS
                else "trait" if key in TRAIT_KEYS
                else "model" if key in MODEL_KEYS
                else None
            )
            if not ns:
                continue
            for seg in re.split(r"[;,]", value):
                seg = seg.strip()
                if not seg:
                    continue
                name = re.split(r"[:=]", seg)[0].strip() if ns == "perk" else seg
                if not name or name.isdigit():
                    continue
                if unknown(name, ns):
                    problems.append(
                        f"MISSING   {rel}:{line}  {key} -> {name!r} is not a known {ns}"
                    )
    return problems


def gather(root: Path) -> list[tuple[str, str]]:
    return [
        (str(p.relative_to(root.parent)), p.read_text(encoding="utf-8", errors="replace"))
        for p in sorted(root.rglob("*.txt"))
        if "media/scripts" in p.as_posix()
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default="mods")
    ap.add_argument("--git-ref", help="scan a git ref instead of the working tree")
    ap.add_argument("--db", default=str(DB))
    a = ap.parse_args()

    V = vanilla_sets(Path(a.db))
    print(
        f"index: {len(V['recipe'])} recipes, {len(V['trait'])} traits, "
        f"{len(V['item'])} items, {len(V['model'])} models, {len(V['perk'])} perks"
    )

    if a.git_ref:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(
                f"git archive {a.git_ref} {a.path} | tar -x -C {td}",
                shell=True, cwd=REPO, check=True,
            )
            files = gather(Path(td) / a.path)
            print(f"scanning {a.git_ref}:{a.path} - {len(files)} script files")
            problems = check(files, V)
    else:
        root = (REPO / a.path).resolve()
        files = gather(root)
        print(f"scanning {root} - {len(files)} script files")
        problems = check(files, V)

    if not problems:
        print("\nCLEAN - every reference resolves")
        return 0
    print(f"\n{len(problems)} problem(s):\n")
    for p in problems:
        print("  " + p)
    return 1


if __name__ == "__main__":
    sys.exit(main())
