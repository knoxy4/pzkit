#!/usr/bin/env python3
"""Write the publish.vdf steamcmd uploads from, for every published mod.

Hand-written BBCode descriptions on the Workshop page are preserved: an existing
publish.vdf keeps its description, and only the title, changenote and the
server-operator footer are rewritten. A mod with no publish.vdf yet gets one
built from the config description.

  python publishvdf.py --note "0.4.1 - fixed the shower"
  python publishvdf.py --note "..." --check

Note: a "tags" block in the VDF is silently ignored by steamcmd's
workshop_build_item. Workshop categories can only be set through the in-game
uploader, which reads workshop.txt, or the Steam UGC API. Do not add one.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import sys
from pathlib import Path, PureWindowsPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as cfg  # noqa: E402


def footer(m: dict) -> str:
    return f"Server operators: WorkshopItems={m['fileId']} / Mods={m['id']}"


def build_vdf(m: dict, desc: str, note: str, workshop_dir: Path) -> str:
    # steamcmd reads this file on Windows, so the paths in it are Windows paths
    # regardless of where the tool ran. Joining a POSIX path with a literal
    # backslash produces a mixed separator that steamcmd silently fails on.
    base = str(PureWindowsPath(workshop_dir) / m["id"])
    return (
        '"workshopitem"\n{\n'
        f'\t"appid"\t\t\t"{cfg.APPID}"\n'
        f'\t"publishedfileid"\t"{m["fileId"]}"\n'
        f'\t"contentfolder"\t\t"{base}\\Contents"\n'
        f'\t"previewfile"\t\t"{base}\\preview.jpg"\n'
        f'\t"visibility"\t\t"0"\n'
        f'\t"title"\t\t\t"{m["name"]}"\n'
        f'\t"description"\t"{desc}"\n'
        f'\t"changenote"\t"{note}"\n'
        "}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--note", help="changenote; <name> is replaced with the mod's title")
    ap.add_argument("--check", action="store_true", help="report differences, write nothing")
    ap.add_argument("--mod", help="only this mod id")
    args = ap.parse_args()

    if not args.note and not args.check:
        ap.error("--note is required unless --check is given")

    c = cfg.load()
    mods = [c.mod(args.mod)] if args.mod else c.published()
    if args.mod and not mods[0]:
        sys.exit(f"no mod '{args.mod}' in {c.path}")

    dirty = 0
    for m in mods:
        if not m.get("fileId"):
            print(f"{m['id']:22} skipped - not published yet (fileId is null)")
            continue
        path = c.workshop_dir / m["id"] / "publish.vdf"
        if path.exists():
            text = io.open(path, encoding="utf-8-sig").read()
            found = re.search(r'"description"\s+"(.*?)"\s*\n\s*"changenote"', text, re.S)
            if not found:
                print(f"{m['id']:22} SKIP - cannot find the description block in {path}")
                continue
            desc = found.group(1)
            if footer(m) not in desc:
                desc = re.sub(r"\n*Server operators:[^\n]*\n*$", "\n", desc).rstrip("\n")
                desc += "\n\n" + footer(m)
        else:
            desc = m.get("description", "") + "\n\n" + footer(m)

        note = (args.note or "").replace("<name>", m["name"])
        new = build_vdf(m, desc, note, c.workshop_dir)
        old = io.open(path, encoding="utf-8-sig").read() if path.exists() else None
        status = "same" if old == new else ("DIFF" if args.check else "wrote")
        if status == "wrote":
            path.parent.mkdir(parents=True, exist_ok=True)
            io.open(path, "w", encoding="utf-8", newline="\n").write(new)
        dirty += status == "DIFF"
        print(f"{m['id']:22} publish.vdf={status}  title={m['name']}")

    return 1 if (args.check and dirty) else 0


if __name__ == "__main__":
    sys.exit(main())
