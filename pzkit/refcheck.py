"""Type-aware reference checking for B42 mod scripts.

pzkit's original validator only checked module-qualified refs (`Base.Foo`)
outside craftRecipe blocks, so bare-name references in keyed fields like
`GrantedRecipes`, `XPBoosts`, `LearnedRecipes` and trait lists were invisible
to it - which is how phantom recipes (`Make_Metal_Drum`, `Basic Mechanics`)
passed `validate` GREEN.

This module resolves every keyed reference against type-specific pools pulled
from the vanilla index, plus the names a mod defines itself. It is imported by
the validator (so GREEN means references resolve) and usable standalone.

It reuses scripts_parser rather than re-scanning lines: block context is what
makes a deprecation call correct (`DisplayName` is dead on `item` but alive on
`entity`/`fluid`/`CraftLogic` - 342 live uses in buildid 24449161), and the
real parser is the only thing that handles space-bearing names
(`base:out of shape`), K&R headers and `/* */` comments the same way the game
does. Verified against the whole 1,004-file vanilla corpus: identical keyed-ref
extraction to the line-regex it replaces, zero divergence.

It also guards against the index being stale: `index_provenance()` surfaces the
buildid and age so a caller never validates silently against an out-of-date
snapshot of the game.
"""
from __future__ import annotations

import datetime as _dt
import re
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from .scripts_parser import ParsedFile, ScriptBlock, parse_script

# field name -> which vanilla block type its values must resolve against
RECIPE_KEYS = {"GrantedRecipes", "LearnedRecipes", "TeachedRecipes", "RecipeList"}
PERK_KEYS = {"XPBoosts", "xpAward", "SkillRequired", "AutoLearnAll", "AutoLearnAny"}
TRAIT_KEYS = {"MutuallyExclusiveTraits", "GrantedTraits", "FreeTraits", "RemoveTraits"}
MODEL_KEYS = {"StaticModel", "WorldStaticModel"}

# key -> (reason, block types it is deprecated IN). None = deprecated everywhere.
DEPRECATED = {
    "TeachedRecipes": ("renamed to LearnedRecipes in B42", None),
    "Type": ("replaced by ItemType at 42.13.0", ("item",)),
    "DisplayName": ("removed at 42.12.0 - use ItemName translations", ("item",)),
}

# block types whose names a mod is allowed to reference from its own keyed fields
_OWN = ("craftRecipe", "item", "character_trait_definition",
        "character_profession_definition", "model")

# perk names are scraped from the props that carry them; AutoLearn* included or
# skills that appear nowhere else (LongBlade, Spear) read as phantom perks
_RECIPE_SOURCE_KEYS = ("MetaRecipe", "Researchablerecipes", "recipes")

_PERK_SOURCE_KEYS = ("xpAward", "SkillRequired", "XPBoosts", "AutoLearnAll", "AutoLearnAny")


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


def _alias(pool: set[str], name: str | None) -> None:
    """Record a name plus its module-stripped alias (`base:kitchentools` -> both)."""
    if not name:
        return
    pool.add(name)
    if ":" in name:
        pool.add(name.split(":", 1)[1])


def _walk(blocks: list[ScriptBlock]) -> Iterator[ScriptBlock]:
    for b in blocks:
        yield b
        yield from _walk(b.children)


def _pools(db: Path) -> dict[str, set[str]]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out: dict[str, set[str]] = {}
    for bt, key in (("craftRecipe", "recipe"),
                    ("character_trait_definition", "trait"),
                    ("model", "model")):
        s: set[str] = set()
        for r in con.execute("SELECT name FROM blocks WHERE btype=? AND name IS NOT NULL", (bt,)):
            _alias(s, r["name"])
        out[key] = s
    # Not every legal recipe target is a craftRecipe block. MetaRecipe groups
    # (`LearnedRecipes = base:kitchentools`) and the blacksmith research names
    # (`Researchablerecipes = Blast_Furnace`) are declared by use on VANILLA
    # blocks only - a mod's own values never seed the pool, so a typo in the mod
    # still fails.
    marks = ",".join("?" * len(_RECIPE_SOURCE_KEYS))
    for r in con.execute(f"SELECT DISTINCT value FROM props WHERE key IN ({marks})",
                         _RECIPE_SOURCE_KEYS):
        for seg in re.split(r"[;,]", r["value"] or ""):
            _alias(out["recipe"], seg.strip())
    perks: set[str] = set()
    marks = ",".join("?" * len(_PERK_SOURCE_KEYS))
    for r in con.execute(f"SELECT value FROM props WHERE key IN ({marks})", _PERK_SOURCE_KEYS):
        for seg in re.split(r"[;,]", r["value"] or ""):
            name = re.split(r"[:=]", seg.strip())[0].strip()
            if name and name.isidentifier():
                perks.add(name)
    out["perk"] = perks
    return out


def _own_names(parsed: list[ParsedFile]) -> set[str]:
    """Every name this mod declares itself, plus the MetaRecipe groups it joins."""
    names: set[str] = set()
    for pf in parsed:
        for blk in _walk(pf.blocks):
            if blk.btype in _OWN:
                _alias(names, blk.name)
            for p in blk.props:
                if p.key == "MetaRecipe":
                    for seg in re.split(r"[;,]", p.value):
                        _alias(names, seg.strip())
    return names


def _kind(key: str) -> str | None:
    return ("recipe" if key in RECIPE_KEYS else "perk" if key in PERK_KEYS
            else "trait" if key in TRAIT_KEYS else "model" if key in MODEL_KEYS else None)


def _lua_side(name: str, kind: str) -> bool:
    """True for recipe-knowledge group names the scripts-only index cannot see.

    B42's recipe *knowledge* names (`Basic Mechanics`, `base:hemp growing season`)
    are declared in media/lua, not in a craftRecipe block, so they are absent from
    the index by construction. All 969 vanilla craftRecipe names are bare
    identifiers - zero contain a space or a colon - so a space/colon is a reliable
    tell. Those get WARN, not ERROR: a real typo (`Ghost_Recipe`) still fails hard.
    """
    return kind == "recipe" and (" " in name or ":" in name)


def _msg(key: str, name: str, kind: str) -> str:
    # keyed fields take BARE names; only item refs are module-qualified. Call out
    # a dotted name whose bare half does resolve, instead of a flat "not known".
    if "." in name:
        return (f"{key} -> {name!r}: {kind} refs are bare names, "
                f"not module-qualified - use {name.split('.', 1)[1]!r}")
    return f"{key} -> {name!r} is not a known {kind}"


def check(scripts: list[tuple[str, str]], db: Path) -> list[tuple[str, str, str, int, str]]:
    """-> [(severity, code, file, line, message)]. Empty means every reference resolves."""
    parsed = [parse_script(text, relpath=rel) for rel, text in scripts]
    pools = _pools(db)
    mine = _own_names(parsed)
    problems: list[tuple[str, str, str, int, str]] = []

    def unknown(val: str, kind: str) -> bool:
        v = val.strip().lstrip("\\/")
        if not v or v in mine:
            return False
        if ":" in v and v.split(":", 1)[1] in mine:
            return False
        pool = pools[kind]
        return v not in pool and v.split(":", 1)[-1] not in pool

    for pf in parsed:
        for blk in _walk(pf.blocks):
            for p in blk.props:
                dep = DEPRECATED.get(p.key)
                if dep and (dep[1] is None or blk.btype in dep[1]):
                    problems.append(("ERROR", "REF-deprecated", pf.relpath, p.line,
                                     f"{p.key} - {dep[0]}"))
                kind = _kind(p.key)
                if not kind:
                    continue
                for seg in re.split(r"[;,]", p.value):
                    seg = seg.strip()
                    if not seg:
                        continue
                    name = re.split(r"[:=]", seg)[0].strip() if kind == "perk" else seg
                    if not name or name.isdigit():
                        continue
                    if not unknown(name, kind):
                        continue
                    if _lua_side(name, kind):
                        problems.append(("WARN", "REF-lua-recipe", pf.relpath, p.line,
                                         f"{p.key} -> {name!r} is not in the script index; "
                                         f"recipe-knowledge names live in media/lua - unverifiable"))
                    else:
                        problems.append(("ERROR", "REF-missing", pf.relpath, p.line,
                                         _msg(p.key, name, kind)))
    problems.sort(key=lambda t: (t[2], t[3]))
    return problems
