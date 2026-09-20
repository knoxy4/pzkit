"""G2 gate tests: scaffold->validate green; sabotaged mod correctly RED."""

import pytest

from pzkit.scaffold import scaffold_mod
from pzkit.validator import validate_mod
from pzkit.vanilla_index import default_db_path

HAS_INDEX = default_db_path().is_file()


def _errors(rep):
    return [f for f in rep.findings if f.level == "ERROR"]


def test_scaffold_layout(tmp_path):
    root = scaffold_mod("pzj_hello", tmp_path)
    assert (root / "mod.info").is_file()
    assert (root / "42" / "media" / "scripts" / "pzj_hello_items.txt").is_file()
    assert (root / "42" / "media" / "translations" / "EN" / "ItemName_EN.txt").is_file()
    assert (root / "common" / "media").is_dir()


def test_scaffold_rejects_bad_ids(tmp_path):
    with pytest.raises(ValueError):
        scaffold_mod("hello", tmp_path)
    scaffold_mod("pzj_hello", tmp_path)
    with pytest.raises(FileExistsError):
        scaffold_mod("pzj_hello", tmp_path)


def test_hello_world_validates_green(tmp_path):
    root = scaffold_mod("pzj_hello", tmp_path)
    rep = validate_mod(root)
    assert rep.ok, [f.render() for f in _errors(rep)]


def test_sabotage_unbalanced_brace_is_red(tmp_path):
    root = scaffold_mod("pzj_broken", tmp_path)
    script = root / "42" / "media" / "scripts" / "pzj_broken_items.txt"
    script.write_text(script.read_text().replace("}\n}", "}"), encoding="utf-8")
    rep = validate_mod(root)
    assert not rep.ok
    assert any(f.code == "DSL-syntax" for f in _errors(rep))


def test_sabotage_missing_translation_is_red(tmp_path):
    root = scaffold_mod("pzj_broken2", tmp_path)
    (root / "42" / "media" / "translations" / "EN" / "ItemName_EN.txt").unlink()
    rep = validate_mod(root)
    assert not rep.ok
    assert any(f.code == "TR-missing" for f in _errors(rep))


def test_sabotage_wrong_id_is_red(tmp_path):
    root = scaffold_mod("pzj_broken3", tmp_path)
    mi = root / "mod.info"
    mi.write_text(mi.read_text().replace("id=pzj_broken3", "id=pzj_other"), encoding="utf-8")
    rep = validate_mod(root)
    assert not rep.ok
    assert any(f.code == "LAYOUT-id" for f in _errors(rep))


@pytest.mark.skipif(not HAS_INDEX, reason="vanilla index not built on this machine")
def test_sabotage_phantom_ref_is_red(tmp_path):
    root = scaffold_mod("pzj_broken4", tmp_path)
    recipe = root / "42" / "media" / "scripts" / "pzj_broken4_recipes.txt"
    recipe.write_text(
        """module pzj_broken4
{
    craftRecipe MakeNothing
    {
        time = 10,
        inputs
        {
            item 1 [Base.DefinitelyMissing999],
        }
        outputs
        {
            item 1 mapper:NoSuchMapper,
        }
    }
}
""",
        encoding="utf-8",
    )
    rep = validate_mod(root)
    assert not rep.ok
    codes = {f.code for f in _errors(rep)}
    assert "REF-item" in codes and "REF-mapper" in codes


@pytest.mark.skipif(not HAS_INDEX, reason="vanilla index not built on this machine")
def test_diff_vanilla_classifies(tmp_path):
    from pzkit.diff import diff_vanilla

    root = scaffold_mod("pzj_diffy", tmp_path)
    (root / "42" / "media" / "scripts" / "pzj_diffy_override.txt").write_text(
        "module Base\n{\n    item PickAxe\n    {\n        Weight = 1.0,\n    }\n}\n",
        encoding="utf-8",
    )
    d = diff_vanilla(root)
    assert "item Base.PickAxe" in d["overrides"]
    assert "item pzj_diffy.HelloDoodad" in d["new"]


def test_lua_stage_never_silent_without_toolchain(tmp_path):
    import shutil as _sh

    root = scaffold_mod("pzj_lua", tmp_path)
    (root / "42" / "media" / "lua" / "client" / "hello.lua").write_text(
        'print("hi")\n', encoding="utf-8"
    )
    rep = validate_mod(root)
    lua_findings = [f for f in rep.findings if f.code.startswith("LUA")]
    if _sh.which("luacheck") is None and _sh.which("luac") is None:
        assert any(f.code == "LUA-toolchain" and f.level == "SKIP" for f in lua_findings)
    else:
        assert not [f for f in lua_findings if f.level == "ERROR"]
