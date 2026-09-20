#!/usr/bin/env python3
"""Write mod.info (root and 42/) and workshop.txt for every mod in the config.

One description, one version, one author, written to every place the game and
Steam read them. Keeping them in three hand-edited files is how a mod ends up
published under last month's version number.

  python modinfo.py            # write everything
  python modinfo.py --check    # report differences, write nothing
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg  # noqa: E402


def mod_info(m: dict, c: cfg.Config) -> str:
    lines = [
        f"name={m['name']}",
        f"id={m['id']}",
        f"author={c.author}",
        f"description={m.get('description', '')}",
        "poster=poster.png",
        f"modversion={m['version']}",
        f"versionMin={c.version_min}",
        "tags=" + ";".join(m.get("tags", [])),
    ]
    if m.get("fileId"):
        lines.append("url=" + cfg.WS_URL.format(m["fileId"]))
    return "\n".join(lines) + "\n"


def workshop_txt(m: dict) -> str:
    lines = [
        "version=1",
        f"title={m['name']}",
        f"description={m.get('description', '')}",
        "tags=" + ";".join(m.get("tags", [])),
        f"visibility={m.get('visibility', 'public')}",
    ]
    if m.get("fileId"):
        lines.append(f"id={m['fileId']}")
    return "\n".join(lines) + "\n"


def put(path: Path, text: str, check: bool) -> str:
    old = None
    if path.exists():
        with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
            old = f.read()
    if old == text:
        return "same"
    if check:
        return "DIFF"
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return "wrote"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report differences, write nothing")
    ap.add_argument("--mod", help="only this mod id")
    args = ap.parse_args()

    c = cfg.load()
    mods = [c.mod(args.mod)] if args.mod else c.mods
    if args.mod and not mods[0]:
        sys.exit(f"no mod '{args.mod}' in {c.path}")

    dirty = 0
    for m in mods:
        root = c.mods_source / m["id"]
        if not root.is_dir():
            print(f"MISSING {root}")
            continue
        text = mod_info(m, c)
        r1 = put(root / "mod.info", text, args.check)
        r2 = put(root / "42" / "mod.info", text, args.check)
        r3 = "n/a"
        if m.get("fileId"):
            r3 = put(c.workshop_dir / m["id"] / "workshop.txt", workshop_txt(m), args.check)
        dirty += sum(r == "DIFF" for r in (r1, r2, r3))
        print(f"{m['id']:22} mod.info={r1:5} 42/mod.info={r2:5} workshop.txt={r3}")

    if args.check and dirty:
        print(f"\n{dirty} file(s) differ from the config")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
