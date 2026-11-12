import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from pixelforge import model
from pixelforge.__main__ import main
from pixelforge.game import GITIGNORE, PHASER, VITE, files, scaffold_game
from pixelforge.model import ASSETS
from pixelforge.project import init_project

HELPER = (ASSETS / "phaser" / "pixelforge.js").read_text(encoding="utf-8")


def run(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        main([str(a) for a in argv])
    return out.getvalue()


class GameStarterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "quest"
        init_project(self.root, "Test Quest", "topdown")

    def tearDown(self):
        model.set_root(None)
        self._tmp.cleanup()

    def test_scaffold_writes_the_starter(self):
        report = scaffold_game(self.root)
        for rel in ("package.json", "vite.config.js", "index.html", "src/main.js", "src/game.js",
                    "src/scenes/Boot.js", "src/scenes/Level.js", "src/scenes/Hud.js", "src/objects/Walker.js"):
            self.assertTrue((self.root / rel).is_file(), rel)
        pkg = json.loads((self.root / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["name"], "test-quest")
        self.assertEqual(pkg["dependencies"], {"phaser": PHASER})
        self.assertEqual(pkg["devDependencies"], {"vite": VITE})
        self.assertRegex(VITE, r"^\d+\.\d+\.\d+$")   # pinned exactly, no ^ or ~
        self.assertLessEqual({"dev", "build"}, set(pkg["scripts"]))
        self.assertIn("<title>Test Quest</title>", (self.root / "index.html").read_text(encoding="utf-8"))
        self.assertIn("publicDir: 'export'", (self.root / "vite.config.js").read_text(encoding="utf-8"))
        ignored = (self.root / ".gitignore").read_text(encoding="utf-8").split()
        self.assertEqual([g for g in ["previews/", *GITIGNORE] if g not in ignored], [])
        self.assertTrue(any("no levels yet" in n for n in report.notes))

    def test_starter_imports_exist_in_the_helper(self):
        exported = set(re.findall(r"^export (?:function|const|class) (\w+)", HELPER, re.M))
        for rel, text in files("x").items():
            for names, src in re.findall(r"import \{([^}]*)\} from '([^']*pixelforge\.js)'", text):
                self.assertEqual(src, "../../export/pixelforge.js", rel)
                missing = {n.strip() for n in names.split(",") if n.strip()} - exported
                self.assertEqual(missing, set(), rel)

    def test_rerun_keeps_files_unless_forced(self):
        scaffold_game(self.root)
        main_js = self.root / "src" / "main.js"
        main_js.write_text("// mine\n", encoding="utf-8")
        report = scaffold_game(self.root)
        self.assertEqual(main_js.read_text(encoding="utf-8"), "// mine\n")
        self.assertTrue(all(c.startswith("=") for c in report.changes), report.changes)
        gi = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertEqual(gi.count("node_modules/"), 1)
        scaffold_game(self.root, force=True)
        self.assertIn("Phaser.Game", main_js.read_text(encoding="utf-8"))

    def test_needs_a_project(self):
        with self.assertRaises(FileNotFoundError):
            scaffold_game(Path(self._tmp.name) / "nowhere")

    def test_cli_and_new_level_player(self):
        run("--root", self.root, "new", "ant", "--class", "small")   # a side-view character
        run("--root", self.root, "new", "hero")                       # topdown, from the game's view
        run("--root", self.root, "new", "terrain", "--tileset")
        out = run("--root", self.root, "new-level", "start")
        self.assertIn("played as hero", out)
        level = json.loads((self.root / "levels" / "start.json").read_text(encoding="utf-8"))
        self.assertEqual(level["player"], "hero")
        hero = json.loads((self.root / "sprites" / "hero" / "sprite.json").read_text(encoding="utf-8"))
        self.assertEqual(list(hero["animations"]), ["idle_down"])
        run("--root", self.root, "new-level", "cave", "--player", "ant")
        self.assertEqual(json.loads((self.root / "levels" / "cave.json").read_text(encoding="utf-8"))["player"], "ant")
        out = run("--root", self.root, "game")
        self.assertIn("+ src/scenes/Level.js", out)
        self.assertIn("npm install && npm run dev", out)

    @unittest.skipUnless(os.environ.get("PIXELFORGE_SLOW_TESTS") and shutil.which("npm"),
                         "set PIXELFORGE_SLOW_TESTS=1 (needs npm and the network) to build the starter with Vite")
    def test_vite_build(self):
        run("--root", self.root, "new", "terrain", "--tileset")
        run("--root", self.root, "paint", "terrain", "tile_0", "frect 0 0 15 15 g")
        run("--root", self.root, "new-level", "start")
        run("--root", self.root, "export", "--all")
        run("--root", self.root, "game")
        npm = shutil.which("npm")
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=self.root, check=True, capture_output=True)
        subprocess.run([npm, "run", "build"], cwd=self.root, check=True, capture_output=True)
        self.assertTrue((self.root / "dist" / "index.html").is_file())
        self.assertTrue((self.root / "dist" / "levels" / "start.json").is_file())


if __name__ == "__main__":
    unittest.main()
