"""Type-aware reference checking for B42 mod scripts.

pzkit's original validator only checked module-qualified refs (`Base.Foo`)
outside craftRecipe blocks, so bare-name references in keyed fields like
`GrantedRecipes`, `XPBoosts`, `LearnedRecipes` and trait lists were invisible
to it - which is how phantom recipes (`Make_Metal_Drum`, `Basic Mechanics`)
passed `validate` GREEN.

This module resolves every keyed reference against type-specific pools pulled
from the vanilla index, plus the names a mod defines itself. It is imported by
the validator (so GREEN means references resolve) and usable standalone.

It also guards against the index being stale: `index_provenance()` surfaces the
buildid and age so a caller never validates silently against an out-of-date
snapshot of the game.
"""
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from pathlib import Path

# field name -> which vanilla block type its values must resolve against
RECIPE_KEYS = {"GrantedRecipes", "LearnedRecipes", "TeachedRecipes", "RecipeList"}
PERK_KEYS = {"XPBoosts", "xpAward", "SkillRequired", "AutoLearnAll", "AutoLearnAny"}
TRAIT_KEYS = {"MutuallyExclusiveTraits", "GrantedTraits", "FreeTraits", "RemoveTraits"}
MODEL_KEYS = {"StaticModel", "WorldStaticModel"}

DEPRECATED = {
    "TeachedRecipes": "renamed to LearnedRecipes in B42",
    "Type": "replaced by ItemType at 42.13.0",
    "DisplayName": "removed at 42.12.0 - use ItemName translations",
}

_BLOCK = re.compile(r"^\s*(\w+)\s+([\w:.\-]+)\s*$")
_PROP = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*(.+?),?\s*$")
_OWN = ("craftRecipe", "item", "character_trait_definition",
        "character_profession_definition")


def index_provenance(db: Path) -> dict:
    """buildid, parse date, and age-in-days of the vanilla index."""
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    meta = {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM meta")}
    parsed = meta.get("parsed_at", "")
    age = None
    try:
        age = (_dt.datetime.now() - _dt.datetime.fromisoformat(parsed)).days
    except ValueError:
        pass
    return {"buildid": meta.get("game_buildid", "unknown"),
            "parsed_at": parsed, "age_days": age}


def _pools(db: Path) -> dict[str, set[str]]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out: dict[str, set[str]] = {}
    for bt, key in (("craftRecipe", "recipe"),
                    ("character_trait_definition", "trait"),
                    ("item", "item"), ("model", "model")):
        s: set[str] = set()
        for r in con.execute("SELECT name FROM blocks WHERE btype=? AND name IS NOT NULL", (bt,)):
            s.add(r["name"])
            if ":" in r["name"]:
                s.add(r["name"].split(":", 1)[1])
        out[key] = s
    perks: set[str] = set()
    for r in con.execute("SELECT value FROM props WHERE key IN ('xpAward','SkillRequired','XPBoosts')"):
        for seg in re.split(r"[;,]", r["value"] or ""):
            name = re.split(r"[:=]", seg.strip())[0].strip()
            if name and name.isidentifier():
                perks.add(name)
    out["perk"] = perks
    return out


def _own_names(scripts: list[tuple[str, str]]) -> set[str]:
    names: set[str] = set()
    for _rel, text in scripts:
        for raw in text.splitlines():
            m = _BLOCK.match(raw.split("//")[0].rstrip())
            if m and m.group(1) in _OWN:
                n = m.group(2)
                names.add(n)
                if ":" in n:
                    names.add(n.split(":", 1)[1])
    return names


def check(scripts: list[tuple[str, str]], db: Path) -> list[tuple[str, str, int, str]]:
    """-> [(severity, code, line, message)]. Empty means every reference resolves."""
    pools = _pools(db)
    mine = _own_names(scripts)
    problems: list[tuple[str, str, int, str]] = []

    def unknown(val: str, kind: str) -> bool:
        v = val.strip().lstrip("\\/")
        if not v or v in mine:
            return False
        if ":" in v and v.split(":", 1)[1] in mine:
            return False
        pool = pools[kind]
        return v not in pool and v.split(":", 1)[-1] not in pool

    for rel, text in scripts:
        for i, raw in enumerate(text.splitlines(), 1):
            line = raw.split("//")[0].rstrip()
            m = _PROP.match(line)
            if not m:
                continue
            key, value = m.group(1), m.group(2)
            if key in DEPRECATED:
                problems.append(("ERROR", "REF-deprecated", i,
                                 f"{key} - {DEPRECATED[key]}"))
            kind = ("recipe" if key in RECIPE_KEYS else "perk" if key in PERK_KEYS
                    else "trait" if key in TRAIT_KEYS else "model" if key in MODEL_KEYS
                    else None)
            if not kind:
                continue
            for seg in re.split(r"[;,]", value):
                seg = seg.strip()
                if not seg:
                    continue
                name = re.split(r"[:=]", seg)[0].strip() if kind == "perk" else seg
                if not name or name.isdigit():
                    continue
                if unknown(name, kind):
                    problems.append(("ERROR", "REF-missing", i,
                                     f"{key} -> {name!r} is not a known {kind}"))
    return problems
