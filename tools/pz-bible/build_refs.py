#!/usr/bin/env python3
"""Generate pz-bible reference lists from an installed Project Zomboid B42 build.

Every list is extracted from files on disk (plus two optional online sources for
the engine API surface). Nothing is hand-maintained, and nothing ships in this
repo: a name list that looks authoritative but predates the current build is
worse than no list at all.

    python3 build_refs.py --game "/path/to/ProjectZomboid" --out refs/

Vanilla only by default. To also index installed and subscribed mods so your own
identifiers verify too:

    python3 build_refs.py --game "<game>" \\
        --mods "~/Zomboid/mods" \\
        --mods "<steam>/steamapps/workshop/content/108600"

Two lists come from outside the install, because the engine API is not in it:
`api`, `enums` and part of `perks` from PZ-Umbrella's typed definitions, and
`events` from PZEventDoc. Use --umbrella-dir to point at a local checkout, or
--offline to skip both and keep any existing copies of those files.
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

UMBRELLA_ZIP = "https://github.com/PZ-Umbrella/Umbrella/archive/refs/heads/main.zip"
EVENTS_MD = "https://raw.githubusercontent.com/demiurgeQuantified/PZEventDoc/develop/docs/Events.md"

# The original PowerShell extractor used -match / Select-String, which are
# case-insensitive in PowerShell. Keeping that behaviour matters: script blocks
# in the wild are written `Item`, `item` and `ITEM`. The three places the
# original deliberately used -cmatch are case-sensitive here too, and marked.
ICASE = re.IGNORECASE


def _sorted_unique(values) -> list[str]:
    """Deduplicate case-sensitively, order case-insensitively.

    PowerShell's `Sort-Object -Unique` compares case-insensitively, so it would
    collapse `Base.Axe` and `Base.axe` into one entry. PZ names are
    case-sensitive and the verifier treats a case mismatch as an error, so
    collapsing them would make the bible lie. Both are kept.
    """
    seen = {v for v in values if v}
    return sorted(seen, key=lambda s: (s.lower(), s))


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _under(path: Path, *segments: str) -> bool:
    """True when `path` sits under an adjacent run of directories.

    `media` and `scripts` must be consecutive: a mod with `media/scripts/x.txt`
    counts, one with `media/textures/scripts/x.txt` does not. Matching them
    independently pulls in unrelated trees and inflates every list.
    """
    parts = [p.lower() for p in path.parts]
    want = [s.lower() for s in segments]
    return any(parts[i:i + len(want)] == want for i in range(len(parts) - len(want) + 1))


def _script_files(game: Path, mod_roots: list[Path]) -> list[Path]:
    files = sorted(p for p in (game / "media" / "scripts").rglob("*.txt") if p.is_file())
    for root in mod_roots:
        files += sorted(
            p for p in root.rglob("*.txt")
            if p.is_file() and _under(p, "media", "scripts")
        )
    return files


def _lua_files(game: Path, mod_roots: list[Path]) -> list[Path]:
    files = sorted(p for p in (game / "media" / "lua").rglob("*.lua") if p.is_file())
    for root in mod_roots:
        files += sorted(
            p for p in root.rglob("*.lua")
            if p.is_file() and _under(p, "media", "lua")
        )
    return files


# --------------------------------------------------------------------------
# script blocks
# --------------------------------------------------------------------------

_RE_MODULE = re.compile(r"^\s*module\s+([A-Za-z0-9_]+)", ICASE)
_SCRIPT_RULES = [
    ("item", re.compile(r"^\s*item\s+([A-Za-z0-9_]+)", ICASE)),
    ("sound", re.compile(r"^\s*sound\s+([A-Za-z0-9_]+)", ICASE)),
    ("model", re.compile(r"^\s*model\s+([A-Za-z0-9_]+)", ICASE)),
    ("recipe", re.compile(r"^\s*(?:craftRecipe|entity)\s+([A-Za-z0-9_]+)", ICASE)),
    ("evolvedrecipe", re.compile(r"^\s*evolvedrecipe\s+([A-Za-z0-9_ ]+?)\s*\{?\s*$", ICASE)),
    ("fluid", re.compile(r"^\s*fluid\s+([A-Za-z0-9_]+)", ICASE)),
    ("energy", re.compile(r"^\s*energy\s+([A-Za-z0-9_]+)", ICASE)),
    ("attachment", re.compile(r"^\s*attachment\s+([A-Za-z0-9_]+)", ICASE)),
    ("timedaction", re.compile(r"^\s*timedAction\s+([A-Za-z0-9_]+)", ICASE)),
    ("animscript", re.compile(r"^\s*anim\s+([A-Za-z0-9_]+)", ICASE)),
    ("vehiclepart", re.compile(r"^\s*part\s+([A-Za-z0-9_]+)", ICASE)),
    ("model2", re.compile(r"(?:StaticModel|WorldStaticModel)\s*=\s*([A-Za-z0-9_.]+)\s*,", ICASE)),
    ("itemtype", re.compile(r"ItemType\s*=\s*([a-z:]+)\s*,", ICASE)),
    ("category", re.compile(r"DisplayCategory\s*=\s*([A-Za-z0-9_]+)\s*,", ICASE)),
    ("icon", re.compile(r"^\s*Icon\s*=\s*([A-Za-z0-9_]+)\s*,", ICASE)),
    ("tags", re.compile(r"^\s*Tags\s*=\s*([^,]+),", ICASE)),
]
_RE_VEHICLE = re.compile(r"^\s*vehicle\s+([A-Za-z0-9_]+)", ICASE)
_RE_FIXING = re.compile(r"^\s*fixing\s+([A-Za-z0-9_ ]+?)\s*$", ICASE)


def scan_scripts(files: list[Path]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for f in files:
        module = "Base"
        for line in _read_lines(f):
            m = _RE_MODULE.match(line)
            if m:
                module = m.group(1)
                continue
            # First match wins, exactly as the original's `continue` chain did.
            for kind, rx in _SCRIPT_RULES:
                m = rx.search(line)
                if not m:
                    continue
                if kind == "item":
                    out["item"].append(f"{module}.{m.group(1)}")
                elif kind == "model2":
                    out["model"].append(m.group(1))
                elif kind == "tags":
                    out["tag"].extend(t.strip() for t in m.group(1).split(";"))
                else:
                    out[kind].append(m.group(1).strip())
                break
        # Separate pass in the original, kept separate: the rule chain above
        # never matches a `vehicle` or `fixing` line, but folding them in would
        # make that an assumption instead of a fact.
        for line in _read_lines(f):
            m = _RE_VEHICLE.match(line)
            if m:
                out["vehicle"].append(m.group(1))
                continue
            m = _RE_FIXING.match(line)
            if m:
                out["fixing"].append(m.group(1).strip())
    return out


# --------------------------------------------------------------------------
# lua-derived lists
# --------------------------------------------------------------------------

def scan_distributions(game: Path) -> tuple[list[str], list[str], list[str]]:
    items_dir = game / "media" / "lua" / "server" / "Items"
    keys: list[str] = []
    rx = re.compile(r"^(?:\t| {1,4})([A-Za-z][A-Za-z0-9_]*) = \{")
    for name in ("Distributions.lua", "SuburbsDistributions.lua"):
        for line in _read_lines(items_dir / name):
            m = rx.match(line)
            if m:
                keys.append(m.group(1))
    # case-SENSITIVE split, as in the original (-cmatch): lowercase keys are
    # room names, capitalised ones are container distributions.
    rooms = [k for k in keys if k[:1].islower()]
    dists = [k for k in keys if k[:1].isupper()]

    # Case-SENSITIVE on purpose. Procedural list names are capitalised; the
    # lowercase keys at the same indent (`items`, `junk`) are fields *inside* a
    # distribution table, not lists. A case-insensitive match picks them up and
    # the verifier then confirms two names that are not procedural lists.
    proclists: list[str] = []
    rx2 = re.compile(r"^[\t ]+([A-Z][A-Za-z0-9_]*) = \{")
    for line in _read_lines(items_dir / "ProceduralDistributions.lua"):
        m = rx2.match(line)
        if m:
            proclists.append(m.group(1))
    return rooms, dists, proclists


def scan_perks(lua_files: list[Path]) -> list[str]:
    rx = re.compile(r"Perks\.([A-Za-z0-9_]+)", ICASE)
    skip = {"fromstring", "get", "max", "none"}
    found = []
    for f in lua_files:
        for m in rx.finditer(_read_text(f)):
            if m.group(1).lower() not in skip:
                found.append(m.group(1))
    return found


def scan_lua_classes_and_functions(lua_files: list[Path]) -> tuple[list[str], list[str]]:
    rx_cls = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*[A-Za-z0-9_]+:derive\(", ICASE | re.M)
    rx_fn = re.compile(r"^function ([A-Za-z][A-Za-z0-9_]*)\s*\(", ICASE | re.M)
    classes, fns = [], []
    for f in lua_files:
        text = _read_text(f)
        classes += rx_cls.findall(text)
        fns += rx_fn.findall(text)
    return classes, fns


def scan_sandboxvars(game: Path) -> list[str]:
    path = game / "media" / "lua" / "shared" / "Sandbox" / "Apocalypse.lua"
    rx = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=")
    return [m.group(1) for line in _read_lines(path)
            if (m := rx.match(line)) and m.group(1) != "SandboxVars"]


def scan_foragecats(game: Path) -> list[str]:
    rx = re.compile(r'^\s*name\s*=\s*"([^"]+)"', ICASE)
    found = []
    for f in (game / "media" / "lua" / "shared" / "Foraging").rglob("*.lua"):
        for line in _read_lines(f):
            m = rx.match(line)
            if m:
                found.append(m.group(1))
    return found


# --------------------------------------------------------------------------
# asset-derived lists
# --------------------------------------------------------------------------

def scan_translations(game: Path, mod_roots: list[Path]) -> list[str]:
    dirs = [game / "media" / "lua" / "shared" / "Translate"]
    for root in mod_roots:
        dirs += [d for d in root.rglob("Translate") if d.is_dir()]
    rx_json = re.compile(r'^\s*"([A-Za-z0-9_]+)"\s*:', re.M)
    rx_lua = re.compile(r'^\s*([A-Za-z0-9_]+)\s*=\s*"', re.M)
    keys: list[str] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in (".json", ".txt"):
                continue
            if ".preknx" in f.name or ".bak" in f.name:
                continue
            raw = _read_text(f)
            if not raw:
                continue
            # Regex rather than a JSON parse: some of these ship trailing commas.
            keys += (rx_json if f.suffix.lower() == ".json" else rx_lua).findall(raw)
    return keys


def scan_clothing(game: Path, mod_roots: list[Path]) -> tuple[list[str], list[str]]:
    xmls = [game / "media" / "clothing" / "clothing.xml"]
    item_dirs = [game / "media" / "clothing" / "clothingItems"]
    for root in mod_roots:
        xmls += [p for p in root.rglob("clothing.xml")
                 if p.is_file() and _under(p, "media", "clothing")]
        item_dirs += [d for d in root.rglob("clothingItems") if d.is_dir()]

    rx = re.compile(r"<m_Name>([^<]+)</m_Name>")
    outfits: list[str] = []
    for x in xmls:
        if x.is_file():
            outfits += rx.findall(_read_text(x))

    items: list[str] = []
    for d in item_dirs:
        if d.is_dir():
            items += [p.stem for p in d.glob("*.xml")]
    return outfits, items


def scan_animsets(game: Path) -> list[str]:
    base = game / "media" / "AnimSets"
    if not base.is_dir():
        return []
    return [str(d.relative_to(base)).replace(os.sep, "/")
            for d in base.rglob("*") if d.is_dir()]


def scan_tilesheets(game: Path) -> list[str]:
    """Printable-string scan of the binary tile definitions.

    Entries are sheet names (`walls_exterior_house_01`); a sprite is the sheet
    plus `_<index>`. The verifier accepts either and does not validate the
    index range.
    """
    path = game / "media" / "newtiledefinitions.tiles"
    if not path.is_file():
        return []
    raw = path.read_bytes().decode("latin-1")
    # case-SENSITIVE, as in the original (-cmatch)
    keep = re.compile(r"^[a-z][a-z0-9_]+_\d+$")
    return [s for s in re.findall(r"[\x20-\x7E]{6,}", raw) if keep.match(s)]


# --------------------------------------------------------------------------
# off-install sources: Umbrella typed defs, PZEventDoc
# --------------------------------------------------------------------------

def fetch_umbrella(dest: Path) -> Path | None:
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(UMBRELLA_ZIP, timeout=120) as r:
            blob = r.read()
    except Exception as exc:  # noqa: BLE001 - network is best-effort by design
        print(f"  ! Umbrella download failed: {exc}", file=sys.stderr)
        return None
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        z.extractall(dest)
    return dest


def scan_umbrella(umb: Path) -> dict[str, list[str]]:
    lua = [p for p in umb.rglob("*.lua") if p.is_file()]
    if not lua:
        return {}
    rx_method = re.compile(r"^function ([A-Za-z0-9_]+)[:.]([A-Za-z0-9_]+)", ICASE | re.M)
    rx_enum = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z0-9_]+)\s*=\s*nil", ICASE | re.M)
    rx_global = re.compile(r"^function ([A-Za-z0-9_]+)\s*\(", ICASE | re.M)
    rx_field = re.compile(r"---@field ([A-Za-z0-9_]+)", ICASE)

    api, enums, globals_, perks = [], [], [], []
    for f in lua:
        text = _read_text(f)
        api += [f"{cls.lstrip('_')}:{meth}" for cls, meth in rx_method.findall(text)]
        enums += [f"{cls}.{member}" for cls, member in rx_enum.findall(text)]
        globals_ += rx_global.findall(text)
        if f.name == "Perks.lua":
            perks += rx_field.findall(text)
    return {"api": api, "enum": enums, "luafunc": globals_, "perk": perks}


def fetch_events() -> list[str]:
    try:
        with urllib.request.urlopen(EVENTS_MD, timeout=60) as r:
            md = r.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        print(f"  ! Event fetch failed: {exc}", file=sys.stderr)
        return []
    events = re.findall(r"(?m)^## ([A-Za-z][A-Za-z0-9_.]*)", md)
    if len(events) <= 100:
        print("  ! Event list looked wrong (too few entries); ignoring", file=sys.stderr)
        return []
    return events


# --------------------------------------------------------------------------

FILENAMES = {
    "item": "items.txt", "itemtype": "itemtypes.txt", "category": "displaycategories.txt",
    "tag": "tags.txt", "icon": "icons.txt", "sound": "sounds.txt", "model": "models.txt",
    "recipe": "recipes.txt", "evolvedrecipe": "evolvedrecipes.txt", "fluid": "fluids.txt",
    "energy": "energies.txt", "attachment": "attachments.txt",
    "timedaction": "timedactions.txt", "animscript": "animscripts.txt",
    "vehiclepart": "vehicleparts.txt", "vehicle": "vehicles.txt", "fixing": "fixings.txt",
    "room": "rooms.txt", "containerdist": "containerdists.txt", "proclist": "proclists.txt",
    "perk": "perks.txt", "luaclass": "luaclasses.txt", "luafunc": "luafunctions.txt",
    "sandboxvar": "sandboxvars.txt", "translation": "translations.txt",
    "outfit": "outfits.txt", "clothingitem": "clothingitems.txt",
    "foragecat": "foragecats.txt", "animset": "animsets.txt", "tile": "tilesheets.txt",
    "api": "api.txt", "enum": "enums.txt", "event": "events.txt",
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Extract pz-bible reference lists from an installed PZ B42 build.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--game", default=os.environ.get("PZ_DIR"),
                    help="Project Zomboid install directory (or set PZ_DIR)")
    ap.add_argument("--mods", action="append", default=[], metavar="DIR",
                    help="Extra mod root to index (repeatable): ~/Zomboid/mods, "
                         "or a Steam workshop content/108600 directory")
    ap.add_argument("--out", default="refs", help="output directory (default: refs/)")
    ap.add_argument("--umbrella-dir", metavar="DIR",
                    help="local PZ-Umbrella checkout; skips the download")
    ap.add_argument("--offline", action="store_true",
                    help="skip Umbrella and PZEventDoc; keeps existing api/enums/events")
    args = ap.parse_args()

    if not args.game:
        ap.error("--game is required (or set PZ_DIR)")
    game = Path(args.game).expanduser().resolve()
    if not (game / "media").is_dir():
        ap.error(f"no media/ directory under {game} - is that the game install?")

    mod_roots = []
    for m in args.mods:
        p = Path(m).expanduser().resolve()
        if p.is_dir():
            mod_roots.append(p)
        else:
            print(f"  ! skipping missing mod root: {p}", file=sys.stderr)

    out = Path(args.out).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)

    print(f"game : {game}")
    for p in mod_roots:
        print(f"mods : {p}")
    print(f"out  : {out}\n")

    collected: dict[str, list[str]] = defaultdict(list)

    scripts = _script_files(game, mod_roots)
    print(f"scanning {len(scripts)} script files ...")
    for kind, values in scan_scripts(scripts).items():
        collected[kind] += values

    lua = _lua_files(game, mod_roots)
    print(f"scanning {len(lua)} lua files ...")
    rooms, dists, proclists = scan_distributions(game)
    collected["room"] += rooms
    collected["containerdist"] += dists
    collected["proclist"] += proclists
    collected["perk"] += scan_perks(lua)
    classes, fns = scan_lua_classes_and_functions(lua)
    collected["luaclass"] += classes
    collected["luafunc"] += fns
    collected["sandboxvar"] += scan_sandboxvars(game)
    collected["foragecat"] += scan_foragecats(game)

    print("scanning assets ...")
    collected["translation"] += scan_translations(game, mod_roots)
    outfits, clothing = scan_clothing(game, mod_roots)
    collected["outfit"] += outfits
    collected["clothingitem"] += clothing
    collected["animset"] += scan_animsets(game)
    collected["tile"] += scan_tilesheets(game)

    tmp = None
    if not args.offline:
        print("fetching typed definitions ...")
        if args.umbrella_dir:
            umb = Path(args.umbrella_dir).expanduser().resolve()
        else:
            tmp = Path(tempfile.mkdtemp(prefix="pzumbrella-"))
            umb = fetch_umbrella(tmp) or tmp
        for kind, values in scan_umbrella(umb).items():
            collected[kind] += values
        collected["event"] += fetch_events()
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)

    print()
    written = skipped = 0
    for kind, filename in sorted(FILENAMES.items(), key=lambda kv: kv[1]):
        values = _sorted_unique(collected.get(kind, []))
        target = out / filename
        if not values:
            # An empty result means the source was unavailable this run, not
            # that the game has none of that kind. Never overwrite a good list
            # with nothing.
            state = "kept existing" if target.exists() else "no source"
            print(f"  {filename:<24} {'-':>7}  ({state})")
            skipped += 1
            continue
        target.write_text("\n".join(values) + "\n", encoding="utf-8")
        print(f"  {filename:<24} {len(values):>7}")
        written += 1

    total = sum(len(_sorted_unique(v)) for v in collected.values())
    print(f"\n{written} lists written, {skipped} skipped, {total} names total")
    if args.offline:
        print("offline: api.txt, enums.txt and events.txt were not refreshed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
