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
            "pixelforge": {"sprite": sprite.name, "kind": sprite.kind, "view": sprite.view,
                           "class": sprite.size_class, "origin": list(sprite.origin),
                           "anchor": sprite.anchor, "body": dict(zip("xywh", sprite.body_rect())),
                           "animations": anim_info, **({"prop": prop_info(sprite)} if sprite.kind == "prop" else {})},
        },
    }
    return img, data


def prop_info(sprite: Sprite) -> dict:
    """How export/pixelforge.js places a prop: addPixelforgeProp reads this."""
    return {"layer": sprite.layer, "scroll": sprite.scroll, "solid": sprite.solid,
            "footprint": list(sprite.body_rect()), "ysort": sprite.view == "topdown" and sprite.layer == "world",
            "tiles": f"{sprite.name}_tiles" if sprite.slice else None}


def _grid_sheet(sprite: Sprite, grids: list, cols: int, cw: int, ch: int, padding: int) -> tuple[Image.Image, int, int]:
    """Cells of cw x ch left to right, top to bottom, `cols` per row, `padding` px apart."""
    rows = max(1, -(-len(grids) // cols))
    sheet_w, sheet_h = max(1, cols * (cw + padding) - padding), max(1, rows * (ch + padding) - padding)
    img = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    for s, g in enumerate(grids):
        img.alpha_composite(to_image(sprite, g), ((s % cols) * (cw + padding), (s // cols) * (ch + padding)))
    return img, sheet_w, sheet_h


def _tiled_json(name: str, image: str, size: tuple[int, int], tw: int, th: int, padding: int, cols: int,
                names: list[str], props: list[dict], anims: dict[int, list[list[int]]], total: int,
                sample: list, stamps: dict, autotile: dict | None = None) -> dict:
    tiles = []
    for i, (tname, p) in enumerate(zip(names, props)):
        tile = {"id": i, "properties": [_tiled_property("name", tname)]
                + [_tiled_property(k, v) for k, v in p.items()]}
        if i in anims:
            tile["animation"] = [{"tileid": s, "duration": ms} for s, ms in anims[i]]
        tiles.append(tile)
    return {
        "type": "tileset", "version": "1.10", "tiledversion": "1.10.2",
        "name": name, "image": image, "imagewidth": size[0], "imageheight": size[1],
        "tilewidth": tw, "tileheight": th, "margin": 0, "spacing": padding,
        "columns": cols, "tilecount": total, "tiles": tiles,
        # read by export/pixelforge.js (Tiled ignores it): names[i] and properties[i] describe tile i,
        # animations["i"] = [[slot, ms], ...] is the frame sequence the helper plays for tile i,
        # stamps[name] = rows of tile indices (-1 = leave empty) that stampPixelforgeTiles places
        "pixelforge": {"tileset": name, "names": names, "properties": props,
                       "animations": {str(i): a for i, a in anims.items()}, "sample": sample, "stamps": stamps,
                       **({"autotile": autotile} if autotile else {})},
    }


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
    cols = max(1, min(sprite.columns, len(slots)))
    img, sheet_w, sheet_h = _grid_sheet(sprite, [sprite.resolve(e) for e in slots], cols, tw, th, padding)
    names = sprite.tile_names()
    stamps = {n: sprite.stamp_map(n) for n in sprite.stamps}
    data = _tiled_json(sprite.name, f"{sprite.name}.png", (sheet_w, sheet_h), tw, th, padding, cols, names,
                       [sprite.tile_properties(n) for n in names], anims, len(slots), sprite.sample_map(), stamps,
                       sprite.autotile)
    return img, data


def build_slices(sprite: Sprite, padding: int = 1) -> tuple[Image.Image, dict]:
    """A prop with "slice": [tw, th] cut into tiles, as a Tiled tileset named <prop>_tiles, so a
    building drawn as one picture can also be painted into tile maps. Blank cells are dropped. Tile
    properties: `collides` where a solid prop's footprint covers the cell, and (top-down) `above` for
    cells wholly above the footprint (the roof): put those on a layer drawn over the player.
    The whole building is the tileset's sample map and its one stamp."""
    tw, th = sprite.slice
    art = sprite.resolve(next(iter(sprite.animations.values())).frames[0])
    fx, fy, fw, fh = sprite.body_rect()
    nx, ny = -(-sprite.width // tw), -(-sprite.height // th)
    grids, names, props, block = [], [], [], []
    for r in range(ny):
        row = []
        for c in range(nx):
            g = art.crop(c * tw, r * th, tw, th)
            if not g.opaque_count():
                row.append(-1)
                continue
            p: dict = {}
            x0, y0 = c * tw, r * th
            covers = x0 < fx + fw and fx < x0 + tw and y0 < fy + fh and fy < y0 + th
            if sprite.solid and covers:
                p["collides"] = True
            if sprite.view == "topdown" and y0 + th <= fy:
                p["above"] = True
            row.append(len(grids))
            grids.append(g)
            names.append(f"{sprite.name}_r{r}c{c}")
            props.append(p)
        block.append(row)
    name = f"{sprite.name}_tiles"
    cols = max(1, min(nx, len(grids)))
    img, sheet_w, sheet_h = _grid_sheet(sprite, grids, cols, tw, th, padding)
    data = _tiled_json(name, f"{name}.png", (sheet_w, sheet_h), tw, th, padding, cols, names, props, {},
                       len(grids), block, {sprite.name: block})
    return img, data


def build_atlas(sprite: Sprite, padding: int = 1) -> tuple[Image.Image, dict]:
    """Icons as a texture atlas: frames keyed by icon name, so `this.add.image(x, y, 'items', 'potion')`.
    Same JSON-hash layout as sprite sheets, loaded the same way (load.aseprite caches the JSON too)."""
    w, h = sprite.width, sprite.height
    names = sprite.tile_names()
    cols = max(1, min(sprite.columns, len(names)))
    img, sheet_w, sheet_h = _grid_sheet(sprite, [sprite.tile(n) for n in names], cols, w, h, padding)
    frames = {}
    for i, n in enumerate(names):
        x, y = (i % cols) * (w + padding), (i // cols) * (h + padding)
        frames[n] = {"frame": {"x": x, "y": y, "w": w, "h": h}, "rotated": False, "trimmed": False,
                     "spriteSourceSize": {"x": 0, "y": 0, "w": w, "h": h}, "sourceSize": {"w": w, "h": h},
                     "duration": 100}
    data = {"frames": frames,
            "meta": {"app": "pixelforge", "version": "1.0", "image": f"{sprite.name}.png", "format": "RGBA8888",
                     "size": {"w": sheet_w, "h": sheet_h}, "scale": "1", "frameTags": [], "layers": [], "slices": [],
                     # nine[name] = [left, right, top, bottom]: addPixelforgePanel stretches only the middle
                     "pixelforge": {"sprite": sprite.name, "kind": "icons", "icons": names,
                                    "nine": {n: m["nine"] for n, m in sprite.item_meta.items() if "nine" in m}}}}
    return img, data


def build_font(sprite: Sprite, padding: int = 1) -> tuple[Image.Image, dict, str]:
    """A bitmap font: the glyph sheet, a small JSON (for the index and the dashboard) and an AngelCode
    BMFont XML file, which Phaser reads with load.bitmapFont. Without lowercase glyphs, lowercase
    letters reuse the capitals, so `bitmapText` never drops a letter."""
    w, h = sprite.width, sprite.height
    chars = sprite.tile_names()
    cols = max(1, min(sprite.columns, len(chars)))
    img, sheet_w, sheet_h = _grid_sheet(sprite, [sprite.tile(c) for c in chars], cols, w, h, padding)
    entries = []
    for i, c in enumerate(chars):
        x, y = (i % cols) * (w + padding), (i // cols) * (h + padding)
        entries.append((ord(c), x, y, sprite.glyph_widths[c]))
    have = {chr(e[0]) for e in entries}
    if not any(c.islower() for c in have):
        entries += [(ord(c.lower()), x, y, gw) for code, x, y, gw in list(entries)
                    for c in [chr(code)] if c.isupper() and c.lower() not in have]
    entries.append((32, 0, 0, 0))  # space: nothing drawn, just an advance
    sp = sprite.letter_spacing

    def esc(v: str) -> str:
        return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

    lines = ['<?xml version="1.0"?>', "<font>",
             f'  <info face="{esc(sprite.name)}" size="{h}" bold="0" italic="0" charset="" unicode="1" '
             f'stretchH="100" smooth="0" aa="0" padding="0,0,0,0" spacing="{padding},{padding}"/>',
             f'  <common lineHeight="{sprite.line_height}" base="{h}" scaleW="{sheet_w}" scaleH="{sheet_h}" '
             f'pages="1" packed="0"/>',
             f'  <pages><page id="0" file="{esc(sprite.name)}.png"/></pages>',
             f'  <chars count="{len(entries)}">']
    for code, x, y, gw in sorted(entries):
        adv = sprite.space_width if code == 32 else gw + sp
        lines.append(f'    <char id="{code}" x="{x}" y="{y}" width="{gw}" height="{0 if code == 32 else h}" '
                     f'xoffset="0" yoffset="0" xadvance="{adv}" page="0" chnl="15"/>')
    lines += ["  </chars>", "</font>", ""]
    data = {"pixelforge": {"kind": "font", "font": sprite.name, "chars": "".join(chars), "size": [w, h],
                           "lineHeight": sprite.line_height, "spacing": sp, "space": sprite.space_width,
                           "widths": sprite.glyph_widths},
            "image": f"{sprite.name}.png", "xml": f"{sprite.name}.xml"}
    return img, data, "\n".join(lines)


def preview_build(sprite: Sprite, padding: int = 1) -> tuple[Image.Image, dict]:
    """What the dashboard and gallery draw: tile-like kinds as a tileset grid, the rest as sheets."""
    return (build_tileset if sprite.tiled else build_sheet)(sprite, padding)


def export_sprite(sprite: Sprite, out_dir: Path | None = None, padding: int = 1) -> list[Path]:
    """Writes export/<name>.png + .json (and a font's .xml, a sliced prop's <name>_tiles.png/.json).
    Returns every path written, the PNG and JSON first."""
    out = out_dir or export_dir()
    out.mkdir(parents=True, exist_ok=True)
    extra: list[tuple[str, object]] = []
    if sprite.kind == "font":
        img, data, xml = build_font(sprite, padding)
        extra.append((f"{sprite.name}.xml", xml))
    elif sprite.kind == "icons":
        img, data = build_atlas(sprite, padding)
    elif sprite.kind == "tileset":
        img, data = build_tileset(sprite, padding)
    else:
        img, data = build_sheet(sprite, padding)
        if sprite.slice:
            timg, tdata = build_slices(sprite, padding)
            extra += [(f"{sprite.name}_tiles.png", timg), (f"{sprite.name}_tiles.json", tdata)]
    png, js = out / f"{sprite.name}.png", out / f"{sprite.name}.json"
    img.save(png)
    js.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    paths = [png, js]
    for fname, content in extra:
        p = out / fname
        if isinstance(content, Image.Image):
            content.save(p)
        elif isinstance(content, dict):
            p.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
        else:
            p.write_text(content, encoding="utf-8")
        paths.append(p)
    return paths


INDEX_GROUPS = ("sprites", "props", "tilesets", "icons", "fonts", "levels")


def index_group(data: dict) -> str:
    """Which export/index.json list an exported JSON file belongs to."""
    if data.get("type") == "tileset":
        return "tilesets"
    kind = data.get("pixelforge", {}).get("kind") or data.get("meta", {}).get("pixelforge", {}).get("kind")
    return {"prop": "props", "icons": "icons", "font": "fonts"}.get(kind, "sprites")


def write_index(out_dir: Path | None = None) -> Path:
    """export/index.json lists every exported asset by kind (read by the viewer pages)."""
    out = out_dir or export_dir()
    found: dict[str, list[str]] = {g: [] for g in INDEX_GROUPS}
    for js in sorted(out.glob("*.json")):
        if js.stem == "index":
            continue
        try:
            data = json.loads(js.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        found[index_group(data)].append(js.stem)
    found["levels"] = sorted(p.stem for p in (out / "levels").glob("*.json"))
    p = out / "index.json"
    p.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
    return p
