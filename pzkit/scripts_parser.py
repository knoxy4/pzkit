"""Parser for PZ's B42 script DSL (media/scripts/**/*.txt) -> block trees.

P1 deliverable. Feeds the SQLite + LanceDB vanilla index (vanilla_index.py).

DSL grammar warts observed in the real 42.x corpus (buildid 24449161) — this
list seeds the pz-modding skill (P4); keep it current:

- Statements are comma-terminated, but the final statement before `}` may
  omit the comma. `}` implicitly flushes a pending statement.
- Block headers are `<type> [name...] {` where the name may contain SPACES
  (`fixing Fix Pistol`) or be absent entirely (`model {`, `skin {`,
  `inputs {`, `clip {`).
- `=` appears INSIDE values: `Fixer = Base.Pistol2; Aiming=3` — split
  key/value on the FIRST `=` only, never rsplit/regex-split.
- Values are unquoted free text: spaces (`Name = Prepare Soup`), numeric
  tuples (`offset = 0.0 0.3681 0.0`), `;`-separated lists (Tags, Fixer),
  `:`-scoped atoms (`ItemType = base:alarmclock`, `xpAward = Woodwork:5`),
  paths (`texture = Vehicles/vehicle_van_lights`).
- craftRecipe `inputs`/`outputs` entries are NOT key=value; they have their
  own mini-grammar: `item <n> [A;B]|tags[a;b]|mapper:Name [mode:keep]
  [flags[F1;F2]] [mappers[M]]`. Fluids use fractional amounts
  (`fluid 0.25 [...]`). Parsed by parse_recipe_entry().
- `itemMapper <Name> {}` blocks map output item -> input item with a
  `default =` fallback; keys AND values are both item FQNs, so a k=v prop
  table is the right model, not a special case.
- Comments: only `/* ... */` exists in the corpus (28 files), no `//`.
  Assume non-nesting (TIS's own parser doesn't nest them).
- Blocks nest at least 3 deep: `module > xuiSkin default > entity ES_X`.
- Multiple `module` blocks per file are legal; everything lives under
  `module Base` in vanilla but mods use their own module names.
- `imports { Base }` blocks exist (3 vanilla files) — entries, not props.
- B41 `recipe` blocks are EXTINCT in the 42.x corpus (0 hits) — everything
  is `craftRecipe`. Tools that grep for `recipe` parse nothing (see wink's
  MCP server: 0 recipes indexed).
- Item DisplayName is gone from item blocks (translations own it now);
  don't expect it when round-tripping B41 examples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass
class Prop:
    key: str
    value: str
    line: int


@dataclass
class ScriptBlock:
    btype: str
    name: str | None
    props: list[Prop] = field(default_factory=list)
    entries: list[tuple[str, int]] = field(default_factory=list)  # bare statements
    children: list[ScriptBlock] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0


@dataclass
class ParsedFile:
    relpath: str
    blocks: list[ScriptBlock] = field(default_factory=list)  # top-level (module, version...)
    header_props: list[Prop] = field(default_factory=list)  # stray top-level k=v
    warnings: list[str] = field(default_factory=list)


@dataclass
class RecipeEntry:
    """One inputs{}/outputs{} statement, e.g. `item 1 [Base.Log] flags[Prop2]`."""

    kind: str  # item | fluid | energy | ...
    amount: float | None = None
    targets: list[str] = field(default_factory=list)  # [Base.A;Base.B]
    tags: list[str] = field(default_factory=list)  # tags[a;b]
    mapper: str | None = None  # mapper:Name
    mode: str | None = None  # mode:keep|destroy
    rtype: str | None = None  # type:Electricity (energy)
    flags: list[str] = field(default_factory=list)
    mappers: list[str] = field(default_factory=list)
    extras: list[str] = field(default_factory=list)  # unrecognized tokens, kept honest


def _strip_comments(text: str) -> str:
    # replace with equivalent newlines to keep line numbers stable
    return BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _flush(stmt: str, line: int, block: ScriptBlock | None, out: ParsedFile) -> None:
    stmt = stmt.strip()
    if not stmt:
        return
    if "=" in stmt:
        key, value = stmt.split("=", 1)
        prop = Prop(key.strip(), value.strip(), line)
        if block is None:
            out.header_props.append(prop)
        else:
            block.props.append(prop)
    elif block is None:
        out.warnings.append(f"{out.relpath}:{line}: stray top-level token {stmt!r}")
    else:
        block.entries.append((stmt, line))


def parse_script(text: str, relpath: str = "<string>") -> ParsedFile:
    """Parse one script file's text into a tolerant block tree. Never raises on corpus input."""
    out = ParsedFile(relpath=relpath)
    text = _strip_comments(text)
    stack: list[ScriptBlock] = []
    pending: list[str] = []
    stmt_line = line = 1
    for ch in text:
        if ch == "\n":
            line += 1
        if ch == "{":
            header = "".join(pending).strip()
            pending.clear()
            if "=" in header:
                out.warnings.append(f"{relpath}:{line}: '=' in block header {header!r}")
            words = header.split(None, 1)
            btype = words[0] if words else "<anonymous>"
            name = words[1].strip() if len(words) > 1 else None
            blk = ScriptBlock(btype=btype, name=name, start_line=stmt_line)
            (stack[-1].children if stack else out.blocks).append(blk)
            stack.append(blk)
            stmt_line = line
        elif ch == "}":
            _flush("".join(pending), stmt_line, stack[-1] if stack else None, out)
            pending.clear()
            if stack:
                stack.pop().end_line = line
            else:
                out.warnings.append(f"{relpath}:{line}: unbalanced '}}'")
            stmt_line = line
        elif ch == ",":
            _flush("".join(pending), stmt_line, stack[-1] if stack else None, out)
            pending.clear()
            stmt_line = line
        else:
            if not pending:
                # don't buffer leading whitespace: it would pin stmt_line to the
                # previous '{' or ',' and report every statement a line early
                if ch.isspace():
                    continue
                stmt_line = line
            pending.append(ch)
    if stack:
        out.warnings.append(
            f"{relpath}: unclosed block {stack[-1].btype!r} from line {stack[-1].start_line}"
        )
    _flush("".join(pending), stmt_line, None, out)
    return out


def parse_script_file(path: str | Path) -> ParsedFile:
    p = Path(path)
    return parse_script(p.read_text(encoding="utf-8", errors="replace"), relpath=p.name)


_BRACKET = re.compile(r"^(\w+)\[(.*)\]$")


def parse_recipe_entry(text: str) -> RecipeEntry:
    """Parse one inputs/outputs statement. Unknown tokens land in .extras, never lost."""
    tokens = _tokenize_entry(text)
    entry = RecipeEntry(kind=tokens[0] if tokens else "")
    for tok in tokens[1:]:
        if entry.amount is None and re.fullmatch(r"\d+(\.\d+)?", tok):
            entry.amount = float(tok)
        elif tok.startswith("[") and tok.endswith("]"):
            entry.targets = [t.strip() for t in tok[1:-1].split(";") if t.strip()]
        elif m := _BRACKET.match(tok):
            word, body = m.group(1).lower(), [t.strip() for t in m.group(2).split(";") if t.strip()]
            if word == "tags":
                entry.tags = body
            elif word == "flags":
                entry.flags = body
            elif word == "mappers":
                entry.mappers = body
            else:
                entry.extras.append(tok)
        elif ":" in tok:
            word, _, val = tok.partition(":")
            wl = word.lower()
            if wl == "mapper":
                entry.mapper = val
            elif wl == "mode":
                entry.mode = val
            elif wl == "type":
                entry.rtype = val
            else:
                entry.extras.append(tok)
        elif "." in tok:
            entry.targets.append(tok)  # bare FQN output: `item 3 Base.Plank`
        else:
            entry.extras.append(tok)
    return entry


def _tokenize_entry(text: str) -> list[str]:
    # split on whitespace, but keep [...] groups (which contain no nesting) intact
    tokens, buf, depth = [], [], 0
    for ch in text.strip():
        if ch.isspace() and depth == 0:
            if buf:
                tokens.append("".join(buf))
                buf = []
        else:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth = max(0, depth - 1)
            buf.append(ch)
    if buf:
        tokens.append("".join(buf))
    return tokens
