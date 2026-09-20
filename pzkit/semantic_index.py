"""LanceDB semantic layer over the SQLite vanilla index — P1's fuzzy half.

Embeds one document per named game block via LOCAL Ollama (nomic-embed-text);
never a metered API (CONVENTIONS §10). Reads blocks from vanilla_index's DB —
it never re-parses scripts. Rebuild after every SQLite rebuild.
"""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.request
from pathlib import Path

from . import vanilla_index as vi

EMBED_MODEL = "nomic-embed-text"
# named, player-meaningful block types; anon plumbing (model{}, clip{}) rides along as prop text
DOC_BTYPES = (
    "item",
    "craftRecipe",
    "vehicle",
    "sound",
    "evolvedrecipe",
    "fixing",
    "timedAction",
    "entity",
    "fluid",
    "energy",
)
_BATCH = 128
_MAX_DOC_CHARS = 2000  # vehicles fold in deep part trees; nomic window fits this fine


def default_lance_dir() -> Path:
    env = os.environ.get("PZKIT_LANCE_DIR")
    return Path(env) if env else vi.default_db_path().parent / "lance"


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


def embed_batch(texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    req = urllib.request.Request(
        f"{_ollama_url()}/api/embed",
        data=json.dumps({"model": model, "input": texts}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)["embeddings"]


def _block_doc(con: sqlite3.Connection, row: sqlite3.Row) -> str:
    # whole subtree: nested anon blocks (model{}, skin{}, clip{}) carry the searchable
    # identity of vehicles/sounds/entities; parent comes first so truncation keeps it
    ids = [
        r["id"]
        for r in con.execute(
            """WITH RECURSIVE sub(id) AS (
                   SELECT ? UNION ALL
                   SELECT b.id FROM blocks b JOIN sub ON b.parent_id = sub.id)
               SELECT id FROM sub ORDER BY id""",
            (row["id"],),
        )
    ]
    marks = ",".join("?" * len(ids))
    props = con.execute(
        f"SELECT key, value FROM props WHERE block_id IN ({marks}) ORDER BY block_id, seq", ids
    ).fetchall()
    prop_text = "; ".join(f"{p['key']}={p['value']}" for p in props)
    doc = f"{row['btype']} {row['name']} in {row['module'] or '?'}: {prop_text}"
    if row["btype"] == "craftRecipe":
        io = con.execute(
            "SELECT direction, target FROM recipe_targets WHERE block_id = ?", (row["id"],)
        ).fetchall()
        ins = [r["target"] for r in io if r["direction"] == "input"]
        outs = [r["target"] for r in io if r["direction"] == "output"]
        doc += f" | consumes {', '.join(ins)} | produces {', '.join(outs)}"
    else:
        entries = con.execute(
            f"SELECT text FROM entries WHERE block_id IN ({marks}) ORDER BY block_id, seq", ids
        ).fetchall()
        if entries:
            doc += " | " + "; ".join(e["text"] for e in entries)
    return doc[:_MAX_DOC_CHARS]


def build_semantic(
    db_path: Path | None = None, lance_dir: Path | None = None, model: str = EMBED_MODEL
) -> int:
    import lancedb

    con = vi.connect(db_path)
    rows = con.execute(
        f"""SELECT b.id, b.module, b.btype, b.name FROM blocks b
            WHERE b.name IS NOT NULL AND b.btype IN ({",".join("?" * len(DOC_BTYPES))})""",
        DOC_BTYPES,
    ).fetchall()
    docs = [(r["id"], r["module"], r["btype"], r["name"], _block_doc(con, r)) for r in rows]

    db = lancedb.connect(lance_dir or default_lance_dir())
    records = []
    for i in range(0, len(docs), _BATCH):
        chunk = docs[i : i + _BATCH]
        vectors = embed_batch([d[4] for d in chunk], model)
        records += [
            {
                "block_id": d[0],
                "module": d[1],
                "btype": d[2],
                "name": d[3],
                "text": d[4],
                "vector": v,
            }
            for d, v in zip(chunk, vectors)
        ]
    db.create_table("blocks", records, mode="overwrite")
    meta = vi.get_meta(con)
    (Path(lance_dir or default_lance_dir()) / "STAMP.json").write_text(
        json.dumps({"game_buildid": meta.get("game_buildid"), "model": model, "docs": len(records)})
    )
    return len(records)


def semantic_search(
    query: str, k: int = 10, lance_dir: Path | None = None, model: str = EMBED_MODEL
) -> list[dict]:
    import lancedb

    db = lancedb.connect(lance_dir or default_lance_dir())
    table = db.open_table("blocks")
    vec = embed_batch([query], model)[0]
    hits = table.search(vec).limit(k).to_list()
    return [
        {k2: h[k2] for k2 in ("block_id", "module", "btype", "name", "_distance")} for h in hits
    ]
