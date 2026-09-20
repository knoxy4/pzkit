"""pzkit CLI — thin wrapper over the library; the MCP server is the primary interface."""

import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser(prog="pzkit")
    sub = p.add_subparsers(dest="cmd", required=True)

    ix = sub.add_parser("index", help="Build/query the vanilla data index (P1)")
    ixsub = ix.add_subparsers(dest="index_cmd", required=True)
    ib = ixsub.add_parser("build", help="Full rebuild from media/scripts")
    ib.add_argument("--scripts", help="media/scripts dir (default: env PZ_SCRIPTS_DIR or WSL dedi)")
    ib.add_argument("--db", help="output DB path (default: env PZKIT_DB or pzkit/data/vanilla.db)")
    ixsub.add_parser("semantic-build", help="Embed blocks into LanceDB via local Ollama")
    iq = ixsub.add_parser("query", help="Query the index (G1 surface)")
    iq.add_argument("--db")
    g = iq.add_mutually_exclusive_group(required=True)
    g.add_argument("--sprite", help="items/blocks referencing this sprite/icon/model")
    g.add_argument("--consumes", help="recipes with this item in inputs")
    g.add_argument("--produces", help="recipes with this item in outputs")
    g.add_argument("--search", help="full-text search over blocks")
    g.add_argument("--semantic", help="semantic search via LanceDB")
    g.add_argument("--meta", action="store_true", help="show index stamp")

    sc = sub.add_parser("scaffold", help="Scaffold a new B42 mod (P2)")
    sc.add_argument("mod_id")
    sc.add_argument("--mods-root", default=None, help="default: repo mods/")
    sc.add_argument("--name", default=None, help="display name")
    va = sub.add_parser("validate", help="Validate a mod (P2)")
    va.add_argument("mod_path")
    df = sub.add_parser("diff", help="What a mod overrides vs ships fresh (P2)")
    df.add_argument("mod_path")
    te = sub.add_parser(
        "test",
        help="Boot-smoke a mod on the rig; 'none' = bare, 'baseline' = capture noise baseline (P3)",
    )
    te.add_argument("mod_path")

    args = p.parse_args()
    from pathlib import Path

    if args.cmd == "index":
        return _index(args)
    if args.cmd == "scaffold":
        from .scaffold import scaffold_mod

        root = (
            Path(args.mods_root) if args.mods_root else Path(__file__).resolve().parents[2] / "mods"
        )
        print(f"scaffolded {scaffold_mod(args.mod_id, root, args.name)}")
        return 0
    if args.cmd == "validate":
        from .validator import validate_mod

        rep = validate_mod(args.mod_path)
        for f in rep.findings:
            print(f.render())
        print(f"{'GREEN' if rep.ok else 'RED'} — {args.mod_path}")
        return 0 if rep.ok else 1
    if args.cmd == "test":
        import json

        from .testrig import capture_baseline, test_mod

        if args.mod_path == "baseline":
            v = capture_baseline()
        else:
            v = test_mod(args.mod_path if args.mod_path != "none" else None)
        print(json.dumps(v.to_dict(), indent=1))
        return 0 if v.ok else 1
    if args.cmd == "diff":
        import json

        from .diff import diff_vanilla

        print(json.dumps(diff_vanilla(args.mod_path), indent=1))
        return 0
    raise NotImplementedError(f"'{args.cmd}' lands in its phase — see PZ-JARVIS-PLAN.md section 4")


def _index(args: argparse.Namespace) -> int:
    from pathlib import Path

    from . import vanilla_index as vi

    if args.index_cmd == "build":
        scripts = Path(args.scripts) if args.scripts else vi.default_scripts_path()
        if not scripts or not scripts.is_dir():
            print("scripts dir not found — pass --scripts or set PZ_SCRIPTS_DIR", file=sys.stderr)
            return 2
        db = Path(args.db) if args.db else vi.default_db_path()
        counts = vi.build_index(scripts, db)
        meta = vi.get_meta(vi.connect(db))
        print(f"indexed {counts} -> {db}")
        print(f"buildid {meta['game_buildid']} @ {meta['parsed_at']}")
        return 0

    if args.index_cmd == "semantic-build":
        from . import semantic_index as si

        n = si.build_semantic()
        print(f"embedded {n} blocks -> {si.default_lance_dir()}")
        return 0

    if args.semantic:
        from . import semantic_index as si

        for h in si.semantic_search(args.semantic):
            print(f"{h['btype']} {h['name']} | {h['module']} | d={h['_distance']:.3f}")
        return 0

    con = vi.connect(Path(args.db) if args.db else None)
    if args.meta:
        for k, v in vi.get_meta(con).items():
            print(f"{k}: {v}")
        return 0
    if args.sprite:
        rows = vi.items_referencing(con, args.sprite)
    elif args.consumes:
        rows = vi.recipes_consuming(con, args.consumes)
    elif args.produces:
        rows = vi.recipes_producing(con, args.produces)
    else:
        rows = vi.search_blocks(con, args.search)
    for r in rows:
        print(" | ".join(str(v) for v in r))
    print(f"({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
