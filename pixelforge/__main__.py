"""pixelforge CLI.  Run `python -m pixelforge -h` or `python -m pixelforge <cmd> -h`."""
from __future__ import annotations

import argparse
import http.server
import json
import shutil
import sys
from pathlib import Path

from . import __version__
from . import export as ex
from . import model
from . import render as rd
from .boxes import frame_boxes
from .gallery import render_gallery
from .grid import TRANSPARENT, Grid
from .importer import import_png
from .model import ASSETS, Sprite, SpriteError, list_sprites, root, sprites_dir
from .project import init_project, upgrade_project
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
    """`anim index` or `@frame_id` addressing. Returns (grid, label, prev, next)."""
    if anim.startswith("@"):
        fid = anim[1:]
        return s.load_frame(fid, strict=False), f"{s.name} @{fid}", None, None
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
        anims = ", ".join(f"{k}({len(a.frames)})" for k, a in s.animations.items())
        print(f"{n:16} {s.width}x{s.height}  {len(s.palette)} colors  {anims}")


def cmd_new(args):
    path = sprites_dir() / args.name
    if path.exists():
        sys.exit(f"{_rel(path)} already exists")
    meta: dict = {"name": args.name}
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
    elif args.size:
        w, h = _size(args.size)
    else:
        sys.exit("give a size (e.g. 64x48) or --class")
    nox, noy = w // 2, h
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
    if not args.no_boxes:
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
                     gridlines=not args.no_grid, boxes=boxes)
    tag = args.anim.lstrip("@") + ("" if args.anim.startswith("@") else f"_{int(args.index)}")
    out = Path(args.out) if args.out else _previews() / f"{s.name}_{tag}{'_onion' if args.onion else ''}.png"
    img.save(out)
    print(_rel(out))


def cmd_sheet(args):
    s = Sprite.load(args.sprite)
    anims = args.anims or list(s.animations)
    for a in anims:
        s.anim(a)
    img = rd.sheet(s, anims, scale=args.scale, onion=args.onion, boxes=args.boxes)
    suffix = ("_" + "_".join(args.anims) if args.anims else "") + ("_onion" if args.onion else "")
    out = _previews() / f"{s.name}_sheet{suffix}.png"
    img.save(out)
    print(_rel(out))


def cmd_gif(args):
    s = Sprite.load(args.sprite)
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
    exported = sorted(p.stem for p in ex.export_dir().glob("*.json") if p.stem != "index")
    out.append(_rel(ex.write_index(exported)))
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


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serves /viewer/ and /phaser/ from the installed package, everything else from the project."""

    def translate_path(self, path):
        parts = path.split("?", 1)[0].split("#", 1)[0].lstrip("/").split("/")
        if parts and parts[0] in ("viewer", "phaser"):
            return str(ASSETS.joinpath(*parts))
        return super().translate_path(path)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def cmd_serve(args):
    handler = lambda *a, **kw: _Handler(*a, directory=str(root()), **kw)  # noqa: E731
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {root()}")
        print(f"  viewer:  http://127.0.0.1:{args.port}/viewer/")
        print(f"  phaser:  http://127.0.0.1:{args.port}/viewer/phaser.html")
        print(f"  gallery: http://127.0.0.1:{args.port}/export/gallery.html  (after `pixelforge gallery`)")
        print("Ctrl+C to stop")
        httpd.serve_forever()


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
    q.add_argument("--size", help="explicit WxH instead of a class")
    q.set_defaults(fn=cmd_new)

    for name, fn, hlp in (("show", cmd_show, "print a frame as text with coordinates"),
                          ("render", cmd_render, "zoomed PNG preview of one frame")):
        q = sub.add_parser(name, help=hlp)
        q.add_argument("sprite")
        q.add_argument("anim", help="animation name, or @frame_id for a raw frame file")
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

    q = sub.add_parser("resize", help="re-canvas a sprite, keeping it on its origin")
    q.add_argument("sprite")
    q.add_argument("size", nargs="?", help="WxH, e.g. 64x48")
    q.add_argument("--class", dest="cls", help="use a size class instead of WxH")
    q.set_defaults(fn=cmd_resize)

    q = sub.add_parser("gif", help="animated GIF preview(s)")
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

    q = sub.add_parser("serve", help="serve the project for viewer/index.html")
    q.add_argument("--port", type=int, default=8000)
    q.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    if args.root:
        model.set_root(args.root)
    try:
        args.fn(args)
    except SpriteError as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
