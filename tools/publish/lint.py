#!/usr/bin/env python3
"""Pre-flight checks on a mod folder, run before staging.

Four checks. Every one of them is a defect that has actually shipped:

1. InheritCondition with no disposal mode. A recipe line like

       item 1 [Base.Saucepan] flags[InheritCondition]

   hands the container back to the player *as well as* consuming it. On a
   public server an item-duplication bug is an economy leak that players find
   and quietly exploit. Vanilla always pairs the flag with an explicit mode --
   see entity_Drying_Rack_craftRecipe.txt, which writes `mode:destroy` on every
   input.

2. Byte-order marks. PZ's script and JSON parsers choke on them and the failure
   surfaces somewhere unrelated, which makes it expensive to find.

3. Unparseable JSON in Translate/.

4. craftRecipe names with no matching key in Translate/EN/Recipes.json.
   CraftRecipe.Load looks the recipe up by its BARE name, so a `Recipe_Foo` key
   silently falls back to displaying the raw id. That one cost a five-mod
   republish.

Exit code is 1 if any ERROR fired, 0 otherwise. Warnings never fail a build.

    python lint.py YourModId
    python lint.py --all
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import os
import subprocess


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.check_output(
            ["git", "-C", str(here), "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return here


REPO = Path(os.environ.get("PZ_REPO_ROOT") or _repo_root())

TEXT_SUFFIXES = {".txt", ".json", ".lua", ".info"}
INHERIT = re.compile(r"flags\[[^\]]*InheritCondition[^\]]*\]", re.IGNORECASE)
HAS_MODE = re.compile(r"\bmode:\s*\w+", re.IGNORECASE)
CRAFT_RECIPE = re.compile(r"^\s*craftRecipe\s+([^\s{]+)", re.IGNORECASE)


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def _loc(self, where: Path, line: int | None) -> str:
        try:
            shown = where.relative_to(REPO) if where.is_relative_to(REPO) else where
        except ValueError:
            shown = where
        return f"{shown}" + (f":{line}" if line else "")

    def error(self, where: Path, line: int | None, msg: str) -> None:
        self.errors.append(f"  ERROR {self._loc(where, line)}\n        {msg}")

    def warn(self, where: Path, line: int | None, msg: str) -> None:
        self.warnings.append(f"  warn  {self._loc(where, line)}\n        {msg}")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def check_bom(path: Path, rep: Report) -> None:
    if path.read_bytes()[:3] == b"\xef\xbb\xbf":
        rep.error(path, None, "file starts with a UTF-8 byte-order mark")


def check_json(path: Path, rep: Report) -> None:
    try:
        json.loads(read(path))
    except Exception as exc:
        rep.error(path, None, f"does not parse as JSON: {exc}")


def check_inherit_condition(path: Path, rep: Report) -> None:
    for number, line in enumerate(read(path).splitlines(), 1):
        if INHERIT.search(line) and not HAS_MODE.search(line):
            rep.error(path, number,
                      "InheritCondition with no mode: -- this duplicates the "
                      "container. Add mode:destroy, or mode:keep if the item "
                      "really is meant to survive.")


def recipe_keys(mod: Path) -> tuple[set[str], Path | None]:
    for candidate in sorted(mod.rglob("Recipes.json")):
        try:
            return set(json.loads(read(candidate)).keys()), candidate
        except Exception:
            return set(), candidate
    return set(), None


def check_recipe_names(mod: Path, rep: Report) -> None:
    declared: list[tuple[Path, int, str]] = []
    for script in mod.rglob("*.txt"):
        if "scripts" not in script.parts:
            continue
        for number, line in enumerate(read(script).splitlines(), 1):
            found = CRAFT_RECIPE.match(line)
            if found:
                declared.append((script, number, found.group(1)))
    if not declared:
        return
    keys, source = recipe_keys(mod)
    if source is None:
        rep.warn(mod, None,
                 f"{len(declared)} craftRecipe(s) but no Recipes.json anywhere")
        return
    for script, number, name in declared:
        if name in keys:
            continue
        if f"Recipe_{name}" in keys:
            rep.error(script, number,
                      f"'{name}' is keyed as 'Recipe_{name}' in {source.name}. "
                      f"CraftRecipe.Load wants the bare name, so this silently "
                      f"displays the raw id.")
        else:
            rep.warn(script, number, f"'{name}' has no key in {source.name}")


def lint(mod: Path) -> Report:
    rep = Report()
    for path in sorted(mod.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        check_bom(path, rep)
        if path.suffix.lower() == ".json":
            check_json(path, rep)
        elif path.suffix.lower() == ".txt":
            check_inherit_condition(path, rep)
    check_recipe_names(mod, rep)
    return rep


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mods", nargs="*", help="mod folder name(s)")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--root", default=None,
                        help="lint a folder outside the repo, e.g. a staged mod")
    args = parser.parse_args()

    base = Path(args.root).resolve() if args.root else REPO / "mods"
    if args.all:
        targets = [p for p in sorted(base.iterdir())
                   if p.is_dir() and (p / "42" / "mod.info").exists()]
    else:
        targets = [base / name for name in args.mods]
    if not targets:
        parser.error("give one or more mod names, or --all")

    failed = 0
    for mod in targets:
        if not mod.is_dir():
            print(f"{mod.name:<24} NOT FOUND")
            failed = 1
            continue
        rep = lint(mod)
        status = "FAIL" if rep.errors else ("warn" if rep.warnings else "ok")
        print(f"{mod.name:<24} {status:>4}  "
              f"{len(rep.errors)} error(s), {len(rep.warnings)} warning(s)")
        for line in rep.errors + rep.warnings:
            print(line)
        if rep.errors:
            failed = 1
    return failed


if __name__ == "__main__":
    sys.exit(main())
