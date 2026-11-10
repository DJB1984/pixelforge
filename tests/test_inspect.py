import json
import shutil
import subprocess
import unittest

from PIL import Image

from pixelforge import compare as cmp
from pixelforge import context as cx
from pixelforge import motion
from pixelforge.model import Sprite, SpriteError

from helpers import TempProject

# 6x6 "character": body (hurt) layer + a sword (hit) layer that sticks out to the right
BODY = "......\n..kk..\n..kk..\n..kk..\n..kk..\n..kk..\n"
BOB = "......\n......\n..kk..\n..kk..\n..kk..\n..kk..\n"
SWORD = "......\n......\n....ww\n......\n......\n......\n"
FAR = "......\n.....w\n......\n......\n......\n......\n"


def hero(p, animations, frames=None):
    p.sprite("hero", (6, 6), {"k": "#181425", "w": "#ffffff"},
             frames or {"body": BODY, "bob": BOB, "sword": SWORD, "far": FAR}, animations)
    meta = p.root / "sprites/hero/sprite.json"
    m = json.loads(meta.read_text())
    m["roles"] = {"sword": "hit", "far": "hit"}
    m["body"] = [2, 5]
    meta.write_text(json.dumps(m))


class MotionTest(unittest.TestCase):
    def test_measure(self):
        with TempProject() as p:
            hero(p, {"idle": {"fps": 4, "frames": ["body", {"from": "body", "layers": ["sword"], "active": True}]}})
            fm = motion.measure(Sprite.load("hero"), "idle")
            self.assertEqual((fm[0].head, fm[0].feet, fm[0].cx, fm[0].cy), (1, 5, 3.0, 3.5))
            self.assertIsNone(fm[0].tip)
            self.assertEqual(fm[1].tip, (5, 2))          # sword pixels don't count as body
            self.assertEqual(fm[1].head, 1)
            self.assertEqual((fm[1].start, fm[1].ms, fm[1].active), (250, 250, True))
            self.assertEqual(fm[1].changed, 2)

    def test_notes(self):
        with TempProject() as p:
            frames = {"body": BODY, "bob": BOB, "sword": SWORD, "far": FAR}
            hero(p, {"attack": {"fps": 10, "loop": False, "frames": [
                         "body", {"from": "body", "layers": ["sword"], "active": True, "duration": 300}]},
                     "idle": {"fps": 4, "loop": True, "frames": [
                         "body", "bob", "body", "bob", {"from": "body", "offset": [0, 4]}]}}, frames)  # 1px bob, then a 3px drop
            s = Sprite.load("hero")
            text = "\n".join(motion.notes(s, "attack", motion.measure(s, "attack")))
            self.assertIn("wind-up isn't held", text)
            self.assertIn("active frame 1 lasts 300ms, longer than the wind-up", text)
            self.assertIn("no recovery after the last active frame", text)
            idle = "\n".join(motion.notes(s, "idle", motion.measure(s, "idle")))
            self.assertIn("head: frame 3->4 moves 3px; a typical step is 1px", idle)
            self.assertIn("idle breathing usually reads best at 1px", idle)
            img = motion.chart(s, "attack", motion.measure(s, "attack"))
            self.assertGreater(img.width, 600)


class ContextTest(unittest.TestCase):
    def test_contrast(self):
        self.assertAlmostEqual(cx.contrast((0, 0, 0, 255), (255, 255, 255, 255)), 21.0, places=1)
        self.assertEqual(cx.contrast((99, 199, 77, 255), (99, 199, 77, 255)), 1.0)

    def test_blending_edges_are_found(self):
        with TempProject() as p:
            hero(p, {"idle": {"frames": ["body"]}})
            s = Sprite.load("hero")
            dark = cx.Ground("#181425", Image.new("RGBA", (6, 6), (0x18, 0x14, 0x25, 255)))
            light = cx.Ground("#ffffff", Image.new("RGBA", (6, 6), (255, 255, 255, 255)))
            self.assertEqual(len(cx.edge_contrast(s, s.frame("idle", 0), dark.patch).low), 10)  # outline = ground
            self.assertEqual(cx.edge_contrast(s, s.frame("idle", 0), light.patch).low, [])
            img, report = cx.context_sheet(s, [("idle[0]", s.frame("idle", 0))], [dark, light])
            self.assertIn("10 of 10 edge pixels (100%) blend in", report[0])
            self.assertIn("0 of 10", report[1])

    def test_ground_from_tileset(self):
        with TempProject() as p:
            d = p.root / "sprites/terrain"
            (d / "frames").mkdir(parents=True)
            (d / "frames/g.txt").write_text("gG\nGg\n")
            (d / "sprite.json").write_text(json.dumps({"type": "tileset", "size": [2, 2],
                                                      "palette": {"g": "#63c74d", "G": "#3e8948"}, "tiles": ["g"]}))
            gr = cx.ground("terrain", 5, 3)
            self.assertEqual((gr.label, gr.patch.size), ("terrain:g", (5, 3)))
            self.assertEqual(gr.patch.getpixel((2, 0)), (0x63, 0xc7, 0x4d, 255))   # tiled
            with self.assertRaises(SpriteError):
                cx.ground("terrain:nope", 5, 3)


@unittest.skipUnless(shutil.which("git"), "git not installed")
class CompareTest(unittest.TestCase):
    def git(self, p, *args):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=p.root,
                       check=True, capture_output=True)

    def test_against_head(self):
        with TempProject() as p:
            hero(p, {"idle": {"frames": ["body", "bob"]}})
            self.git(p, "init", "-q")
            self.git(p, "add", "-A")
            self.git(p, "commit", "-qm", "hero")
            (p.root / "sprites/hero/frames/bob.txt").write_text(BOB.replace("..kk..\n..kk..\n..kk..\n..kk..\n",
                                                                           "..kk..\n..kw..\n..kk..\n.kkk..\n"))
            s = Sprite.load("hero")
            with cmp.sprite_at("hero") as before:
                self.assertIsNotNone(before)
                lines, img = cmp.compare_all(before, s, 4, "HEAD")
            self.assertEqual(lines[0], "idle[1]: 2 px changed (+1 added, -0 removed, ~1 recolored) within x 1-3, y 3-5")
            self.assertEqual(lines[-1], "1 frame(s) unchanged")
            self.assertIsNotNone(img)
            with cmp.sprite_at("nobody") as missing:
                self.assertIsNone(missing)
            with self.assertRaisesRegex(SpriteError, "not a commit"):
                with cmp.sprite_at("hero", "nope"):
                    pass

    def test_align_on_origin(self):
        a = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
        b = Image.new("RGBA", (6, 4), (0, 0, 255, 255))
        before, after = cmp.align(a, (2, 4), b, (3, 4))   # b is a wider canvas, same feet point
        self.assertEqual(before.size, (6, 4))
        self.assertEqual(before.getpixel((0, 0))[3], 0)    # a sits 1px in from the left
        self.assertEqual(before.getpixel((1, 0)), (255, 0, 0, 255))


if __name__ == "__main__":
    unittest.main()
