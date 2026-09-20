"""SQLite vanilla index over parsed B42 scripts — the exact layer of P1's data spine.

Build: walk media/scripts/**/*.txt -> scripts_parser -> normalized tables.
Query: the G1 gate lives here (items_referencing / recipes_consuming) plus FTS.
LanceDB semantic layer rides on top of this DB, it never re-parses.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
from pathlib import Path

from .scripts_parser import ParsedFile, ScriptBlock, parse_recipe_entry, parse_script

PARSER_VERSION = 1
APPID = "380870"

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE files (
    id INTEGER PRIMARY KEY, relpath TEXT UNIQUE, sha1 TEXT, mtime REAL, nblocks INTEGER
);
CREATE TABLE blocks (
    id INTEGER PRIMARY KEY, file_id INTEGER REFERENCES files(id), parent_id INTEGER,
    module TEXT, btype TEXT, name TEXT, depth INTEGER, start_line INTEGER, end_line INTEGER
);
CREATE TABLE props (
    block_id INTEGER REFERENCES blocks(id), seq INTEGER, key TEXT, value TEXT, line INTEGER
);
CREATE TABLE entries (
    block_id INTEGER REFERENCES blocks(id), seq INTEGER, text TEXT, line INTEGER
);
CREATE TABLE recipe_targets (
    block_id INTEGER REFERENCES blocks(id), direction TEXT, seq INTEGER,
    kind TEXT, target TEXT, target_is TEXT, amount REAL, mode TEXT, raw TEXT
);
CREATE TABLE refs (block_id INTEGER REFERENCES blocks(id), kind TEXT, value TEXT);
CREATE TABLE warnings (relpath TEXT, message TEXT);
CREATE INDEX idx_blocks_name ON blocks(name);
CREATE INDEX idx_blocks_type ON blocks(btype);
CREATE INDEX idx_props_key ON props(key);
CREATE INDEX idx_refs_kv ON refs(kind, value);
CREATE INDEX idx_rt_target ON recipe_targets(target, direction);
"""

_ICON_KEYS = {"icon", "iconsfortexture", "hotbaricon"}
_MODEL_KEYS = {
    "worldstaticmodel",
    "staticmodel",
    "weaponsprite",
    "physicsobject",
    "carmechanicsoverlay",
    "file",
    "model",
}
_TEXTURE_KEY_RE = re.compile(r"texture|sprite", re.IGNORECASE)
_SOUND_KEY_RE = re.compile(r"sound", re.IGNORECASE)
_ITEM_FQN = re.compile(r"^[A-Za-z_]\w*\.[A-Za-z_][\w.]*$")


def default_scripts_path() -> Path | None:
    """Locate media/scripts, preferring PZ_SCRIPTS_DIR.

    The fallback probes a WSL2 dedicated-server install, which is a convenience
    for one common setup and not a requirement - set PZ_SCRIPTS_DIR and none of
    this runs.
    """
    env = os.environ.get("PZ_SCRIPTS_DIR")
    if env:
        return Path(env)
    user = os.environ.get("PZ_WSL_USER") or os.environ.get("USER") or os.environ.get("USERNAME")
    if not user:
        return None
    distros = [os.environ["PZ_WSL_DISTRO"]] if os.environ.get("PZ_WSL_DISTRO") else [
        "Ubuntu", "Ubuntu-24.04",
    ]
    for distro in distros:
        p = Path(rf"\\wsl.localhost\{distro}\home\{user}\pzserver\media\scripts")
        if p.is_dir():
            return p
    return None


def default_db_path() -> Path:
    env = os.environ.get("PZKIT_DB")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "data" / "vanilla.db"


def _game_buildid(scripts_path: Path) -> str:
    """Walk up from media/scripts to steamapps/appmanifest and read the Steam buildid."""
    for parent in scripts_path.parents:
        manifest = parent / "steamapps" / f"appmanifest_{APPID}.acf"
        if manifest.is_file():
            m = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text(errors="replace"))
            if m:
                return m.group(1)
    return "unknown"


def build_index(scripts_path: Path, db_path: Path) -> dict[str, int]:
    """Full rebuild (atomic swap via temp file). Returns count summary."""
    tmp = db_path.with_suffix(".building")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(_SCHEMA)
    fts = _try_fts(con)

    counts = {"files": 0, "blocks": 0, "props": 0, "recipes": 0, "warnings": 0}
    for path in sorted(scripts_path.rglob("*.txt")):
        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_script(text, relpath=path.relative_to(scripts_path).as_posix())
        _insert_file(con, parsed, text, counts, fts)
    _insert_meta(con, scripts_path, counts)
    con.commit()
    con.close()
    os.replace(tmp, db_path)
    return counts


def _try_fts(con: sqlite3.Connection) -> bool:
    try:
        con.execute(
            "CREATE VIRTUAL TABLE blocks_fts USING fts5(name, module, btype, proptext, content='')"
        )
        return True
    except sqlite3.OperationalError:
        return False


def _insert_file(
    con: sqlite3.Connection, parsed: ParsedFile, text: str, counts: dict, fts: bool
) -> None:
    fid = con.execute(
        "INSERT INTO files (relpath, sha1, mtime, nblocks) VALUES (?,?,?,?)",
        (parsed.relpath, hashlib.sha1(text.encode()).hexdigest(), time.time(), len(parsed.blocks)),
    ).lastrowid
    counts["files"] += 1
    for w in parsed.warnings:
        con.execute("INSERT INTO warnings VALUES (?,?)", (parsed.relpath, w))
        counts["warnings"] += 1
    for blk in parsed.blocks:
        module = blk.name if blk.btype == "module" else None
        _insert_block(con, blk, fid, None, module, 0, counts, fts)


def _insert_block(
    con: sqlite3.Connection,
    blk: ScriptBlock,
    fid: int,
    parent: int | None,
    module: str | None,
    depth: int,
    counts: dict,
    fts: bool,
) -> None:
    bid = con.execute(
        "INSERT INTO blocks (file_id, parent_id, module, btype, name, depth, start_line, end_line)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (fid, parent, module, blk.btype, blk.name, depth, blk.start_line, blk.end_line),
    ).lastrowid
    counts["blocks"] += 1
    for seq, p in enumerate(blk.props):
        con.execute("INSERT INTO props VALUES (?,?,?,?,?)", (bid, seq, p.key, p.value, p.line))
        counts["props"] += 1
    for seq, (text, line) in enumerate(blk.entries):
        con.execute("INSERT INTO entries VALUES (?,?,?,?)", (bid, seq, text, line))
    _extract_refs(con, bid, blk)
    if blk.btype == "craftRecipe":
        counts["recipes"] += 1
        _extract_recipe_io(con, bid, blk)
    if fts and blk.btype != "module":
        proptext = " ".join(f"{p.key} {p.value}" for p in blk.props)
        con.execute(
            "INSERT INTO blocks_fts (rowid, name, module, btype, proptext) VALUES (?,?,?,?,?)",
            (bid, blk.name or "", module or "", blk.btype, proptext),
        )
    for child in blk.children:
        child_module = child.name if child.btype == "module" else module
        _insert_block(con, child, fid, bid, child_module, depth + 1, counts, fts)


def _extract_refs(con: sqlite3.Connection, bid: int, blk: ScriptBlock) -> None:
    def add(kind: str, value: str) -> None:
        value = value.strip()
        if value:
            con.execute("INSERT INTO refs VALUES (?,?,?)", (bid, kind, value))

    for p in blk.props:
        kl = p.key.lower()
        segments = [s.strip() for s in p.value.split(";") if s.strip()]
        if kl in _ICON_KEYS:
            for s in segments:
                add("icon", s)
        elif kl in _MODEL_KEYS:
            for s in segments:
                add("model", s)
        elif kl == "tags":
            for s in segments:
                add("tag", s)
        elif _TEXTURE_KEY_RE.search(kl):
            for s in segments:
                add("texture", s)
        elif _SOUND_KEY_RE.search(kl):
            for s in segments:
                add("sound", s)
        for s in segments:
            # first ';' segment of Fixer etc. is an FQN; skill suffixes (Aiming=3) are not
            if _ITEM_FQN.match(s) and not _looks_numeric_tail(s):
                add("item", s)


def _looks_numeric_tail(s: str) -> bool:
    return bool(re.search(r"\.\d", s))


def _extract_recipe_io(con: sqlite3.Connection, bid: int, blk: ScriptBlock) -> None:
    for child in blk.children:
        direction = {"inputs": "input", "outputs": "output"}.get(child.btype)
        if not direction:
            continue
        for seq, (text, _line) in enumerate(child.entries):
            e = parse_recipe_entry(text)
            rows = (
                [(t, "item") for t in e.targets]
                + [(t, "tag") for t in e.tags]
                + ([(e.mapper, "mapper")] if e.mapper else [])
            )
            for target, tis in rows:
                con.execute(
                    "INSERT INTO recipe_targets VALUES (?,?,?,?,?,?,?,?,?)",
                    (bid, direction, seq, e.kind, target, tis, e.amount, e.mode, text),
                )


def _insert_meta(con: sqlite3.Connection, scripts_path: Path, counts: dict) -> None:
    meta = {
        "game_buildid": _game_buildid(scripts_path),
        "source_path": str(scripts_path),
        "parsed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "parser_version": str(PARSER_VERSION),
        "counts": json.dumps(counts),
    }
    con.executemany("INSERT INTO meta VALUES (?,?)", meta.items())


# ---- query side (G1 gate) ----------------------------------------------------


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(db_path or default_db_path())
    con.row_factory = sqlite3.Row
    return con


def items_referencing(con: sqlite3.Connection, sprite: str) -> list[sqlite3.Row]:
    """Blocks whose icon/model/texture refs name this sprite/model/icon."""
    return con.execute(
        """SELECT DISTINCT b.module, b.btype, b.name, r.kind, r.value, f.relpath
           FROM refs r JOIN blocks b ON b.id = r.block_id JOIN files f ON f.id = b.file_id
           WHERE r.kind IN ('icon','model','texture') AND r.value = ? COLLATE NOCASE
           ORDER BY b.btype, b.name""",
        (sprite,),
    ).fetchall()


def recipes_consuming(con: sqlite3.Connection, item: str) -> list[sqlite3.Row]:
    """craftRecipes with this item (FQN or bare name, or a tag) in inputs."""
    variants = [item, f"Base.{item}"] if "." not in item else [item, item.split(".", 1)[1]]
    return con.execute(
        """SELECT DISTINCT b.module, b.name, rt.target, rt.target_is, rt.amount, rt.mode,
                  f.relpath
           FROM recipe_targets rt
           JOIN blocks b ON b.id = rt.block_id JOIN files f ON f.id = b.file_id
           WHERE rt.direction = 'input' AND rt.target IN (?, ?) COLLATE NOCASE
           ORDER BY b.name""",
        (*variants,),
    ).fetchall()


def recipes_producing(con: sqlite3.Connection, item: str) -> list[sqlite3.Row]:
    variants = [item, f"Base.{item}"] if "." not in item else [item, item.split(".", 1)[1]]
    return con.execute(
        """SELECT DISTINCT b.module, b.name, rt.target, rt.amount, f.relpath
           FROM recipe_targets rt
           JOIN blocks b ON b.id = rt.block_id JOIN files f ON f.id = b.file_id
           WHERE rt.direction = 'output' AND rt.target IN (?, ?) COLLATE NOCASE
           ORDER BY b.name""",
        (*variants,),
    ).fetchall()


def search_blocks(con: sqlite3.Connection, query: str, limit: int = 20) -> list[sqlite3.Row]:
    try:
        return con.execute(
            """SELECT b.module, b.btype, b.name, f.relpath
               FROM blocks_fts JOIN blocks b ON b.id = blocks_fts.rowid
               JOIN files f ON f.id = b.file_id
               WHERE blocks_fts MATCH ? ORDER BY rank LIMIT ?""",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        like = f"%{query}%"
        return con.execute(
            """SELECT b.module, b.btype, b.name, f.relpath FROM blocks b
               JOIN files f ON f.id = b.file_id
               WHERE b.name LIKE ? ORDER BY b.name LIMIT ?""",
            (like, limit),
        ).fetchall()


def get_meta(con: sqlite3.Connection) -> dict[str, str]:
    return dict(con.execute("SELECT key, value FROM meta"))
