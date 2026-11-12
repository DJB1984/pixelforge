import http.server
import json
import threading
import unittest
import urllib.request

from pixelforge import critiques as cq
from pixelforge import server
from pixelforge.__main__ import main
from pixelforge.level import Level
from pixelforge.model import SpriteError
from pixelforge.screens import _bands, _labelled, centred, check_hud, compose, hud_image, render_screen, screen_positions

from test_level import LevelProject


def ui(p, hud):
    """An icon sheet `ui` (one 4x4 icon, "dot") and a font `font`, plus pixelforge.json "hud"."""
    d = p.root / "sprites" / "ui"
    (d / "frames").mkdir(parents=True)
    (d / "frames" / "dot.txt").write_text("rrrr\n" * 4)
    (d / "sprite.json").write_text(json.dumps({"type": "icons", "size": [4, 4], "palette": {"r": "#ff0000"},
                                               "icons": ["dot"]}))
    f = p.root / "sprites" / "font"
    f.mkdir(parents=True)
    (f / "glyphs.txt").write_text("= A\nw.w\nwww\nw.w\n")
    (f / "sprite.json").write_text(json.dumps({"type": "font", "size": [3, 3], "palette": {"w": "#ffffff"}}))
    cfg = json.loads((p.root / "pixelforge.json").read_text())
    (p.root / "pixelforge.json").write_text(json.dumps({**cfg, "hud": hud}))


class ScreensTest(unittest.TestCase):
    def test_screen_positions(self):
        with LevelProject() as p:   # screens are 16x8 (the resolution), tiles 4x4
            p.level("wide", layers=[{"name": "g", "rows": ["g" * 10] * 2}], objects={"rows": ["@" + "." * 9, "." * 10]})
            lv = Level.load("wide")   # 40x8: three screens across, the last pulled back to the edge
            self.assertEqual(screen_positions(lv), [(0, 0), (16, 0), (24, 0)])
            self.assertEqual(centred(lv, 9, 1), (24, 0))
            # 3 rows = 12px tall, more than a screen and a quarter: two rows of screens
            p.level("tall", layers=[{"name": "g", "rows": ["gggg"] * 3}], objects={"rows": ["@...", "....", "...."]})
            self.assertEqual(screen_positions(Level.load("tall")), [(0, 0), (0, 4)])
            # a level barely taller than a screen gets one row, where the camera sits with the spawn centred
            p.level("short", layers=[{"name": "g", "rows": ["gggg"] * 9}], objects={"rows": ["...."] * 8 + ["@..."]},
                    camera={"zoom": 0.25})   # screens 64x32 over a 16x36 level
            self.assertEqual(screen_positions(Level.load("short")), [(0, 4)])

    def test_compose_and_render_a_screen(self):
        with LevelProject() as p:
            p.level("a", background={"color": "#112233"}, layers=[{"name": "g", "rows": ["g...", "g..."]}],
                    objects={"legend": {"r": {"prop": "rock"}}, "rows": ["@...", "..r."]})
            lv = Level.load("a")
            comp = compose(lv)
            world = comp.world()
            self.assertEqual(world.size, (16, 8))
            self.assertEqual(world.getpixel((0, 0))[:3], (0, 255, 0))       # ground tile
            self.assertEqual(world.getpixel((15, 0))[:3], (0x11, 0x22, 0x33))  # background
            self.assertEqual(world.getpixel((10, 7))[:3], (0, 0, 0))         # the rock, standing on row 1
            self.assertEqual(comp.world(sky=False).getpixel((15, 0))[3], 0)  # without the sky: transparent
            shot = render_screen(comp, (0, 0), None)
            self.assertEqual(shot.size, (16, 8))
            self.assertGreater(_labelled(world, 2, lv, True, True).width, world.width)

    def test_long_levels_are_cut_into_bands(self):
        with LevelProject() as p:
            p.level("long", layers=[{"name": "g", "rows": ["g" * 40]}], objects={"rows": ["@" + "." * 39]})
            lv = Level.load("long")   # 160px wide; at 2x in a 100px budget: strips of 48px (3 screens of 16)
            bands = _bands(_labelled(compose(lv).world(), 2, lv, True, False), 2, lv, 100)
            self.assertEqual([x for x, _ in bands], [0, 48, 96, 144])
            self.assertEqual([b.width for _, b in bands], [96, 96, 96, 32])

    def test_hud(self):
        with LevelProject() as p:
            ui(p, [{"icon": "ui:dot", "at": [1, 1], "repeat": 2, "step": 6}, {"text": "font:A", "at": [0, 6], "tint": "#00ff00"}])
            img = hud_image(16, 8)
            self.assertEqual([img.getpixel((x, 1))[:3] for x in (1, 7)], [(255, 0, 0)] * 2)
            self.assertEqual(img.getpixel((12, 1))[3], 0)       # only two of them
            self.assertEqual(img.getpixel((0, 6))[:3], (0, 255, 0))   # tinted text
            self.assertEqual(check_hud(), [])
            ui_bad = [{"icon": "ui:nope"}, {"text": "A"}, {"panel": "ui:dot", "size": [8, 8]}, {"at": [0, 0]}, {"text": "ui:A"}]
            cfg = json.loads((p.root / "pixelforge.json").read_text())
            (p.root / "pixelforge.json").write_text(json.dumps({**cfg, "hud": ui_bad}))
            got = "\n".join(check_hud())
            for want in ("has no icon 'nope'", "must be \"sheet:TEXT\"", "no \"nine\" insets", "needs \"icon\"", "not a font"):
                self.assertIn(want, got)

    def test_level_command_writes_previews(self):
        with LevelProject() as p:
            p.level("a", layers=[{"name": "g", "rows": ["g" * 8] * 2}], objects={"rows": ["@" + "." * 7, "." * 8]})
            for argv, out in ((["level", "a"], "level_a.png"), (["level", "a", "--screens"], "level_a_screens.png"),
                              (["level", "a", "--at", "6,1"], "level_a_at_6_1.png")):
                main(argv)
                self.assertTrue((p.root / "previews" / out).is_file(), out)

    def test_level_critiques(self):
        with LevelProject() as p:
            p.level("a", layers=[{"name": "g", "rows": ["gggg", "g###"]}],
                    objects={"legend": {"r": {"prop": "rock"}}, "rows": ["@.r.", "...."]})
            t = cq.clean_target({"asset": "a", "level": True, "region": [6, 2, 100, 100]})
            self.assertEqual(t, {"asset": "a", "level": True, "region": [6, 2, 10, 6]})   # clamped to 16x8
            self.assertEqual(cq.label(t), "a > level > spot (6,2 10x6)")
            text = "\n".join(cq.details(t))
            self.assertIn("rows 0-1, columns 1-3", text)
            self.assertIn("layer g: grass, wall", text)
            self.assertIn("rock", text)
            with self.assertRaises(SpriteError):
                cq.clean_target({"asset": "nope", "level": True})
            c = cq.add(t, "too dark")
            self.assertTrue(cq.render_target(c).is_file())
            self.assertTrue(cq.render_target(cq.add({"asset": "a", "level": True}, "whole")).is_file())


class LevelServerTest(unittest.TestCase):
    def test_levels_and_game_formats(self):
        with LevelProject() as p:
            ui(p, [{"icon": "ui:dot", "at": [0, 0]}])
            p.level("a", layers=[{"name": "g", "rows": ["gggg", "gggg"]}], objects={"rows": ["@...", "...."]})
            httpd = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), lambda *a, **kw: server.Handler(*a, directory=str(p.root), **kw))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"

            def call(path):
                with urllib.request.urlopen(base + path) as r:
                    body = r.read()
                    return json.loads(body) if r.headers.get_content_type() == "application/json" else body
            try:
                assets = {a["name"]: a for a in call("/api/project")["assets"]}
                a = assets["a"]
                self.assertEqual((a["type"], a["w"], a["h"], a["screen"], a["screens"]), ("level", 16, 8, [16, 8], [[0, 0]]))
                self.assertEqual([o["type"] for o in a["objects"]], ["spawn"])
                self.assertTrue(call(a["sheet"]).startswith(b"\x89PNG"))
                self.assertEqual(call("/live/index.json")["hud"], [{"icon": "ui:dot", "at": [0, 0]}])
                # the game loads icons as an atlas and fonts as BMFont XML; the dashboard still gets its grid
                self.assertIn("dot", call("/live/ui.json")["frames"])
                self.assertIn(b"<font>", call("/live/font.xml"))
                self.assertEqual(assets["ui"]["tiles"][0]["name"], "dot")
                rev = call("/api/state")["rev"]
                p.level("a", layers=[{"name": "g", "rows": ["gggg", "ggg."]}], objects={"rows": ["@...", "...."]})
                self.assertNotEqual(call("/api/state")["rev"], rev)   # editing a level is a change too
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
