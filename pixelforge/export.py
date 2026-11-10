"""Export sprite sheets as PNG + Aseprite-format JSON (loadable by Phaser's load.aseprite)."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .boxes import anim_boxes
from .model import Sprite, root
from .render import to_image


def export_dir() -> Path:
    return root() / "export"


def build_sheet(sprite: Sprite, padding: int = 1) -> tuple[Image.Image, dict]:
    """One row per animation. Frame keys are "0".."N-1" in playback order, which is what
    Phaser's createFromAseprite expects. Tag names are "<sprite>_<anim>" so several
    characters can share Phaser's global animation namespace."""
    anims = list(sprite.animations.values())
    cols = max((len(a.frames) for a in anims), default=1)
    cw, ch = sprite.width + padding, sprite.height + padding
    sheet_w, sheet_h = max(1, cols * cw - padding), max(1, len(anims) * ch - padding)
    img = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    pivot = {"x": sprite.origin[0] / sprite.width, "y": sprite.origin[1] / sprite.height}

    frames: dict[str, dict] = {}
    tags, anim_info = [], {}
    n = 0
    for row, a in enumerate(anims):
        start = n
        boxes = anim_boxes(sprite, a.name)
        for col, grid in enumerate(sprite.anim_frames(a.name)):
            x, y = col * cw, row * ch
            img.alpha_composite(to_image(sprite, grid), (x, y))
            frames[str(n)] = {
                "frame": {"x": x, "y": y, "w": sprite.width, "h": sprite.height},
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": sprite.width, "h": sprite.height},
                "sourceSize": {"w": sprite.width, "h": sprite.height},
                "pivot": pivot,
                "duration": a.duration_ms(col),
                # [x, y, w, h] in frame pixels; read by export/pixelforge.js (Phaser ignores it)
                "pixelforge": boxes[col],
            }
            n += 1
        tag = f"{sprite.name}_{a.name}"
        tags.append({"name": tag, "from": start, "to": n - 1, "direction": "forward",
                     "color": "#000000ff"})
        anim_info[tag] = {"anim": a.name, "loop": a.loop, "fps": a.fps, "frames": n - start}

    data = {
        "frames": frames,
        "meta": {
            "app": "pixelforge",
            "version": "1.0",
            "image": f"{sprite.name}.png",
            "format": "RGBA8888",
            "size": {"w": sheet_w, "h": sheet_h},
            "scale": "1",
            "frameTags": tags,
            "layers": [],
            "slices": [],
            "pixelforge": {"sprite": sprite.name, "class": sprite.size_class, "origin": list(sprite.origin),
                           "anchor": sprite.anchor, "body": dict(zip("xywh", sprite.body_rect())),
                           "animations": anim_info},
        },
    }
    return img, data


def _tiled_property(name: str, value) -> dict:
    kind = ("bool" if isinstance(value, bool) else "int" if isinstance(value, int)
            else "float" if isinstance(value, float) else "string")
    return {"name": name, "type": kind, "value": value if kind != "string" else str(value)}


def build_tileset(sprite: Sprite, padding: int = 1) -> tuple[Image.Image, dict]:
    """Tiles left to right, top to bottom, `columns` per row: tile i (its position in sprite.json
    "tiles") sits at column i % columns, row i // columns, which is the index Phaser and Tiled use.
    The JSON is a Tiled tileset (.tsj), so Tiled can open it directly; Phaser only needs the PNG
    plus the tile size, margin 0 and spacing (= padding).

    An animated tile's first frame is the tile itself; its other frames go in extra slots after the
    last named tile, so adding animation frames never renumbers tiles that maps already use."""
    tw, th = sprite.width, sprite.height
    n = len(sprite.tiles)
    slots: list = [entry for _, entry in sprite.tiles]
    anims: dict[int, list[list[int]]] = {}   # tile id -> [[slot, ms], ...]
    for i, (name, _) in enumerate(sprite.tiles):
        if name in sprite.tile_anims:
            frames = sprite.tile_anims[name]
            anims[i] = [[i, frames[0][1]]]
            for entry, ms in frames[1:]:
                anims[i].append([len(slots), ms])
                slots.append(entry)
    total = len(slots)
    cols = max(1, min(sprite.columns, total))
    rows = max(1, -(-total // cols))
    sheet_w, sheet_h = cols * (tw + padding) - padding, rows * (th + padding) - padding
    img = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for s, entry in enumerate(slots):
        img.alpha_composite(to_image(sprite, sprite.resolve(entry)),
                            ((s % cols) * (tw + padding), (s // cols) * (th + padding)))
    tiles, props = [], []
    for i, (name, _) in enumerate(sprite.tiles):
        p = sprite.tile_properties(name)
        props.append(p)
        tile = {"id": i, "properties": [_tiled_property("name", name)]
                + [_tiled_property(k, v) for k, v in p.items()]}
        if i in anims:
            tile["animation"] = [{"tileid": s, "duration": ms} for s, ms in anims[i]]
        tiles.append(tile)
    data = {
        "type": "tileset", "version": "1.10", "tiledversion": "1.10.2",
        "name": sprite.name, "image": f"{sprite.name}.png", "imagewidth": sheet_w, "imageheight": sheet_h,
        "tilewidth": tw, "tileheight": th, "margin": 0, "spacing": padding,
        "columns": cols, "tilecount": total, "tiles": tiles,
        # read by export/pixelforge.js (Tiled ignores it): names[i] and properties[i] describe tile i,
        # animations["i"] = [[slot, ms], ...] is the frame sequence the helper plays for tile i
        "pixelforge": {"tileset": sprite.name, "names": sprite.tile_names(), "properties": props,
                       "animations": {str(i): a for i, a in anims.items()}, "sample": sprite.sample_map()},
    }
    return img, data


def export_sprite(sprite: Sprite, out_dir: Path | None = None, padding: int = 1) -> tuple[Path, Path]:
    out = out_dir or export_dir()
    out.mkdir(parents=True, exist_ok=True)
    img, data = (build_tileset if sprite.kind == "tileset" else build_sheet)(sprite, padding)
    png, js = out / f"{sprite.name}.png", out / f"{sprite.name}.json"
    img.save(png)
    js.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return png, js


def write_index(out_dir: Path | None = None) -> Path:
    """export/index.json lists every exported sprite and tileset (read by the viewer pages)."""
    out = out_dir or export_dir()
    found: dict[str, list[str]] = {"sprites": [], "tilesets": []}
    for js in sorted(out.glob("*.json")):
        if js.stem == "index":
            continue
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        found["tilesets" if data.get("type") == "tileset" else "sprites"].append(js.stem)
    p = out / "index.json"
    p.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
    return p
