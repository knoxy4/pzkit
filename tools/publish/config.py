#!/usr/bin/env python3
"""Shared configuration for the Workshop publishing tools.

One file describes your mods and where things live on this machine; every tool
in this directory reads it. Nothing is hardcoded to a particular user, repo or
mod set.

Resolution order for the config file:
  1. $PZPUBLISH_CONFIG
  2. ./pzpublish.json
  3. <git repo root>/pzpublish.json

Any path field can be overridden by an environment variable, which is how CI
and a second machine stay out of the committed file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

APPID = "108600"
WS_URL = "https://steamcommunity.com/sharedfiles/filedetails/?id={}"


def repo_root(start: Path | None = None) -> Path:
    """Git root of the directory you are working in, not of this script.

    These tools are meant to be usable from any mod repo, including one that
    does not contain them. Resolving from __file__ would find the toolkit's own
    checkout and quietly look for your mods inside it.
    """
    here = (start or Path.cwd())
    try:
        out = subprocess.check_output(
            ["git", "-C", str(here), "rev-parse", "--show-toplevel"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return here


def _find_config() -> Path:
    env = os.environ.get("PZPUBLISH_CONFIG")
    if env:
        return Path(env).expanduser()
    local = Path.cwd() / "pzpublish.json"
    if local.is_file():
        return local
    return repo_root() / "pzpublish.json"


class Config:
    def __init__(self, data: dict, path: Path):
        self.path = path
        self._d = data

        self.author: str = data.get("author", "")
        self.version_min: str = data.get("versionMin", "42.0.0")
        self.steam_user: str = os.environ.get("PZ_STEAM_USER") or data.get("steamUser", "")
        self.mods: list[dict] = data.get("mods", [])

        self.workshop_dir = self._path("workshopDir", "PZ_WORKSHOP_DIR",
                                       "~/Zomboid/Workshop")
        self.game_mods_dir = self._path("modsDir", "PZ_MODS_DIR", "~/Zomboid/mods")
        self.steamcmd = self._path("steamcmd", "PZ_STEAMCMD", "steamcmd")

        src = data.get("modsSource")
        if src:
            self.mods_source = Path(src).expanduser()
        else:
            root = repo_root()
            self.mods_source = root / "mods" if (root / "mods").is_dir() else root

    def _path(self, key: str, env: str, default: str) -> Path:
        return Path(os.environ.get(env) or self._d.get(key) or default).expanduser()

    def mod(self, mod_id: str) -> dict | None:
        return next((m for m in self.mods if m.get("id") == mod_id), None)

    def published(self) -> list[dict]:
        return [m for m in self.mods if m.get("fileId")]


def load(required: bool = True) -> Config:
    path = _find_config()
    if not path.is_file():
        if not required:
            return Config({}, path)
        sys.exit(
            f"no config found at {path}\n"
            "Copy pzpublish.example.json to pzpublish.json at your repo root and "
            "edit it, or set PZPUBLISH_CONFIG to point at one."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        sys.exit(f"{path} is not valid JSON: {exc}")

    missing = [k for k in ("author", "mods") if k not in data]
    if missing:
        sys.exit(f"{path} is missing required key(s): {', '.join(missing)}")
    for i, m in enumerate(data.get("mods", [])):
        for k in ("id", "name", "version"):
            if k not in m:
                sys.exit(f"{path}: mods[{i}] is missing '{k}'")
    return Config(data, path)
