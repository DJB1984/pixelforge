import contextlib
import io
import json
import sys
import unittest

from pixelforge import model, playtest as pt
from pixelforge.export import build_sheet, export_sprite, write_index
from pixelforge.level import Level
from pixelforge.model import Sprite, SpriteError, list_sprites
from pixelforge.validate import check_sprite

from helpers import TempProject
from test_level import LevelProject

DOT = ("." * 8 + "\n") * 3 + ("..gGGg..\n" * 5)   # 8x8, a blob on the bottom rows
SPARK = ("." * 8 + "\n") * 3 + "...ww...\n" + "..wwww..\n" + "...ww...\n" + ("." * 8 + "\n") * 2


def meta(d):
    return json.loads((d / "sprite.json").read_text())


def set_meta(d, **kw):
    m = meta(d)
    m.update(kw)
    (d / "sprite.json").write_text(json.dumps(m))


def errors(name):
    return [str(i) for i in check_sprite(name) if i.level == "error"]


def run_cli(*args):
    from pixelforge.__main__ import main
    out = io.StringIO()
    old = sys.argv
    sys.argv = ["pixelforge", *args]
    try:
        with contextlib.redirect_stdout(out):
            main()
        return 0, out.getvalue()
    except SystemExit as e:
        return e.code, out.getvalue()
    finally:
        sys.argv = old


class FxTest(unittest.TestCase):
    def fx(self, p, **kw):
        d = p.sprite("spark", (8, 8), {"w": "#ffffff"}, {"a": SPARK, "b": SPARK.replace("wwww", ".ww.")},
                     {"pop": {"frames": ["a", "b"]}})
        set_meta(d, type="fx", **kw)
        return d

    def test_plays_once_in_front_without_hurtboxes(self):
        with TempProject() as p:
            self.fx(p)
            s = Sprite.load("spark")
            self.assertEqual((s.kind, s.layer, s.anim("pop").loop), ("fx", "front", False))
            _, data = build_sheet(s)
            pf = data["meta"]["pixelforge"]
            self.assertEqual((pf["kind"], pf["fx"], pf["animations"]["spark_pop"]["loop"]), ("fx", {"layer": "front"}, False))
            self.assertTrue(all(f["pixelforge"]["hurt"] == [] for f in data["frames"].values()))
            self.assertEqual(errors("spark"), [])

    def test_index_group_and_looping_warning(self):
        with TempProject() as p:
            d = self.fx(p, layer="world")
            m = meta(d)
            m["animations"]["pop"]["loop"] = True
            (d / "sprite.json").write_text(json.dumps(m))
            self.assertEqual(Sprite.load("spark").layer, "world")
            self.assertTrue(any("never ends" in str(i) for i in check_sprite("spark")))
            export_sprite(Sprite.load("spark"))
            self.assertEqual(json.loads(write_index().read_text())["fx"], ["spark"])

    def test_levels_dont_place_effects(self):
        with LevelProject() as p:
            self.fx(p)
            p.level("a", layers=[{"name": "ground", "rows": ["gggg"] * 2}],
                    objects={"legend": {"s": {"sprite": "spark"}}, "rows": ["@...", "..s."]})
            self.assertTrue(any("is an effect" in e for e in Level.load("a").errors()), Level.load("a").errors())

    def test_new_fx(self):
        with TempProject() as p:
            (p.root / "pixelforge.json").write_text("{}")
            (p.root / "palettes").mkdir()
            (p.root / "palettes" / "game.json").write_text(json.dumps({"colors": {
                "outline": "#181425", "white": "#ffffff", "yellow": "#fee761"}}))
            code, out = run_cli("new", "boom", "--fx", "--size", "24x24")
            self.assertIn(code, (None, 0), out)
            s = Sprite.load("boom")
            self.assertEqual((s.kind, s.width, s.origin, list(s.animations)), ("fx", 24, (12, 12), ["play"]))


class VariantTest(unittest.TestCase):
    def slime(self, p, variants):
        d = p.sprite("slime", (8, 8), {"g": "green", "G": "forest"}, {"idle_0": DOT}, {"idle": {"frames": ["idle_0"]}})
        (p.root / "palettes").mkdir(exist_ok=True)
        (p.root / "palettes" / "game.json").write_text(json.dumps({"colors": {
            "green": "#63c74d", "forest": "#3e8948", "blue": "#0099db", "navy": "#124e89"}}))
        set_meta(d, variants=variants)
        return d

    def test_listed_after_the_base_and_recolored(self):
        with TempProject() as p:
            p.sprite("bat", (8, 8), {"k": "#000000"}, {"a": DOT.replace("g", "k").replace("G", "k")}, {"fly": {"frames": ["a"]}})
            self.slime(p, {"slime_blue": {"palette": {"g": "blue", "G": "navy"}}})
            self.assertEqual(list_sprites(), ["bat", "slime", "slime_blue"])
            self.assertEqual(model.sprite_folder("slime_blue"), p.root / "sprites" / "slime")
            s = Sprite.load("slime_blue")
            self.assertEqual((s.name, s.base, s.palette["g"], s.palette["G"]), ("slime_blue", "slime", (0, 153, 219, 255), (18, 78, 137, 255)))
            self.assertEqual(Sprite.load("slime").variants, ["slime_blue"])
            self.assertEqual(s.frame("idle", 0).cells, Sprite.load("slime").frame("idle", 0).cells)   # same pixels, new colors
            paths = export_sprite(s)
            data = json.loads(paths[1].read_text())
            self.assertEqual([t["name"] for t in data["meta"]["frameTags"]], ["slime_blue_idle"])
            self.assertEqual((data["meta"]["image"], data["meta"]["pixelforge"]["variant_of"]), ("slime_blue.png", "slime"))
            self.assertEqual(json.loads(write_index().read_text())["sprites"], ["slime_blue"])
            self.assertEqual(errors("slime_blue"), [])

    def test_bad_variants(self):
        with TempProject() as p:
            self.slime(p, {"slime_x": {"palette": {"q": "blue"}}, "slime_y": {"size": [4, 4]}})
            with self.assertRaisesRegex(SpriteError, "aren't keys in slime's palette"):
                Sprite.load("slime_x")
            with self.assertRaisesRegex(SpriteError, "unknown keys"):
                Sprite.load("slime_y")
            self.assertTrue(errors("slime_x"))

    def test_a_folder_of_the_same_name_wins(self):
        with TempProject() as p:
            p.sprite("slime_blue", (8, 8), {"g": "#ff0000", "G": "#880000"}, {"idle_0": DOT}, {"idle": {"frames": ["idle_0"]}})
            self.slime(p, {"slime_blue": {"palette": {"g": "blue"}}})
            self.assertEqual(list_sprites(), ["slime", "slime_blue"])
            self.assertIsNone(Sprite.load("slime_blue").base)
            self.assertTrue(any("same name" in str(i) for i in check_sprite("slime")))

    def test_editing_commands_refuse_and_levels_place_it(self):
        with TempProject() as p:
            (p.root / "pixelforge.json").write_text("{}")
            self.slime(p, {"slime_blue": {"palette": {"g": "blue"}}})
            code, _ = run_cli("paint", "slime_blue", "idle_0", "px 0 0 g")
            self.assertIn("palette variant of slime", str(code))
            code, _ = run_cli("new", "slime_blue")
            self.assertIn("already a palette variant", str(code))
            self.assertEqual((p.root / "sprites/slime/frames/idle_0.txt").read_text(), DOT)

    def test_levels_place_it(self):
        with LevelProject() as p:
            self.slime(p, {"slime_blue": {"palette": {"g": "blue"}}})
            p.level("a", layers=[{"name": "ground", "rows": ["gggg"] * 2}],
                    objects={"legend": {"s": {"sprite": "slime_blue", "type": "enemy"}}, "rows": ["@...", "..s."]})
            lv = Level.load("a")
            self.assertEqual(lv.errors(), [])
            self.assertEqual([(o.sprite, o.type) for o in lv.objects if o.sprite], [("slime_blue", "enemy")])

    def test_live_signature_follows_the_base(self):
        from pixelforge.server import asset_sig
        with TempProject() as p:
            d = self.slime(p, {"slime_blue": {"palette": {"g": "blue"}}})
            before = asset_sig("slime_blue")
            import os
            os.utime(d / "frames" / "idle_0.txt", (1, 1))
            self.assertNotEqual(asset_sig("slime_blue"), before)


class DialogNotesTest(unittest.TestCase):
    def test_dialog_events_and_no_stuck_while_talking(self):
        e = pt.parse_expect("dialog welcome_sign")
        self.assertEqual((e.event, e.match), ("dialog", "welcome_sign"))
        trace = [{"t": t, "input": ["right"], "x": 10.0, "y": 50.0, "dialogOpen": True} for t in range(0, 2000, 100)]
        r = pt.Run(level="t", script="", view="topdown", trace=trace,
                   events=[{"t": 300, "type": "dialog", "name": "welcome_sign", "text": "Welcome!\nMore"}])
        notes = pt.notes(r)
        self.assertFalse(any(n.startswith("stuck") for n in notes), notes)
        self.assertIn("dialogs: welcome_sign at 0.30s ('Welcome!')", notes)
        self.assertEqual(pt.check_expect(e, {}, r.events)[0], True)


if __name__ == "__main__":
    unittest.main()
