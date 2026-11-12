"""pixelforge CLI.  Run `python -m pixelforge -h` or `python -m pixelforge <cmd> -h`."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from . import compare as cmp
from . import critiques as cq
from . import context as cx
from . import export as ex
from . import level as lvl
from . import model
from . import motion
from . import render as rd
from .boxes import frame_boxes
from .gallery import render_gallery
from .grid import TRANSPARENT, Grid
from .importer import import_png
from .model import ASSETS, Sprite, SpriteError, list_sprites, root, sprites_dir
from .project import init_project, upgrade_project
from .server import serve
from .validate import check

_rel = model.rel


def _previews() -> Path:
    d = root() / "previews"
    d.mkdir(exist_ok=True)
    return d


def _size(s: str) -> tuple[int, int]:
    w, _, h = s.lower().partition("x")
    return int(w), int(h or w)


def _frame_target(s: Sprite, anim: str, index: str):
    """`anim index`, `@frame_id` or (tilesets) `tile_name` addressing. Returns (grid, label, prev, next)."""
    if anim.startswith("@"):
        fid = anim[1:]
        part = s.layer_path(fid) == s.part_path(fid)
        return s.load_layer(fid, strict=False), f"{s.name} @{fid}{' (part)' if part else ''}", None, None
    if s.tiled:
        return s.tile(anim), f"{s.name} tile {s.tile_index(anim)} {anim}", None, None
    a = s.anim(anim)
    i = int(index) % len(a.frames)
    frames = s.anim_frames(anim)
    n = len(frames)
    prev = frames[i - 1] if (i > 0 or a.loop) and n > 1 else None
    nxt = frames[(i + 1) % n] if (i < n - 1 or a.loop) and n > 1 else None
    return frames[i], f"{s.name}:{anim}[{i}]  {a.duration_ms(i)}ms", prev, nxt


# ---- commands -------------------------------------------------------------------------------
def cmd_list(args):
    for n in list_sprites():
        s = Sprite.load(n)
        if s.tiled:
            noun = {"icons": "icons", "font": "glyphs"}.get(s.kind, "tiles")
            names = "".join(s.tile_names()) if s.kind == "font" else \
                ", ".join(s.tile_names()[:6]) + (", ..." if len(s.tiles) > 6 else "")
            print(f"{n:16} {s.width}x{s.height}  {len(s.palette)} colors  {s.kind}: {len(s.tiles)} {noun} ({names})"
                  + (f"  stamps: {', '.join(s.stamps)}" if s.stamps else ""))
            continue
        anims = ", ".join(f"{k}({len(a.frames)})" for k, a in s.animations.items())
        what = (f"prop ({s.layer}{', solid' if s.solid else ''}{f', scroll {s.scroll:g}' if s.scroll != 1 else ''}"
                f"{', sliced' if s.slice else ''})  ") if s.kind == "prop" else ""
        print(f"{n:16} {s.width}x{s.height}  {len(s.palette)} colors  {what}{anims}")
    for n in lvl.list_levels():
        try:
            lv = lvl.Level.load(n)
        except SpriteError as e:
            print(f"{n:16} level: error: {e}")
            continue
        types = {}
        for o in lv.objects:
            types[o.type] = types.get(o.type, 0) + 1
        print(f"{n:16} level  {lv.width}x{lv.height} tiles ({lv.pixel_size[0]}x{lv.pixel_size[1]} px)  {lv.view}  "
              f"{', '.join(lv.tilesets)}  layers: {', '.join(l.name for l in lv.layers)}  objects: "
              + (", ".join(f"{k} {v}" for k, v in types.items()) or "none"))


def _split(names: list[str]) -> tuple[list[str], list[str]]:
    """Names given on the command line -> (sprites, levels). No names: every sprite and level."""
    if not names:
        return list_sprites(), lvl.list_levels()
    levels = set(lvl.list_levels())
    return [n for n in names if n not in levels], [n for n in names if n in levels]


def cmd_new_level(args):
    try:
        p = lvl.new_level(args.name, _size(args.size) if args.size else None, args.tileset, args.player)
    except SpriteError as e:
        sys.exit(str(e))
    lv = lvl.Level.load(args.name)
    print(f"created {_rel(p)}: {lv.width}x{lv.height} tiles of {lv.tileset}, {lv.view} view, a spawn ('@') in "
          f"objects.rows, " + (f"played as {lv.player}" if lv.player else
                               "no player yet (draw a character, then set \"player\")"))


def cmd_level(args):
    from . import screens as sc
    try:
        lv = lvl.Level.load(args.name)
    except SpriteError as e:
        sys.exit(str(e))
    if args.at:
        try:
            tx, ty = (int(v) for v in args.at.replace(" ", "").split(","))
        except ValueError:
            sys.exit(f"--at takes a tile as X,Y, got {args.at!r}")
        cam = sc.centred(lv, tx, ty)
        img, lines = sc.screens_sheet(lv, [cam], f"{lv.name} at tile ({tx}, {ty})")
        out = _previews() / f"level_{lv.name}_at_{tx}_{ty}.png"
    elif args.screens:
        img, lines = sc.screens_sheet(lv)
        out = _previews() / f"level_{lv.name}_screens.png"
    else:
        img, lines = sc.level_overview(lv)
        out = _previews() / f"level_{lv.name}.png"
    for line in lines:
        print(line)
    img.save(out)
    print(_rel(out))


def cmd_new(args):
    path = sprites_dir() / args.name
    if path.exists():
        sys.exit(f"{_rel(path)} already exists")
    meta: dict = {"name": args.name}
    if args.tileset:
        w, h = _size(args.size or "16")
        meta.update({"type": "tileset", "size": [w, h], "columns": model.TILE_COLUMNS,
                     "palette": {"k": "outline", "g": "green", "G": "forest"},
                     "tiles": ["tile_0"], "properties": {"wall*": {"collides": True}}})
        (path / "frames").mkdir(parents=True)
        (path / "frames" / "tile_0.txt").write_text(Grid.blank(w, h).to_text(), encoding="utf-8")
        (path / "sprite.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        print(f"created {_rel(path)}/sprite.json and frames/tile_0.txt ({w}x{h} tileset)")
        return
    if args.icons or args.font:
        return _new_ui(args, path, meta)
    if args.prop or args.building:
        return _new_prop(args, path, meta)
    args.cls = args.cls or model.VIEW_CLASS[model.game_view()]
    if args.size:
        w, h = _size(args.size)
        meta.update(size=[w, h], origin=[w // 2, h])
    else:
        classes = model.size_classes()
        if args.cls not in classes:
            sys.exit(f"unknown class {args.cls!r}; known: {', '.join(classes)}")
        w, h = classes[args.cls]["size"]
        meta["class"] = args.cls
    meta.update({
        "palette": {"k": "outline", "w": "white"},
        "roles": {"weapon*": "hit", "fx_*": "hit"},
        # top-down animations are <action>_<down|up|side> (playFacing and the player controller rely on it)
        "animations": {"idle_down" if args.cls == "topdown" and not args.size else "idle":
                       {"fps": 4, "loop": True, "frames": ["idle_0"]}},
    })
    (path / "frames").mkdir(parents=True)
    (path / "frames" / "idle_0.txt").write_text(Grid.blank(w, h).to_text(), encoding="utf-8")
    (path / "sprite.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"created {_rel(path)}/sprite.json and frames/idle_0.txt ({w}x{h}"
          f"{', class ' + args.cls if not args.size else ''})")


def _write_new(path: Path, meta: dict, frames: dict[str, Grid], parts: dict[str, Grid] | None = None) -> None:
    for sub, files in (("frames", frames), ("parts", parts or {})):
        if files:
            (path / sub).mkdir(parents=True, exist_ok=True)
        for fid, g in files.items():
            (path / sub / f"{fid}.txt").write_text(g.to_text(), encoding="utf-8")
    (path / "sprite.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


BUILDING_SIZE = {"side": (96, 80), "topdown": (64, 80), "overhead": (64, 64)}


def _new_prop(args, path: Path, meta: dict) -> None:
    """A prop (object, decoration, background accent) or, with --building, a building made of parts."""
    view = model.game_view()
    if args.size:
        w, h = _size(args.size)
    else:
        w, h = BUILDING_SIZE[view] if args.building else (32, 32)
    meta.update({"type": "prop", "size": [w, h], "origin": [w // 2, h // 2] if view == "overhead" else [w // 2, h]})
    parts: dict[str, Grid] = {}
    if not args.building:
        meta.update(palette={"k": "outline", "w": "white"}, animations={"idle": {"fps": 4, "frames": ["idle_0"]}})
        if view == "topdown":
            meta["footprint"] = [w // 4, h - max(4, h // 4), w // 2, max(4, h // 4)]
        _write_new(path, meta, {"idle_0": Grid.blank(w, h)})
        print(f"created {_rel(path)}/sprite.json and frames/idle_0.txt ({w}x{h} prop, {view} view)")
        return
    dw, dh = 12, min(20, h // 3)
    meta.update({
        "palette": {"k": "outline", "w": "white", "b": "brown", "B": "dark_brown", "r": "rust", "R": "crimson",
                    "g": "light_gray", "G": "gray"},
        "animations": {"closed": {"frames": [{"layers": [
            "walls", "roof",
            {"part": "door", "at": [w // 2 - dw // 2, h - dh]},
            {"part": "window", "at": [[w // 5 - 4, h - dh - 2], [w - w // 5 - 4, h - dh - 2]]}]}]}},
        "slice": [16, 16],
    })
    if view == "topdown":
        meta["footprint"] = [0, 16, w, h - 16]   # the house stands on everything but the roof's top edge (walk-behind)
    elif view == "side":
        meta["solid"] = False   # side-view houses are scenery the player walks in front of
    parts = {"door": Grid.blank(dw, dh), "window": Grid.blank(8, 8)}
    _write_new(path, meta, {"walls": Grid.blank(w, h), "roof": Grid.blank(w, h)}, parts)
    print(f"created {_rel(path)}/sprite.json, frames/walls.txt + roof.txt ({w}x{h}) and parts/door.txt "
          f"({dw}x{dh}) + window.txt (8x8): a {view}-view building, sliced into 16x16 tiles on export")


def _new_ui(args, path: Path, meta: dict) -> None:
    if args.icons:
        w, h = _size(args.size or "16")
        meta.update({"type": "icons", "size": [w, h], "columns": model.TILE_COLUMNS,
                     "palette": {"k": "outline", "w": "white"}, "icons": ["icon_0"]})
        _write_new(path, meta, {"icon_0": Grid.blank(w, h)})
        print(f"created {_rel(path)}/sprite.json and frames/icon_0.txt ({w}x{h} icons)")
        return
    w, h = _size(args.size or "5x7")
    template = ASSETS / "font_5x7.txt"
    meta.update({"type": "font", "size": [w, h], "spacing": 1, "space": 3, "line_height": h + 3,
                 "palette": {"#": "white", "k": "outline"}})
    path.mkdir(parents=True)
    if (w, h) == (5, 7):
        shutil.copyfile(template, path / "glyphs.txt")
        note = "a starter 5x7 font (A-Z, 0-9, punctuation): restyle it or draw your own"
    else:
        (path / "glyphs.txt").write_text("= A\n" + (("." * w) + "\n") * h, encoding="utf-8")
        note = f"one blank {w}x{h} glyph to start from"
    (path / "sprite.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"created {_rel(path)}/sprite.json and glyphs.txt ({note})")


def cmd_resize(args):
    """Re-canvas every frame file, keeping the character on its origin (anchor: bottom-centre)."""
    meta_path = sprites_dir() / args.sprite / "sprite.json"
    s = Sprite.load(args.sprite)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if args.cls:
        classes = model.size_classes()
        if args.cls not in classes:
            sys.exit(f"unknown class {args.cls!r}; known: {', '.join(classes)}")
        w, h = classes[args.cls]["size"]
        nox, noy = classes[args.cls].get("origin", [w // 2, h])
    elif args.size:
        w, h = _size(args.size)
        nox, noy = w // 2, h
    else:
        sys.exit("give a size (e.g. 64x48) or --class")
    dx, dy = nox - s.origin[0], noy - s.origin[1]
    lost = []
    for fid in s.frame_ids():
        g = s.load_frame(fid, strict=False)
        out = Grid.blank(w, h)
        for y, row in enumerate(g.cells):
            for x, c in enumerate(row):
                if c != TRANSPARENT:
                    if 0 <= x + dx < w and 0 <= y + dy < h:
                        out.cells[y + dy][x + dx] = c
                    else:
                        lost.append(fid)
        s.frame_path(fid).write_text(out.to_text(), encoding="utf-8")
    for key in ("size", "origin", "body"):
        meta.pop(key, None)
    if args.cls:
        meta["class"] = args.cls
    else:
        meta.pop("class", None)
        meta.update(size=[w, h], origin=[nox, noy])
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"{s.name}: {s.width}x{s.height} -> {w}x{h}, content moved by ({dx}, {dy}), "
          f"{len(s.frame_ids())} frame files")
    if lost:
        print(f"warning: pixels fell outside the new canvas in: {', '.join(sorted(set(lost)))}")


def cmd_show(args):
    s = Sprite.load(args.sprite)
    g, label, _, _ = _frame_target(s, args.anim, args.index)
    print(label)
    print(g.to_ruled_text())
    used = sorted(g.keys())
    print("keys: " + "  ".join(f"{k}={s.palette_raw.get(k, '??UNDEFINED')}" for k in used))


def cmd_render(args):
    s = Sprite.load(args.sprite)
    g, label, prev, nxt = _frame_target(s, args.anim, args.index)
    part = args.anim.startswith("@") and s.layer_path(args.anim[1:]) == s.part_path(args.anim[1:])
    boxes = None
    if not args.no_boxes and not s.tiled and not part:
        if args.anim.startswith("@"):  # a raw layer: show its role as if active
            boxes = frame_boxes(s, args.anim[1:], active=True)
        else:
            a = s.anim(args.anim)
            i = int(args.index) % len(a.frames)
            boxes = frame_boxes(s, a.frames[i], a.active(i))
            if a.active(i):
                label += "  ACTIVE"
    if s.kind == "prop" and not part:
        label += f"  footprint {list(s.body_rect())}" + (f"  slice {s.slice[0]}x{s.slice[1]}" if s.slice else "")
    img = rd.preview(s, g, scale=args.scale or rd.auto_scale(g.width, g.height), title=label,
                     prev=prev if args.onion else None, nxt=nxt if args.onion else None,
                     gridlines=not args.no_grid, boxes=boxes, show_origin=not s.tiled and not part,
                     slices=s.slice if s.kind == "prop" and not part else None)
    tag = args.anim.lstrip("@") + ("" if args.anim.startswith("@") or s.tiled else f"_{int(args.index)}")
    out = Path(args.out) if args.out else _previews() / f"{s.name}_{tag}{'_onion' if args.onion else ''}.png"
    img.save(out)
    print(_rel(out))


def cmd_tiles(args):
    s = Sprite.load(args.tileset)
    if not s.tiled:
        sys.exit(f"{s.name} is a {s.kind}, not a tileset/icons/font; use `sheet` for it")
    if s.kind == "font":   # `tiles myfont "GAME OVER"`: the words, set in the font
        img = rd.font_preview(s, [" ".join(args.tiles)] if args.tiles else None, scale=args.scale)
        out = _previews() / f"{s.name}_font.png"
        img.save(out)
        print(_rel(out))
        return
    for t in args.tiles:
        s.tile_index(t)
    repeat = args.repeat if s.kind == "tileset" else 1   # icons don't repeat edge to edge
    img = rd.tileset_preview(s, args.tiles or None, scale=args.scale, repeat=repeat)
    out = _previews() / f"{s.name}_tiles{'_' + '_'.join(args.tiles) if args.tiles else ''}.png"
    img.save(out)
    print(_rel(out))


def cmd_sheet(args):
    s = Sprite.load(args.sprite)
    if s.tiled:
        args.tileset, args.tiles, args.repeat, args.scale = args.sprite, [], 3, args.scale or 4
        return cmd_tiles(args)
    anims = args.anims or list(s.animations)
    for a in anims:
        s.anim(a)
    img = rd.sheet(s, anims, scale=args.scale or rd.auto_scale(s.width, s.height, most=6, budget=500),
                   onion=args.onion, boxes=args.boxes)
    suffix = ("_" + "_".join(args.anims) if args.anims else "") + ("_onion" if args.onion else "")
    out = _previews() / f"{s.name}_sheet{suffix}.png"
    img.save(out)
    print(_rel(out))


def cmd_motion(args):
    s = Sprite.load(args.sprite)
    if s.tiled:
        sys.exit(f"{s.name} is a tileset; `tiles {s.name}` shows its animated tiles frame by frame")
    for a in args.anims or list(s.animations):
        fm = motion.measure(s, a)
        print(motion.table(s, a, fm))
        for n in motion.notes(s, a, fm):
            print(f"  - {n}")
        out = _previews() / f"{s.name}_{a}_motion.png"
        motion.chart(s, a, fm).save(out)
        print(_rel(out) + "\n")


def cmd_compare(args):
    s = Sprite.load(args.sprite)
    with cmp.sprite_at(s.name, args.ref) as before:
        if args.target is None:
            lines, img = cmp.compare_all(before, s, args.scale, args.ref)
            print(f"{s.name}: working tree vs {args.ref}")
            for line in lines:
                print(f"  {line}")
            if img is not None:
                out = _previews() / f"{s.name}_compare.png"
                img.save(out)
                print(_rel(out))
            return
        if before is None:
            sys.exit(f"{s.name} is not in {args.ref}: nothing to compare against")
        if args.target.startswith("@"):
            fid, label = args.target[1:], args.target
            b = rd.to_image(before, before.load_frame(fid, strict=False)) if before.frame_path(fid).is_file() else None
            a = rd.to_image(s, s.load_frame(fid, strict=False))
        elif s.tiled:
            label = args.target
            b = rd.to_image(before, before.tile(label)) if label in before.tile_names() else None
            a = rd.to_image(s, s.tile(label))
        else:
            i = int(args.index)
            label = f"{args.target}[{i}]"
            a = rd.to_image(s, s.frame(args.target, i))
            ba = before.animations.get(args.target)
            b = rd.to_image(before, before.frame(args.target, i)) if ba and -len(ba.frames) <= i < len(ba.frames) else None
        if b is None:
            print(f"{label} is new since {args.ref}")
        b, a = cmp.align(b, before.origin, a, s.origin)
        img, d = cmp.triptych(b, a, args.scale, f"{s.name} {label}", args.ref)
        print(f"{s.name} {label} vs {args.ref}: {d.summary()}")
        out = _previews() / f"{s.name}_{label.strip('@').replace('[', '_').rstrip(']')}_compare.png"
        img.save(out)
        print(_rel(out))


def cmd_context(args):
    s = Sprite.load(args.sprite)
    if s.tiled:
        sys.exit(f"{s.name} is a tileset; use `context <sprite> <anim> --on {s.name}:<tile>`")
    a = s.anim(args.anim)
    idx = [int(args.index) % len(a.frames)] if args.index is not None else range(len(a.frames))
    frames = [(f"{args.anim}[{i}]", s.frame(args.anim, i)) for i in idx]
    grounds = [cx.ground(o, s.width, s.height) for o in args.on] if args.on else cx.default_grounds(s.width, s.height)
    img, report = cx.context_sheet(s, frames, grounds, scale=args.scale)
    for line in report:
        print(line)
    out = _previews() / f"{s.name}_{args.anim}{'_' + str(idx[0]) if args.index is not None else ''}_context.png"
    img.save(out)
    print(_rel(out))


def cmd_gif(args):
    s = Sprite.load(args.sprite)
    if s.tiled:  # `gif terrain` = the sample map; `gif terrain water` = one tile, 3x3
        if args.anim:
            s.tile_index(args.anim)
        elif not s.sample:
            sys.exit(f"{s.name} has no sample map; name a tile, e.g. `gif {s.name} {s.tile_names()[0]}`")
        out = _previews() / f"{s.name}_{args.anim or 'sample'}.gif"
        rd.save_tiles_gif(s, out, args.anim, scale=max(1, args.scale // 2))
        print(_rel(out))
        return
    anims = [args.anim] if args.anim else list(s.animations)
    for a in anims:
        out = _previews() / f"{s.name}_{a}.gif"
        rd.save_gif(s, a, out, scale=args.scale)
        print(_rel(out))


def cmd_palette(args):
    s = Sprite.load(args.sprite)
    out = _previews() / f"{s.name}_palette.png"
    rd.palette_swatch(s).save(out)
    for k, v in s.palette_raw.items():
        print(f"  {k}  {v:14} {'#%02x%02x%02x' % s.palette[k][:3]}")
    print(_rel(out))


def cmd_check(args):
    names, levels = _split(args.sprites)
    issues = check(names, levels, hud=not args.sprites)
    shown = [i for i in issues if args.verbose or i.level != "info"]
    for i in shown:
        print(i)
    errors = sum(i.level == "error" for i in issues)
    warns = sum(i.level == "warn" for i in issues)
    infos = sum(i.level == "info" for i in issues)
    print(f"{len(names)} sprite(s)" + (f", {len(levels)} level(s)" if levels else "")
          + f": {errors} error(s), {warns} warning(s), {infos} info"
          + ("" if args.verbose or not infos else " (use -v to show info)"))
    sys.exit(1 if errors else 0)


def cmd_export(args):
    names, levels = _split([] if args.all else args.sprites)
    bad = [i for i in check(names, levels) if i.level == "error"]
    if bad and not args.force:
        for i in bad:
            print(i)
        sys.exit("export aborted: fix errors above (or pass --force)")
    for line in _export(names, args.padding, levels):
        print(line)


def _export(names: list[str], padding: int = 1, levels: list[str] | None = None) -> list[str]:
    out = []
    for n in names:
        out.append("  ".join(_rel(p) for p in ex.export_sprite(Sprite.load(n), padding=padding)))
    for n in levels or []:
        out.append(_rel(lvl.export_level(lvl.Level.load(n))))
    ex.export_dir().mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ASSETS / "phaser" / "pixelforge.js", ex.export_dir() / "pixelforge.js")
    out.append(_rel(ex.write_index()))
    return out


def cmd_import(args):
    s = import_png(Path(args.png), args.name, cell=_size(args.cell) if args.cell else None,
                   padding=args.padding, anim=args.anim, fps=args.fps,
                   atlas=Path(args.atlas) if args.atlas else None)
    print(f"imported into sprites/{s.name}: " + ", ".join(f"{k}({len(a.frames)})" for k, a in s.animations.items()))


def cmd_dup(args):
    s = Sprite.load(args.sprite)
    src = s.layer_path(args.src)
    dst = src.parent / f"{args.dst}.txt"   # a part copies to a part, a frame to a frame
    if dst.exists() and not args.force:
        sys.exit(f"{_rel(dst)} exists (use --force)")
    g = s.load_layer(args.src, strict=False)
    if args.flip:
        g = g.flip(args.flip)
    if args.offset:
        g = g.offset(*args.offset)
    dst.write_text(g.to_text(), encoding="utf-8")
    print(_rel(dst))


def _flood(g: Grid, x: int, y: int, key: str) -> int:
    target = g.get(x, y)
    if target == key:
        return 0
    stack, n = [(x, y)], 0
    while stack:
        cx, cy = stack.pop()
        if 0 <= cx < g.width and 0 <= cy < g.height and g.cells[cy][cx] == target:
            g.cells[cy][cx] = key
            n += 1
            stack += [(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)]
    return n


def _line(x0, y0, x1, y1):
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        yield x0, y0
        if (x0, y0) == (x1, y1):
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def cmd_paint(args):
    """Apply drawing ops to a frame file in place. Ops are ';'-separated, e.g.
    "px 3 4 k; frect 2 2 5 5 s; box 0 0 9 9 k; line 0 0 7 7 k; fill 10 10 a;
     mirror lr; swap a b; shift 1 0; move 8 3 21 17 0 1"   ("." erases)
    """
    s = Sprite.load(args.sprite)
    g = s.load_layer(args.frame, strict=False)
    for raw in " ".join(args.ops).split(";"):
        parts = raw.split()
        if not parts:
            continue
        op, a = parts[0], parts[1:]
        if op == "px":
            for i in range(0, len(a) - 2, 3):
                g.set(int(a[i]), int(a[i + 1]), a[i + 2])
        elif op in ("rect", "frect", "box"):  # frect = filled, box = outline only
            x0, y0, x1, y1, k = int(a[0]), int(a[1]), int(a[2]), int(a[3]), a[4]
            for y in range(min(y0, y1), max(y0, y1) + 1):
                for x in range(min(x0, x1), max(x0, x1) + 1):
                    edge = x in (x0, x1) or y in (y0, y1)
                    if op != "box" or edge:
                        g.set(x, y, k)
        elif op == "line":
            for x, y in _line(int(a[0]), int(a[1]), int(a[2]), int(a[3])):
                g.set(x, y, a[4])
        elif op == "fill":
            _flood(g, int(a[0]), int(a[1]), a[2])
        elif op == "clear":
            g = Grid.blank(g.width, g.height)
        elif op == "mirror":  # lr: copy left half onto right half (symmetric front views); rl: reverse
            half = g.width // 2
            for y in range(g.height):
                for x in range(half):
                    if a and a[0] == "rl":
                        g.cells[y][x] = g.cells[y][g.width - 1 - x]
                    else:
                        g.cells[y][g.width - 1 - x] = g.cells[y][x]
        elif op == "swap":
            g = g.replace(a[0], a[1])
        elif op == "shift":
            g = g.offset(int(a[0]), int(a[1]))
        elif op == "move":  # cut rect x0 y0 x1 y1 and paste its opaque pixels at +dx +dy
            x0, y0, x1, y1, dx, dy = map(int, a[:6])
            cut = [(x, y, g.get(x, y)) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]
            for x, y, _ in cut:
                g.set(x, y, TRANSPARENT)
            for x, y, k in cut:
                if k != TRANSPARENT:
                    g.set(x + dx, y + dy, k)
        else:
            sys.exit(f"unknown op {op!r} (px rect box line fill clear mirror swap shift move)")
    for k in g.keys():
        if k not in s.palette:
            print(f"warning: key {k!r} is not in the palette")
    s.layer_path(args.frame).write_text(g.to_text(), encoding="utf-8")
    print(_rel(s.layer_path(args.frame)))


def cmd_serve(args):
    serve(args.port)


def cmd_critiques(args):
    """Critiques left in the dashboard (`serve`). Default: list the ones still to fix."""
    if args.action == "watch":
        try:
            cq.watch(once=args.once, emit=lambda line: print(line, flush=True))
        except KeyboardInterrupt:
            pass
        return
    if args.action in ("show", "done", "reopen", "delete"):
        if args.id is None:
            sys.exit(f"usage: pixelforge critiques {args.action} ID")
        c = cq.get(args.id)
        if args.action == "show":
            print(cq.summary_line(c))
            for line in cq.details(c["target"]):
                print(f"  {line}")
            print(f"  {_rel(cq.render_target(c))}")
            return
        if args.action == "delete":
            cq.delete(c["id"])
            print(f"deleted #{c['id']}")
            return
        if args.action == "reopen":
            cq.update(c["id"], status="open")
            print(f"reopened #{c['id']}")
            return
        cq.update(c["id"], status="fixed", note=args.message)
        print(f"fixed #{c['id']}: {cq.label(c['target'])}")
        name = c["target"]["asset"]
        names, levels = ([], [name]) if c["target"].get("level") else ([name], [])
        bad = [i for i in check(names, levels) if i.level == "error"]
        if bad:
            for i in bad:
                print(f"  {i}")
            print(f"  not exported: fix the errors above, then `pixelforge export {name}`")
        else:
            for line in _export(names, levels=levels):
                print(f"  {line}")
        return
    shown = [c for c in cq.all_critiques() if args.all or c["status"] != "fixed"]
    if not shown:
        print("no open critiques" if not args.all else "no critiques")
        return
    for c in shown:
        print(f"#{c['id']:<3} {c['status']:7} {cq.label(c['target'])}")
        print(f"     {c['text']}")
        for line in cq.details(c["target"]):
            print(f"     {line}")
        if c.get("note"):
            print(f"     fixed: {c['note']}")


def cmd_init(args):
    """Turn a folder (default: current) into a pixelforge art root for one game."""
    target = Path(args.dir).resolve()
    try:
        report = init_project(target, args.name, args.view, _size(args.resolution))
    except FileExistsError as e:
        sys.exit(str(e))
    print(f"initialised pixelforge {__version__} project '{args.name or target.name}' in {target}")
    for c in report.changes:
        print(f"  {c}")
    for n in report.notes:
        print(f"  note: {n}")
    print("next: pixelforge new hero   (or ask Claude to draw a character)")


def cmd_upgrade(args):
    """Bring this game's folder up to the installed pixelforge (after `git pull` in the tool repo)."""
    target = root()
    try:
        report, previous = upgrade_project(target, dry_run=args.dry_run)
    except FileNotFoundError as e:
        sys.exit(str(e))
    print(f"pixelforge {previous or 'unknown'} -> {__version__} in {target}" + ("  (dry run)" if args.dry_run else ""))
    for c in report.changes or ["(project files already current)"]:
        print(f"  {c}")
    if args.dry_run or args.no_export:
        print("  sprites not re-exported" + (" (dry run)" if args.dry_run else ""))
    elif names := list_sprites():
        levels = lvl.list_levels()
        errors = [i for i in check(names, levels) if i.level == "error"]
        if errors:
            print(f"  sprites NOT re-exported: `pixelforge check` reports {len(errors)} error(s); fix them, "
                  f"then run `pixelforge export --all`")
        else:
            _export(names, levels=levels)
            print(f"  ~ re-exported {len(names)} sprite(s)" + (f", {len(levels)} level(s)" if levels else "")
                  + " and export/pixelforge.js")
            gallery = ex.export_dir() / "gallery.html"
            if gallery.exists():
                gallery.write_text(render_gallery(), encoding="utf-8")
                print("  ~ rebuilt export/gallery.html")
    for n in report.notes:
        print(f"  note: {n}")


def cmd_game(args):
    """Scaffold a Phaser + Vite game around this art folder."""
    from .game import scaffold_game
    target = root()
    try:
        report = scaffold_game(target, force=args.force)
    except FileNotFoundError as e:
        sys.exit(str(e))
    print(f"Phaser + Vite game starter in {target}")
    for c in report.changes:
        print(f"  {c}")
    for n in report.notes:
        print(f"  note: {n}")
    print("next: npm install && npm run dev   (http://localhost:5173; run `pixelforge export` after art changes)")


def cmd_gallery(args):
    out = Path(args.out) if args.out else ex.export_dir() / "gallery.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    html = render_gallery(args.sprites or None, fragment=args.fragment)
    out.write_text(html, encoding="utf-8")
    print(f"{_rel(out)}  ({len(html.encode()) / 1024:.0f} KB, self-contained: open it or send it to anyone)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="pixelforge", description="Text-grid pixel art + animation toolkit")
    p.add_argument("--root", help="project folder (default: nearest folder with pixelforge.json, else cwd)")
    p.add_argument("--version", action="version", version=f"pixelforge {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    q = sub.add_parser("init", help="set up a game folder for pixelforge")
    q.add_argument("dir", nargs="?", default=".")
    q.add_argument("--name", help="game name shown in the gallery (default: folder name)")
    q.add_argument("--view", choices=model.VIEWS, default="side",
                   help="the game's camera: side (platformer), topdown (3/4 view) or overhead (bird's-eye)")
    q.add_argument("--resolution", default="320x180", help="base screen size before scaling (default 320x180)")
    q.set_defaults(fn=cmd_init)

    q = sub.add_parser("upgrade", help="update this game's guide/scaffolding to the installed pixelforge, re-export")
    q.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    q.add_argument("--no-export", action="store_true", help="skip re-exporting sprites")
    q.set_defaults(fn=cmd_upgrade)

    q = sub.add_parser("game", help="scaffold a Phaser + Vite game around this folder (src/, index.html, package.json)")
    q.add_argument("--force", action="store_true", help="replace starter files that already exist")
    q.set_defaults(fn=cmd_game)

    q = sub.add_parser("gallery", help="self-contained HTML page of every sprite + animation")
    q.add_argument("sprites", nargs="*")
    q.add_argument("--out", help="default: export/gallery.html")
    q.add_argument("--fragment", action="store_true", help="omit <html>/<head>/<body> wrapper")
    q.set_defaults(fn=cmd_gallery)

    sub.add_parser("list", help="list sprites and levels").set_defaults(fn=cmd_list)

    q = sub.add_parser("new-level", help="scaffold levels/NAME.json: one screen of ground plus a spawn")
    q.add_argument("name")
    q.add_argument("--size", help="WxH in tiles (default: one screen at the game's resolution)")
    q.add_argument("--tileset", help="default: the first tileset")
    q.add_argument("--player", help="the character it's played with (default: the first one drawn for the view)")
    q.set_defaults(fn=cmd_new_level)

    q = sub.add_parser("level", help="render a whole level (screen grid, labels), or --screens / --at X,Y: what "
                                     "the player sees, with the HUD")
    q.add_argument("name")
    g = q.add_mutually_exclusive_group()
    g.add_argument("--screens", action="store_true", help="every camera-sized screen at 1x and 2x, numbered")
    g.add_argument("--at", metavar="X,Y", help="one screen centred on this tile")
    q.set_defaults(fn=cmd_level)

    q = sub.add_parser("new", help="scaffold a sprite")
    q.add_argument("name")
    q.add_argument("--class", dest="cls", help="size class from pixelforge.json (default: humanoid for a side "
                                              "view, topdown or overhead for those views)")
    q.add_argument("--size", help="explicit WxH instead of a class (--tileset/--icons: cell size, default 16x16; "
                                  "--prop: 32x32; --building: by view; --font: glyph cell, default 5x7)")
    kind = q.add_mutually_exclusive_group()
    kind.add_argument("--tileset", action="store_true", help="a tileset (terrain, walls, floors) instead of a sprite")
    kind.add_argument("--prop", action="store_true", help="an object: chest, tree, sign, a background accent")
    kind.add_argument("--building", action="store_true", help="a prop made of parts (walls, roof, door, windows), "
                                                              "also exported as tiles")
    kind.add_argument("--icons", action="store_true", help="a UI atlas: item icons, panels and buttons")
    kind.add_argument("--font", action="store_true", help="a bitmap font (starts from a 5x7 font)")
    q.set_defaults(fn=cmd_new)

    q = sub.add_parser("tiles", help="tileset preview: each tile repeated 3x3 (shows seams), the sample map and "
                                     "stamps; icons with their panels stretched; a font's glyphs and sample text")
    q.add_argument("tileset")
    q.add_argument("tiles", nargs="*", help="only these tiles (default: all); for a font, text to set")
    q.add_argument("--scale", type=int, default=4)
    q.add_argument("--repeat", type=int, default=3)
    q.set_defaults(fn=cmd_tiles)

    for name, fn, hlp in (("show", cmd_show, "print a frame as text with coordinates"),
                          ("render", cmd_render, "zoomed PNG preview of one frame")):
        q = sub.add_parser(name, help=hlp)
        q.add_argument("sprite")
        q.add_argument("anim", help="animation name, @id for a raw frame or part file, or a tileset's tile name")
        q.add_argument("index", nargs="?", default="0")
        if name == "render":
            q.add_argument("--scale", type=int, help="zoom (default 16, less for big canvases)")
            q.add_argument("--onion", action="store_true", help="ghost prev (red) / next (blue) frames")
            q.add_argument("--no-boxes", action="store_true", help="hide body/hurt/hit box outlines")
            q.add_argument("--no-grid", action="store_true")
            q.add_argument("--out")
        q.set_defaults(fn=fn)

    q = sub.add_parser("sheet", help="contact sheet of animations")
    q.add_argument("sprite")
    q.add_argument("anims", nargs="*")
    q.add_argument("--scale", type=int, help="zoom (default 6, less for big canvases)")
    q.add_argument("--onion", action="store_true")
    q.add_argument("--boxes", action="store_true", help="outline body box, hurtboxes, hitboxes")
    q.set_defaults(fn=cmd_sheet)

    q = sub.add_parser("motion", help="per-frame positions + timing table, spacing notes and a timeline chart")
    q.add_argument("sprite")
    q.add_argument("anims", nargs="*", help="default: every animation")
    q.set_defaults(fn=cmd_motion)

    q = sub.add_parser("compare", help="before (git) / after / changed pixels, for a frame or the whole sprite")
    q.add_argument("sprite")
    q.add_argument("target", nargs="?", help="animation, @frame_id or tile name (default: every frame)")
    q.add_argument("index", nargs="?", default="0")
    q.add_argument("--ref", default="HEAD", help="git commit to compare against (default HEAD)")
    q.add_argument("--scale", type=int, default=8)
    q.set_defaults(fn=cmd_compare)

    q = sub.add_parser("context", help="sprite on real ground tiles at game zoom, grayscale, contrast check")
    q.add_argument("sprite")
    q.add_argument("anim")
    q.add_argument("index", nargs="?", help="one frame (default: every frame)")
    q.add_argument("--on", action="append", metavar="GROUND",
                   help="tileset, tileset:tile or #rrggbb; repeatable (default: each tileset's first tile)")
    q.add_argument("--scale", type=int, default=3, help="game zoom (default 3)")
    q.set_defaults(fn=cmd_context)

    q = sub.add_parser("resize", help="re-canvas a sprite, keeping it on its origin")
    q.add_argument("sprite")
    q.add_argument("size", nargs="?", help="WxH, e.g. 64x48")
    q.add_argument("--class", dest="cls", help="use a size class instead of WxH")
    q.set_defaults(fn=cmd_resize)

    q = sub.add_parser("gif", help="animated GIF preview(s); for a tileset: its sample map, or one tile")
    q.add_argument("sprite")
    q.add_argument("anim", nargs="?")
    q.add_argument("--scale", type=int, default=8)
    q.set_defaults(fn=cmd_gif)

    q = sub.add_parser("palette", help="palette swatch")
    q.add_argument("sprite")
    q.set_defaults(fn=cmd_palette)

    q = sub.add_parser("check", help="lint sprites")
    q.add_argument("sprites", nargs="*")
    q.add_argument("-v", "--verbose", action="store_true")
    q.set_defaults(fn=cmd_check)

    q = sub.add_parser("export", help="sprite sheet PNG + Aseprite JSON for Phaser")
    q.add_argument("sprites", nargs="*")
    q.add_argument("--all", action="store_true")
    q.add_argument("--padding", type=int, default=1)
    q.add_argument("--force", action="store_true")
    q.set_defaults(fn=cmd_export)

    q = sub.add_parser("import", help="PNG -> sprite frames")
    q.add_argument("png")
    q.add_argument("name")
    q.add_argument("--cell", help="slice a uniform sheet, e.g. 32x32")
    q.add_argument("--padding", type=int, default=0)
    q.add_argument("--anim", default="imported")
    q.add_argument("--fps", type=float, default=8)
    q.add_argument("--atlas", help="Aseprite/pixelforge JSON (auto-detected next to the PNG)")
    q.set_defaults(fn=cmd_import)

    q = sub.add_parser("dup", help="copy a frame file (optionally flipped/shifted)")
    q.add_argument("sprite")
    q.add_argument("src")
    q.add_argument("dst")
    q.add_argument("--flip", choices=["h", "v"])
    q.add_argument("--offset", type=int, nargs=2, metavar=("DX", "DY"))
    q.add_argument("--force", action="store_true")
    q.set_defaults(fn=cmd_dup)

    q = sub.add_parser("paint", help="drawing ops on a frame file", description=cmd_paint.__doc__,
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    q.add_argument("sprite")
    q.add_argument("frame", help="frame or part id (file name without .txt)")
    q.add_argument("ops", nargs="+")
    q.set_defaults(fn=cmd_paint)

    q = sub.add_parser("serve", help="the dashboard: every sprite and tileset, live, with critiques")
    q.add_argument("--port", type=int, default=8000)
    q.set_defaults(fn=cmd_serve)

    q = sub.add_parser("critiques", help="critiques left in the dashboard: list, watch, show, done",
                       description=cmd_critiques.__doc__)
    q.add_argument("action", nargs="?", default="list", choices=["list", "watch", "show", "done", "reopen", "delete"])
    q.add_argument("id", nargs="?", type=int)
    q.add_argument("--all", action="store_true", help="list: include fixed ones")
    q.add_argument("--once", action="store_true", help="watch: return as soon as critiques are handed over")
    q.add_argument("-m", "--message", help="done: what you changed (shown in the dashboard)")
    q.set_defaults(fn=cmd_critiques)

    args = p.parse_args(argv)
    if args.root:
        model.set_root(args.root)
    try:
        args.fn(args)
    except SpriteError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
