"""Parts placed on big canvases, props (objects, buildings, background accents), tileset stamps,
icon atlases and bitmap fonts."""
import contextlib
import io
import json
import shutil
import unittest

from PIL import Image

from pixelforge import model
from pixelforge.__main__ import main
from pixelforge.export import build_font, build_slices, export_sprite, write_index
from pixelforge.model import Sprite, SpriteError, parse_glyphs
from pixelforge.project import init_project, upgrade_project
from pixelforge.render import font_text, nine_slice, tileset_preview
from pixelforge.validate import check_sprite

from helpers import TempProject

PAL = {"k": "#000000", "w": "#ffffff", "r": "#ff0000"}


def write(p, name, meta, frames=None, parts=None, extra=None):
    d = p.root / "sprites" / name
    for sub, files in (("frames", frames or {}), ("parts", parts or {})):
        if files:
            (d / sub).mkdir(parents=True, exist_ok=True)
        for fid, text in files.items():
            (d / sub / f"{fid}.txt").write_text(text)
    for fname, text in (extra or {}).items():
        d.mkdir(parents=True, exist_ok=True)
        (d / fname).write_text(text)
    d.mkdir(parents=True, exist_ok=True)
    (d / "sprite.json").write_text(json.dumps({"name": name, **meta}))
    return d


def blank(w, h):
    return ("." * w + "\n") * h


def messages(name):
    return "\n".join(str(i) for i in check_sprite(name))


class PartsTest(unittest.TestCase):
    def test_parts_place_at_positions_with_flip_and_replace(self):
        with TempProject() as p:
            write(p, "house", {"size": [10, 6], "palette": PAL, "animations": {"a": {"frames": [{"layers": [
                "wall", {"part": "win", "at": [[1, 1], [6, 1]]}, {"part": "arrow", "at": [4, 4], "flip": "h",
                                                                  "replace": {"k": "r"}}]}]}}},
                  frames={"wall": "w" * 10 + "\n" + ("w" + "." * 8 + "w\n") * 4 + "w" * 10 + "\n"},
                  parts={"win": "kk\nkk\n", "arrow": "k.\nkk\n"})
            g = Sprite.load("house").frame("a", 0)
            self.assertEqual("".join(g.cells[1]), "wkk...kk.w")
            self.assertEqual("".join(g.cells[4][4:6]), ".r")   # flipped "k." -> ".k", recoloured
            self.assertEqual("".join(g.cells[5][4:6]), "rr")
            self.assertNotIn("error", messages("house"))

    def test_part_roles_and_errors(self):
        with TempProject() as p:
            write(p, "s", {"size": [8, 8], "palette": PAL, "roles": {"blade": "hit"},
                           "animations": {"a": {"frames": [{"from": "body", "layers": [{"part": "blade", "at": [5, 2]}],
                                                            "active": True}]},
                                          "b": {"frames": [{"layers": [{"part": "ghost"}]}]}}},
                  frames={"body": blank(8, 4) + "..kk....\n" * 4}, parts={"blade": "k\nk\nk\n", "ragged": "kk\nk\n",
                                                                         "far": "k\n"})
            from pixelforge.boxes import frame_boxes
            s = Sprite.load("s")
            boxes = frame_boxes(s, s.anim("a").frames[0], True)
            self.assertEqual(boxes["hit"], [[5, 2, 1, 3]])
            out = messages("s")
            self.assertIn("parts/ragged.txt: row 1 has 1 chars, expected 2", out)
            self.assertIn("parts/ghost.txt: placed by a {\"part\": ...} entry but the file doesn't exist", out)
            self.assertIn("parts/far.txt: not placed", out)
            with self.assertRaises(SpriteError):
                s.resolve({"part": "blade", "offset": [1, 0]})   # parts take at, not offset

    def test_off_canvas_part_warns(self):
        with TempProject() as p:
            write(p, "s", {"size": [4, 4], "palette": PAL, "animations": {"a": {"frames": [
                {"layers": ["f", {"part": "dot", "at": [[9, 9], [3, 3]]}]}]}}},
                  frames={"f": "kkkk\n" * 4}, parts={"dot": "kk\n"})
            out = messages("s")
            self.assertIn("entirely off", out)
            self.assertIn("runs off the canvas edge at (3,3)", out)


class PropTest(unittest.TestCase):
    def house(self, p, **meta):
        art = blank(8, 2) + "kkkkkkkk\n" * 2 + "wwwwwwww\n" * 4   # roof rows 2-3, walls 4-7
        return write(p, "house", {"type": "prop", "size": [8, 8], "palette": PAL,
                                  "animations": {"closed": {"frames": ["art"]}, "open": {"frames": ["art"]}}, **meta},
                     frames={"art": art})

    def test_footprint_layer_and_export_meta(self):
        with TempProject() as p:
            self.house(p, footprint=[0, 5, 8, 3], view="topdown")
            s = Sprite.load("house")
            self.assertEqual((s.kind, s.layer, s.solid, s.scroll), ("prop", "world", True, 1.0))
            self.assertEqual(s.body_rect(), (0, 5, 8, 3))
            paths = export_sprite(s, p.root / "export")
            meta = json.loads(paths[1].read_text())["meta"]["pixelforge"]
            self.assertEqual(meta["kind"], "prop")
            self.assertEqual(meta["body"], {"x": 0, "y": 5, "w": 8, "h": 3})
            self.assertEqual(meta["prop"], {"layer": "world", "scroll": 1.0, "solid": True, "footprint": [0, 5, 8, 3],
                                            "ysort": True, "tiles": None})
            self.assertEqual(json.loads(write_index(p.root / "export").read_text())["props"], ["house"])

    def test_background_accent_defaults(self):
        with TempProject() as p:
            self.house(p, scroll=0.3)
            s = Sprite.load("house")
            self.assertEqual((s.layer, s.solid), ("back", False))
            self.assertEqual(s.body_rect(), (0, 2, 8, 6))   # no footprint: the art's bounds

    def test_topdown_solid_without_footprint_warns(self):
        with TempProject() as p:
            self.house(p, view="topdown")
            self.assertIn("without a footprint", messages("house"))
            self.house(p, view="side")
            self.assertNotIn("without a footprint", messages("house"))

    def test_slices_into_tiles_with_collision_and_walk_behind(self):
        with TempProject() as p:
            self.house(p, footprint=[0, 5, 8, 3], view="topdown", slice=[4, 4])
            s = Sprite.load("house")
            img, data = build_slices(s)
            pf = data["pixelforge"]
            # 2x2 cells: top row (y 0-3) has the roof, so all four cells have art
            self.assertEqual(pf["sample"], [[0, 1], [2, 3]])
            self.assertEqual(pf["stamps"], {"house": [[0, 1], [2, 3]]})
            self.assertEqual(pf["properties"], [{"above": True}, {"above": True}, {"collides": True}, {"collides": True}])
            self.assertEqual((data["tilewidth"], data["tilecount"]), (4, 4))
            paths = export_sprite(s, p.root / "export")
            self.assertEqual([x.name for x in paths], ["house.png", "house.json", "house_tiles.png", "house_tiles.json"])
            self.assertIn("house_tiles", json.loads(write_index(p.root / "export").read_text())["tilesets"])

    def test_blank_cells_are_left_out_of_slices(self):
        with TempProject() as p:
            write(p, "rock", {"type": "prop", "size": [8, 4], "palette": PAL, "slice": [4, 4],
                              "animations": {"a": {"frames": ["f"]}}}, frames={"f": "kk......\n" * 4})
            _, data = build_slices(Sprite.load("rock"))
            self.assertEqual(data["pixelforge"]["sample"], [[0, -1]])


class StampTest(unittest.TestCase):
    def test_stamps_resolve_through_the_sample_legend(self):
        with TempProject() as p:
            write(p, "kit", {"type": "tileset", "size": [2, 2], "palette": PAL, "tiles": ["roof", "wall", "door"],
                             "sample": {"legend": {"^": "roof", "#": "wall", "d": "door"}, "rows": ["^^"]},
                             "stamps": {"hut": {"rows": ["^^^", "#d#"]},
                                        "shed": {"legend": {"x": "wall"}, "rows": ["x x"]},
                                        "bad": {"rows": ["?"]}}},
                  frames={"roof": "rr\nrr\n", "wall": "ww\nww\n", "door": "kk\nkk\n"})
            s = Sprite.load("kit")
            self.assertEqual(s.stamp_map("hut"), [[0, 0, 0], [1, 2, 1]])
            self.assertEqual(s.stamp_map("shed"), [[1, -1, 1]])
            self.assertIn("stamps/bad", messages("kit"))
            img = tileset_preview(s)
            self.assertGreater(img.height, 0)


class IconsTest(unittest.TestCase):
    def test_atlas_frames_by_name_and_nine_slice(self):
        with TempProject() as p:
            write(p, "ui", {"type": "icons", "size": [6, 6], "columns": 2, "palette": PAL,
                            "icons": ["potion", {"name": "panel", "from": "panel", "nine": [2, 2, 2, 2]}, "coin"]},
                  frames={"potion": blank(6, 2) + "..rr..\n" * 4, "panel": "kkkkkk\n" + "kwwwwk\n" * 4 + "kkkkkk\n",
                          "coin": blank(6, 6)})
            s = Sprite.load("ui")
            self.assertTrue(s.tiled)
            paths = export_sprite(s, p.root / "export")
            data = json.loads(paths[1].read_text())
            self.assertEqual(list(data["frames"]), ["potion", "panel", "coin"])
            self.assertEqual(data["frames"]["coin"]["frame"], {"x": 0, "y": 7, "w": 6, "h": 6})
            self.assertEqual(data["meta"]["pixelforge"]["nine"], {"panel": [2, 2, 2, 2]})
            self.assertEqual(json.loads(write_index(p.root / "export").read_text())["icons"], ["ui"])
            out = messages("ui")
            self.assertIn("icon 2 'coin'", out)                    # empty icon warns
            self.assertNotIn("seam", out)
            # stretched: the 2px border stays 2px, the middle grows
            img = Image.new("RGBA", (6, 6), (255, 255, 255, 255))
            img.paste((0, 0, 0, 255), (0, 0, 2, 6))
            wide = nine_slice(img, [2, 2, 2, 2], 20, 6)
            self.assertEqual([wide.getpixel((x, 3))[0] for x in (0, 1, 2, 10, 19)], [0, 0, 255, 255, 255])

    def test_bad_nine_and_animated_icons(self):
        with TempProject() as p:
            write(p, "ui", {"type": "icons", "size": [4, 4], "palette": PAL,
                            "icons": [{"name": "p", "from": "p", "nine": [2, 2, 1, 1]},
                                      {"name": "spin", "frames": ["p", "p"]}]}, frames={"p": "kkkk\n" * 4})
            out = messages("ui")
            self.assertIn("leaves no middle", out)
            self.assertIn("can't animate", out)


FONT = """header lines are ignored
= A
.#.
#.#
###
#.#
= I
#
#
#
#
= -
..
##
..
..
"""


class FontTest(unittest.TestCase):
    def font(self, p, glyphs=FONT, **meta):
        return write(p, "f", {"type": "font", "size": [3, 4], "palette": {"#": "#ffffff"}, "spacing": 1,
                              "space": 2, **meta}, extra={"glyphs.txt": glyphs})

    def test_glyphs_widths_and_bmfont_xml(self):
        with TempProject() as p:
            self.font(p)
            s = Sprite.load("f")
            self.assertEqual(s.tile_names(), ["A", "I", "-"])
            self.assertEqual(s.glyph_widths, {"A": 3, "I": 1, "-": 2})
            self.assertEqual(s.tile("I").cells[0], list("#.."))        # left-aligned in its 3-wide cell
            self.assertEqual(s.tile_properties("A"), {"advance": 4})
            _, data, xml = build_font(s)
            self.assertEqual(data["pixelforge"]["chars"], "AI-")
            self.assertIn('<char id="65" x="0" y="0" width="3" height="4" xoffset="0" yoffset="0" xadvance="4"', xml)
            self.assertIn('<char id="97" x="0" y="0" width="3"', xml)  # 'a' reuses 'A'
            self.assertIn('<char id="32" x="0" y="0" width="0" height="0" xoffset="0" yoffset="0" xadvance="2"', xml)
            self.assertIn('<common lineHeight="6" base="4"', xml)
            paths = export_sprite(s, p.root / "export")
            self.assertEqual([x.name for x in paths], ["f.png", "f.json", "f.xml"])
            self.assertEqual(json.loads(write_index(p.root / "export").read_text())["fonts"], ["f"])
            # "AI A": A(3)+1, I(1)+1, space 2, a->A(3)+1
            self.assertEqual(font_text(s, "AI a").width, 4 + 2 + 2 + 4)
            self.assertNotIn("error", messages("f"))

    def test_glyph_problems_are_errors(self):
        glyphs, problems = parse_glyphs("= A\n###\n#\n= BB\n#\n= W\n####\n####\n", 3, 2)
        self.assertEqual(set(glyphs), {"A", "W"})
        self.assertEqual(len(problems), 3)                             # ragged A, "BB", W too wide
        with TempProject() as p:
            self.font(p, glyphs="= A\n#\n")
            self.assertIn("[error] f/glyphs", messages("f"))


class ScaffoldTest(unittest.TestCase):
    def run_cli(self, *argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            main(["--root", str(model.root()), *argv])
        return buf.getvalue()

    def test_new_kinds(self):
        with TempProject() as p:
            (p.root / "pixelforge.json").write_text(json.dumps({"name": "g", "view": "topdown"}))
            (p.root / "palettes").mkdir()
            shutil.copyfile(model.ASSETS / "game.json", p.root / "palettes" / "game.json")
            model.set_root(p.root)
            self.run_cli("new", "hero")
            self.assertEqual(Sprite.load("hero").size_class, "topdown")   # the view picks the class
            self.run_cli("new", "crate", "--prop", "--size", "16x16")
            crate = Sprite.load("crate")
            self.assertEqual((crate.kind, crate.footprint), ("prop", (4, 12, 8, 4)))
            self.run_cli("new", "inn", "--building")
            inn = Sprite.load("inn")
            self.assertEqual((inn.width, inn.height, inn.slice, inn.footprint), (64, 80, (16, 16), (0, 16, 64, 64)))
            self.assertEqual(inn.part_ids(), ["door", "window"])
            self.run_cli("new", "items", "--icons")
            self.assertEqual(Sprite.load("items").kind, "icons")
            self.run_cli("new", "hud", "--font")
            hud = Sprite.load("hud")
            self.assertGreaterEqual(len(hud.tile_names()), 50)
            self.assertNotIn("[error]", messages("hud"))

    def test_view_and_resolution_settings(self):
        with TempProject() as p:
            init_project(p.root / "game", "g", view="overhead", resolution=(480, 270))
            cfg = json.loads((p.root / "game" / "pixelforge.json").read_text())
            self.assertEqual((cfg["view"], cfg["resolution"]), ("overhead", [480, 270]))
            model.set_root(p.root / "game")
            self.assertEqual((model.game_view(), model.game_resolution()), ("overhead", (480, 270)))
            old = p.root / "old"
            old.mkdir()
            (old / "pixelforge.json").write_text(json.dumps({"name": "old", "pixelforge": {"guide": None}}))
            report, _ = upgrade_project(old)
            self.assertTrue(any('"view"' in c for c in report.changes))
            cfg = json.loads((old / "pixelforge.json").read_text())
            self.assertEqual((cfg["view"], cfg["resolution"]), ("side", [320, 180]))

    def test_oversized_prop_warns(self):
        with TempProject() as p:
            (p.root / "pixelforge.json").write_text(json.dumps({"name": "g", "resolution": [6, 6]}))
            model.set_root(p.root)
            write(p, "big", {"type": "prop", "size": [8, 8], "palette": PAL, "animations": {"a": {"frames": ["f"]}}},
                  frames={"f": "kkkkkkkk\n" * 8})
            self.assertIn("bigger than the game's 6x6 screen", messages("big"))


if __name__ == "__main__":
    unittest.main()
