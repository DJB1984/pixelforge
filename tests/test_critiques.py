import http.server
import json
import threading
import unittest
import urllib.request

from pixelforge import critiques as cq
from pixelforge import server
from pixelforge.model import SpriteError

from helpers import TempProject

BODY = "......\n..kk..\n..kk..\n..kk..\n..kk..\n..kk..\n"
TILE = "gggg\ngggg\ngggg\ngggg\n"


def project(p):
    p.sprite("hero", (6, 6), {"k": "#181425"}, {"body": BODY},
             {"idle": {"fps": 4, "frames": ["body", "body"]}})
    d = p.sprite("ground", (4, 4), {"g": "#63c74d"}, {"grass": TILE}, {})
    meta = json.loads((d / "sprite.json").read_text())
    meta.update({"type": "tileset", "tiles": ["grass"], "sample": {"legend": {"g": "grass"}, "rows": ["gg", "gg"]}})
    (d / "sprite.json").write_text(json.dumps(meta))


class CritiqueStoreTest(unittest.TestCase):
    def test_targets_are_validated_and_clamped(self):
        with TempProject() as p:
            project(p)
            c = cq.add({"asset": "hero", "anim": "idle", "frame": 1, "region": [4, 4, 9, 9]}, "  feet too wide ")
            self.assertEqual(c["text"], "feet too wide")
            self.assertEqual(c["target"], {"asset": "hero", "anim": "idle", "frame": 1, "region": [4, 4, 2, 2]})
            self.assertEqual(cq.label(c["target"]), "hero > idle > frame 1 > spot (4,4 2x2)")
            self.assertIn('frame entry: body', cq.details(c["target"])[0])
            m = cq.add({"asset": "ground", "map": True, "region": [3, 3, 2, 2]}, "seam")
            self.assertEqual(cq.details(m["target"]), ["sample map tiles under the spot: grass"])
            for bad in ({"asset": "nope"}, {"asset": "hero", "anim": "run"},
                        {"asset": "hero", "anim": "idle", "frame": 5}, {"asset": "hero", "region": [0, 0, 1, 1]},
                        {"asset": "ground", "tile": "lava"}):
                with self.assertRaises(SpriteError):
                    cq.add(bad, "x")
            with self.assertRaises(SpriteError):
                cq.add({"asset": "hero"}, "   ")

    def test_lifecycle_and_watch(self):
        with TempProject() as p:
            project(p)
            a = cq.add({"asset": "hero"}, "too dark")
            b = cq.add({"asset": "ground", "tile": "grass"}, "too flat")
            lines = []
            cq.watch(once=True, emit=lines.append, interval=0)
            self.assertEqual(len(lines), 3)
            self.assertIn(f"critique #{a['id']} on hero: too dark", lines[0])
            self.assertEqual({c["status"] for c in cq.all_critiques()}, {"working"})
            self.assertFalse(cq.watching())        # the heartbeat goes when the watcher does
            cq.update(a["id"], status="fixed", note="lightened the armour")
            self.assertEqual(cq.get(a["id"])["note"], "lightened the armour")
            cq.update(a["id"], status="open")      # reopening clears the old note
            self.assertNotIn("note", cq.get(a["id"]))
            cq.delete(b["id"])
            self.assertEqual([c["id"] for c in cq.all_critiques()], [a["id"]])
            self.assertTrue(cq.render_target(cq.get(a["id"])).is_file())


class ServerTest(unittest.TestCase):
    def test_api(self):
        with TempProject() as p:
            project(p)
            httpd = http.server.ThreadingHTTPServer(
                ("127.0.0.1", 0), lambda *a, **kw: server.Handler(*a, directory=str(p.root), **kw))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"

            def call(path, data=None, method=None):
                req = urllib.request.Request(base + path, method=method,
                                             data=json.dumps(data).encode() if data is not None else None,
                                             headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req) as r:
                    body = r.read()
                    return json.loads(body) if r.headers.get_content_type() == "application/json" else body
            try:
                proj = call("/api/project")
                self.assertEqual({a["name"]: a["type"] for a in proj["assets"]}, {"hero": "sprite", "ground": "tileset"})
                hero = next(a for a in proj["assets"] if a["name"] == "hero")
                self.assertEqual([len(a["frames"]) for a in hero["anims"]], [2])
                self.assertTrue(call(hero["sheet"]).startswith(b"\x89PNG"))
                self.assertEqual(call("/live/index.json"), {"sprites": ["hero"], "props": [], "tilesets": ["ground"], "icons": [], "fonts": []})
                rev = call("/api/state")["rev"]

                c = call("/api/critiques", {"target": {"asset": "hero", "anim": "idle", "frame": 0}, "text": "wobbly"})
                self.assertEqual(call("/api/state")["critiques"][0]["text"], "wobbly")
                self.assertEqual(call(f"/api/critiques/{c['id']}", {"status": "fixed"})["status"], "fixed")
                with self.assertRaises(urllib.error.HTTPError) as e:
                    call("/api/critiques", {"target": {"asset": "nope"}, "text": "x"})
                self.assertEqual(e.exception.code, 400)
                e.exception.close()

                # editing a frame changes the revision and the live sheet, without exporting
                (p.root / "sprites/hero/frames/body.txt").write_text(BODY.replace("..kk..\n", "kkkk..\n", 1))
                self.assertNotEqual(call("/api/state")["rev"], rev)
                call(f"/api/critiques/{c['id']}", method="DELETE")
                self.assertEqual(call("/api/state")["critiques"], [])
            finally:
                httpd.shutdown()
                httpd.server_close()


if __name__ == "__main__":
    unittest.main()
