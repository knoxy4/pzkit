# pz-bible — ground truth for B42 names

Project Zomboid fails *silently* on identifiers that do not exist. A loot-list
key with a typo never fires. A `craftRecipe` output naming a nonexistent item
can abort world load. Nothing logs anything useful. Most mod bugs are not logic
bugs — they are a string that matches nothing, and the game will not tell you.

pz-bible extracts every string-keyed name the game actually knows, from your own
install, and checks candidates against it.

## Build the lists

```bash
python3 build_refs.py --game "/path/to/ProjectZomboid" --out refs/
```

Roughly 110,000 names from a vanilla install, in about 25 seconds. To also index
installed and subscribed mods, so your own identifiers verify too:

```bash
python3 build_refs.py --game "<game>" \
    --mods ~/Zomboid/mods \
    --mods "<steam>/steamapps/workshop/content/108600"
```

**No reference lists ship in this repo, deliberately.** They go stale the moment
the game updates, and a stale list that looks authoritative is worse than no
list — it produces confident wrong answers in both directions. Build them from
the version you are actually modding against, and rebuild after every game
update.

`api`, `enums` and part of `perks` come from
[PZ-Umbrella](https://github.com/PZ-Umbrella/Umbrella)'s typed definitions and
`events` from
[PZEventDoc](https://github.com/demiurgeQuantified/PZEventDoc), because the
engine API surface is not in the install. Pass `--umbrella-dir` to use a local
checkout, or `--offline` to skip both. Umbrella can lag a fresh patch by a few
days.

## Verify a name

```bash
python3 pz_verify.py <kind> <name>        # exit 0 hit, 1 miss
python3 pz_verify.py any MTGBooster       # check across every kind
python3 pz_verify.py search enum CharacterTrait
python3 pz_verify.py list fluid
```

No Python at hand? The lists are one name per line, sorted — `grep -x 'Base.Axe'
refs/items.txt` works. Exact, case-sensitive match means real.

### What the answers mean

| Result | Meaning |
|---|---|
| `OK` | Ship it. |
| `CASE MISMATCH` | An error, not a warning. PZ names are case-sensitive; use the spelling returned. |
| `NOT ON THAT CLASS` (api) | The method exists, on the classes listed. Fine if one is a plausible parent — that is inheritance. An empty owner list means it does not exist. |
| `NOT FOUND` | A hard stop. Take a suggested candidate or redesign. Never ship the name with a caveat. |

`NOT FOUND` prints candidates ranked by similarity to the name's **last
segment** — `Base.Nonsense` is scored against the `Axe` in `Base.Axe`, not
against the whole string — with names sharing your module or class nudged up.
The floor scales with length: a long name has to match far more closely to
count as a typo. When nothing clears it you get no candidates at all, which is
the honest answer; a list of eight wrong names just trains you to ignore the
rule above. Set `PZ_BIBLE_MIN_SIM` (default `0.62`) to loosen or tighten it.

In `any` mode, kinds whose list has not been built are **skipped, not treated as
misses**, and named at the end. An unchecked kind is not a verified miss, and
`NOT FOUND` is a hard stop — so it has to be clear which one you are looking
at.

One corollary, learned the hard way: `NOT FOUND` only counts if the reference
set actually indexes that kind of file. Check coverage before writing a missing
name up as a defect — an early version indexed no translation keys at all, so
every vanilla `getText` key came back `NOT FOUND` and a real function got
reported as a fabrication.

## Kinds

`item` (Module.Item) · `api` (Class:method) · `enum` (typed constants —
`ItemTag.AEROSOL`, `CharacterTrait.HANDY`, `ItemBodyLocation.HAT`; B42 Lua uses
these instead of raw strings) · `translation` · `tile` · `room` · `proclist` ·
`containerdist` · `tag` · `icon` · `sound` · `model` · `recipe` ·
`evolvedrecipe` · `fluid` · `energy` · `attachment` · `timedaction` ·
`animscript` · `vehicle` · `vehiclepart` · `outfit` · `clothingitem` ·
`foragecat` · `animset` · `perk` · `event` · `sandboxvar` · `luaclass` ·
`luafunc` · `fixing` · `category` · `itemtype` — plus `any`.

## Known limits

- `enums.txt` is a superset: every `X.Y = nil` static Umbrella declares, not
  only enum classes. Everything in it is real; it just also verifies non-enum
  statics.
- `foragecats.txt` mixes category, zone and def names. All are real
  forageSystem keys.
- `perks.txt` unions observed vanilla usage with Umbrella's `Perks` fields.
- `tile` accepts a sheet name or `sheet_N`; the sprite index range is **not**
  validated.
- Not covered: animation clip names inside `anims_X`, and FMOD `.bank`
  internals — B42 strings banks carry bus and VCA names, not `event:/` paths, so
  the modder-facing surface is the `sound` script blocks, which `sounds.txt`
  already has.

## Catches on record

Real fabrications this caught before they shipped, which is the whole argument
for the tool:

- `Type = Normal` — a B41-ism. Produces a half-loaded item with a null
  `getItemType()` and a debug-UI crash. B42 wants `ItemType = base:normal`.
- `IsoPlayer:playSound` — does not exist. Sound goes through
  `player:getEmitter():playSound(...)`.
- `ItemContainer:getItemById` — deprecated per the typings.
- Bracketed `craftRecipe` outputs — `item 1 [Base.X]` invokes the OutputMapper
  and aborts world load. Vanilla syntax is unbracketed.
- `OnZombieSpawn`, `comicshop` — plausible inventions, both caught with correct
  suggestions.

## Provenance

`build_refs.py` is a port of a PowerShell extractor that was bound to one
machine. It reproduces that extractor's output exactly on every list derived
purely from the install — verified set-identical on rooms, container
distributions, sandbox vars, anim sets, tile sheets, forage categories, timed
actions, energies, fluids, evolved recipes, perks and events.

It deviates in two places, both deliberate:

1. **Deduplication is case-sensitive.** PowerShell's `Sort-Object -Unique`
   compares case-insensitively and would collapse `Base.Axe` and `Base.axe`
   into one entry. Since the verifier treats a case mismatch as an error,
   collapsing them makes the bible lie.
2. **Procedural list names are matched case-sensitively.** PowerShell's
   `Select-String` is case-insensitive, so the original's `[A-Z]` also matched
   lowercase and picked up `items` and `junk` — field names *inside* a
   distribution table, never list names. They are excluded here.
