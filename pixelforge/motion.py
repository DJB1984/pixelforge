"""Animation motion as numbers: where the head, body and weapon are in every frame, and when.

A still image can't show timing, so `motion` measures it instead: per-frame positions, how far
each part moves per step, and how long each frame is held. Uneven steps, an unheld wind-up or a
long smear frame show up in the table and the chart.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .grid import TRANSPARENT
from .model import ROLES, Sprite
from .render import HIT_COLOR, LABEL_BG, LABEL_FG, checkerboard, font, to_image, zoom

JUMP_RATIO = 2.5   # a step this many times the typical step reads as a pop
MIN_SPAN = 4       # px: the smallest value range a chart band shows
MUTED = (150, 150, 160, 255)
SERIES_COLORS = [(250, 200, 40, 255), (90, 170, 255, 255), (120, 220, 140, 255), (240, 110, 90, 255)]


@dataclass
class FrameMotion:
    index: int
    start: int                     # ms from the start of the animation
    ms: int
    active: bool
    head: int | None               # top row of body pixels
    feet: int | None               # bottom row of body pixels
    cx: float | None               # body pixels' centre
    cy: float | None
    tip: tuple[int, int] | None    # weapon pixel farthest from the body box centre
    reach: float | None            # ...and its distance from that centre
    changed: int | None            # pixels that differ from the previous frame
    moved: int | None              # ...after the best whole-sprite shift of up to 2px


def measure(sprite: Sprite, anim: str) -> list[FrameMotion]:
    a = sprite.anim(anim)
    bx, by, bw, bh = sprite.body_rect()
    ccx, ccy = bx + bw / 2, by + bh / 2
    out, t, prev = [], 0, None
    for i, entry in enumerate(a.frames):
        g, roles = sprite.resolve_roles(entry)
        body = [(x, y) for y, row in enumerate(roles.cells) for x, c in enumerate(row) if c == ROLES["hurt"]]
        if not body:  # no hurt layers: treat every pixel as body
            body = [(x, y) for y, row in enumerate(g.cells) for x, c in enumerate(row) if c != TRANSPARENT]
        hit = [(x, y) for y, row in enumerate(roles.cells) for x, c in enumerate(row) if c == ROLES["hit"]]
        dist = lambda p: ((p[0] + 0.5 - ccx) ** 2 + (p[1] + 0.5 - ccy) ** 2) ** 0.5  # noqa: E731
        tip = max(hit, key=dist) if hit else None
        ms = a.duration_ms(i)
        out.append(FrameMotion(
            i, t, ms, a.active(i),
            min(y for _, y in body) if body else None, max(y for _, y in body) if body else None,
            round(sum(x + 0.5 for x, _ in body) / len(body), 1) if body else None,
            round(sum(y + 0.5 for _, y in body) / len(body), 1) if body else None,
            tip, round(dist(tip), 1) if tip else None,
            len(g.diff(prev)) if prev else None,
            min(len(g.offset(dx, dy).diff(prev)) for dx in range(-2, 3) for dy in range(-2, 3)) if prev else None,
        ))
        t += ms
        prev = g
    return out


def _steps(sprite: Sprite, anim: str, fm: list[FrameMotion]) -> list[tuple[int, int]]:
    n = len(fm)
    pairs = [(i, i + 1) for i in range(n - 1)]
    if sprite.anim(anim).loop and n > 2:
        pairs.append((n - 1, 0))
    return pairs


def notes(sprite: Sprite, anim: str, fm: list[FrameMotion]) -> list[str]:
    """Plain-language observations: uneven spacing, bob size, anticipation and smear timing."""
    a = sprite.anim(anim)
    out: list[str] = []
    pairs = _steps(sprite, anim, fm)

    def scalar(attr):
        return lambda f, g: (abs(getattr(g, attr) - getattr(f, attr))
                             if getattr(f, attr) is not None and getattr(g, attr) is not None else None)

    def tip_step(f, g):
        if f.tip is None or g.tip is None:
            return None
        return round(((g.tip[0] - f.tip[0]) ** 2 + (g.tip[1] - f.tip[1]) ** 2) ** 0.5, 1)

    series = {"head": scalar("head"), "body centre x": scalar("cx"), "body centre y": scalar("cy")}
    if any(f.tip for f in fm):
        series["weapon tip"] = tip_step
    for name, step in series.items():
        steps = [(i, j, step(fm[i], fm[j])) for i, j in pairs]
        steps = [(i, j, s) for i, j, s in steps if s is not None]
        moving = [s for _, _, s in steps if s > 0]
        if len(steps) < 3 or len(moving) < 2:
            continue
        typical = statistics.median(moving)
        for i, j, s in steps:
            if s > max(2, JUMP_RATIO * typical):
                snap = fm[i].active or fm[j].active
                out.append(f"{name}: frame {i}->{j} moves {s:g}px; a typical step is {typical:g}px. "
                           + ("Snapping into or out of an active frame is expected for a smear."
                              if snap else "Uneven spacing reads as a pop; add an in-between or spread the move."))

    heads = [f.head for f in fm if f.head is not None]
    if a.loop and heads:
        bob = max(heads) - min(heads)
        line = f"head bob: {bob}px (rows {min(heads)}-{max(heads)})"
        if "idle" in anim and bob > 2:
            line += "; idle breathing usually reads best at 1px"
        out.append(line)
    feet = [f.feet for f in fm if f.feet is not None]
    if sprite.anchor == "feet" and feet and len(set(feet)) > 1:
        out.append(f"feet rows vary {sorted(set(feet))}: fine for a jump or hop, a slide otherwise")

    active = [f for f in fm if f.active]
    if active:
        first = active[0].index
        windup = fm[:first]
        typical = statistics.median(f.ms for f in fm)
        if not windup:
            out.append("no wind-up: the first frame is already active; anticipation sells the hit")
        else:
            hold = max(f.ms for f in windup)
            if hold < 1.25 * typical:
                out.append(f"wind-up isn't held: its longest frame is {hold}ms against a typical {typical:g}ms; "
                           f"hold the anticipation pose longer")
            slow = [f for f in active if f.ms > hold]
            if slow:
                out.append(f"active frame {slow[0].index} lasts {slow[0].ms}ms, longer than the wind-up "
                           f"({hold}ms); smears read best fast")
        if not a.loop and active[-1].index == len(fm) - 1:
            out.append("no recovery after the last active frame; a follow-through frame makes the strike land")
        reach = [f.reach for f in active if f.reach is not None]
        if reach:
            out.append(f"reach on active frames: {min(reach):g}-{max(reach):g}px from the body box centre")
    return out


def table(sprite: Sprite, anim: str, fm: list[FrameMotion]) -> str:
    a = sprite.anim(anim)
    total = sum(f.ms for f in fm)
    head = (f"{sprite.name}:{anim}  {len(fm)} frames, {total}ms, "
            f"{'loops' if a.loop else 'plays once'}  (y grows downward; origin {list(sprite.origin)})")
    rows = [" #     ms  start  head  feet  body centre   weapon tip  reach  changed (after shift)"]
    for f in fm:
        centre = f"{f.cx:5.1f},{f.cy:5.1f}" if f.cx is not None else "-"
        tip = f"({f.tip[0]},{f.tip[1]})" if f.tip else "-"
        changed = f"{f.changed} ({f.moved})" if f.changed is not None else "-"
        rows.append(f"{f.index:>2}{'*' if f.active else ' '} {f.ms:>5}  {f.start:>5}  {f.head if f.head is not None else '-':>4}  "
                    f"{f.feet if f.feet is not None else '-':>4}  {centre:>12}  {tip:>10}  "
                    f"{f.reach if f.reach is not None else '-':>5}  {changed}")
    return "\n".join([head, *rows, "  (* = active)"])


def chart(sprite: Sprite, anim: str, fm: list[FrameMotion], thumb_scale: int = 2) -> Image.Image:
    """Frame thumbnails in order, each tied to where it starts on a time axis, over step plots of
    head height, body centre and weapon reach. Active frames are shaded red."""
    a = sprite.anim(anim)
    ox, oy = sprite.origin
    total = max(1, sum(f.ms for f in fm))
    pad, left, band_h = 12, 150, 64
    tw, th = sprite.width * thumb_scale, sprite.height * thumb_scale
    plot_w = max(600, len(fm) * (tw + 8))
    width = left + plot_w + pad * 2
    bands = [("head height", [oy - f.head if f.head is not None else None for f in fm], "px above origin"),
             ("body centre height", [round(oy - f.cy, 1) if f.cy is not None else None for f in fm], "px"),
             ("body centre x", [round(f.cx - ox, 1) if f.cx is not None else None for f in fm], "px from origin")]
    if any(f.reach is not None for f in fm):
        bands.append(("weapon reach", [f.reach for f in fm], "px from body centre"))
    strip_y = pad + 20
    axis_y = strip_y + th + 34
    height = axis_y + 24 + len(bands) * (band_h + 10) + pad
    img = Image.new("RGBA", (width, height), LABEL_BG)
    d = ImageDraw.Draw(img)
    f_small, f_label = font(10), font(12)
    d.text((pad, pad), f"{sprite.name}:{anim}  {total}ms  {'loops' if a.loop else 'plays once'}",
           fill=LABEL_FG, font=font(13))
    tx = lambda ms: left + pad + ms * plot_w / total  # noqa: E731

    slot = plot_w / max(1, len(fm))
    for f in fm:
        x0 = int(left + pad + f.index * slot + (slot - tw) / 2)
        cell = checkerboard(tw, th, thumb_scale * 2)
        cell.alpha_composite(zoom(to_image(sprite, sprite.frame(anim, f.index)), thumb_scale))
        img.alpha_composite(cell, (x0, strip_y))
        if f.active:
            d.rectangle([x0 - 2, strip_y - 2, x0 + tw + 1, strip_y + th + 1], outline=HIT_COLOR, width=2)
        d.text((x0, strip_y + th + 3), f"{f.index}  {f.ms}ms", fill=HIT_COLOR if f.active else LABEL_FG, font=f_small)
        d.line([(x0 + tw / 2, strip_y + th + 16), (tx(f.start), axis_y)], fill=MUTED)
    d.line([(tx(0), axis_y), (tx(total), axis_y)], fill=LABEL_FG)
    for f in fm + [None]:
        t = f.start if f else total
        d.line([(tx(t), axis_y - 3), (tx(t), axis_y + 3)], fill=LABEL_FG)
        d.text((tx(t), axis_y + 5), f"{t}", fill=MUTED, font=f_small, anchor="ma")
    d.text((pad, axis_y - 6), "time (ms)", fill=MUTED, font=f_small)

    y = axis_y + 24
    for k, (name, values, unit) in enumerate(bands):
        known = [v for v in values if v is not None]
        top, bottom = y, y + band_h
        d.rectangle([left + pad, top, left + pad + plot_w, bottom], fill=(42, 42, 50, 255))
        for f in fm:
            if f.active:
                d.rectangle([tx(f.start), top, tx(f.start + f.ms), bottom], fill=(90, 36, 44, 255))
        d.text((pad, top + 4), name, fill=LABEL_FG, font=f_label)
        d.text((pad, top + 20), unit, fill=MUTED, font=f_small)
        if known:
            lo, hi = min(known), max(known)
            if hi - lo < MIN_SPAN:  # sub-pixel wobble shouldn't fill the band and look like a big move
                mid = (hi + lo) / 2
                lo, hi = mid - MIN_SPAN / 2, mid + MIN_SPAN / 2
            d.text((pad, top + 36), f"range {min(known):g} to {max(known):g}", fill=MUTED, font=f_small)
            vy = lambda v: bottom - 8 - (v - lo) / (hi - lo) * (band_h - 16)  # noqa: E731
            color = SERIES_COLORS[k % len(SERIES_COLORS)]
            last = None
            for f, v in zip(fm, values):
                if v is None:
                    last = None
                    continue
                x0, x1 = tx(f.start), tx(f.start + f.ms)
                if last is not None:
                    d.line([(x0, vy(last)), (x0, vy(v))], fill=color, width=1)
                d.line([(x0, vy(v)), (x1, vy(v))], fill=color, width=3)
                d.ellipse([x0 - 3, vy(v) - 3, x0 + 3, vy(v) + 3], fill=color)
                d.text((x0 + 5, vy(v) - 13), f"{v:g}", fill=LABEL_FG, font=f_small)
                last = v
        y = bottom + 10
    return img
