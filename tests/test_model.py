import unittest

from pixelforge.model import Sprite, SpriteError
from pixelforge.validate import check_sprite

from helpers import TempProject

F0 = "....\n.kk.\n.kk.\n.kk.\n"
F1 = "....\n.kk.\n.kk.\n....\n"


class ModelTest(unittest.TestCase):
    def test_resolve_entries(self):
        with TempProject() as p:
            p.sprite("t", (4, 4), {"k": "#000000", "r": "#ff0000"}, {"a": F0, "hat": "rr..\n....\n....\n....\n"},
                     {"idle": {"fps": 5, "frames": [
                         "a",
                         {"from": "a", "offset": [1, 0]},
                         {"from": "a", "layers": ["hat"], "flip": "h", "duration": 300},
                         {"from": "a", "replace": {"k": "r"}},
                     ]}})
            s = Sprite.load("t")
            f = s.anim_frames("idle")
            self.assertEqual(f[1].to_text(), "....\n..kk\n..kk\n..kk\n")
            self.assertEqual(f[2].to_text(), "..rr\n.kk.\n.kk.\n.kk.\n")
            self.assertEqual(f[3].keys(), {"r"})
            self.assertEqual(s.anim("idle").duration_ms(0), 200)
            self.assertEqual(s.anim("idle").duration_ms(2), 300)
            self.assertEqual(s.origin, (2, 4))

    def test_named_colors_and_errors(self):
        with TempProject() as p:
            (p.root / "palettes").mkdir()
            (p.root / "palettes" / "game.json").write_text('{"colors": {"ink": "#101010"}}')
            p.sprite("t", (4, 4), {"k": "ink"}, {"a": F0}, {"idle": {"frames": ["a"]}})
            self.assertEqual(Sprite.load("t").palette["k"], (16, 16, 16, 255))
            p.sprite("bad", (4, 4), {"k": "nope"}, {"a": F0}, {"idle": {"frames": ["a"]}})
            with self.assertRaisesRegex(SpriteError, "not a hex color"):
                Sprite.load("bad")
            with self.assertRaisesRegex(SpriteError, "no animation 'run'"):
                Sprite.load("t").anim("run")

    def test_validate(self):
        with TempProject() as p:
            p.sprite("t", (4, 4), {"k": "#000000"},
                     {"a": F0, "b": F1, "broken": "...\nxk..\n....\n....\n", "dot": "k...\n....\n..kk\n..kk\n"},
                     {"idle": {"frames": ["a", "b", "missing"]}, "dot": {"frames": ["dot"]}})
            joined = "\n".join(str(i) for i in check_sprite("t"))
            self.assertIn("row 0 has 3 chars", joined)
            self.assertIn("undefined palette keys ['x']", joined)
            self.assertIn("frame file not found", joined)
            self.assertIn("t:dot[0]: floating pixels (no opaque neighbours) at (0,0)", joined)
            self.assertIn("lowest opaque row varies", joined)
            self.assertIn("broken.txt: not used by any animation", joined)


if __name__ == "__main__":
    unittest.main()
