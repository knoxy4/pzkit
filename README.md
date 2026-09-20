# pzkit

Tooling for **Project Zomboid Build 42** mod development: parse the game's own
script data, index it, scaffold a mod, and validate one against reality before
you ship it.

The premise is that PZ fails *silently* on names that do not exist. A loot-list
key with a typo never fires. A `craftRecipe` output that references a
nonexistent item can abort world load with nothing useful in the log. Most mod
bugs are not logic bugs — they are a string that does not match anything in the
game, and nothing tells you.

pzkit builds an index from **your** installed copy of the game and checks your
mod's references against it.

## Install

```bash
git clone https://github.com/knoxy4/pzkit
cd pzkit
pip install -e .
```

Python 3.11+. The core has **no dependencies** — it is stdlib only. Optional
extras: `pip install -e ".[mcp]"` for the MCP server, `".[semantic]"` for the
LanceDB layer, `".[dev]"` for ruff and pytest.

## Quick start

Point it at your game's script directory and build the index:

```bash
export PZ_SCRIPTS_DIR="/path/to/ProjectZomboid/media/scripts"
pzkit index build
```

Then ask it things:

```bash
pzkit index query --consumes Base.Nails      # recipes that consume nails
pzkit index query --produces Base.Plank      # recipes that make planks
pzkit index query --sprite carpentry_01_16   # what uses this sprite
```

And validate a mod:

```bash
pzkit validate /path/to/YourMod
```

Validation covers mod layout, script DSL syntax, references against the vanilla
index, translation files, and Lua (via luacheck if present). **Stages that
cannot run skip loudly** — a missing index or a missing Lua toolchain reports as
SKIPPED, never as a silent pass. Green means checked.

## What's in here

| Path | What |
|---|---|
| `pzkit/vanilla_index.py` | SQLite index over parsed B42 scripts. Walks `media/scripts/**/*.txt`, normalizes into tables, adds FTS. |
| `pzkit/scripts_parser.py` | Parser for PZ's script DSL — items, recipes, blocks, nested props. |
| `pzkit/validator.py` | Layout, syntax, references, translations and Lua checks. |
| `pzkit/refcheck.py` | Type-aware reference resolution, including bare-name keyed fields (`GrantedRecipes`, `XPBoosts`, trait lists) that naive checking misses. Surfaces index staleness so you never validate against an out-of-date snapshot. |
| `pzkit/scaffold.py` | New-mod scaffolding in the B42 layout. |
| `pzkit/testrig.py` | Boot-test harness — does the mod actually load? |
| `pzkit/semantic_index.py` | Optional fuzzy search, embedding via a **local** Ollama. Never a metered API. |
| `pzkit/mcp_server.py` | MCP server, so an AI assistant can query the index instead of guessing names. |
| `tools/probe/` | Read-only probes over vanilla data: the global API surface, level-0 craft recipes, timed actions, the foraging schema, radio data, icon and model inventories. |
| `tools/art/` | Icon pipeline. PZ inventory icons are 32x32 and most art dies at that size; these build at 64, downscale, and show you the result at true size on a dark panel before you believe it. |
| `tools/ws_deploy.ps1` | One-command Steam Workshop publish via SteamCMD (Windows). Never stores or reads a password — SteamCMD caches credentials after one interactive login. |
| `tools/hallucination_sweep.py` | Standalone reference sweep for script references to things that do not exist. |

## Configuration

Everything is environment variables; nothing is hardcoded to a machine.

| Variable | Default | What |
|---|---|---|
| `PZ_SCRIPTS_DIR` | — | Your game's `media/scripts` directory. Required for indexing. |
| `PZKIT_DB` | `data/vanilla.db` | Where the SQLite index lives. |
| `PZKIT_LANCE_DIR` | — | LanceDB directory for the semantic layer. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Local embedding endpoint. |
| `COMFYUI_URL` | `http://127.0.0.1:8288` | Local image generation, for the art helpers. |
| `PZ_TEXTURES_DIR` | — | Default textures directory for `tools/art/` scripts (each also takes a path argument). |

## A note on ground truth

The index is built from *your* install, on purpose. This repo ships no
extracted game data: name lists go stale the moment the game updates, and a
stale list that looks authoritative is worse than no list. Rebuild after every
game update — `refcheck` will tell you when the index is older than the build
it is checking against.

## Related

- **[pz-sprite-forge](https://github.com/Leeheejin/pz-sprite-forge)** by Leeheejin — models custom PZ tiles in Blender with the projection and lighting measured from the game's own art. Separate MIT project, not affiliated with this one, and worth your time if you make furniture or props.

## Contributing

Issues and pull requests welcome. Two things to know:

1. **No metered APIs.** Everything here is meant to run in CI and on a nightly
   schedule. A tool that costs money per invocation stops getting run, so it
   stops being trusted. Local models are fine; hosted inference is not.
2. **Fail loudly.** A check that cannot run reports SKIPPED. Nothing in this
   codebase is allowed to pass silently when it did not actually verify
   anything — that is the exact failure mode the whole project exists to fix.

## License

MIT. See [LICENSE](LICENSE).

Project Zomboid is a trademark of The Indie Stone. This project is an
independent, unofficial modding tool and is not affiliated with or endorsed by
The Indie Stone.
