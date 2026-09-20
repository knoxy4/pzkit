from pzkit.scripts_parser import parse_recipe_entry, parse_script

ITEM = """
module Base
{
    /* comment, with = and { inside */
    item Pocketwatch
    {
        DisplayCategory = Memento,
        Tags = base:hasmetal;base:fitskeyring,
        SoundRadius = 7,
    }
}
"""

RECIPE = """
module Base
{
    craftRecipe SawLogs
    {
        time = 230,
        inputs
        {
            item 1 [Base.Log] flags[Prop2],
            item 1 tags[base:saw] mode:keep flags[MayDegradeLight;Prop1],
        }
        outputs
        {
            item 3 Base.Plank,
        }
        itemMapper StickMapper
        {
            Base.WoodenStick2 = Base.LongStick,
            default = Base.WoodenStick2,
        }
    }
}
"""

FIXING = """
module Base
{
    fixing Fix Pistol
    {
        Require = Base.Pistol,
        Fixer = Base.Pistol; Aiming=3
    }
}
"""

VEHICLE = """
module Base
{
    vehicle Van
    {
        model
        {
            file = Vehicles_Van,
            offset = 0.0 0.3681 0.0,
        }
        maxSpeed = 60.0,
    }
}
"""


def test_item_block():
    f = parse_script(ITEM)
    assert not f.warnings
    mod = f.blocks[0]
    assert (mod.btype, mod.name) == ("module", "Base")
    item = mod.children[0]
    assert (item.btype, item.name) == ("item", "Pocketwatch")
    props = {p.key: p.value for p in item.props}
    assert props["Tags"] == "base:hasmetal;base:fitskeyring"
    assert props["SoundRadius"] == "7"


def test_recipe_structure_and_entries():
    f = parse_script(RECIPE)
    recipe = f.blocks[0].children[0]
    assert recipe.btype == "craftRecipe"
    kids = {c.btype: c for c in recipe.children}
    assert set(kids) == {"inputs", "outputs", "itemMapper"}
    e = parse_recipe_entry(kids["inputs"].entries[0][0])
    assert (e.kind, e.amount, e.targets, e.flags) == ("item", 1.0, ["Base.Log"], ["Prop2"])
    e2 = parse_recipe_entry(kids["inputs"].entries[1][0])
    assert (e2.tags, e2.mode) == (["base:saw"], "keep")
    out = parse_recipe_entry(kids["outputs"].entries[0][0])
    assert (out.amount, out.targets) == (3.0, ["Base.Plank"])
    mapper_props = {p.key: p.value for p in kids["itemMapper"].props}
    assert mapper_props["default"] == "Base.WoodenStick2"


def test_multiword_name_and_embedded_equals():
    f = parse_script(FIXING)
    fx = f.blocks[0].children[0]
    assert fx.name == "Fix Pistol"
    props = {p.key: p.value for p in fx.props}
    # missing trailing comma before } and '=' inside the value both survive
    assert props["Fixer"] == "Base.Pistol; Aiming=3"


def test_anonymous_nested_block_and_tuple_value():
    f = parse_script(VEHICLE)
    van = f.blocks[0].children[0]
    model = van.children[0]
    assert (model.btype, model.name) == ("model", None)
    props = {p.key: p.value for p in model.props}
    assert props["offset"] == "0.0 0.3681 0.0"


def test_unbalanced_brace_warns_not_raises():
    f = parse_script("module Base { item X { Weight = 1,")
    assert any("unclosed" in w for w in f.warnings)
