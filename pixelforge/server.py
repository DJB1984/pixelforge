"""`pixelforge serve`: the dashboard, the live asset API and the critique API.

/                      -> /viewer/ (the dashboard)
/viewer/*, /phaser/*   from the installed package
/live/index.json       every asset by kind, built from the working tree (not export/)
/live/<name>.png|json  the same sheet + JSON `export` would write, rebuilt whenever the sources change
                       (icons and fonts: the atlas JSON / font JSON + <name>.xml, as `export` writes them)
                       (<prop>_tiles for a sliced building's tileset)
/live/levels/<name>.json  a level's Tiled map, built from levels/ (tileset images at ../<tileset>.png)
/live/level/<name>.png    the level composited like the game (what the dashboard's Levels page shows)
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
from .export import INDEX_GROUPS, KIND_GROUP, build_atlas, build_font, build_slices, preview_build, prop_info
from .level import Level, level_data, levels_dir, list_levels
from .model import (ASSETS, Sprite, SpriteError, describe_entry, list_sprites, project_config, root, sprite_folder,
                    sprites_dir, to_hex)


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
    d = sprite_folder(name)   # a variant changes with its base's files
    return _files_sig([*_shared_files(), d / "sprite.json", *sorted(d.glob("**/*.txt"))])   # frames, parts, glyphs


def sprites_sig() -> str:
    return _files_sig([*_shared_files(), *sorted(sprites_dir().glob("*/sprite.json")),
                       *sorted(sprites_dir().glob("*/**/*.txt"))])


def project_sig() -> str:
    return sprites_sig() + _files_sig(sorted(levels_dir().glob("*.json")))


def level_sig(name: str) -> str:
    """A level depends on its own file and on every tileset and prop it uses: all the sprites."""
    return sprites_sig() + _files_sig([levels_dir() / f"{name}.json"])


def _png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class LiveBuilds:
    """Sheets built straight from sprites/, cached until a source file changes. A sliced building's
    tileset is `<prop>_tiles`; a level is `level:<name>` (its Tiled map, no image)."""

    def __init__(self):
        self._cache: dict[str, tuple] = {}
        self._lock = threading.Lock()

    def get(self, name: str) -> tuple[str, bytes, dict, Sprite]:
        sig = asset_sig(name)
        with self._lock:
            hit = self._cache.get(name)
            if hit and hit[0] == sig:
                return hit
            s = Sprite.load(name)
            img, data = preview_build(s, 1)
            self._cache[name] = entry = (sig, _png(img), data, s)
            return entry

    def game(self, name: str) -> tuple[str, dict, str | None]:
        """Icons and fonts as the game loads them (the dashboard draws them as a tileset grid, from the
        same PNG): an atlas JSON, or a font's JSON and BMFont XML."""
        sig = asset_sig(name)
        key = f"game:{name}"
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == sig:
                return hit
            s = Sprite.load(name)
            if s.kind == "font":
                _, data, xml = build_font(s, 1)
            else:
                (_, data), xml = build_atlas(s, 1), None
            self._cache[key] = entry = (sig, data, xml)
            return entry

    def slices(self, prop: str) -> tuple[str, bytes, dict]:
        sig = asset_sig(prop)
        key = f"{prop}_tiles"
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == sig:
                return hit
            img, data = build_slices(Sprite.load(prop), 1)
            self._cache[key] = entry = (sig, _png(img), data)
            return entry

    def level(self, name: str) -> tuple[str, dict]:
        sig = level_sig(name)
        key = f"level:{name}"
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == sig:
                return hit
        data = level_data(Level.load(name))   # slow (it builds every tileset it uses): don't hold the lock
        with self._lock:
            self._cache[key] = entry = (sig, data)
        return entry

    def level_view(self, name: str) -> tuple[str, bytes, dict]:
        """The level composited like the game draws it (1x, accents at camera 0,0) and what the
        dashboard draws over it: screens, objects."""
        from .screens import compose, screen_positions
        sig = level_sig(name)
        key = f"view:{name}"
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] == sig:
                return hit
        lv = Level.load(name)
        img = compose(lv).world()
        info = {"w": lv.pixel_size[0], "h": lv.pixel_size[1], "tile": [lv.tile_w, lv.tile_h],
                "cells": [lv.width, lv.height], "view": lv.view, "screen": list(lv.screen_size()),
                "screens": [list(c) for c in screen_positions(lv)], "player": lv.player,
                "tilesets": list(lv.tilesets), "layers": [l.name for l in lv.layers],
                "objects": [{**o.to_dict(), **({"art": list(o.art)} if o.art else {})} for o in lv.objects],
                "errors": lv.errors()}
        with self._lock:
            self._cache[key] = entry = (sig, _png(img), info)
        return entry


BUILDS = LiveBuilds()


def sliced_props() -> list[str]:
    out = []
    for n in list_sprites():
        try:
            s = BUILDS.get(n)[3]
        except Exception:
            continue
        if s.kind == "prop" and s.slice:
            out.append(n)
    return out


def live_index() -> dict:
    found: dict[str, list[str]] = {g: [] for g in INDEX_GROUPS}
    for n in list_sprites():
        try:
            kind = BUILDS.get(n)[3].kind
        except Exception:
            continue
        found[KIND_GROUP.get(kind, "sprites")].append(n)
    found["tilesets"] = sorted(found["tilesets"] + [f"{p}_tiles" for p in sliced_props()])
    found["levels"] = list_levels()
    if project_config().get("hud"):
        found["hud"] = project_config()["hud"]
    return found


def _asset(name: str) -> dict:
    try:
        sig, _, data, s = BUILDS.get(name)
    except Exception as e:   # a half-edited sprite shouldn't take the whole dashboard down
        return {"name": name, "type": "error", "error": str(e)}
    base = {"name": name, "rev": sig, "sheet": f"/live/{name}.png?v={sig}", "w": s.width, "h": s.height,
            "palette": [[k, to_hex(s.palette[k]), v] for k, v in s.palette_raw.items()],
            **({"variantOf": s.base} if s.base else {}), **({"variants": s.variants} if s.variants else {})}
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
    if s.kind == "fx":
        out["fx"] = {"layer": s.layer}
    return out


def _level_asset(name: str) -> dict:
    try:
        sig, _, info = BUILDS.level_view(name)
    except Exception as e:   # as for sprites: one broken level shouldn't take the dashboard down
        return {"name": name, "type": "error", "error": str(e)}
    return {"name": name, "type": "level", "rev": sig, "sheet": f"/live/level/{name}.png?v={sig}", **info}


def project_data() -> dict:
    sprites = list_sprites()
    # a level named like a sprite would shadow it in the dashboard (assets are keyed by name)
    levels = [_level_asset(n) for n in list_levels() if n not in sprites]
    return {"game": project_config().get("name") or root().name, "version": __version__,
            "rev": project_sig(), "assets": levels + [_asset(n) for n in sprites]}


def state_data() -> dict:
    try:
        crits, err = cq.all_critiques(), None
    except SpriteError as e:
        crits, err = [], str(e)
    return {"rev": project_sig(), "critiques": crits, "watching": cq.watching(), "error": err}


# ---- HTTP ---------------------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    quiet = False

    def log_message(self, fmt, *args):   # the dashboard polls; keep the terminal readable
        if not self.quiet and not self.path.startswith(("/api/state", "/live/")):
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
            if parts[:2] == ["live", "levels"] and len(parts) == 3 and parts[2].endswith(".json"):
                name = parts[2][:-5]
                if name not in list_levels():
                    return self._json({"error": f"no level {name}"}, 404)
                return self._json(BUILDS.level(name)[1])
            if parts[:2] == ["live", "level"] and len(parts) == 3 and parts[2].endswith(".png"):
                name = parts[2][:-4]
                if name not in list_levels():
                    return self._json({"error": f"no level {name}"}, 404)
                png = BUILDS.level_view(name)[1]
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(png)))
                self.end_headers()
                self.wfile.write(png)
                return
        except (SpriteError, ValueError, OSError) as e:
            return self._json({"error": str(e)}, 500)
        super().do_GET()

    def _live(self, file: str) -> None:
        if file == "index.json":
            return self._json(live_index())
        name, _, ext = file.rpartition(".")
        if ext not in ("png", "json", "xml"):
            return self._json({"error": f"no live asset {file}"}, 404)
        if name not in list_sprites() and name.endswith("_tiles") and name[:-6] in sliced_props():
            _, png, data = BUILDS.slices(name[:-6])
        elif name in list_sprites():
            _, png, data, s = BUILDS.get(name)
            if s.kind in ("icons", "font") and ext != "png":
                _, data, xml = BUILDS.game(name)
                if ext == "xml":
                    if xml is None:
                        return self._json({"error": f"{name} is not a font"}, 404)
                    body = xml.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/xml")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
        else:
            return self._json({"error": f"no live asset {file}"}, 404)
        if ext == "xml":
            return self._json({"error": f"no live asset {file}"}, 404)
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


def make_server(port: int, quiet: bool = False) -> http.server.ThreadingHTTPServer:
    """The dashboard's server, not started (port 0: any free port; `pixelforge play` runs one, quiet, in a
    thread)."""
    cls = type("QuietHandler", (Handler,), {"quiet": True}) if quiet else Handler
    handler = lambda *a, **kw: cls(*a, directory=str(root()), **kw)  # noqa: E731
    return http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve(port: int) -> None:
    with make_server(port) as httpd:
        print(f"pixelforge dashboard: http://127.0.0.1:{port}/   ({root()})")
        print("Ctrl+C to stop")
        httpd.serve_forever()
