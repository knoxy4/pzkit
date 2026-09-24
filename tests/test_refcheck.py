"""Regression tests for refcheck's parser and reference resolution."""
from __future__ import annotations

import sqlite3

import pytest

from pzkit import refcheck


@pytest.fixture
def db(tmp_path):
    p = tmp_path / "vanilla.db"
    con = sqlite3.connect(p)
    con.executescript(
        "CREATE TABLE blocks (btype TEXT, module TEXT, name TEXT);"
        "CREATE TABLE props (key TEXT, value TEXT);"
        "CREATE TABLE meta (key TEXT, value TEXT);"
    )
    con.executemany("INSERT INTO blocks VALUES (?,?,?)", [
        ("craftRecipe", "Base", "Make_Metal_Drum"),
        ("character_trait_definition", "Base", "Brave"),
        ("item", "Base", "Plank"),
        ("model", "Base", "CanClosed"),
    ])
    con.execute("INSERT INTO props VALUES ('xpAward','Woodwork:5')")
    con.commit()
    return p


def test_kr_style_block_headers_count_as_own_names(db):
    """`item Foo {` on one line must register Foo, same as the split-line form."""
    text = """module MyMod {
    craftRecipe Make_Thing {
        inputs { item 1 Base.Plank, }
    }
    item Booster {
        GrantedRecipes = Make_Thing,
    }
}
"""
    assert refcheck.check([("s.txt", text)], db) == []


def test_mod_defined_model_resolves(db):
    text = """module MyMod {
    model MyProp
    {
        mesh = props/MyProp,
    }
    item PropItem
    {
        WorldStaticModel = MyProp,
    }
}
"""
    assert refcheck.check([("s.txt", text)], db) == []


def test_block_commented_refs_are_ignored(db):
    text = """module MyMod {
    item Thing
    {
/*
        MutuallyExclusiveTraits = OldTraitName,
        Type = Weapon,
*/
        GrantedTraits = Brave,
    }
}
"""
    assert refcheck.check([("s.txt", text)], db) == []


def test_findings_carry_file_and_line(db):
    text = """module MyMod {
    item T
    {
        GrantedRecipes = Nope,
    }
}
"""
    sev, code, rel, line, _msg = refcheck.check([("42/media/scripts/i.txt", text)], db)[0]
    assert (sev, code, rel, line) == ("ERROR", "REF-missing", "42/media/scripts/i.txt", 4)


def test_module_qualified_recipe_ref_gets_targeted_message(db):
    text = """module MyMod {
    item T
    {
        GrantedRecipes = Base.Make_Metal_Drum,
    }
}
"""
    (finding,) = refcheck.check([("s.txt", text)], db)
    assert finding[1] == "REF-missing"
    assert "bare names" in finding[4] and "Make_Metal_Drum" in finding[4]


def test_real_phantom_recipe_still_caught(db):
    text = """module MyMod {
    item T
    {
        GrantedRecipes = Make_Metal_Drum;Ghost_Recipe,
    }
}
"""
    msgs = [f[4] for f in refcheck.check([("s.txt", text)], db)]
    assert len(msgs) == 1 and "Ghost_Recipe" in msgs[0]
