"""Dedi boot-smoke rig: isolated B42 server boot per mod, structured verdict.

P3 deliverable. Isolation via -cachedir (own config/saves/console/mods) so the
rig never touches the live server instance. -nosteam, ports 16271/16272 (kept
out of the public firewall range on purpose). The model reads verdicts, never
watches logs scroll (plan §4 P3).

Console noise policy: known-benign vanilla ERROR lines (observed on clean
boots of buildid 24449161) are counted, not flagged. Everything else marked
ERROR/exception-ish fails the verdict. The allowlist is append-only and each
entry names its evidence.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

# All paths are WSL-side (Linux) paths; the *_UNC pairs are how Windows reaches
# them. Override any of these via environment variables — the defaults assume a
# WSL2 Ubuntu install with the dedicated server under ~/pzserver.
_WSL_USER = (os.environ.get("PZRIG_WSL_USER") or os.environ.get("USER")
             or os.environ.get("USERNAME") or "pzuser")
_WSL_DISTRO = os.environ.get("PZRIG_WSL_DISTRO", "Ubuntu")
_WSL_HOME = os.environ.get("PZRIG_WSL_HOME", f"/home/{_WSL_USER}")


def _unc(linux_path: str) -> Path:
    """Map a WSL Linux path to the UNC path Windows uses to reach it.

    Built as one string rather than by joining Path parts, so the separators
    stay backslashes even when this module is imported on a non-Windows host.
    """
    tail = linux_path.strip("/").replace("/", "\\")
    return Path(rf"\\wsl.localhost\{_WSL_DISTRO}\{tail}")


RIG_CACHEDIR = os.environ.get("PZRIG_CACHEDIR", f"{_WSL_HOME}/pzjarvis-rig")
RIG_SERVERNAME = os.environ.get("PZRIG_SERVERNAME", "pzjarvis-testrig")
RIG_UNC = _unc(RIG_CACHEDIR)
# control files live OUTSIDE the cachedir: PZ treats cachedir root as its own
CTL = os.environ.get("PZRIG_CTL", f"{_WSL_HOME}/pzjarvis-ctl")
CTL_UNC = _unc(CTL)
PZSERVER = os.environ.get("PZRIG_SERVER_DIR", f"{_WSL_HOME}/pzserver")
SENTINEL = "*** SERVER STARTED ****"

# single-purpose launcher: bash stays alive through the spawn (a backgrounded
# `A && B & C` chain races WSL session teardown — twice-burned footgun), and
# the pidfile gets the real binary's pid via comm-name match (no self-match).
_LAUNCH_SH = f"""#!/usr/bin/env bash
cd {PZSERVER}
setsid nohup ./start-server.sh -cachedir={RIG_CACHEDIR} -servername {RIG_SERVERNAME} \\
    -nosteam -adminpassword "$(cat {PZSERVER}/servertest_admin.txt)" \\
    > {CTL}/rig-run.log 2>&1 < /dev/null &
for _ in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    pid=$(pgrep -x ProjectZomboid6 -a | grep -F {RIG_CACHEDIR} | cut -d" " -f1 | head -1)
    if [ -n "$pid" ]; then echo "$pid" > {CTL}/rig.pid; exit 0; fi
done
exit 1
"""

# benign on clean vanilla boots (evidence: servertest first boot 2026-07-30)
_BENIGN = [
    re.compile(r"IsoPropertyType\.lookupOrDefaultStr"),
    re.compile(r"IsoPropertyTypeNotFoundException"),
    re.compile(r"Missing ThumpSound"),
    re.compile(r"libjsig\.so.*cannot be preloaded"),
    re.compile(r"DebugFileWatcher\.registerDir"),
    re.compile(r"A restricted method in java\.lang\.System"),
]
_SUSPECT = re.compile(
    r"LUA ERROR|Callframe|KahluaThread|java\.lang\.\w*(Exception|Error)"
    r"|^ERROR|Exception thrown|StackTrace|\.lua:\d+",
    re.IGNORECASE,
)

_RIG_INI_SEED = """\
DefaultPort=16271
UDPPort=16272
UPnP=false
Open=true
Public=false
PublicName=pzjarvis-testrig
Mods={mods}
Map=Muldraugh, KY
"""


@dataclass
class Verdict:
    booted: bool = False
    boot_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    benign_noise: int = 0
    timed_out: bool = False
    log_path: str = ""

    @property
    def ok(self) -> bool:
        return self.booted and not self.errors and not self.timed_out

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "booted": self.booted,
            "boot_seconds": round(self.boot_seconds, 1),
            "errors": self.errors[:40],
            "benign_noise": self.benign_noise,
            "timed_out": self.timed_out,
            "log": self.log_path,
        }


def _wsl(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wsl", "-e", "bash", "-c", cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _win_to_wsl(p: Path) -> str:
    r = _wsl(f"wslpath -a '{Path(p).as_posix()}'")
    return r.stdout.strip()


def _prepare(mod_path: Path | None) -> str:
    """Reset rig console, (re)link mod, seed ini. Returns Mods= id or ''."""
    mod_id = ""
    _wsl(
        f"rm -rf {RIG_CACHEDIR}/mods && "
        f"mkdir -p {RIG_CACHEDIR}/Server {RIG_CACHEDIR}/mods {CTL} && "
        f"rm -f {RIG_CACHEDIR}/server-console.txt {CTL}/rig.pid {CTL}/rig-run.log"
    )
    if mod_path is not None:
        mod_id = Path(mod_path).name
        wsl_mod = _win_to_wsl(Path(mod_path).resolve())
        # copy, not symlink: PZ's ZipBackup and 9P symlinks disagree, and copies
        # keep the rig hermetic from live edits mid-boot
        r = _wsl(
            f"cp -rL '{wsl_mod}' {RIG_CACHEDIR}/mods/{mod_id} && test -d {RIG_CACHEDIR}/mods/{mod_id}"
        )
        if r.returncode != 0:
            raise RuntimeError(f"mod staging failed: {r.stderr.strip()[:200]}")
    ini = _RIG_INI_SEED.format(mods=mod_id)
    # merge over existing generated ini if present: seed keys win
    merge = f"""
python3 - <<'EOF'
import pathlib
p = pathlib.Path("{RIG_CACHEDIR}/Server/{RIG_SERVERNAME}.ini")
seed = {json.dumps(ini)}
seedkv = dict(ln.split("=", 1) for ln in seed.splitlines() if "=" in ln)
if p.is_file():
    out = []
    for ln in p.read_text().splitlines():
        k = ln.split("=", 1)[0] if "=" in ln else None
        out.append(f"{{k}}={{seedkv.pop(k)}}" if k in seedkv else ln)
    out += [f"{{k}}={{v}}" for k, v in seedkv.items()]
    p.write_text("\\n".join(out) + "\\n")
else:
    p.write_text(seed)
EOF
"""
    _wsl(merge)
    pin = (
        Path(__file__).resolve().parents[2]
        / "testrig"
        / "config"
        / f"{RIG_SERVERNAME}_SandboxVars.lua"
    )
    if pin.is_file():
        (RIG_UNC / "Server" / f"{RIG_SERVERNAME}_SandboxVars.lua").write_bytes(pin.read_bytes())
    return mod_id


def _launch() -> bool:
    _wsl(f"mkdir -p {CTL}")
    (CTL_UNC / "launch-rig.sh").write_text(_LAUNCH_SH, encoding="utf-8", newline="\n")
    r = _wsl(f"bash {CTL}/launch-rig.sh", timeout=30)
    return r.returncode == 0


def _rig_pid() -> str:
    try:
        return (CTL_UNC / "rig.pid").read_text().strip()
    except OSError:
        return ""


def _kill() -> None:
    pid = _rig_pid()
    if pid:
        _wsl(f'pg=$(ps -o pgid= -p {pid} | tr -d " "); [ -n "$pg" ] && kill -- -$pg; true')


def _console_text() -> str:
    for p in (RIG_UNC / "server-console.txt", CTL_UNC / "rig-run.log"):
        try:
            if p.is_file():
                t = p.read_text(encoding="utf-8", errors="replace")
                if t.strip():
                    return t
        except OSError:
            continue
    return ""


_TIMESTAMP = re.compile(r"f:\d+\s+st:[\d,]+>?")
_BASELINE_FILE = CTL_UNC / "baseline-errors.txt"


def _normalize(ln: str) -> str:
    return _TIMESTAMP.sub("", ln).strip()


_ANIM_PROBE = re.compile(r"NoSuchFileException: .*/(AnimSets|actiongroups)")


def _suspects(text: str) -> tuple[list[str], int]:
    """(non-benign suspect lines, benign count) from console text."""
    out, benign = [], 0
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if not _SUSPECT.search(ln):
            continue
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        # engine probes AnimSets/actiongroups in every mod and throws per miss
        if "visitFileFailed" in ln and _ANIM_PROBE.search(nxt):
            benign += 1
            continue
        if any(b.search(ln) for b in _BENIGN):
            benign += 1
        else:
            out.append(ln.strip()[:240])
    return out, benign


def _load_baseline() -> set[str] | None:
    try:
        return {ln for ln in _BASELINE_FILE.read_text(encoding="utf-8").splitlines() if ln}
    except OSError:
        return None


def capture_baseline() -> Verdict:
    """Bare boot; store its normalized error set as the per-build noise baseline."""
    v = test_mod(None, use_baseline=False)
    if v.booted:
        _BASELINE_FILE.write_text(
            "\n".join(sorted({_normalize(e) for e in v.errors})) + "\n", encoding="utf-8"
        )
    return v


_MOD_NOT_FOUND = re.compile(r'required mod "([^"]+)" not found')


def _classify(text: str, verdict: Verdict, use_baseline: bool) -> None:
    for m in _MOD_NOT_FOUND.finditer(text):
        verdict.errors.append(f"MOD NOT LOADED: {m.group(1)}")
    suspects, verdict.benign_noise = _suspects(text)
    baseline = _load_baseline() if use_baseline else None
    if baseline is None:
        verdict.errors += suspects
        if use_baseline:
            verdict.errors.insert(0, "NO BASELINE — run `pzkit test baseline` first")
        return
    verdict.errors += [s for s in suspects if _normalize(s) not in baseline]


def test_mod(
    mod_path: str | Path | None, timeout_s: int = 300, use_baseline: bool = True
) -> Verdict:
    """Boot the rig with (or without) a mod; return the structured verdict."""
    v = Verdict(log_path=f"{RIG_CACHEDIR}/server-console.txt")
    _prepare(Path(mod_path) if mod_path else None)
    t0 = time.time()
    if not _launch():
        v.errors.append("rig launcher: server process never appeared (see rig-run.log)")
        _classify(_console_text(), v, use_baseline)
        _kill()
        return v
    try:
        while time.time() - t0 < timeout_s:
            text = _console_text()
            if SENTINEL in text:
                v.booted = True
                v.boot_seconds = time.time() - t0
                break
            if "TERMINATING" in text or _dead():
                v.boot_seconds = time.time() - t0
                break
            time.sleep(3)
        else:
            v.timed_out = True
            v.boot_seconds = time.time() - t0
        time.sleep(2)  # let trailing lua errors flush after the sentinel
        _classify(_console_text(), v, use_baseline)
    finally:
        _kill()
    return v


def _dead() -> bool:
    pid = _rig_pid()
    if not pid:
        return False  # launcher verified the spawn; empty pidfile means UNC lag, not death
    r = _wsl(f"kill -0 {pid} 2>/dev/null && echo alive || echo dead")
    return "dead" in r.stdout
