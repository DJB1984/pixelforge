"""Lint rules for sprites. Each issue is (level, where, message); level is error/warn/info."""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .boxes import frame_boxes
from .grid import TRANSPARENT, Grid
from .model import Sprite, SpriteError, describe_entry, load_game_palette

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
            issues.append(Issue("info", where, "not used by any animation"))

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

        bottoms = [g.bbox()[3] for _, g in valid]
        if len(set(bottoms)) > 1:
            level = "warn" if a.loop else "info"
            issues.append(Issue(level, where,
                                f"lowest opaque row varies across frames {bottoms}; feet may jitter "
                                f"(ignore for jumps/bobs that are intentional)"))
        if all(b != oy - 1 for b in bottoms):
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
                issues.append(Issue("warn", where,
                                    f"frames {i}->{j} change {moved}/{union} pixels ({moved / union:.0%}) even "
                                    f"after aligning shifts; motion may look like a jump cut"))
            if changed == 0 and len(grids) > 1:
                issues.append(Issue("info", where, f"frames {i} and {j} are identical"))
    return issues


def check(names: list[str]) -> list[Issue]:
    out = []
    for n in names:
        out.extend(check_sprite(n))
    return out
