import json
import unittest

from PIL import Image

from pixelforge.export import export_sprite
from pixelforge.importer import import_png
from pixelforge.model import Sprite

from helpers import TempProject

F0 = "....\n.kk.\n.rk.\n.kk.\n"
F1 = "....\n.kk.\n.kr.\n.kk.\n"


class ExportTest(unittest.TestCase):
    def test_aseprite_json_shape_and_roundtrip(self):
        with TempProject() as p:
            p.sprite("hero", (4, 4), {"k": "#000000", "r": "#ff0000"}, {"a": F0, "b": F1},
                     {"idle": {"fps": 4, "loop": True, "frames": ["a", "b"]},
                      "hit": {"fps": 10, "loop": False, "frames": [{"from": "a", "duration": 50}]}})
            png, js = export_sprite(Sprite.load("hero"), p.root / "export")
            data = json.loads(js.read_text())
            # What Phaser's createFromAseprite reads: frames keyed "0".."N", per-frame duration, meta.frameTags
            self.assertEqual(list(data["frames"]), ["0", "1", "2"])
            self.assertEqual([f["duration"] for f in data["frames"].values()], [250, 250, 50])
            self.assertEqual(data["meta"]["frameTags"][0], {"name": "hero_idle", "from": 0, "to": 1,
                                                            "direction": "forward", "color": "#000000ff"})
            self.assertEqual(data["frames"]["0"]["pivot"], {"x": 0.5, "y": 1.0})
            self.assertFalse(data["meta"]["pixelforge"]["animations"]["hero_hit"]["loop"])
            img = Image.open(png)
            self.assertEqual(img.size, (9, 9))  # 2 cols x 2 rows, 1px padding
            self.assertEqual(img.getpixel((1, 2)), (255, 0, 0, 255))

            back = import_png(png, "copy")
            orig = Sprite.load("hero")
            for anim in ("idle", "hit"):
                for g_o, g_b in zip(orig.anim_frames(anim), back.anim_frames(anim), strict=True):
                    self.assertEqual([[orig.color(c) for c in r] for r in g_o.cells],
                                     [[back.color(c) for c in r] for r in g_b.cells])
            self.assertFalse(back.anim("hit").loop)
            self.assertEqual(back.anim("idle").fps, 4)
            for anim in ("idle", "hit"):
                self.assertEqual([back.anim(anim).duration_ms(i) for i in range(len(back.anim(anim).frames))],
                                 [orig.anim(anim).duration_ms(i) for i in range(len(orig.anim(anim).frames))])


if __name__ == "__main__":
    unittest.main()
