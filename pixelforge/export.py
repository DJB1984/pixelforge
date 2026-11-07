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
                           "body": dict(zip("xywh", sprite.body_rect())), "animations": anim_info},
        },
    }
    return img, data


def export_sprite(sprite: Sprite, out_dir: Path | None = None, padding: int = 1) -> tuple[Path, Path]:
    out = out_dir or export_dir()
    out.mkdir(parents=True, exist_ok=True)
    img, data = build_sheet(sprite, padding)
    png, js = out / f"{sprite.name}.png", out / f"{sprite.name}.json"
    img.save(png)
    js.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return png, js


def write_index(names: list[str], out_dir: Path | None = None) -> Path:
    """export/index.json lists every exported sprite (used by viewer/index.html)."""
    out = out_dir or export_dir()
    p = out / "index.json"
    p.write_text(json.dumps({"sprites": sorted(names)}, indent=2) + "\n", encoding="utf-8")
    return p
