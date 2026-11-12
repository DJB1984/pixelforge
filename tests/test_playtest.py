import importlib.util
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from pixelforge import model
from pixelforge import playtest as pt
from pixelforge.level import Level

from test_level import LevelProject

REPO = Path(__file__).resolve().parents[1]


class FakeGame:
    """A side-view player on flat ground at y=100 with a wall at x=60: enough physics for the runner."""

    def __init__(self):
        self.x, self.y, self.vy, self.events, self.shots = 10.0, 100.0, 0.0, [], []
        self.held_jump = False

    def state(self):
        ev, self.events = self.events, []
        return {"level": "t", "x": round(self.x, 2), "y": round(self.y, 2), "vx": 0, "vy": round(self.vy, 2),
                "onGround": self.y >= 100 and self.vy >= 0, "facing": "right", "anim": "idle", "events": ev}

    def step(self, frames, inp):
        for _ in range(frames):
            on = self.y >= 100 and self.vy >= 0
            if inp.get("jump") and not self.held_jump and on:
                self.vy = -300
                self.events.append({"type": "jump"})
            self.held_jump = bool(inp.get("jump"))
            self.x = min(60.0, self.x + (120 if inp.get("right") else 0) / 60)
            self.vy += 900 / 60
            self.y += self.vy / 60
            if self.y >= 100:
                if not on:
                    self.events.append({"type": "land"})
                self.y, self.vy = 100.0, 0.0
        return self.state()

    def shot(self, path):
        self.shots.append(path.name)


def run(script, every=15, view="side"):
    game = FakeGame()
    r = pt.Run(level="t", script=script, view=view)
    pt.run_script(pt.parse_script(script), game, r, every, Path("."))
    return r, game


class ParseTest(unittest.TestCase):
    def test_actions(self):
        acts = pt.parse_script("right+run 1.5s; jump # a full jump\nwait 800ms\nshot\nexpect x > 200")
        self.assertEqual([a.kind for a in acts], ["hold", "press", "wait", "shot", "expect"])
        self.assertEqual(acts[0].keys, ("right", "run"))
        self.assertEqual(acts[0].frames, 90)
        self.assertEqual(acts[2].frames, 48)
        self.assertEqual([a.where for a in acts], ["line 1", "line 1", "line 2", "line 3", "line 4"])
        # a one-line script numbers its actions instead
        self.assertEqual([a.where for a in pt.parse_script("wait 1s; expect onGround")], ["action 1", "action 2"])
        self.assertEqual(pt.parse_duration("10ms"), 1)   # never less than a frame

    def test_expects(self):
        e = pt.parse_expect("x >= 12.5")
        self.assertEqual((e.field, e.op, e.value), ("x", ">=", 12.5))
        e = pt.parse_expect("not onGround")
        self.assertEqual((e.field, e.op, e.negate), ("onGround", None, True))
        e = pt.parse_expect("anim = princess_run")
        self.assertEqual((e.op, e.value), ("==", "princess_run"))
        e = pt.parse_expect("no trigger door")
        self.assertEqual((e.event, e.match, e.negate), ("trigger", "door", True))
        e = pt.parse_expect("inventory has key")
        self.assertEqual((e.field, e.op, e.value), ("inventory", "has", "key"))

    def test_errors(self):
        for bad, says in [("rigth 1s", "unknown key 'rigth'"), ("right 2", "with a unit"), ("wait", "takes a time"),
                          ("expect x > big", "compares numbers"), ("expect", "needs something"),
                          ("right 1s now", "too many words"), ("shot 3", "takes nothing")]:
            with self.assertRaises(pt.ScriptError, msg=bad) as cm:
                pt.parse_script(f"wait 1s\n{bad}")
            self.assertIn("script line 2", str(cm.exception))
            self.assertIn(says, str(cm.exception))

    def test_read_script(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "route.txt"
            f.write_text("right 1s\nexpect onGround\n")
            self.assertEqual(pt.read_script(str(f)), "right 1s\nexpect onGround\n")
        self.assertEqual(pt.read_script("right 1s; jump"), "right 1s; jump")
        self.assertEqual(pt.read_script(None), "wait 1s")


class CheckTest(unittest.TestCase):
    STATE = {"x": 300.25, "y": 100, "onGround": True, "anim": "princess_run", "health": 3, "inventory": ["key"]}
    EVENTS = [{"t": 500, "type": "trigger", "name": "D", "object": "door", "to": "inn"}, {"t": 900, "type": "land"}]

    def check(self, text):
        return pt.check_expect(pt.parse_expect(text), self.STATE, self.EVENTS)[0]

    def test_fields(self):
        for text, want in [("x > 200", True), ("x < 200", False), ("y == 100", True), ("health >= 3", True),
                           ("onGround", True), ("not onGround", False), ("onGround == true", True),
                           ("anim == princess_run", True), ("anim != princess_run", False),
                           ("inventory has key", True), ("inventory has sword", False), ("anim > 3", False),
                           ("coins > 0", False)]:
            self.assertEqual(self.check(text), want, text)
        self.assertIn("no field 'coins'", pt.check_expect(pt.parse_expect("coins"), self.STATE, [])[1])

    def test_events(self):
        # an event matches by its name, its type or where it leads
        for text, want in [("trigger", True), ("trigger door", True), ("trigger D", True), ("trigger inn", True),
                           ("trigger shop", False), ("no trigger shop", True), ("land", True), ("no fell", True),
                           ("hit", False)]:
            self.assertEqual(self.check(text), want, text)
        self.assertEqual(pt.check_expect(pt.parse_expect("trigger"), {}, self.EVENTS)[1], "1 at 0.50s")


class RunTest(unittest.TestCase):
    def test_holds_presses_and_shots(self):
        r, game = run("right 500ms; jump; shot; expect not onGround; wait 1s; expect onGround; expect land")
        # shots: the start, every 15 frames, the `shot` line, and the end
        whys = [s["why"] for s in r.shots]
        self.assertEqual(whys[0], "start")
        self.assertIn("shot", whys)
        self.assertEqual(game.shots[:2], ["00.png", "01.png"])
        self.assertEqual(r.shots[1]["t"], 250)
        # the press held jump to the top of the jump, so the expect right after sees it in the air
        self.assertEqual([x["passed"] for x in r.expects], [True, True, True])
        self.assertEqual([e["type"] for e in r.events], ["jump", "land"])
        self.assertEqual(r.trace[0]["input"], [])
        self.assertIn("right", r.trace[1]["input"])
        jump_end = [e for e in r.trace if "jump" in e["input"]][-1]
        self.assertGreaterEqual(jump_end["vy"], 0)   # held until it stopped rising
        self.assertLess(jump_end["y"], 60)

    def test_no_player(self):
        class Empty(FakeGame):
            def state(self):
                return {"level": "t", "events": []}
        with self.assertRaises(RuntimeError) as cm:
            pt.run_script([], Empty(), pt.Run(level="t", script="", view="side"), None, None)
        self.assertIn("no player", str(cm.exception))


class NotesTest(unittest.TestCase):
    def test_stuck_hurt_triggers_expects(self):
        r, _ = run("right 2s; expect x > 100; expect onGround")   # the wall at x=60 stops it after 0.4s
        r.events.append({"t": 1000, "type": "trigger", "name": "D", "object": "door", "to": "inn"})
        r.trace[5]["health"], r.trace[6]["health"] = 3, 2
        notes = pt.notes(r)
        self.assertTrue(any(n.startswith("stuck: holding right from 0.4") and "(60, 100)" in n for n in notes), notes)
        self.assertIn("triggers: D (door) -> inn at 1.00s", notes)
        self.assertTrue(any(n.startswith("hurt: health 3 -> 2 at") for n in notes), notes)
        self.assertIn("expect x > 100 (action 2, at 2.00s): FAILED, x = 60", notes)
        self.assertIn("expect onGround (action 3, at 2.00s): passed, onGround = true", notes)
        self.assertTrue(pt.failed(r))

    def test_not_stuck_when_moving_or_brief(self):
        r, _ = run("right 400ms; wait 2s; right 900ms")   # waiting isn't stuck, and 0.9s against the wall is brief
        notes = pt.notes(r)
        self.assertFalse(any(n.startswith("stuck") for n in notes), notes)
        self.assertIn("triggers: none fired", notes)
        self.assertFalse(pt.failed(r))

    def test_fell_and_never_landed(self):
        trace = [{"t": 0, "input": [], "x": 50, "y": 100, "onGround": True},
                 {"t": 100, "input": ["right"], "x": 90, "y": 300, "onGround": False},
                 {"t": 200, "input": ["right"], "x": 50, "y": 100, "onGround": False}]
        r = pt.Run(level="t", script="", view="side", trace=trace,
                   events=[{"t": 50, "type": "jump"}, {"t": 200, "type": "fell"}])
        notes = pt.notes(r, (200, 120))
        # the fall is placed where the player was before the step that sent it back to the spawn
        self.assertIn("fell out of the world at 0.20s near x=90 (and went back to the spawn)", notes)
        self.assertIn("never landed after the jump at 0.05s (still in the air at the end)", notes)
        r = pt.Run(level="t", script="", view="side", trace=[{**t, "onGround": False} for t in trace[1:2]])
        notes = pt.notes(r, (200, 120))
        self.assertTrue(any(n.startswith("never stood on the ground") for n in notes), notes)
        self.assertTrue(any(n.startswith("left the level at 0.10s") for n in notes), notes)
        # top-down has no ground to stand on
        r = pt.Run(level="t", script="", view="topdown", trace=[{**t, "onGround": False} for t in trace[:1]])
        self.assertEqual(pt.notes(r, (200, 120)), ["triggers: none fired"])

    def test_page_errors_fail(self):
        r = pt.Run(level="t", script="", view="side", errors=["TypeError: x is undefined"])
        self.assertIn("page error: TypeError: x is undefined", pt.notes(r))
        self.assertTrue(pt.failed(r))


class SheetTest(unittest.TestCase):
    def test_contact_sheet_and_route(self):
        with LevelProject() as p, tempfile.TemporaryDirectory() as d:
            p.level("a", layers=[{"name": "g", "rows": ["gggg", "gggg"]}],
                    objects={"legend": {"D": {"type": "door", "to": "a"}}, "rows": ["@..D", "...."]})
            lv = Level.load("a")
            r, game = run("right 300ms; jump; expect onGround; expect land")
            for i in range(len(r.shots)):
                Image.new("RGBA", (16, 8), (i * 20, 90, 200, 255)).save(Path(d) / f"{i:02d}.png")
            img = pt.contact_sheet(r, Path(d), lv, (16, 8))
            self.assertGreater(img.width, 16 * 2 * 3)
            route = pt.route_image(lv, r)
            self.assertEqual(route.size[0] % lv.pixel_size[0], 0)   # a whole-number zoom of the level
            # no level: just the shots
            self.assertLess(pt.contact_sheet(r, Path(d), None, (16, 8)).height, img.height)


class CliTest(unittest.TestCase):
    def test_without_playwright(self):
        with LevelProject() as p, mock.patch.dict(sys.modules, {"playwright": None, "playwright.sync_api": None}):
            p.level("a", layers=[{"name": "g", "rows": ["gggg"]}], objects={"rows": ["@..."]})
            with self.assertRaises(pt.PlayUnavailable) as cm:
                pt.play("a", "wait 1s")
            self.assertIn("[play]", str(cm.exception))
            self.assertIn("playwright install chromium", str(cm.exception))


def _online() -> bool:
    try:
        socket.create_connection(("cdn.jsdelivr.net", 443), timeout=3).close()
        return True
    except OSError:
        return False


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Playwright isn't installed (pip install -e .[play])")
class PlayIntegrationTest(unittest.TestCase):
    """The real thing: this repo's meadow in headless Chromium (Phaser comes from the CDN)."""

    def test_meadow(self):
        if not _online():
            self.skipTest("offline: play.html loads Phaser from cdn.jsdelivr.net")
        model.set_root(REPO)
        try:
            with tempfile.TemporaryDirectory() as d:
                try:
                    r, sheet = pt.play("meadow", "right+run 1.8s; right+run+jump; right+run 600ms; "
                                       "expect x > 360; expect onGround; expect no fell",
                                       shot_every_ms=500, out_dir=Path(d))
                except pt.PlayUnavailable as e:
                    self.skipTest(str(e))
                self.assertEqual(r.errors, [])
                self.assertEqual([x["passed"] for x in r.expects], [True, True, True], pt.notes(r))
                self.assertEqual([e["type"] for e in r.events], ["jump", "land"])
                self.assertTrue(sheet.is_file())
                shots = sorted((Path(d) / "play_meadow").glob("*.png"))
                self.assertEqual(len(shots), len(r.shots))
                with Image.open(shots[0]) as im:
                    self.assertEqual(im.size, tuple(model.game_resolution()))
                log = json.loads((Path(d) / "play_meadow" / "log.json").read_text())
                self.assertIn("notes", log)
        finally:
            model.set_root(None)


if __name__ == "__main__":
    unittest.main()
