"""Import PNGs (single frames, uniform sheets, or Aseprite/pixelforge atlases) into a sprite."""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from .grid import TRANSPARENT, Grid
from .model import RGBA, Sprite, sprites_dir, to_hex

KEY_POOL = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#@$%&*+=?<>/~^!"


class Palette:
    """Maps RGBA colors to single-char keys, reusing an existing sprite palette if given."""

    def __init__(self, existing: Sprite | None = None):
        self.raw: dict[str, str] = dict(existing.palette_raw) if existing else {}
        self.by_color: dict[RGBA, str] = {}
        if existing:
            for k, rgba in existing.palette.items():
                self.by_color.setdefault(rgba, k)

    def key_for(self, rgba: RGBA) -> str:
        if rgba[3] == 0:
            return TRANSPARENT
        if rgba in self.by_color:
            return self.by_color[rgba]
        free = next((c for c in KEY_POOL if c not in self.raw), None)
        if free is None:
            raise ValueError(f"image uses more than {len(KEY_POOL)} colors; reduce colors first")
        self.raw[free] = to_hex(rgba)
        self.by_color[rgba] = free
        return free


def image_to_grid(img: Image.Image, pal: Palette) -> Grid:
    img = img.convert("RGBA")
    g = Grid.blank(img.width, img.height)
    px = img.load()
    for y in range(img.height):
        for x in range(img.width):
            g.cells[y][x] = pal.key_for(px[x, y])
    return g


def import_png(png: Path, name: str, cell: tuple[int, int] | None = None, padding: int = 0,
               anim: str = "imported", fps: float = 8, atlas: Path | None = None) -> Sprite:
    """Create or extend sprites/<name>/ from a PNG.

    - atlas: an Aseprite/pixelforge JSON; frames are sliced per its rects and grouped by frameTags.
      Auto-detected when <png stem>.json sits next to the PNG.
    - cell: slice a uniform sheet (left->right, top->bottom) into one animation.
    - neither: the whole PNG is one frame.
    """
    img = Image.open(png).convert("RGBA")
    if atlas is None and png.with_suffix(".json").is_file():
        atlas = png.with_suffix(".json")

    path = sprites_dir() / name
    existing = Sprite.load(name) if (path / "sprite.json").is_file() else None
    pal = Palette(existing)

    anims: dict[str, dict] = {}
    frames_out: dict[str, Grid] = {}
    if atlas is not None:
        data = json.loads(atlas.read_text(encoding="utf-8"))
        fr = data["frames"]
        if isinstance(fr, list):  # JSON-array flavour
            fr = {f.get("filename", str(i)): f for i, f in enumerate(fr)}
        keys = list(fr)
        meta = data.get("meta", {})
        info = meta.get("pixelforge", {}).get("animations", {})
        tags = meta.get("frameTags") or [{"name": anim, "from": 0, "to": len(keys) - 1}]
        first = fr[keys[0]]["frame"]
        w, h = first["w"], first["h"]
        for tag in tags:
            ti = info.get(tag["name"], {})
            aname = ti.get("anim", tag["name"])
            ids = []
            for i in range(tag["from"], tag["to"] + 1):
                f = fr[keys[i]]
                r = f["frame"]
                fid = f"{aname}_{i - tag['from']}"
                frames_out[fid] = image_to_grid(img.crop((r["x"], r["y"], r["x"] + r["w"], r["y"] + r["h"])), pal)
                ids.append(fid)
            durations = [fr[keys[i]].get("duration", 100) for i in range(tag["from"], tag["to"] + 1)]
            a_fps = ti.get("fps") or round(1000 / (sum(durations) / len(durations)), 2)
            default_ms = round(1000 / a_fps)
            # keep per-frame timing wherever it differs from the animation's fps
            entries = [fid if d == default_ms else {"from": fid, "duration": d} for fid, d in zip(ids, durations)]
            anims[aname] = {"fps": a_fps, "loop": ti.get("loop", True), "frames": entries}
        origin = meta.get("pixelforge", {}).get("origin")
    else:
        w, h = cell or img.size
        ids = []
        i = 0
        for y in range(0, img.height - h + 1, h + padding):
            for x in range(0, img.width - w + 1, w + padding):
                g = image_to_grid(img.crop((x, y, x + w, y + h)), pal)
                if g.opaque_count() == 0:
                    continue
                fid = f"{anim}_{i}"
                frames_out[fid] = g
                ids.append(fid)
                i += 1
        anims[anim] = {"fps": fps, "loop": True, "frames": ids}
        origin = None

    (path / "frames").mkdir(parents=True, exist_ok=True)
    for fid, g in frames_out.items():
        (path / "frames" / f"{fid}.txt").write_text(g.to_text(), encoding="utf-8")

    meta_path = path / "sprite.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {
        "name": name, "size": [w, h], "origin": origin or [w // 2, h], "palette": {}, "animations": {}}
    meta["palette"] = pal.raw
    meta.setdefault("animations", {}).update(anims)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return Sprite.load(name)
