"""Hurtboxes and hitboxes, computed from the pixels of role-tagged layers.

hurt  = where the character can be hit (layers with role "hurt", the default): one tight box.
hit   = where an attack deals damage (role "hit"), only on frames marked "active": a few small
        boxes covering the weapon, so a diagonal blade isn't one mostly-empty rectangle.
Boxes are [x, y, w, h] in frame pixels, grown (or shrunk, if negative) by hit_pad / hurt_pad.
"""
from __future__ import annotations

from .grid import Grid
from .model import ROLES, Sprite

Rect = tuple[int, int, int, int]  # left, top, right, bottom (inclusive)

HIT_CELL = 6       # px; hit pixels are covered by boxes no bigger than this before merging
MAX_HIT_BOXES = 6


def _points(roles: Grid, mark: str) -> list[tuple[int, int]]:
    return [(x, y) for y, row in enumerate(roles.cells) for x, c in enumerate(row) if c == mark]


def _bbox(points) -> Rect:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _area(r: Rect) -> int:
    return (r[2] - r[0] + 1) * (r[3] - r[1] + 1)


def _union(a: Rect, b: Rect) -> Rect:
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def cover(points: list[tuple[int, int]], cell: int = HIT_CELL, max_boxes: int = MAX_HIT_BOXES) -> list[Rect]:
    """A few rectangles that cover `points` tightly: tight boxes per grid cell, then greedy merging
    of the pair that wastes the least area, while merging is cheap or there are too many boxes."""
    cells: dict[tuple[int, int], list] = {}
    for x, y in points:
        cells.setdefault((x // cell, y // cell), []).append((x, y))
    rects = [_bbox(ps) for ps in cells.values()]
    while len(rects) > 1:
        best = None
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                u = _union(rects[i], rects[j])
                waste = _area(u) - _area(rects[i]) - _area(rects[j])
                if best is None or waste < best[0]:
                    best = (waste, i, j, u)
        waste, i, j, u = best
        cheap = waste <= 0.25 * (_area(rects[i]) + _area(rects[j]))
        if not cheap and len(rects) <= max_boxes:
            break
        rects = [r for k, r in enumerate(rects) if k not in (i, j)] + [u]
    return sorted(rects, key=lambda r: (r[1], r[0]))


def _xywh(r: Rect, pad: int) -> list[int]:
    x, y, w, h = r[0] - pad, r[1] - pad, r[2] - r[0] + 1 + 2 * pad, r[3] - r[1] + 1 + 2 * pad
    if w < 1:
        x, w = x + w // 2, 1
    if h < 1:
        y, h = y + h // 2, 1
    return [x, y, w, h]


def frame_boxes(sprite: Sprite, entry, active: bool) -> dict[str, list[list[int]]]:
    _, roles = sprite.resolve_roles(entry)
    hurt_pts = _points(roles, ROLES["hurt"]) if sprite.kind != "fx" else []   # nothing hits an effect
    hit_pts = _points(roles, ROLES["hit"]) if active else []
    return {
        "hurt": [_xywh(_bbox(hurt_pts), sprite.hurt_pad)] if hurt_pts else [],
        "hit": [_xywh(r, sprite.hit_pad) for r in cover(hit_pts)] if hit_pts else [],
    }


def anim_boxes(sprite: Sprite, anim: str) -> list[dict[str, list[list[int]]]]:
    a = sprite.anim(anim)
    return [frame_boxes(sprite, e, a.active(i)) for i, e in enumerate(a.frames)]
