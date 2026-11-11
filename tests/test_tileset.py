import json
import unittest

from PIL import Image

from pixelforge.export import export_sprite, write_index
from pixelforge.model import Sprite, SpriteError, list_sprites
from pixelforge.render import tileset_preview
from pixelforge.validate import check_sprite

from helpers import TempProject

GRASS = "gggg\ngGgg\ngggg\nggGg\n"
DIRT = "tttt\ntttt\ntntt\ntttt\n"
EDGE = "gggg\nbbbb\n....\n....\n"
STRIPE = "kkkk\nwwww\nwwww\nwwww\n"   # dark top row: a line shows every time it repeats vertically


def tileset(p, tiles, **extra):
    d = p.root / "sprites" / "terrain"
    (d / "frames").mkdir(parents=True)
    for fid, text in {"grass": GRASS, "dirt": DIRT, "edge": EDGE, "stripe": STRIPE}.items():
        (d / "frames" / f"{fid}.txt").write_text(text)
    meta = {"name": "terrain", "type": "tileset", "size": [4, 4], "columns": 2,
            "palette": {"g": "#63c74d", "G": "#3e8948", "t": "#e4a672", "n": "#b86f50", "b": "#733e39",
                        "k": "#181425", "w": "#ffffff"},
            "tiles": tiles, **extra}
    (d / "sprite.json").write_text(json.dumps(meta))
    return d


class TilesetTest(unittest.TestCase):
    def test_indices_names_and_properties(self):
        with TempProject() as p:
            tileset(p, ["grass", "dirt", {"name": "dirt_n", "from": "dirt", "layers": ["edge"]}],
                    properties={"dirt*": {"slow": 0.5}, "dirt_n": {"collides": True}})
            s = Sprite.load("terrain")
            self.assertEqual(s.kind, "tileset")
            self.assertEqual(s.tile_names(), ["grass", "dirt", "dirt_n"])
            self.assertEqual(s.tile_index("dirt_n"), 2)
            self.assertEqual(s.tile_properties("dirt_n"), {"slow": 0.5, "collides": True})
            self.assertEqual(s.tile_properties("grass"), {})
            self.assertEqual(s.tile("dirt_n").cells[1], list("bbbb"))  # edge layered over dirt
            with self.assertRaises(SpriteError):
                s.tile_index("lava")

    def test_export_grid_and_tiled_json(self):
        with TempProject() as p:
            tileset(p, ["grass", "dirt", {"name": "dirt_n", "from": "dirt", "layers": ["edge"]}],
                    properties={"dirt_n": {"collides": True}},
                    sample={"legend": {"g": "grass", "n": "dirt_n"}, "rows": ["gn", "n "]})
            png, js = export_sprite(Sprite.load("terrain"), p.root / "export")
            data = json.loads(js.read_text())
            # 3 tiles, 2 columns, 1px spacing: 9x9 image, tile 2 at column 0 of row 1
            img = Image.open(png)
            self.assertEqual(img.size, (9, 9))
            self.assertEqual(img.getpixel((0, 5 + 1)), (0x73, 0x3e, 0x39, 255))   # tile 2 row 1 = edge shadow
            self.assertEqual(img.getpixel((4, 0)), (0, 0, 0, 0))                   # spacing column
            for k, v in {"type": "tileset", "tilewidth": 4, "tileheight": 4, "margin": 0, "spacing": 1,
                         "columns": 2, "tilecount": 3, "imagewidth": 9, "imageheight": 9,
                         "image": "terrain.png"}.items():
                self.assertEqual(data[k], v, k)
            self.assertEqual(data["tiles"][2]["properties"],
                             [{"name": "name", "type": "string", "value": "dirt_n"},
                              {"name": "collides", "type": "bool", "value": True}])
            self.assertEqual(data["pixelforge"]["names"], ["grass", "dirt", "dirt_n"])
            self.assertEqual(data["pixelforge"]["sample"], [[0, 2], [2, -1]])

    def test_index_lists_sprites_and_tilesets_apart(self):
        with TempProject() as p:
            tileset(p, ["grass"])
            p.sprite("hero", (4, 4), {"k": "#000000"}, {"a": "....\n.kk.\n.kk.\n.kk.\n"},
                     {"idle": {"frames": ["a"]}})
            self.assertEqual(list_sprites("tileset"), ["terrain"])
            self.assertEqual(list_sprites("sprite"), ["hero"])
            for n in ("terrain", "hero"):
                export_sprite(Sprite.load(n), p.root / "export")
            idx = json.loads(write_index(p.root / "export").read_text())
            self.assertEqual(idx, {"sprites": ["hero"], "props": [], "tilesets": ["terrain"], "icons": [], "fonts": [], "levels": []})

    def test_check(self):
        with TempProject() as p:
            tileset(p, ["grass", "grass", "stripe", "edge", {"name": "bad", "from": "nope"}],
                    properties={"lava*": {"collides": True}},
                    sample={"legend": {"g": "grass", "x": "lava"}, "rows": ["gg", "gq?"]})
            issues = check_sprite("terrain")
            text = "\n".join(map(str, issues))
            self.assertIn("duplicate tile name", text)
            self.assertIn("'stripe': visible seam when repeated top-bottom", text)
            self.assertNotIn("'grass': visible seam", text)
            self.assertIn("'edge': 8 transparent pixels", text)
            self.assertIn("frame file not found", text)
            self.assertIn("pattern 'lava*' matches no tiles", text)
            self.assertIn("legend 'x' -> 'lava': no such tile", text)
            self.assertIn("characters not in the legend: ? q", text)
            self.assertIn("rows have different lengths", text)
            self.assertNotIn("no animations", text)

    def test_animated_tiles(self):
        with TempProject() as p:
            tileset(p, ["grass",
                        {"name": "water", "fps": 4, "frames": ["dirt", {"from": "dirt", "roll": [1, 0]},
                                                               {"from": "dirt", "duration": 100}]},
                        {"name": "shore", "frames": "water", "layers": ["edge"]},
                        "stripe"])
            s = Sprite.load("terrain")
            self.assertEqual([ms for _, ms in s.tile_frames("water")], [250, 250, 100])
            self.assertEqual(s.tile("water", 0).cells[2], list("tntt"))
            self.assertEqual(s.tile("water", 250).cells[2], list("ttnt"))          # rolled right, wrapping
            self.assertEqual(s.tile("water", 600 + 250).cells[2], list("ttnt"))    # loops every 600ms
            self.assertEqual(s.tile("shore", 250).cells[1], list("bbbb"))          # edge layered on every frame
            self.assertEqual(s.tile("shore", 250).cells[2], list("ttnt"))          # ...in step with water

            png, js = export_sprite(s, p.root / "export")
            data = json.loads(js.read_text())
            # named tiles keep 0..3; the extra frames fill slots 4.. after them
            self.assertEqual(data["tilecount"], 4 + 2 + 2)
            self.assertEqual(data["pixelforge"]["names"], ["grass", "water", "shore", "stripe"])
            self.assertEqual(data["pixelforge"]["animations"], {"1": [[1, 250], [4, 250], [5, 100]],
                                                                "2": [[2, 250], [6, 250], [7, 100]]})
            self.assertEqual(data["tiles"][1]["animation"], [{"tileid": 1, "duration": 250},
                                                             {"tileid": 4, "duration": 250},
                                                             {"tileid": 5, "duration": 100}])
            self.assertNotIn("animation", data["tiles"][0])
            img = Image.open(png)
            # 2 columns: slot 4 (water frame 1, dirt rolled right) is column 0, row 2; its row 2 = "ttnt"
            self.assertEqual(img.getpixel((2, 2 * 5 + 2)), (0xb8, 0x6f, 0x50, 255))
            self.assertEqual(img.size, (9, 19))
            from pixelforge.render import tile_timeline
            self.assertEqual(tile_timeline(s, ["water", "shore"]), [(0, 250), (250, 250), (500, 100)])

    def test_animated_tile_errors(self):
        with TempProject() as p:
            tileset(p, [{"name": "shore", "frames": "water"}])
            with self.assertRaisesRegex(SpriteError, "animated tile listed before it"):
                Sprite.load("terrain")
        with TempProject() as p:
            tileset(p, [{"name": "w", "from": "dirt", "frames": ["dirt"]}])
            with self.assertRaisesRegex(SpriteError, "not both"):
                Sprite.load("terrain")
        with TempProject() as p:
            tileset(p, [{"name": "one", "frames": ["dirt"]}, {"name": "same", "frames": ["dirt", "dirt"]}])
            text = "\n".join(map(str, check_sprite("terrain")))
            self.assertIn("single frame, so it never animates", text)
            self.assertIn("'same' frame 1: same as frame 0", text)

    def test_preview_renders(self):
        with TempProject() as p:
            tileset(p, ["grass", "dirt"], sample={"legend": {"g": "grass", "d": "dirt"}, "rows": ["gd", "dg"]})
            img = tileset_preview(Sprite.load("terrain"), scale=2)
            self.assertGreater(img.width, 100)


if __name__ == "__main__":
    unittest.main()
