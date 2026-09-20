"""Scaffold a B42-correct mod skeleton.

Layout: mod.info + common/ + 42/media/{scripts,lua,translations}. The example
item ships references verified against the vanilla index (Icon/model
AlarmClock), so a fresh scaffold validates green end to end, translations
included.

Mod ids are unconstrained by default. Set PZKIT_MOD_PREFIX if your project
requires every mod to share a namespace - scaffold and validate will then both
enforce it.
"""

from __future__ import annotations

import os
from pathlib import Path

# Empty by default: a shared namespace is a project convention, not a property
# of Build 42, and hardcoding one makes this tool refuse everyone else's mods.
MOD_PREFIX = os.environ.get("PZKIT_MOD_PREFIX", "")

_MOD_INFO = """\
name={display_name}
id={mod_id}
description={description}
modversion=0.1.0
"""

_EXAMPLE_ITEM = """\
module {mod_id}
{{
    item HelloDoodad
    {{
        DisplayCategory = Junk,
        Weight = 0.1,
        Icon = AlarmClock,
        WorldStaticModel = AlarmClock,
    }}
}}
"""

_EXAMPLE_TRANSLATION = """\
ItemName_EN = {{
    ItemName_{mod_id}.HelloDoodad = "Hello Doodad",
}}
"""


def scaffold_mod(
    mod_id: str,
    mods_root: str | Path,
    display_name: str | None = None,
    description: str = "",
    with_example_item: bool = True,
) -> Path:
    """Create the skeleton; returns the mod dir. Refuses bad ids and existing dirs."""
    if MOD_PREFIX and not mod_id.startswith(MOD_PREFIX):
        raise ValueError(
            f"mod id must start with {MOD_PREFIX!r} (set by PZKIT_MOD_PREFIX): {mod_id!r}"
        )
    if not mod_id or not mod_id.replace("_", "").isalnum():
        raise ValueError(f"mod id must be alphanumeric/underscore: {mod_id!r}")
    root = Path(mods_root) / mod_id
    if root.exists():
        raise FileExistsError(f"{root} already exists — scaffold refuses to overwrite")

    media = root / "42" / "media"
    for d in (
        root / "common" / "media",
        media / "scripts",
        media / "lua" / "client",
        media / "lua" / "server",
        media / "lua" / "shared",
        media / "translations" / "EN",
    ):
        d.mkdir(parents=True)

    display_name = display_name or mod_id.removeprefix(MOD_PREFIX).replace("_", " ").title()
    info = _MOD_INFO.format(display_name=display_name, mod_id=mod_id, description=description)
    # both locations: B42 loader resolves the versioned copy (rig-verified);
    # root copy keeps B41-style tooling and humans oriented
    (root / "mod.info").write_text(info, encoding="utf-8")
    (root / "42" / "mod.info").write_text(info, encoding="utf-8")
    if with_example_item:
        (media / "scripts" / f"{mod_id}_items.txt").write_text(
            _EXAMPLE_ITEM.format(mod_id=mod_id), encoding="utf-8"
        )
        (media / "translations" / "EN" / "ItemName_EN.txt").write_text(
            _EXAMPLE_TRANSLATION.format(mod_id=mod_id), encoding="utf-8"
        )
    return root
