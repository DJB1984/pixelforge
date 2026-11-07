import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from pixelforge import __version__, model
from pixelforge.__main__ import main
from pixelforge.model import ASSETS
from pixelforge.project import GUIDE_HEADING, _sha, init_project, upgrade_project

GUIDE = (ASSETS / "CLAUDE.md").read_text(encoding="utf-8")
OLD_GUIDE = GUIDE_HEADING + "\n\nAn older guide without hitboxes.\n"


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "game"

    def tearDown(self):
        model.set_root(None)
        self._tmp.cleanup()

    def cfg(self):
        return json.loads((self.root / "pixelforge.json").read_text())

    def pretend_installed_long_ago(self, guide_text):
        """As if init ran under an older pixelforge that wrote `guide_text`."""
        (self.root / "CLAUDE.md").write_text(guide_text, encoding="utf-8")
        cfg = self.cfg()
        cfg["pixelforge"].update(version="0.1.0", guide_sha256=_sha(guide_text))
        (self.root / "pixelforge.json").write_text(json.dumps(cfg))

    def test_init_records_version_and_guide(self):
        init_project(self.root, "Quest")
        meta = self.cfg()["pixelforge"]
        self.assertEqual(meta["version"], __version__)
        self.assertEqual(meta["guide"], "CLAUDE.md")
        self.assertEqual(meta["guide_sha256"], _sha(GUIDE))
        with self.assertRaises(FileExistsError):
            init_project(self.root)

    def test_unedited_guide_is_replaced(self):
        init_project(self.root)
        self.pretend_installed_long_ago(OLD_GUIDE)
        report, previous = upgrade_project(self.root)
        self.assertEqual(previous, "0.1.0")
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), GUIDE)
        self.assertEqual(self.cfg()["pixelforge"], {"version": __version__, "guide": "CLAUDE.md",
                                                    "guide_sha256": _sha(GUIDE)})

    def test_edited_guide_is_left_alone(self):
        init_project(self.root)
        self.pretend_installed_long_ago(OLD_GUIDE)
        edited = OLD_GUIDE + "\nOur team's own rule: enemies are always purple.\n"
        (self.root / "CLAUDE.md").write_text(edited, encoding="utf-8")
        report, _ = upgrade_project(self.root)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), edited)
        self.assertEqual((self.root / "CLAUDE.pixelforge-new.md").read_text(encoding="utf-8"), GUIDE)
        self.assertTrue(any("merge CLAUDE.pixelforge-new.md" in n for n in report.notes))

    def test_legacy_project_gets_backup_and_scaffolding(self):
        self.root.mkdir()
        (self.root / "pixelforge.json").write_text('{"name": "Old"}')
        (self.root / "CLAUDE.md").write_text(OLD_GUIDE, encoding="utf-8")
        report, previous = upgrade_project(self.root)
        self.assertIsNone(previous)
        self.assertEqual((self.root / "CLAUDE.md.bak").read_text(encoding="utf-8"), OLD_GUIDE)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), GUIDE)
        self.assertIn("humanoid", self.cfg()["classes"])
        self.assertTrue((self.root / "palettes/game.json").is_file())

    def test_unmanaged_guide_and_dry_run(self):
        self.root.mkdir()
        (self.root / "pixelforge.json").write_text('{"name": "Tool", "pixelforge": {"guide": null}}')
        (self.root / "CLAUDE.md").write_text("# The tool repo's own notes\n", encoding="utf-8")
        before = (self.root / "pixelforge.json").read_text()
        upgrade_project(self.root, dry_run=True)
        self.assertEqual((self.root / "pixelforge.json").read_text(), before)   # dry run writes nothing
        self.assertFalse((self.root / "sprites").exists())
        upgrade_project(self.root)
        self.assertEqual((self.root / "CLAUDE.md").read_text(encoding="utf-8"), "# The tool repo's own notes\n")
        self.assertIsNone(self.cfg()["pixelforge"]["guide"])

    def test_cli_upgrade_reexports(self):
        with contextlib.redirect_stdout(io.StringIO()):
            main(["init", str(self.root)])
            main(["--root", str(self.root), "new", "hero", "--class", "small"])
            (self.root / "sprites/hero/frames/idle_0.txt").write_text(("." * 32 + "\n") * 31 + "k" * 32 + "\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--root", str(self.root), "upgrade"])
        self.assertIn("re-exported 1 sprite(s)", out.getvalue())
        self.assertTrue((self.root / "export/hero.json").is_file())
        self.assertTrue((self.root / "export/pixelforge.js").is_file())


if __name__ == "__main__":
    unittest.main()
