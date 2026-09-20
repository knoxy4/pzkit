"""Unit tests for the rig's console classifier — no boots, canned console text."""

from pzkit.testrig import Verdict, _classify, _normalize, _suspects

LUA_CRASH = """\
LOG  : Network      f:0 st:1,234> *** SERVER STARTED ****
ERROR: General      f:0 st:1,300 at KahluaThread.flushErrorMessage      > dumping Lua stack trace
java.lang.RuntimeException: attempted index: threshold of non-table: null at KahluaThread.tableget(KahluaThread.java:1430).
"""

VANILLA_NOISE = """\
ERROR: ld.so: object 'libjsig.so' from LD_PRELOAD cannot be preloaded (cannot open shared object file): ignored.
ERROR: General      f:0 st:1,100 at IsoPropertyType.lookupOrDefaultStr> Exception thrown
ERROR: General      f:0 st:1,200> Missing ThumpSound for breakable object fencing_01_9
"""

ANIM_PROBE = """\
ERROR: General      f:0 st:1,400> AdvancedAnimator$1.visitFileFailed> Exception thrown
\tjava.nio.file.NoSuchFileException: /rig/mods/pzj_x/42/media/AnimSets at UnixException.translateToIOException(null:-1).
"""

MOD_MISSING = 'WARN : Mod          f:0 st:1,500 at ZomboidFileSystem.loadModAndRequired> required mod "pzj_ghost" not found\n'


def test_normalize_strips_timestamps():
    a = _normalize("ERROR: General      f:0 st:116,384,014> X happened")
    b = _normalize("ERROR: General      f:0 st:999,111,222> X happened")
    assert a == b
    assert "st:" not in a and "X happened" in a


def test_lua_crash_is_flagged():
    suspects, _ = _suspects(LUA_CRASH)
    assert any("RuntimeException" in s for s in suspects)
    assert any("KahluaThread" in s for s in suspects)


def test_vanilla_noise_is_benign():
    suspects, benign = _suspects(VANILLA_NOISE)
    assert suspects == []
    assert benign == 3


def test_anim_probe_lookahead_is_benign():
    suspects, benign = _suspects(ANIM_PROBE)
    assert suspects == []
    assert benign == 1


def test_mod_not_found_fails_verdict():
    v = Verdict()
    _classify(MOD_MISSING, v, use_baseline=False)
    assert any("MOD NOT LOADED: pzj_ghost" in e for e in v.errors)


def test_baseline_diff_suppresses_known_noise(tmp_path, monkeypatch):
    from pzkit import testrig

    known = "ERROR: General      f:0 st:1,300 at Basements.mergeRoomsOntoMetaCell    > duplicate RoomDef.metaID for room at 1,2,0"
    fresh = "ERROR: General      f:0 st:1,301 at SomethingNew.explode                > kaboom"
    bl = tmp_path / "baseline-errors.txt"
    bl.write_text(testrig._normalize(known) + "\n", encoding="utf-8")
    monkeypatch.setattr(testrig, "_BASELINE_FILE", bl)
    v = Verdict()
    _classify(known + "\n" + fresh + "\n", v, use_baseline=True)
    assert len(v.errors) == 1
    assert "kaboom" in v.errors[0]
