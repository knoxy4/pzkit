"""Mod validation: layout, DSL syntax, references vs vanilla index, translations, Lua.

P2 deliverable. Gate G2: passes a hello-world mod AND fails a deliberately broken one.
Stages that lack their prerequisite (no vanilla DB, no lua toolchain) SKIP loudly —
they never silently pass.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .scaffold import MOD_PREFIX
from .scripts_parser import ParsedFile, ScriptBlock, parse_recipe_entry, parse_script

_ITEM_FQN = re.compile(r"^[A-Za-z_]\w*\.[A-Za-z_][\w.]*$")


@dataclass
class Finding:
    level: str  # ERROR | WARN | SKIP
    code: str
    message: str
    file: str = ""
    line: int = 0

    def render(self) -> str:
        loc = f" [{self.file}:{self.line}]" if self.file else ""
        return f"{self.level} {self.code}: {self.message}{loc}"


@dataclass
class Report:
    mod_path: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.level == "ERROR" for f in self.findings)

    def add(self, level: str, code: str, message: str, file: str = "", line: int = 0) -> None:
        self.findings.append(Finding(level, code, message, file, line))

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "mod": self.mod_path,
            "errors": [f.render() for f in self.findings if f.level == "ERROR"],
            "warnings": [f.render() for f in self.findings if f.level == "WARN"],
            "skipped": [f.render() for f in self.findings if f.level == "SKIP"],
        }


def validate_mod(mod_path: str | Path, db_path: Path | None = None) -> Report:
    mod = Path(mod_path)
    rep = Report(mod_path=str(mod))
    if not mod.is_dir():
        rep.add("ERROR", "LAYOUT-missing", f"mod dir not found: {mod}")
        return rep

    _check_layout(mod, rep)
    parsed = _check_scripts(mod, rep)
    _check_references(rep, parsed, _collect_defs(parsed), db_path)
    _check_keyed_refs(mod, rep, db_path)
    _check_translations(mod, rep, parsed)
    _check_lua(mod, rep)
    return rep


def _check_keyed_refs(mod: Path, rep: Report, db_path: Path | None) -> None:
    """Bare-name refs in GrantedRecipes/XPBoosts/LearnedRecipes/trait lists -
    the class the module-qualified check misses. This is what makes GREEN mean
    'references resolve', not just 'parses'."""
    from . import refcheck, vanilla_index as vi
    db = db_path or vi.default_db_path()
    if not Path(db).is_file():
        return  # _check_references already emits REF-noindex
    prov = refcheck.index_provenance(Path(db))
    if prov["age_days"] is not None and prov["age_days"] > 21:
        rep.add("WARN", "REF-stale-index",
                f"vanilla index is {prov['age_days']}d old (buildid {prov['buildid']}); "
                f"rebuild with `pzkit index build` if the game has updated")
    scripts = [(str(p.relative_to(mod)), p.read_text(encoding="utf-8", errors="replace"))
               for p in _script_files(mod)]
    for sev, code, rel, line, msg in refcheck.check(scripts, Path(db)):
        rep.add(sev, code, msg, file=rel, line=line)


def _check_layout(mod: Path, rep: Report) -> dict[str, str]:
    info: dict[str, str] = {}
    mi = mod / "mod.info"
    if not mi.is_file():
        rep.add("ERROR", "LAYOUT-modinfo", "mod.info missing")
    else:
        for ln in mi.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                info[k.strip()] = v.strip()
        if info.get("id") != mod.name:
            rep.add("ERROR", "LAYOUT-id", f"mod.info id={info.get('id')!r} != folder {mod.name!r}")
        if not info.get("name"):
            rep.add("ERROR", "LAYOUT-name", "mod.info has no name=")
    if not mod.name.startswith(MOD_PREFIX):
        rep.add("ERROR", "LAYOUT-prefix", f"folder must start with {MOD_PREFIX!r} (CONVENTIONS §5)")
    if not (mod / "42").is_dir():
        rep.add("ERROR", "LAYOUT-42", "no 42/ versioned content dir")
    if not (mod / "common").is_dir():
        rep.add("WARN", "LAYOUT-common", "no common/ dir")
    return info


def _script_files(mod: Path) -> list[Path]:
    return sorted(
        p for base in ("42", "common") for p in (mod / base).rglob("media/scripts/**/*.txt")
    )


def _check_scripts(mod: Path, rep: Report) -> list[tuple[str, ParsedFile]]:
    out = []
    for p in _script_files(mod):
        rel = p.relative_to(mod).as_posix()
        parsed = parse_script(p.read_text(encoding="utf-8", errors="replace"), relpath=rel)
        for w in parsed.warnings:
            rep.add("ERROR", "DSL-syntax", w, file=rel)
        for blk in parsed.blocks:
            if blk.btype != "module":
                rep.add(
                    "ERROR",
                    "DSL-toplevel",
                    f"top-level {blk.btype!r} outside a module block",
                    file=rel,
                    line=blk.start_line,
                )
        out.append((rel, parsed))
    if not out:
        rep.add("WARN", "DSL-none", "mod ships no script files")
    return out


def _collect_defs(parsed: list[tuple[str, ParsedFile]]) -> set[str]:
    """All FQNs the mod itself defines (module.name), plus bare names per module."""
    defs: set[str] = set()
    for _rel, pf in parsed:
        for mod_blk in pf.blocks:
            if mod_blk.btype != "module" or not mod_blk.name:
                continue
            for child in mod_blk.children:
                if child.name:
                    defs.add(f"{mod_blk.name}.{child.name.split()[0]}")
    return defs


def _vanilla_names(db_path: Path | None) -> tuple[set[str], set[str]] | None:
    """(FQN set, bare-name set) of vanilla blocks, or None when no index DB exists."""
    from . import vanilla_index as vi

    db = db_path or vi.default_db_path()
    if not Path(db).is_file():
        return None
    con = vi.connect(db)
    fqn, bare = set(), set()
    for r in con.execute("SELECT module, name FROM blocks WHERE name IS NOT NULL"):
        bare.add(r["name"])
        if r["module"]:
            fqn.add(f"{r['module']}.{r['name']}")
    return fqn, bare


def _check_references(
    rep: Report,
    parsed: list[tuple[str, ParsedFile]],
    own: set[str],
    db_path: Path | None,
) -> None:
    vanilla = _vanilla_names(db_path)
    if vanilla is None:
        rep.add("SKIP", "REF-noindex", "vanilla index DB not found — run `pzkit index build`")
        return
    fqn, bare = vanilla

    def known(target: str) -> bool:
        name = target.split(".", 1)[1] if "." in target else target
        return target in fqn or target in own or name in bare or f"Base.{target}" in fqn

    for rel, pf in parsed:
        for mod_blk in pf.blocks:
            if mod_blk.btype != "module":
                continue
            for child in mod_blk.children:
                _check_block_refs(rep, rel, child, known)


def _check_block_refs(rep: Report, rel: str, blk: ScriptBlock, known) -> None:
    if blk.btype == "craftRecipe":
        for sub in blk.children:
            if sub.btype not in ("inputs", "outputs"):
                continue
            mappers = {c.name for c in blk.children if c.btype == "itemMapper" and c.name}
            for text, line in sub.entries:
                e = parse_recipe_entry(text)
                for t in e.targets:
                    if not known(t):
                        rep.add("ERROR", "REF-item", f"unknown {sub.btype} item {t!r}", rel, line)
                if e.mapper and e.mapper not in mappers:
                    rep.add("ERROR", "REF-mapper", f"undefined itemMapper {e.mapper!r}", rel, line)
    else:
        for p in blk.props:
            for seg in (s.strip() for s in p.value.split(";")):
                if _ITEM_FQN.match(seg) and not re.search(r"\.\d", seg) and not known(seg):
                    rep.add(
                        "ERROR", "REF-item", f"unknown item ref {seg!r} in {p.key}", rel, p.line
                    )
    for child in blk.children:
        if child.btype not in ("inputs", "outputs", "itemMapper"):
            _check_block_refs(rep, rel, child, known)


def _check_translations(mod: Path, rep: Report, parsed: list[tuple[str, ParsedFile]]) -> None:
    corpus = ""
    for p in mod.rglob("media/translations/**/*.txt"):
        corpus += p.read_text(encoding="utf-8", errors="replace")
    for _rel, pf in parsed:
        for mod_blk in pf.blocks:
            if mod_blk.btype != "module":
                continue
            for child in mod_blk.children:
                if child.btype == "item" and child.name:
                    key = f"ItemName_{mod_blk.name}.{child.name}"
                    if key not in corpus:
                        rep.add(
                            "ERROR",
                            "TR-missing",
                            f"no translation entry {key!r} (CONVENTIONS §5: day one)",
                        )


def _wsl_path(p: Path) -> str:
    """C:\\x -> /mnt/c/x so a WSL-hosted luacheck can read a Windows path."""
    s = str(p).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":
        return f"/mnt/{s[0].lower()}{s[2:]}"
    return s


def _lua_tool() -> list[str] | None:
    """Native luacheck if present, else WSL's. Windows dev + WSL rig is the norm here."""
    native = shutil.which("luacheck") or shutil.which("luac")
    if native:
        return [native]
    if shutil.which("wsl"):
        r = subprocess.run(["wsl", "-e", "which", "luacheck"],
                           capture_output=True, text=True, check=False)
        if r.returncode == 0 and r.stdout.strip():
            return ["wsl", "-e", "luacheck"]
    return None


def _check_lua(mod: Path, rep: Report) -> None:
    lua_files = sorted(mod.rglob("media/lua/**/*.lua"))
    if not lua_files:
        return
    tool = _lua_tool()
    if tool is None:
        rep.add("SKIP", "LUA-toolchain",
                f"{len(lua_files)} lua files unchecked - no luacheck (apt install lua-check)")
        return
    via_wsl = tool[0] == "wsl"
    for f in lua_files:
        target = _wsl_path(f) if via_wsl else str(f)
        if "luac" in tool[-1] and "luacheck" not in tool[-1]:
            args = tool + ["-p", target]
        else:
            args = tool + ["--formatter", "plain", target]
        r = subprocess.run(args, capture_output=True, text=True, check=False)
        if r.returncode != 0:
            lines = [ln for ln in (r.stdout or r.stderr).strip().splitlines() if ln.strip()]
            for ln in lines[:3]:
                rep.add("ERROR", "LUA-check", ln.strip())
            if len(lines) > 3:
                rep.add("ERROR", "LUA-check", f"...+{len(lines) - 3} more in {f.name}")
