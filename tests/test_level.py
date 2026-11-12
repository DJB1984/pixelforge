import json
import unittest

from pixelforge.level import Level, export_level, level_data, new_level, pick_edge
from pixelforge.validate import check_level

from helpers import TempProject

T = ("g" * 4 + "\n") * 4          # a 4x4 tile, all one color
TILESET = {
    "type": "tileset", "size": [4, 4], "palette": {"g": "#00ff00", "w": "#0000ff", "k": "#000000"},
    "tiles": ["grass", "water", "water_n", "water_s", "water_ne", "wall"],
    "autotile": {"water": {"base": "water", "edges": {"n": "water_n", "s": "water_s", "ne": "water_ne"}}},
    "properties": {"water*": {"collides": True}, "wall": {"collides": True}},
    "sample": {"legend": {"g": "grass", "#": "wall"}, "rows": ["g#"]},
    "stamps": {"block": {"rows": ["##", "##"]}},
}


class LevelProject(TempProject):
    def __enter__(self):
        super().__enter__()
        (self.root / "pixelforge.json").write_text(json.dumps({"view": "topdown", "resolution": [16, 8]}))
        d = self.root / "sprites" / "ground"
        (d / "frames").mkdir(parents=True)
        for t in TILESET["tiles"]:
            (d / "frames" / f"{t}.txt").write_text(T)
        (d / "sprite.json").write_text(json.dumps(TILESET))
        # a solid 8x8 prop standing on its bottom 4 rows
        p = self.root / "sprites" / "rock"
        (p / "frames").mkdir(parents=True)
        (p / "frames" / "a.txt").write_text(("kkkkkkkk\n") * 8)
        (p / "sprite.json").write_text(json.dumps({"type": "prop", "size": [8, 8], "origin": [4, 8],
                                                   "footprint": [0, 4, 8, 4], "palette": {"k": "#000000"},
                                                   "animations": {"idle": {"frames": ["a"]}}}))
        return self

    def level(self, name, **kw):
        (self.root / "levels").mkdir(exist_ok=True)
        data = {"tileset": "ground", **kw}
        (self.root / "levels" / f"{name}.json").write_text(json.dumps(data))


def messages(name):
    return [(i.level, i.message) for i in check_level(name)]


class LevelTest(unittest.TestCase):
    def test_legend_autotile_stamps_and_objects(self):
        with LevelProject() as p:
            p.level("a", legend={"~": "auto:water"},
                    layers=[{"name": "ground", "rows": ["gggg", "g~~g", "g~~g", "gggg"]}],
                    stamps=[{"stamp": "block", "at": [3, 3]}],
                    objects={"legend": {"r": {"prop": "rock"}, "D": {"type": "door", "to": "a", "size": [2, 1]}},
                             "rows": ["@...", "...r", "....", "D..."]})
            lv = Level.load("a")
            names = [[lv.tile_name(c) for c in row] for row in lv.layers[0].cells]
            # top-left water: open to the north and west -> "n" (no "nw" tile); top-right: "ne"
            self.assertEqual(names[1][1:3], ["water_n", "water_ne"])
            self.assertEqual(names[2][1:3], ["water_s", "water_s"])
            self.assertEqual(names[3][3], "wall")                  # the stamp, clipped at the edge
            self.assertTrue(any("fall outside" in m for _, _, m in lv.problems))
            objs = {o.name: o for o in lv.objects}
            self.assertEqual((objs["player"].type, objs["player"].x, objs["player"].y), ("spawn", 2, 4))
            self.assertEqual((objs["rock"].x, objs["rock"].y, objs["rock"].footprint), (14, 8, (10, 4, 8, 4)))
            self.assertEqual(objs["door"].rect, (0, 12, 8, 4))
            self.assertEqual(lv.screen_size(), (16, 8))

    def test_pick_edge_prefers_the_most_specific(self):
        at = {"base": "b", "edges": {"n": "N", "e": "E", "ne": "NE"}}
        self.assertEqual([pick_edge(at, e) for e in ("", "n", "ne", "nse", "w", "nw")], ["b", "N", "NE", "NE", "b", "N"])

    def test_check_reports_level_errors(self):
        with LevelProject() as p:
            p.level("bad", layers=[{"name": "g", "rows": ["gx", "g"]}, {"name": "h", "rows": ["g"]}],
                    objects={"legend": {"D": {"type": "door", "to": "nowhere"}, "z": {"prop": "nothing"}},
                             "rows": ["Dz"]})
            got = messages("bad")
            text = "\n".join(m for _, m in got)
            self.assertIn("'x' at column 1, row 0 is not in the legend", text)
            self.assertIn("every layer must be 2x2", text)
            self.assertIn("door to 'nowhere': no such level", text)
            self.assertIn("no prop 'nothing'", text)
            self.assertIn("no spawn", text)
            self.assertTrue(all(lvl == "error" for lvl, m in got if "legend" in m or "spawn" in m))

    def test_spawn_on_a_wall_or_in_a_footprint(self):
        with LevelProject() as p:
            p.level("wall", layers=[{"rows": ["#g"]}], objects={"rows": ["@."]})
            self.assertIn("spawn is on a colliding tile (wall)", "\n".join(m for _, m in messages("wall")))
            p.level("rock", layers=[{"rows": ["gg"]}],
                    objects={"legend": {"r": {"prop": "rock"}}, "list": [{"type": "spawn", "name": "player", "at": [4, 4]}],
                             "rows": ["r."]})
            self.assertIn("inside 'rock'", "\n".join(m for _, m in messages("rock")))

    def test_reachability_and_overlaps(self):
        with LevelProject() as p:
            p.level("walled", layers=[{"rows": ["g#g", "g#g"]}],
                    objects={"legend": {"c": {"type": "item", "name": "key"}},
                             "rows": ["@.c", "..."], "list": [{"prop": "rock", "at": [4, 8]}, {"prop": "rock", "at": [6, 8]}]})
            text = "\n".join(m for _, m in messages("walled"))
            self.assertIn("can't walk from the spawn to: 'key' (item", text)
            self.assertIn("overlap", text)
            p.level("side", view="side", layers=[{"rows": ["gg"]}], objects={"rows": ["@."]})
            self.assertEqual([lvl for lvl, _ in messages("side")], ["info"], messages("side"))

    def test_export_is_a_tiled_map(self):
        with LevelProject() as p:
            p.level("a", layers=[{"name": "ground", "rows": ["g#"]}, {"name": "roof", "rows": [".g"], "above": True}],
                    objects={"rows": ["@."]}, camera={"zoom": 2}, background={"color": "#123456"})
            lv = Level.load("a")
            d = level_data(lv)
            self.assertEqual(d["tilesets"][0]["firstgid"], 1)
            self.assertEqual(d["tilesets"][0]["image"], "../ground.png")
            self.assertEqual(d["layers"][0]["data"], [1, 6])
            self.assertEqual(d["layers"][1]["properties"], [{"name": "above", "type": "bool", "value": True}])
            objs = d["layers"][2]["objects"]
            self.assertEqual((objs[0]["type"], objs[0]["x"], objs[0]["y"], objs[0]["point"]), ("spawn", 2, 4, True))
            self.assertEqual(d["pixelforge"]["camera"], {"zoom": 2})
            self.assertEqual(d["pixelforge"]["screen"], [8, 4])
            path = export_level(lv)
            self.assertTrue(path.is_file() and path.parent.name == "levels")

    def test_new_level_scaffold_passes_check(self):
        with LevelProject() as p:
            path = new_level("start")
            self.assertTrue(path.is_file())
            lv = Level.load("start")
            self.assertEqual((lv.width, lv.height), (4, 4))       # one 16x8 screen, at least 4 tiles each way
            self.assertEqual([i for i in check_level("start") if i.level == "error"], [])
            with self.assertRaises(Exception):
                new_level("start")


if __name__ == "__main__":
    unittest.main()
