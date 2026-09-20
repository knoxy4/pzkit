"""Build an authoritative PZ global list from B42's own Lua, not from guesswork.

Two sources:
  1. Names vanilla Lua assigns at global scope  -> the mod-facing API surface
  2. Names vanilla Lua CALLS but never defines  -> Java-bound engine globals
"""
import os
import sys
import collections
import pathlib
import re

root = pathlib.Path.home() / "pzserver/media/lua"
files = list(root.rglob("*.lua"))
print(f"scanning {len(files)} vanilla lua files")

defined, called = set(), collections.Counter()
LOCALS = re.compile(r'\blocal\s+([\w, ]+)')

for f in files:
    try:
        t = f.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    # global function defs:  function Foo(  /  function Foo.bar(
    for m in re.finditer(r'^\s*function\s+([A-Za-z_]\w*)\s*[.:(]', t, re.M):
        defined.add(m.group(1))
    # global table/class assignment at col 0:  Foo = {   /  Foo = X:derive(
    for m in re.finditer(r'^([A-Za-z_]\w*)\s*=\s*[\{A-Za-z_]', t, re.M):
        defined.add(m.group(1))
    # called identifiers
    for m in re.finditer(r'\b([A-Za-z_]\w*)\s*\(', t):
        called[m.group(1)] += 1

locals_seen = set()
for f in files[:3000]:
    try:
        for m in LOCALS.finditer(f.read_text(encoding="utf-8", errors="replace")):
            for n in m.group(1).split(","):
                locals_seen.add(n.strip())
    except Exception:
        pass

LUA_BUILTIN = {"if", "for", "while", "return", "and", "or", "not", "then", "do",
               "end", "function", "local", "elseif", "else", "in", "repeat", "until"}

# engine globals: called a lot, never defined in Lua, not a local, not a keyword
engine = {n for n, c in called.items()
          if c >= 5 and n not in defined and n not in locals_seen and n not in LUA_BUILTIN}

api = {d for d in defined if len(d) > 2 and d not in LUA_BUILTIN}

out = sorted(api | engine)
print(f"vanilla-defined API names : {len(api)}")
print(f"engine/Java-bound globals : {len(engine)}")
print(f"TOTAL read_globals        : {len(out)}")

dest = pathlib.Path(
    sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PZ_LUACHECKRC", ".luacheckrc")
)
lines = ['-- luacheck config for PZ B42 mod Lua (Kahlua2 / Lua 5.1).',
         '-- read_globals GENERATED from B42.20 vanilla media/lua by scripts/gen_pz_globals.py',
         '-- Do not hand-edit the list; regenerate when the game updates.',
         'std = "lua51"',
         'max_line_length = false',
         'unused_args = false',
         'globals = { "SandboxVars" }',
         'read_globals = {']
for i in range(0, len(out), 6):
    lines.append("    " + ", ".join(f'"{n}"' for n in out[i:i + 6]) + ",")
lines.append("}")
dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", dest)
