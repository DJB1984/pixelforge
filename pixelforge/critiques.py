"""Critiques: notes the developer leaves on the art in the dashboard (`pixelforge serve`) for Claude to fix.

They live in critiques.json at the project root:
    {"next": 4, "critiques": [{"id": 3, "status": "open", "text": "...", "target": {...},
                               "created": "...", "updated": "...", "note": "..."}]}
A target names an asset and optionally narrows it down:
    sprite:  {"asset": "knight", "anim": "attack", "frame": 2, "region": [x, y, w, h]}
    tileset: {"asset": "terrain", "tile": "water_n", "region": [...]}   or   {"asset": "terrain", "map": true, "region": [...]}
    level:   {"asset": "village", "level": true, "region": [...]}
`region` is in frame (or tile, or sample-map) pixels, the same coordinates as `show` and the hit/hurt boxes;
on a level it's in level pixels (column x 16 for 16px tiles).

Status: open (waiting) -> working (handed to Claude by `critiques watch`) -> fixed (`critiques done`).
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from PIL import ImageDraw

from . import render as rd
from .level import Level, list_levels
from .model import Sprite, SpriteError, describe_entry, list_sprites, root

FILE = "critiques.json"
STATUSES = ("open", "working", "fixed")
WATCH_FRESH_S = 6   # a watcher heartbeat younger than this counts as "Claude is watching"


def path() -> Path:
    return root() / FILE


def _state_dir() -> Path:
    d = root() / "previews"
    d.mkdir(exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _locked():
    """The dashboard server and the CLI both write critiques.json; serialise their read-modify-writes."""
    lock = _state_dir() / ".critiques.lock"
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 10:   # left behind by a crashed writer
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"{lock} is held by another process")
            time.sleep(0.02)
    try:
        yield
    finally:
        os.close(fd)
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def load() -> dict:
    p = path()
    if not p.is_file():
        return {"next": 1, "critiques": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpriteError(f"{p}: invalid JSON: {e}") from None
    data.setdefault("critiques", [])
    data.setdefault("next", max((c["id"] for c in data["critiques"]), default=0) + 1)
    return data


def _save(data: dict) -> None:
    p = path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def all_critiques() -> list[dict]:
    return load()["critiques"]


def get(cid: int) -> dict:
    for c in all_critiques():
        if c["id"] == cid:
            return c
    raise SpriteError(f"no critique #{cid}")


# ---- targets ------------------------------------------------------------------------------
def clean_target(t: dict) -> dict:
    """Validate a target against the project and return it in canonical form."""
    if not isinstance(t, dict) or not isinstance(t.get("asset"), str):
        raise SpriteError("target needs an asset name")
    name = t["asset"]
    if t.get("level"):
        if name not in list_levels():
            raise SpriteError(f"no level {name!r}")
        w, h = Level.load(name).pixel_size
        return _region(t, {"asset": name, "level": True}, w, h)
    if name not in list_sprites():
        raise SpriteError(f"no sprite or tileset {name!r}")
    s = Sprite.load(name)
    out: dict = {"asset": name}
    if s.tiled:
        if t.get("map"):
            if not s.sample_map():
                raise SpriteError(f"{name} has no sample map")
            out["map"] = True
            rows = s.sample_map()
            w, h = max(len(r) for r in rows) * s.width, len(rows) * s.height
        elif t.get("tile") is not None:
            s.tile_index(t["tile"])
            out["tile"] = t["tile"]
            w, h = s.width, s.height
        else:
            w = h = 0
    else:
        if t.get("anim") is not None:
            a = s.anim(t["anim"])
            out["anim"] = a.name
            if t.get("frame") is not None:
                i = int(t["frame"])
                if not 0 <= i < len(a.frames):
                    raise SpriteError(f"{name}:{a.name} has {len(a.frames)} frames, not frame {i}")
                out["frame"] = i
        w, h = (s.width, s.height) if "frame" in out else (0, 0)
    return _region(t, out, w, h)


def _region(t: dict, out: dict, w: int, h: int) -> dict:
    """Adds the target's region (if any), clamped to the w x h surface it sits on."""
    if t.get("region") is not None:
        if not w:
            raise SpriteError("a region needs a frame, tile or map to sit on")
        x, y, rw, rh = (int(v) for v in t["region"])
        x0, y0 = max(0, min(x, w - 1)), max(0, min(y, h - 1))
        x1, y1 = max(x0 + 1, min(x + rw, w)), max(y0 + 1, min(y + rh, h))
        out["region"] = [x0, y0, x1 - x0, y1 - y0]
    return out


def label(t: dict) -> str:
    """knight > attack > frame 2 > spot (24,10 6x5)"""
    parts = [t["asset"]]
    if t.get("level"):
        parts.append("level")
    if "anim" in t:
        parts.append(t["anim"])
    if "frame" in t:
        parts.append(f"frame {t['frame']}")
    if "tile" in t:
        parts.append(f"tile {t['tile']}")
    if t.get("map"):
        parts.append("sample map")
    if "region" in t:
        x, y, w, h = t["region"]
        parts.append(f"spot ({x},{y} {w}x{h})")
    return " > ".join(parts)


def details(t: dict) -> list[str]:
    """What Claude needs to find the art: which frame entry or tile, which layer files."""
    if t.get("level"):
        return _level_details(t)
    try:
        s = Sprite.load(t["asset"])
    except SpriteError as e:
        return [f"(can't load {t['asset']}: {e})"]
    out = []
    if s.tiled:
        if "tile" in t:
            out.append(f"tile {s.tile_index(t['tile'])} {t['tile']}: {describe_entry(s.tiles[s.tile_index(t['tile'])][1])}")
        elif t.get("map") and "region" in t:
            x, y, w, h = t["region"]
            rows = s.sample_map()
            names = s.tile_names()
            seen = []
            for ty in range(y // s.height, (y + h - 1) // s.height + 1):
                for tx in range(x // s.width, (x + w - 1) // s.width + 1):
                    i = rows[ty][tx] if ty < len(rows) and tx < len(rows[ty]) else -1
                    if i >= 0 and names[i] not in seen:
                        seen.append(names[i])
            out.append(f"sample map tiles under the spot: {', '.join(seen) or '(empty)'}")
    else:
        if "frame" in t:
            a = s.anim(t["anim"])
            out.append(f"frame entry: {describe_entry(a.frames[t['frame']])}  ({a.duration_ms(t['frame'])}ms"
                       f"{', active' if a.active(t['frame']) else ''})")
        elif "anim" in t:
            a = s.anim(t["anim"])
            out.append(f"{len(a.frames)} frames at {a.fps:g} fps, {'loops' if a.loop else 'plays once'}")
    return out


def _level_details(t: dict) -> list[str]:
    """Where a level spot is in levels/<name>.json: its rows and columns, the tiles on each layer and
    the objects there."""
    try:
        lv = Level.load(t["asset"])
    except SpriteError as e:
        return [f"(can't load level {t['asset']}: {e})"]
    if "region" not in t:
        return [f"levels/{lv.name}.json: {lv.width}x{lv.height} tiles, {lv.view} view "
                f"(`pixelforge level {lv.name} --screens` shows every screen)"]
    x, y, w, h = t["region"]
    c0, c1 = x // lv.tile_w, min(lv.width - 1, (x + w - 1) // lv.tile_w)
    r0, r1 = y // lv.tile_h, min(lv.height - 1, (y + h - 1) // lv.tile_h)
    span = lambda a, b: f"{a}" if a == b else f"{a}-{b}"
    out = [f"levels/{lv.name}.json: rows {span(r0, r1)}, columns {span(c0, c1)} (0-based: character {c0} of rows[{r0}] "
           f"is the top-left cell)"]
    for layer in lv.layers:
        seen = []
        for cy in range(r0, r1 + 1):
            for cx in range(c0, c1 + 1):
                n = lv.tile_name(layer.cells[cy][cx])
                if n and n not in seen:
                    seen.append(n)
        if seen:
            out.append(f"layer {layer.name}{' (above)' if layer.above else ''}: {', '.join(seen)}")
    objs = []
    for o in lv.objects:
        ox, oy, ow, oh = o.rect or o.art or (o.x, o.y - 1, 1, 1)
        if ox < x + w and x < ox + ow and oy < y + h and y < oy + oh:
            what = o.name if o.type in (o.name, "prop", "sprite") else f"{o.name} ({o.type})"
            objs.append(f"{what} at ({o.x}, {o.y}) from {o.source}")
    out.append("objects: " + ("; ".join(objs) if objs else "none"))
    return out


# ---- changes ------------------------------------------------------------------------------
def add(target: dict, text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise SpriteError("a critique needs some text")
    target = clean_target(target)
    with _locked():
        data = load()
        now = _now()
        c = {"id": data["next"], "status": "open", "text": text, "target": target, "created": now, "updated": now}
        data["next"] += 1
        data["critiques"].append(c)
        _save(data)
    return c


def update(cid: int, **fields) -> dict:
    with _locked():
        data = load()
        for c in data["critiques"]:
            if c["id"] == cid:
                if "status" in fields and fields["status"] not in STATUSES:
                    raise SpriteError(f"status must be one of {', '.join(STATUSES)}")
                c.update({k: v for k, v in fields.items() if v is not None})
                if fields.get("status") == "open":
                    c.pop("note", None)
                c["updated"] = _now()
                _save(data)
                return c
    raise SpriteError(f"no critique #{cid}")


def delete(cid: int) -> None:
    with _locked():
        data = load()
        kept = [c for c in data["critiques"] if c["id"] != cid]
        if len(kept) == len(data["critiques"]):
            raise SpriteError(f"no critique #{cid}")
        data["critiques"] = kept
        _save(data)


# ---- watching -----------------------------------------------------------------------------
def _beat_path() -> Path:
    return _state_dir() / ".critiques-watch"


def watching() -> bool:
    try:
        return time.time() - _beat_path().stat().st_mtime < WATCH_FRESH_S
    except FileNotFoundError:
        return False


def summary_line(c: dict) -> str:
    return f"critique #{c['id']} on {label(c['target'])}: {c['text']}"


def watch(once: bool, emit=print, interval: float = 1.0, stop=None) -> None:
    """Hand open critiques to Claude as they arrive, marking each one `working`.
    once: wait until at least one is open, hand over every open one, return."""
    beat = _beat_path()
    try:
        while not (stop and stop()):
            beat.write_text(str(os.getpid()), encoding="utf-8")
            pending = [c for c in all_critiques() if c["status"] == "open"]
            for c in pending:
                update(c["id"], status="working")
                emit(summary_line(c))
            if pending and once:
                emit("fix each one, then: pixelforge critiques done ID -m \"what you changed\"")
                return
            time.sleep(interval)
    finally:
        try:
            beat.unlink()
        except FileNotFoundError:
            pass


# ---- pictures -----------------------------------------------------------------------------
def render_target(c: dict) -> Path:
    """previews/critique_<id>.png: the critiqued frame / tile / map / animation, the spot outlined."""
    t = c["target"]
    region = t.get("region")
    out = _state_dir() / f"critique_{c['id']}.png"
    if t.get("level"):
        _level_picture(t, region).save(out)
        return out
    s = Sprite.load(t["asset"])
    if s.tiled:
        if "tile" in t:
            img = rd.preview(s, s.tile(t["tile"]), scale=16, title=label(t), show_origin=False, marks=[region] if region else None)
        else:
            rows = s.sample_map()
            scale = 4
            art = rd.zoom(rd.map_image(s, rows), scale) if rows else rd.tileset_preview(s)
            if region and rows:
                _outline(ImageDraw.Draw(art), region, scale)
            img = art
    elif "frame" in t:
        a = s.anim(t["anim"])
        g = s.anim_frames(a.name)[t["frame"]]
        img = rd.preview(s, g, scale=rd.auto_scale(g.width, g.height, most=12), title=label(t), marks=[region] if region else None)
    else:
        img = rd.sheet(s, [t["anim"]] if "anim" in t else list(s.animations), scale=6)
    img.save(out)
    return out


def _level_picture(t: dict, region):
    """A screen's worth of level around the spot at 3x (outlined), and the whole level at 1x with the
    spot marked; with no spot, the level overview."""
    from .screens import compose, level_overview
    lv = Level.load(t["asset"])
    if not region:
        return level_overview(lv)[0]
    world = compose(lv).world()
    W, H = lv.pixel_size
    sw, sh = lv.screen_size()
    x, y, w, h = region
    x0 = max(0, min(x + w // 2 - sw // 2, W - sw))
    y0 = max(0, min(y + h // 2 - sh // 2, H - sh))
    crop = world.crop((x0, y0, min(W, x0 + sw), min(H, y0 + sh)))
    scale = 3
    near = rd.zoom(crop, scale)
    _outline(ImageDraw.Draw(near), [x - x0, y - y0, w, h], scale)
    whole = world.copy()
    _outline(ImageDraw.Draw(whole), region, 1)
    return rd.stack([(f"{label(t)}   (x{scale}: level pixels {x0},{y0} to {x0 + crop.width},{y0 + crop.height})", near),
                     ("the whole level, 1x", whole)])


def _outline(d: ImageDraw.ImageDraw, region, scale: int) -> None:
    x, y, w, h = region
    x0, y0, x1, y1 = x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1
    d.rectangle([x0 - 1, y0 - 1, x1 + 1, y1 + 1], outline=(0, 0, 0, 255), width=1)
    d.rectangle([x0, y0, x1, y1], outline=rd.MARK_COLOR, width=max(1, scale // 6))

