import contextlib
import io
import json
import unittest

from pixelforge.boxes import cover, frame_boxes
from pixelforge.export import build_sheet
from pixelforge.model import Sprite
from pixelforge.__main__ import main

from helpers import TempProject

BODY = "........\n...kk...\n...kk...\n...kk...\n"
BLADE = "........\n.....xxx\n........\n........\n"
TAIL = "x.......\n........\n........\n........\n"


class BoxesTest(unittest.TestCase):
    def make(self, p, **extra):
        p.sprite("t", (8, 4), {"k": "#000000", "x": "#ffffff"}, {"body": BODY, "blade": BLADE, "tail": TAIL},
                 {"attack": {"fps": 10, "loop": False, "frames": [
                     {"layers": ["body", "blade"]},
                     {"layers": ["body", "blade", "tail"], "active": True},
                     {"from": {"layers": ["body", "blade"], "active": True}, "flip": "h", "active": True},
                 ]}})
        meta_path = p.root / "sprites/t/sprite.json"
        meta = json.loads(meta_path.read_text())
        meta.update({"roles": {"blade": "hit", "tail": "none"}}, **extra)
        meta_path.write_text(json.dumps(meta))
        return Sprite.load("t")

    def test_roles_active_and_flip(self):
        with TempProject() as p:
            s = self.make(p)
            f = s.anim("attack").frames
            self.assertEqual(frame_boxes(s, f[0], s.anim("attack").active(0)), {"hurt": [[3, 1, 2, 3]], "hit": []})
            b1 = frame_boxes(s, f[1], True)
            self.assertEqual(b1["hit"], [[5, 1, 3, 1]])          # tail has role none: no box
            self.assertEqual(b1["hurt"], [[3, 1, 2, 3]])
            self.assertEqual(frame_boxes(s, f[2], True)["hit"], [[0, 1, 3, 1]])   # mirrored with the art

    def test_pads_and_export(self):
        with TempProject() as p:
            s = self.make(p, hit_pad=1, hurt_pad=-1)
            _, data = build_sheet(s)
            frames = list(data["frames"].values())
            self.assertEqual(frames[1]["pixelforge"], {"hurt": [[4, 2, 1, 1]], "hit": [[4, 0, 5, 3]]})
            self.assertEqual(frames[0]["pixelforge"]["hit"], [])

    def test_cover_splits_diagonals(self):
        diag = [(i, i) for i in range(24)]
        rects = cover(diag)
        self.assertGreater(len(rects), 1)
        self.assertLess(sum((r[2] - r[0] + 1) * (r[3] - r[1] + 1) for r in rects), 24 * 24 / 2)
        for x, y in diag:
            self.assertTrue(any(r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in rects))

    def test_class_and_resize(self):
        with TempProject() as p:
            p.sprite("k", (4, 4), {"k": "#000000"}, {"a": "....\n.kk.\n.kk.\n.kk.\n"},
                     {"idle": {"frames": ["a"]}})
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--root", str(p.root), "resize", "k", "--class", "humanoid"])
            s = Sprite.load("k")
            self.assertEqual((s.width, s.height, s.origin, s.body), (64, 48, (32, 48), (16, 30)))
            self.assertEqual(s.body_rect(), (24, 18, 16, 30))
            g = s.anim_frames("idle")[0]
            self.assertEqual(g.bbox(), (31, 45, 32, 47))       # still standing on the origin


if __name__ == "__main__":
    unittest.main()
