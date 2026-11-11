"""`pixelforge serve`: the dashboard, the live asset API and the critique API.

/                      -> /viewer/ (the dashboard)
/viewer/*, /phaser/*   from the installed package
/live/index.json       every asset by kind, built from the working tree (not export/)
/live/<name>.png|json  the same sheet + JSON `export` would write, rebuilt whenever the sources change
/api/project           everything the dashboard draws, in one document
/api/state             cheap poll: source revision, critiques, whether Claude is watching
POST /api/critiques            {"target": {...}, "text": "..."}  -> the new critique
POST /api/critiques/<id>       {"status": "open"}                -> reopen
DELETE /api/critiques/<id>
everything else        from the project folder
"""
from __future__ import annotations

import hashlib
import http.server
import io
import json
import threading
from pathlib import Path

from . import __version__
from . import critiques as cq
from .export import INDEX_GROUPS, preview_build, prop_info
from .model import ASSETS, Sprite, SpriteError, describe_entry, list_sprites, project_config, root, sprites_dir, to_hex


# ---- live builds --------------------------------------------------------------------------
def _files_sig(paths) -> str:
    h = hashlib.sha1()
    for p in paths:
        try:
            st = p.stat()
        except FileNotFoundError:
            continue
        h.update(f"{p}|{st.st_mtime_ns}|{st.st_size};".encode())
    return h.hexdigest()[:12]


def _shared_files() -> list[Path]:
    r = root()
    return [r / "pixelforge.json", *sorted((r / "palettes").glob("*.json"))]


def asset_sig(name: str) -> str:
    d = sprites_dir() / name
    return _files_sig([*_shared_files(), d / "sprite.json", *sorted(d.glob("**/*.txt"))])   # frames, parts, glyphs


def project_sig() -> str:
    return _files_sig([*_shared_files(), *sorted(sprites_dir().glob("*/sprite.json")),
                       *sorted(sprites_dir().glob("*/**/*.txt"))])


class LiveBuilds:
    """Sheets built straight from sprites/, cached until a source file changes."""

    def __init__(self):
        self._cache: dict[str, tuple[str, bytes, dict, Sprite]] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> tuple[str, bytes, dict, Sprite]:
        sig = asset_sig(name)
        with self._lock:
            hit = self._cache.get(name)
            if hit and hit[0] == sig:
                return hit
            s = Sprite.load(name)
            img, data = preview_build(s, 1)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            self._cache[name] = entry = (sig, buf.getvalue(), data, s)
            return entry


BUILDS = LiveBuilds()


def live_index() -> dict:
    found: dict[str, list[str]] = {g: [] for g in INDEX_GROUPS}
    for n in list_sprites():
        try:
            kind = BUILDS.get(n)[3].kind
        except Exception:
            continue
        found[{"prop": "props", "tileset": "tilesets", "icons": "icons", "font": "fonts"}.get(kind, "sprites")].append(n)
    return found


def _asset(name: str) -> dict:
    try:
        sig, _, data, s = BUILDS.get(name)
    except Exception as e:   # a half-edited sprite shouldn't take the whole dashboard down
        return {"name": name, "type": "error", "error": str(e)}
    base = {"name": name, "rev": sig, "sheet": f"/live/{name}.png?v={sig}", "w": s.width, "h": s.height,
            "palette": [[k, to_hex(s.palette[k]), v] for k, v in s.palette_raw.items()]}
    if s.tiled:   # tileset, icons, font: a grid of named cells
        pf = data["pixelforge"]
        return {**base, "type": s.kind, "cols": data["columns"], "spacing": data["spacing"],
                "tiles": [{"name": n, "props": p, "entry": describe_entry(s.tiles[i][1])}
                          for i, (n, p) in enumerate(zip(pf["names"], pf["properties"]))],
                "sample": pf["sample"], "anims": pf["animations"], "stamps": pf.get("stamps", {})}
    frames = list(data["frames"].values())
    anims = []
    for tag in data["meta"]["frameTags"]:
        info = data["meta"]["pixelforge"]["animations"][tag["name"]]
        a = s.animations[info["anim"]]
        anims.append({
            "name": info["anim"], "key": tag["name"], "loop": info["loop"], "fps": info["fps"],
            "frames": [{"x": f["frame"]["x"], "y": f["frame"]["y"], "d": f["duration"],
                        "hurt": f["pixelforge"]["hurt"], "hit": f["pixelforge"]["hit"],
                        "active": a.active(i), "entry": describe_entry(a.frames[i])}
                       for i, f in enumerate(frames[tag["from"]:tag["to"] + 1])],
        })
    out = {**base, "type": s.kind, "class": s.size_class, "origin": list(s.origin), "anchor": s.anchor,
           "body": list(s.body_rect()), "anims": anims, "view": s.view}
    if s.kind == "prop":
        out["prop"] = {**prop_info(s), "slice": list(s.slice) if s.slice else None}
    return out


def project_data() -> dict:
    return {"game": project_config().get("name") or root().name, "version": __version__,
            "rev": project_sig(), "assets": [_asset(n) for n in list_sprites()]}


def state_data() -> dict:
    try:
        crits, err = cq.all_critiques(), None
    except SpriteError as e:
        crits, err = [], str(e)
    return {"rev": project_sig(), "critiques": crits, "watching": cq.watching(), "error": err}


# ---- HTTP ---------------------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):   # the dashboard polls; keep the terminal readable
        if not self.path.startswith(("/api/state", "/live/")):
            super().log_message(fmt, *args)

    def _json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def _route(self) -> list[str]:
        return [p for p in self.path.split("?", 1)[0].split("#", 1)[0].split("/") if p]

    def do_GET(self):
        parts = self._route()
        if not parts or parts == ["index.html"]:
            self.send_response(302)
            self.send_header("Location", "/viewer/")
            self.end_headers()
            return
        try:
            if parts == ["api", "project"]:
                return self._json(project_data())
            if parts == ["api", "state"]:
                return self._json(state_data())
            if parts[0] == "live" and len(parts) == 2:
                return self._live(parts[1])
        except (SpriteError, ValueError, OSError) as e:
            return self._json({"error": str(e)}, 500)
        super().do_GET()

    def _live(self, file: str) -> None:
        if file == "index.json":
            return self._json(live_index())
        name, _, ext = file.rpartition(".")
        if name not in list_sprites() or ext not in ("png", "json"):
            return self._json({"error": f"no live asset {file}"}, 404)
        _, png, data, _ = BUILDS.get(name)
        if ext == "json":
            return self._json(data)
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png)))
        self.end_headers()
        self.wfile.write(png)

    def do_POST(self):
        parts = self._route()
        try:
            if parts == ["api", "critiques"]:
                b = self._body()
                return self._json(cq.add(b.get("target"), b.get("text", "")), 201)
            if len(parts) == 3 and parts[:2] == ["api", "critiques"]:
                b = self._body()
                fields = {k: b[k] for k in ("status", "text") if k in b}
                return self._json(cq.update(int(parts[2]), **fields))
        except (SpriteError, ValueError, TimeoutError) as e:
            return self._json({"error": str(e)}, 400)
        self._json({"error": "not found"}, 404)

    def do_DELETE(self):
        parts = self._route()
        if len(parts) == 3 and parts[:2] == ["api", "critiques"]:
            try:
                cq.delete(int(parts[2]))
            except (SpriteError, ValueError, TimeoutError) as e:
                return self._json({"error": str(e)}, 400)
            return self._json({"ok": True})
        self._json({"error": "not found"}, 404)

    def translate_path(self, path):
        parts = path.split("?", 1)[0].split("#", 1)[0].lstrip("/").split("/")
        if parts and parts[0] in ("viewer", "phaser"):
            return str(ASSETS.joinpath(*parts))
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve(port: int) -> None:
    handler = lambda *a, **kw: Handler(*a, directory=str(root()), **kw)  # noqa: E731
    with http.server.ThreadingHTTPServer(("127.0.0.1", port), handler) as httpd:
        print(f"pixelforge dashboard: http://127.0.0.1:{port}/   ({root()})")
        print("Ctrl+C to stop")
        httpd.serve_forever()
