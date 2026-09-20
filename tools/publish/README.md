# Workshop publishing

Getting a Project Zomboid mod onto the Steam Workshop by hand means keeping the
same title, version and description in `mod.info`, `42/mod.info`, `workshop.txt`
and `publish.vdf` in sync, remembering which of them steamcmd actually reads,
and never once mistyping the published file id. Miss the last one and Steam
creates a *second* Workshop item instead of updating yours, which cannot be
undone.

These tools keep all of it in one config file and write the rest.

## Setup

Copy the example config to your mod repo's root and edit it:

```bash
cp pzpublish.example.json /path/to/your-mods/pzpublish.json
```

```json
{
  "author": "yourname",
  "versionMin": "42.20.0",
  "steamUser": "YOUR_STEAM_USERNAME",
  "workshopDir": "~/Zomboid/Workshop",
  "modsDir": "~/Zomboid/mods",
  "steamcmd": "C:\\steamcmd\\steamcmd.exe",
  "mods": [
    { "id": "your_mod", "name": "Your Mod", "version": "0.1.0", "fileId": null,
      "tags": ["Build 42", "Items"], "description": "What it does." }
  ]
}
```

Mod sources are expected at `<repo>/mods/<id>/` or `<repo>/<id>/` — both layouts
work, and `modsSource` overrides it. Run the tools from inside your mod repo;
they locate it from your working directory, not from where the tools live, so
one copy serves every repo.

Every path can be overridden per machine without touching the committed config:
`PZPUBLISH_CONFIG`, `PZ_WORKSHOP_DIR`, `PZ_MODS_DIR`, `PZ_STEAMCMD`,
`PZ_STEAM_USER`.

**No script here ever stores, reads or prompts for a Steam password.** steamcmd
caches credentials after one interactive login. If it ever asks again, the push
aborts and prints the exact command for you to run yourself.

## The flow

```bash
python modinfo.py                       # write mod.info + workshop.txt from the config
python lint.py                          # pre-flight checks
pwsh ./restage.ps1 -Mod your_mod -Ref your_mod-v0.1.0
python publishvdf.py --note "0.1.0 - first release"
pwsh ./first_publish.ps1 -Name your_mod   # first time only
pwsh ./push.ps1 -Name your_mod -Changenote "0.1.1 - fixed the thing"
```

| Tool | Does |
|---|---|
| `modinfo.py` | Writes `mod.info` (root and `42/`) and `workshop.txt` for every mod. `--check` diffs without writing and exits non-zero on drift, so it drops into CI. |
| `lint.py` | Pre-flight checks on a mod folder. Every check is a defect that has actually shipped. |
| `publishvdf.py` | Writes the `publish.vdf` steamcmd uploads from. Preserves a hand-written BBCode description already on the Workshop page — only the title, changenote and server-operator footer are rewritten. |
| `restage.ps1` | Stages a mod into the Workshop content folder **from a git ref**, via `git archive`. |
| `first_publish.ps1` | First upload. Captures the new PublishedFileID and writes it back. |
| `push.ps1` | Updates the changenote and pushes an existing item. |
| `push_all.ps1` | Every published mod in the config, one changenote. |
| `junction.ps1` | Junctions the game's mods folder at your working tree for local testing. |

## Things worth knowing

**Stage from a tag, not from your working tree.** `restage.ps1` uses `git
archive`, so what ships is exactly what the ref contains, and `.gitattributes`
`export-ignore` applies — generator sources, art masters and audit folders never
reach the Workshop. A file copy would ship whatever happened to be on disk.

**The first publish is the dangerous one.** `publishedfileid` starts at `0`.
steamcmd creates the item and prints the new id, and if that id is not written
back into `publish.vdf`, the next push creates a duplicate item. There is no way
to merge two Workshop items afterwards. `first_publish.ps1` exists solely to do
that write-back, and `push.ps1` refuses to run while the id is still `0`.

**Workshop categories cannot be set from the VDF.** A `tags` block in
`publish.vdf` is silently ignored by `workshop_build_item` — verified against a
real content update. Categories can only be set through the in-game uploader,
which reads `workshop.txt`, or through the Steam UGC API. `modinfo.py` writes
`workshop.txt` for exactly this reason.

**After a first publish, check the item page.** Steam shows a legal-agreement
banner on new items; until it is accepted the item is undownloadable, and
nothing in the upload output tells you.

## Requirements

Python 3.11+, PowerShell (Windows PowerShell 5.1 or PowerShell 7+), `git`, `tar`
(ships with Windows 10+), and SteamCMD.
