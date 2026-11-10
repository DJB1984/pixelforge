import shutil
import subprocess
import unittest
from pathlib import Path

from pixelforge.model import Sprite
from pixelforge.validate import check_sprite

from helpers import TempProject

HERE = Path(__file__).resolve().parent


class PhaserHelperTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js not installed")
    def test_rotated_boxes_in_node(self):
        r = subprocess.run(["node", "--no-warnings", str(HERE / "phaser_helper.test.mjs")],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("FAIL", r.stdout)


class CenterAnchorTest(unittest.TestCase):
    def test_overhead_class(self):
        with TempProject() as p:
            p.sprite("oh", (64, 64), {"k": "#000000"}, {"a": ("." * 64 + "\n") * 30 + ("." * 30 + "kkkk" + "." * 30 + "\n") * 4
                                                         + ("." * 64 + "\n") * 30},
                     {"idle": {"frames": ["a"]}, "bob": {"frames": ["a", {"from": "a", "offset": [0, 3]}]}})
            meta = p.root / "sprites/oh/sprite.json"
            import json
            m = json.loads(meta.read_text())
            m.pop("size")
            m["class"] = "overhead"
            meta.write_text(json.dumps(m))
            s = Sprite.load("oh")
            self.assertEqual((s.anchor, s.origin), ("center", (32, 32)))
            self.assertEqual(s.body_rect(), (24, 24, 16, 16))          # centred on the origin
            issues = "\n".join(str(i) for i in check_sprite("oh"))
            self.assertNotIn("feet", issues)                            # no feet to plant from above
            self.assertNotIn("stands on the origin", issues)


if __name__ == "__main__":
    unittest.main()
