"""pzkit MCP server — project-aware tools over stdio (FastMCP).

Run: python -m pzkit.mcp_server. Wire in .mcp.json after PRs merge.
The vanilla oracle (wink's server) stays separate; this server owns anything
that knows about OUR repo, index, and mods.
"""

from __future__ import annotations

from pathlib import Path

from fastmcp import FastMCP

from . import vanilla_index as vi

mcp = FastMCP("pzkit")

_REPO_MODS = Path(__file__).resolve().parents[2] / "mods"


@mcp.tool
def scaffold_mod(mod_id: str, display_name: str = "", description: str = "") -> str:
    """Create a B42-correct mod skeleton under mods/ (pzj_ prefix enforced)."""
    from .scaffold import scaffold_mod as _scaffold

    path = _scaffold(mod_id, _REPO_MODS, display_name or None, description)
    return f"scaffolded {path}"


@mcp.tool
def validate_mod(mod_path: str) -> dict:
    """Validate a mod: layout, DSL syntax, refs vs vanilla index, translations, Lua."""
    from .validator import validate_mod as _validate

    return _validate(mod_path).to_dict()


@mcp.tool
def diff_vanilla(mod_path: str) -> dict:
    """What the mod overrides in vanilla vs ships fresh."""
    from .diff import diff_vanilla as _diff

    return _diff(mod_path)


@mcp.tool
def search_index(query: str, mode: str = "exact", limit: int = 10) -> list:
    """Search the pzkit vanilla index. mode: exact (FTS) | semantic (LanceDB/Ollama)."""
    if mode == "semantic":
        from .semantic_index import semantic_search

        return semantic_search(query, k=limit)
    con = vi.connect()
    return [dict(r) for r in vi.search_blocks(con, query, limit=limit)]


@mcp.tool
def recipes_for(item: str, direction: str = "consuming") -> list:
    """Recipes consuming or producing an item (FQN or bare name)."""
    con = vi.connect()
    fn = vi.recipes_consuming if direction == "consuming" else vi.recipes_producing
    return [dict(r) for r in fn(con, item)]


@mcp.tool
def test_mod(mod_path: str = "", timeout_s: int = 300) -> dict:
    """Boot-smoke a mod on the isolated rig; empty mod_path = bare boot. ~1-3 min."""
    from .testrig import test_mod as _test

    return _test(mod_path or None, timeout_s=timeout_s).to_dict()


@mcp.tool
def generate_art(prompt: str, out_path: str) -> str:
    """Render mod art via local ComfyUI (Z-Image). Needs pzkit/workflows/zimage_default.json."""
    from . import art

    if not art.WORKFLOW.is_file():
        raise FileNotFoundError(
            f"workflow template missing: {art.WORKFLOW} — export it from ComfyUI "
            "(Save API Format), see pzkit/workflows/README.md. Not faking it."
        )
    return art.generate(prompt, out_path)


if __name__ == "__main__":
    mcp.run()
