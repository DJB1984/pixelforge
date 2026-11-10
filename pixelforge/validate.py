"""Lint rules for sprites. Each issue is (level, where, message); level is error/warn/info."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .boxes import frame_boxes
from .grid import TRANSPARENT, Grid
from .model import ROLES, Sprite, SpriteError, describe_entry, load_game_palette

MAX_PALETTE = 16
BIG_DIFF_RATIO = 0.45


@dataclass
class Issue:
    level: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level:5}] {self.where}: {self.message}"


def _coords(points: list[tuple[int, int]], limit: int = 8) -> str:
    s = " ".join(f"({x},{y})" for x, y in points[:limit])
    return s + (f" ... +{len(points) - limit} more" if len(points) > limit else "")


def floating_pixels(g: Grid) -> list[tuple[int, int]]:
    """Opaque pixels with no opaque 8-neighbours."""
    out = []
    for y in range(g.height):
        for x in range(g.width):
            if g.cells[y][x] == TRANSPARENT:
                continue
            if all(g.get(x + dx, y + dy) == TRANSPARENT
                   for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
                out.append((x, y))
    return out


def check_sprite(name: str) -> list[Issue]:
    issues: list[Issue] = []
    try:
        s = Sprite.load(name)
    except SpriteError as e:
        return [Issue("error", name, str(e))]

    # ---- palette ----
    if len(s.palette) > MAX_PALETTE:
        issues.append(Issue("warn", f"{name}/palette",
                            f"{len(s.palette)} colors; pixel art usually reads better with <= {MAX_PALETTE} per sprite"))
    game = load_game_palette()
    if game:
        game_colors = set(game.values())
        off = [k for k, c in s.palette.items() if c not in game_colors]
        if off:
            issues.append(Issue("info", f"{name}/palette", f"keys not from palettes/game.json: {' '.join(off)}"))

    # ---- frame files ----
    used: set[str] = set()

    def collect(entry):
        if isinstance(entry, str):
            used.add(entry)
        elif isinstance(entry, dict):
            if "from" in entry:
                collect(entry["from"])
            for layer in entry.get("layers", []):
                collect(layer)

    for a in s.animations.values():
        for e in a.frames:
            collect(e)
    for name, e in s.tiles:
        for fe, _ in s.tile_frames(name):
            collect(fe)

    for pattern in s.roles:
        if not any(fnmatch.fnmatchcase(f, pattern) for f in s.frame_ids()):
            issues.append(Issue("info", f"{name}/roles", f"pattern {pattern!r} matches no frame files"))

    for fid in s.frame_ids():
        where = f"{name}/frames/{fid}.txt"
        try:
            g = s.load_frame(fid)
        except SpriteError as e:
            issues.append(Issue("error", where, str(e).split(": ", 1)[-1]))
            g = s.load_frame(fid, strict=False)
        bad = [(x, y) for y, r in enumerate(g.cells) for x, c in enumerate(r)
               if c != TRANSPARENT and c not in s.palette]
        if bad:
            keys = sorted({g.cells[y][x] for x, y in bad})
            issues.append(Issue("error", where, f"undefined palette keys {keys} at {_coords(bad)}"))
        if fid not in used:
            issues.append(Issue("info", where, "not used by any " + ("tile" if s.kind == "tileset" else "animation")))

    if s.kind == "tileset":
        return issues + check_tiles(s)

    # ---- animations ----
    if not s.animations:
        issues.append(Issue("warn", name, "no animations defined"))
    ox, oy = s.origin
    seen_floating: set[tuple] = set()
    for aname, a in s.animations.items():
        where = f"{name}:{aname}"
        if not a.frames:
            issues.append(Issue("error", where, "animation has no frames"))
            continue
        grids: list[Grid | None] = []
        for i, entry in enumerate(a.frames):
            try:
                g = s.resolve(entry)
            except SpriteError as e:
                issues.append(Issue("error", f"{where}[{i}]", f"{describe_entry(entry)}: {e}"))
                g = None
            grids.append(g)
            if g is not None and g.opaque_count() == 0:
                issues.append(Issue("error", f"{where}[{i}]", "frame is empty"))
            # judged on the composited frame: a layer's pixel may only touch others once stacked
            fl = floating_pixels(g) if g is not None else []
            if fl and tuple(fl) not in seen_floating:
                seen_floating.add(tuple(fl))
                issues.append(Issue("warn", f"{where}[{i}]", f"floating pixels (no opaque neighbours) at {_coords(fl)}"))
        valid = [(i, g) for i, g in enumerate(grids) if g is not None and g.bbox()]
        if not valid:
            continue

        bx, by, bw, bh = s.body_rect()
        for i, _ in valid:
            boxes = frame_boxes(s, a.frames[i], a.active(i))
            if a.active(i) and not boxes["hit"]:
                issues.append(Issue("warn", f"{where}[{i}]", "marked active but has no pixels from a 'hit' layer "
                                                             "(check sprite.json roles)"))
            if a.loop and boxes["hurt"]:
                x, y, w, h = boxes["hurt"][0]
                over = max(bx - x, by - y, (x + w) - (bx + bw), (y + h) - (by + bh))
                if over > 2:
                    issues.append(Issue("info", f"{where}[{i}]", f"hurtbox {[x, y, w, h]} pokes {over}px outside "
                                                                 f"the body box {[bx, by, bw, bh]}"))

        # feet = lowest *body* pixel: weapons and effects (hit/none layers) may swing below the feet.
        # Centre-anchored (overhead) sprites have no feet to plant, so these checks don't apply.
        bottoms = []
        for i, g in valid if s.anchor == "feet" else []:
            _, roles = s.resolve_roles(a.frames[i])
            body = [y for y, row in enumerate(roles.cells) if ROLES["hurt"] in row]
            bottoms.append(max(body) if body else g.bbox()[3])
        if len(set(bottoms)) > 1:
            level = "warn" if a.loop else "info"
            issues.append(Issue(level, where,
                                f"lowest opaque row varies across frames {bottoms}; feet may jitter "
                                f"(ignore for jumps/bobs that are intentional)"))
        if bottoms and all(b != oy - 1 for b in bottoms):
            issues.append(Issue("info", where, f"no frame stands on the origin (origin y={oy} expects lowest row "
                                               f"{oy - 1}; got {sorted(set(bottoms))})"))

        pairs = list(zip(range(len(grids)), range(1, len(grids))))
        if a.loop and len(grids) > 2:
            pairs.append((len(grids) - 1, 0))
        for i, j in pairs:
            gi, gj = grids[i], grids[j]
            if gi is None or gj is None:
                continue
            union = sum(1 for y in range(gi.height) for x in range(gi.width)
                        if gi.cells[y][x] != TRANSPARENT or gj.get(x, y) != TRANSPARENT)
            changed = len(gi.diff(gj))
            # Ignore whole-sprite shifts (bobs, steps): measure change after the best small realignment.
            moved = min(len(gi.offset(dx, dy).diff(gj)) for dx in range(-2, 3) for dy in range(-2, 3))
            if union and moved / union > BIG_DIFF_RATIO:
                # snapping into/out of an active (smear/strike) frame is the point of an attack
                snap = a.active(i) or a.active(j)
                issues.append(Issue("info" if snap else "warn", where,
                                    f"frames {i}->{j} change {moved}/{union} pixels ({moved / union:.0%}) even "
                                    f"after aligning shifts; " + ("expected for an active attack frame" if snap
                                                                  else "motion may look like a jump cut")))
            if changed == 0 and len(grids) > 1:
                issues.append(Issue("info", where, f"frames {i} and {j} are identical"))
    return issues


def _lum(rgba) -> float:
    r, g, b, _ = rgba
    return 0.299 * r + 0.587 * g + 0.114 * b


def seams(s: Sprite, g: Grid) -> list[str]:
    """Edges that show a line when the tile repeats: the jump in brightness across the wrap
    (last column -> first, bottom row -> top) is far bigger than between neighbours inside it."""
    lum = [[_lum(s.color(c)) if c != TRANSPARENT else None for c in row] for row in g.cells]
    out = []
    for axis, cells in (("left-right", lum), ("top-bottom", [list(col) for col in zip(*lum)])):
        inner = [abs(a - b) for row in cells for a, b in zip(row, row[1:]) if a is not None and b is not None]
        wrap = [abs(row[-1] - row[0]) for row in cells if row[-1] is not None and row[0] is not None]
        if inner and wrap:
            mi, mw = sum(inner) / len(inner), sum(wrap) / len(wrap)
            if mw > 24 and mw > 2.5 * mi:
                out.append(axis)
    return out


def check_tiles(s: Sprite) -> list[Issue]:
    issues: list[Issue] = []
    name = s.name
    if not s.tiles:
        issues.append(Issue("warn", name, "tileset has no tiles (add them to \"tiles\" in sprite.json)"))
    seen: set[str] = set()
    for i, (tname, entry) in enumerate(s.tiles):
        where = f"{name}:tile {i} {tname!r}"
        if tname in seen:
            issues.append(Issue("error", where, "duplicate tile name; each tile needs its own"))
        seen.add(tname)
        frames = s.tile_frames(tname)
        animated = tname in s.tile_anims
        if animated and len(frames) == 1:
            issues.append(Issue("warn", where, "\"frames\" has a single frame, so it never animates"))
        if animated and any(ms <= 0 for _, ms in frames):
            issues.append(Issue("error", where, "frame durations must be positive"))
        grids: list[Grid] = []
        seam_axes: set[str] = set()
        for j, (fe, _) in enumerate(frames):
            fwhere = f"{where} frame {j}" if animated else where
            try:
                g = s.resolve(fe)
            except SpriteError as e:
                issues.append(Issue("error", fwhere, f"{describe_entry(fe)}: {e}"))
                continue
            if grids and not g.diff(grids[-1]):
                issues.append(Issue("info", fwhere, f"same as frame {j - 1}"))
            grids.append(g)
            clear = g.width * g.height - g.opaque_count()
            if clear == g.width * g.height:
                issues.append(Issue("warn", fwhere, "tile is empty"))
            elif clear:
                if j == 0:
                    issues.append(Issue("info", fwhere, f"{clear} transparent pixels (fine for overlays such as "
                                                        f"flowers or edges drawn on a second layer; ground tiles "
                                                        f"usually fill every pixel)"))
            else:
                seam_axes.update(seams(s, g))
        for axis in sorted(seam_axes):
            issues.append(Issue("warn", where, f"visible seam when repeated {axis}: the wrapped edge jumps "
                                               f"in brightness much more than the inside does (`tiles "
                                               f"{name}` shows it; fine for edge/transition tiles)"))
    for pattern in s.tile_props:
        if not any(fnmatch.fnmatchcase(t, pattern) for t in s.tile_names()):
            issues.append(Issue("info", f"{name}/properties", f"pattern {pattern!r} matches no tiles"))
    if s.sample:
        legend = s.sample.get("legend", {})
        for c, tname in legend.items():
            if tname not in seen:
                issues.append(Issue("error", f"{name}/sample", f"legend {c!r} -> {tname!r}: no such tile"))
        rows = s.sample.get("rows", [])
        if len({len(r) for r in rows}) > 1:
            issues.append(Issue("warn", f"{name}/sample", f"rows have different lengths {sorted({len(r) for r in rows})}"))
        bad = sorted({c for r in rows for c in r if c not in legend and c not in " ."})
        if bad:
            issues.append(Issue("error", f"{name}/sample", f"characters not in the legend: {' '.join(bad)}"))
    return issues


def check(names: list[str]) -> list[Issue]:
    out = []
    for n in names:
        out.extend(check_sprite(n))
    return out
