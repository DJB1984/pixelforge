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
        return s.load_frame(fid, strict=False), f"{s.name} @{fid}", None, None
    if s.kind == "tileset":
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
        if s.kind == "tileset":
            print(f"{n:16} {s.width}x{s.height}  {len(s.palette)} colors  tileset: {len(s.tiles)} tiles "
                  f"({', '.join(s.tile_names()[:6])}{', ...' if len(s.tiles) > 6 else ''})")
            continue
        anims = ", ".join(f"{k}({len(a.frames)})" for k, a in s.animations.items())
        print(f"{n:16} {s.width}x{s.height}  {len(s.palette)} colors  {anims}")


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
        "animations": {"idle": {"fps": 4, "loop": True, "frames": ["idle_0"]}},
    })
    (path / "frames").mkdir(parents=True)
    (path / "frames" / "idle_0.txt").write_text(Grid.blank(w, h).to_text(), encoding="utf-8")
    (path / "sprite.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"created {_rel(path)}/sprite.json and frames/idle_0.txt ({w}x{h}"
          f"{', class ' + args.cls if not args.size else ''})")


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
    boxes = None
    if not args.no_boxes and s.kind != "tileset":
        if args.anim.startswith("@"):  # a raw layer: show its role as if active
            boxes = frame_boxes(s, args.anim[1:], active=True)
        else:
            a = s.anim(args.anim)
            i = int(args.index) % len(a.frames)
            boxes = frame_boxes(s, a.frames[i], a.active(i))
            if a.active(i):
                label += "  ACTIVE"
    img = rd.preview(s, g, scale=args.scale, title=label,
                     prev=prev if args.onion else None, nxt=nxt if args.onion else None,
                     gridlines=not args.no_grid, boxes=boxes, show_origin=s.kind != "tileset")
    tag = args.anim.lstrip("@") + ("" if args.anim.startswith("@") or s.kind == "tileset" else f"_{int(args.index)}")
    out = Path(args.out) if args.out else _previews() / f"{s.name}_{tag}{'_onion' if args.onion else ''}.png"
    img.save(out)
    print(_rel(out))


def cmd_tiles(args):
    s = Sprite.load(args.tileset)
    if s.kind != "tileset":
        sys.exit(f"{s.name} is not a tileset (sprite.json needs \"type\": \"tileset\"); use `sheet` for sprites")
    for t in args.tiles:
        s.tile_index(t)
    img = rd.tileset_preview(s, args.tiles or None, scale=args.scale, repeat=args.repeat)
    out = _previews() / f"{s.name}_tiles{'_' + '_'.join(args.tiles) if args.tiles else ''}.png"
    img.save(out)
    print(_rel(out))


def cmd_sheet(args):
    s = Sprite.load(args.sprite)
    if s.kind == "tileset":
        args.tileset, args.tiles, args.repeat = args.sprite, [], 3
        return cmd_tiles(args)
    anims = args.anims or list(s.animations)
    for a in anims:
        s.anim(a)
    img = rd.sheet(s, anims, scale=args.scale, onion=args.onion, boxes=args.boxes)
    suffix = ("_" + "_".join(args.anims) if args.anims else "") + ("_onion" if args.onion else "")
    out = _previews() / f"{s.name}_sheet{suffix}.png"
    img.save(out)
    print(_rel(out))


def cmd_motion(args):
    s = Sprite.load(args.sprite)
    if s.kind == "tileset":
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
        elif s.kind == "tileset":
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
    if s.kind == "tileset":
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
    if s.kind == "tileset":  # `gif terrain` = the sample map; `gif terrain water` = one tile, 3x3
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
    names = args.sprites or list_sprites()
    issues = check(names)
    shown = [i for i in issues if args.verbose or i.level != "info"]
    for i in shown:
        print(i)
    errors = sum(i.level == "error" for i in issues)
    warns = sum(i.level == "warn" for i in issues)
    infos = sum(i.level == "info" for i in issues)
    print(f"{len(names)} sprite(s): {errors} error(s), {warns} warning(s), {infos} info"
          + ("" if args.verbose or not infos else " (use -v to show info)"))
    sys.exit(1 if errors else 0)


def cmd_export(args):
    names = list_sprites() if args.all or not args.sprites else args.sprites
    bad = [i for i in check(names) if i.level == "error"]
    if bad and not args.force:
        for i in bad:
            print(i)
        sys.exit("export aborted: fix errors above (or pass --force)")
    for line in _export(names, args.padding):
        print(line)


def _export(names: list[str], padding: int = 1) -> list[str]:
    out = []
    for n in names:
        png, js = ex.export_sprite(Sprite.load(n), padding=padding)
        out.append(f"{_rel(png)}  {_rel(js)}")
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
    dst = s.frame_path(args.dst)
    if dst.exists() and not args.force:
        sys.exit(f"{_rel(dst)} exists (use --force)")
    g = s.load_frame(args.src, strict=False)
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
    g = s.load_frame(args.frame, strict=False)
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
    s.frame_path(args.frame).write_text(g.to_text(), encoding="utf-8")
    print(_rel(s.frame_path(args.frame)))


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
        bad = [i for i in check([name]) if i.level == "error"]
        if bad:
            for i in bad:
                print(f"  {i}")
            print(f"  not exported: fix the errors above, then `pixelforge export {name}`")
        else:
            for line in _export([name]):
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
        report = init_project(target, args.name)
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
        errors = [i for i in check(names) if i.level == "error"]
        if errors:
            print(f"  sprites NOT re-exported: `pixelforge check` reports {len(errors)} error(s); fix them, "
                  f"then run `pixelforge export --all`")
        else:
            _export(names)
            print(f"  ~ re-exported {len(names)} sprite(s) and export/pixelforge.js")
            gallery = ex.export_dir() / "gallery.html"
            if gallery.exists():
                gallery.write_text(render_gallery(), encoding="utf-8")
                print("  ~ rebuilt export/gallery.html")
    for n in report.notes:
        print(f"  note: {n}")


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
    q.set_defaults(fn=cmd_init)

    q = sub.add_parser("upgrade", help="update this game's guide/scaffolding to the installed pixelforge, re-export")
    q.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    q.add_argument("--no-export", action="store_true", help="skip re-exporting sprites")
    q.set_defaults(fn=cmd_upgrade)

    q = sub.add_parser("gallery", help="self-contained HTML page of every sprite + animation")
    q.add_argument("sprites", nargs="*")
    q.add_argument("--out", help="default: export/gallery.html")
    q.add_argument("--fragment", action="store_true", help="omit <html>/<head>/<body> wrapper")
    q.set_defaults(fn=cmd_gallery)

    sub.add_parser("list", help="list sprites").set_defaults(fn=cmd_list)

    q = sub.add_parser("new", help="scaffold a sprite")
    q.add_argument("name")
    q.add_argument("--class", dest="cls", default="humanoid", help="size class from pixelforge.json (default humanoid)")
    q.add_argument("--size", help="explicit WxH instead of a class (with --tileset: tile size, default 16x16)")
    q.add_argument("--tileset", action="store_true", help="a tileset (terrain, walls, floors) instead of a sprite")
    q.set_defaults(fn=cmd_new)

    q = sub.add_parser("tiles", help="tileset preview: each tile repeated 3x3 (shows seams) + the sample map")
    q.add_argument("tileset")
    q.add_argument("tiles", nargs="*", help="only these tiles (default: all)")
    q.add_argument("--scale", type=int, default=4)
    q.add_argument("--repeat", type=int, default=3)
    q.set_defaults(fn=cmd_tiles)

    for name, fn, hlp in (("show", cmd_show, "print a frame as text with coordinates"),
                          ("render", cmd_render, "zoomed PNG preview of one frame")):
        q = sub.add_parser(name, help=hlp)
        q.add_argument("sprite")
        q.add_argument("anim", help="animation name, @frame_id for a raw frame file, or a tileset's tile name")
        q.add_argument("index", nargs="?", default="0")
        if name == "render":
            q.add_argument("--scale", type=int, default=16)
            q.add_argument("--onion", action="store_true", help="ghost prev (red) / next (blue) frames")
            q.add_argument("--no-boxes", action="store_true", help="hide body/hurt/hit box outlines")
            q.add_argument("--no-grid", action="store_true")
            q.add_argument("--out")
        q.set_defaults(fn=fn)

    q = sub.add_parser("sheet", help="contact sheet of animations")
    q.add_argument("sprite")
    q.add_argument("anims", nargs="*")
    q.add_argument("--scale", type=int, default=6)
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
    q.add_argument("frame", help="frame id (file name without .txt)")
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
