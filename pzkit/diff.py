"""diff_vanilla: what a mod overrides vs ships fresh, per (module, btype, name)."""

from __future__ import annotations

from pathlib import Path

from . import vanilla_index as vi
from .scripts_parser import parse_script


def diff_vanilla(mod_path: str | Path, db_path: Path | None = None) -> dict:
    mod = Path(mod_path)
    db = db_path or vi.default_db_path()
    if not Path(db).is_file():
        return {"error": "vanilla index DB not found — run `pzkit index build`"}
    con = vi.connect(db)
    vanilla = {
        (r["module"], r["btype"], r["name"])
        for r in con.execute("SELECT module, btype, name FROM blocks WHERE name IS NOT NULL")
    }

    overrides, new = [], []
    for base in ("42", "common"):
        for p in sorted((mod / base).rglob("media/scripts/**/*.txt")):
            pf = parse_script(
                p.read_text(encoding="utf-8", errors="replace"),
                relpath=p.relative_to(mod).as_posix(),
            )
            for mod_blk in pf.blocks:
                if mod_blk.btype != "module" or not mod_blk.name:
                    continue
                for child in mod_blk.children:
                    if not child.name:
                        continue
                    entry = f"{child.btype} {mod_blk.name}.{child.name}"
                    if (mod_blk.name, child.btype, child.name) in vanilla:
                        overrides.append(entry)
                    else:
                        new.append(entry)
    return {"overrides": sorted(overrides), "new": sorted(new)}
