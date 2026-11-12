"""Lint rules for sprites. Each issue is (level, where, message); level is error/warn/info."""
from __future__ import annotations

import fnmatch
import itertools
from dataclasses import dataclass

from .boxes import frame_boxes
from .grid import TRANSPARENT, Grid
from .model import (ROLES, Sprite, SpriteError, describe_entry, game_resolution, load_game_palette,
                    part_positions)

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
    used_parts: dict[str, list[tuple[int, int]]] = {}

    def collect(entry):
        if isinstance(entry, str):
            used.add(entry)
        elif isinstance(entry, dict):
            if isinstance(entry.get("part"), str):
                try:
                    used_parts.setdefault(entry["part"], []).extend(part_positions(entry))
                except SpriteError:
                    used_parts.setdefault(entry["part"], [])
            if "from" in entry:
                collect(entry["from"])
            for layer in entry.get("layers", []):
                collect(layer)

    for a in s.animations.values():
        for e in a.frames:
            collect(e)
    for tname, e in s.tiles:
        for fe, _ in s.tile_frames(tname):
            collect(fe)

    for pattern in s.roles:
        if not any(fnmatch.fnmatchcase(f, pattern) for f in s.frame_ids() + s.part_ids()):
            issues.append(Issue("info", f"{name}/roles", f"pattern {pattern!r} matches no frame or part files"))

    for pid in s.part_ids():
        where = f"{name}/parts/{pid}.txt"
        try:
            g = s.load_part(pid)
        except SpriteError as e:
            issues.append(Issue("error", where, str(e).split(": ", 1)[-1]))
            continue
        bad = [(x, y) for y, r in enumerate(g.cells) for x, c in enumerate(r)
               if c != TRANSPARENT and c not in s.palette]
        if bad:
            keys = sorted({g.cells[y][x] for x, y in bad})
            issues.append(Issue("error", where, f"undefined palette keys {keys} at {_coords(bad)}"))
        if pid in s.frame_ids():
            issues.append(Issue("warn", where, f"frames/{pid}.txt has the same name; `paint`/`show @{pid}` "
                                               f"pick the frame file"))
        if pid not in used_parts:
            issues.append(Issue("info", where, "not placed by any {\"part\": ...} entry"))
            continue
        off = [(x, y) for x, y in used_parts[pid]
               if x + g.width <= 0 or y + g.height <= 0 or x >= s.width or y >= s.height]
        cut = [(x, y) for x, y in used_parts[pid] if (x, y) not in off
               and (x < 0 or y < 0 or x + g.width > s.width or y + g.height > s.height)]
        if off:
            issues.append(Issue("warn", where, f"placed entirely off the {s.width}x{s.height} canvas at {_coords(off)}"))
        if cut:
            issues.append(Issue("info", where, f"{g.width}x{g.height} part runs off the canvas edge at {_coords(cut)} "
                                               f"(the overhang is cut)"))
    for pid in sorted(set(used_parts) - set(s.part_ids())):
        issues.append(Issue("error", f"{name}/parts/{pid}.txt", "placed by a {\"part\": ...} entry but the file "
                                                                 "doesn't exist"))

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
            issues.append(Issue("info", where, "not used by any " + ("tile" if s.tiled else "animation")))

    if s.tiled:
        return issues + check_tiles(s)
    if s.kind == "prop":
        issues += check_prop(s)

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
            if a.loop and boxes["hurt"] and s.kind != "prop":   # a prop's body is its footprint
                x, y, w, h = boxes["hurt"][0]
                over = max(bx - x, by - y, (x + w) - (bx + bw), (y + h) - (by + bh))
                if over > 2:
                    issues.append(Issue("info", f"{where}[{i}]", f"hurtbox {[x, y, w, h]} pokes {over}px outside "
                                                                 f"the body box {[bx, by, bw, bh]}"))

        # feet = lowest *body* pixel: weapons and effects (hit/none layers) may swing below the feet.
        # Centre-anchored (overhead) sprites have no feet to plant, so these checks don't apply,
        # and neither do they to props floating in the background (clouds, birds).
        bottoms = []
        plants = s.anchor == "feet" and not (s.kind == "prop" and s.layer == "back")
        for i, g in valid if plants else []:
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


def check_prop(s: Sprite) -> list[Issue]:
    """Props: the footprint has to fit, and the view decides what a sensible footprint is."""
    issues: list[Issue] = []
    name = s.name
    if s.footprint:
        x, y, w, h = s.footprint
        if x < 0 or y < 0 or x + w > s.width or y + h > s.height:
            issues.append(Issue("error", f"{name}/footprint", f"{list(s.footprint)} runs off the "
                                                              f"{s.width}x{s.height} canvas"))
        art = s.art_bounds()
        if art and (x + w <= art[0] or art[0] + art[2] <= x or y + h <= art[1] or art[1] + art[3] <= y):
            issues.append(Issue("warn", f"{name}/footprint", f"{list(s.footprint)} doesn't touch the art "
                                                             f"{list(art)}: nothing visible would block"))
    elif s.solid and s.view == "topdown":
        issues.append(Issue("warn", f"{name}/footprint", "solid top-down prop without a footprint: all of its art "
                                                         "blocks, so the player can't walk behind the roof or "
                                                         "canopy. Set \"footprint\" to the base it stands on"))
    if s.solid and s.layer != "world":
        issues.append(Issue("warn", name, f"\"solid\" on a {s.layer!r}-layer prop; only world props collide"))
    if s.layer == "world" and s.scroll != 1:
        issues.append(Issue("info", name, f"scroll {s.scroll} on a world prop: it will drift against the ground "
                                          f"it stands on (parallax accents belong on \"layer\": \"back\")"))
    if s.slice:
        tw, th = s.slice
        if s.width % tw or s.height % th:
            issues.append(Issue("info", f"{name}/slice", f"{s.width}x{s.height} isn't a whole number of "
                                                         f"{tw}x{th} tiles; the last row/column is cut short"))
    try:
        rw, rh = game_resolution()
    except SpriteError as e:
        return issues + [Issue("error", "pixelforge.json", str(e))]
    art = s.art_bounds()
    if art and (art[2] > rw or art[3] > rh):
        issues.append(Issue("warn", name, f"art is {art[2]}x{art[3]}, bigger than the game's {rw}x{rh} screen "
                                          f"(pixelforge.json \"resolution\")"))
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
    noun = {"icons": "icon", "font": "glyph"}.get(s.kind, "tile")
    for p in s.font_problems:
        issues.append(Issue("error", f"{name}/glyphs", p))
    if not s.tiles:
        where = {"icons": "\"icons\"", "font": "the glyph file"}.get(s.kind, "\"tiles\"")
        issues.append(Issue("warn", name, f"{s.kind} has no {noun}s (add them to {where})"))
    if s.kind == "font":
        missing = [c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in s.glyph_widths]
        if missing:
            issues.append(Issue("info", name, f"no glyphs for {''.join(missing)}"))
    seen: set[str] = set()
    for i, (tname, entry) in enumerate(s.tiles):
        where = f"{name}:{noun} {i} {tname!r}"
        if tname in seen:
            issues.append(Issue("error", where, f"duplicate {noun} name; each {noun} needs its own"))
        seen.add(tname)
        frames = s.tile_frames(tname)
        animated = tname in s.tile_anims
        if animated and s.kind != "tileset":
            issues.append(Issue("error", where, f"{s.kind} can't animate; make an animated pickup a prop instead"))
        nine = s.item_meta.get(tname, {}).get("nine")
        if nine and (nine[0] + nine[1] >= s.width or nine[2] + nine[3] >= s.height):
            issues.append(Issue("error", where, f"nine {nine} leaves no middle to stretch in a {s.width}x{s.height} cell"))
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
                issues.append(Issue("warn", fwhere, f"{noun} is empty"))
            elif s.kind != "tileset":
                continue   # icons and glyphs sit on transparency and never repeat edge to edge
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
    for sname in s.stamps:
        try:
            rows = s.stamp_map(sname)
        except SpriteError as e:
            issues.append(Issue("error", f"{name}/stamps/{sname}", str(e)))
            continue
        if len({len(r) for r in rows}) > 1:
            issues.append(Issue("warn", f"{name}/stamps/{sname}", "rows have different lengths"))
        if not any(i >= 0 for r in rows for i in r):
            issues.append(Issue("warn", f"{name}/stamps/{sname}", "stamp is empty"))
    from .level import EDGE_KEYS
    for terrain, at in s.autotile.items():
        where = f"{name}/autotile/{terrain}"
        for tname in [at["base"], *at.get("edges", {}).values()]:
            if tname not in seen:
                issues.append(Issue("error", where, f"no tile {tname!r}"))
        bad = sorted(set(at.get("edges", {})) - set(EDGE_KEYS))
        if bad:
            issues.append(Issue("error", where, f"edge keys {bad}: use n s e w and their combinations in that "
                                                f"order (ne, nw, se, sw, ns, ew, nse, ...)"))
    return issues


def _overlap(a, b) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def check_level(name: str) -> list[Issue]:
    """Levels: everything the level names exists, the player can start somewhere sensible, doors go
    somewhere, and (top-down) what matters can be walked to."""
    from .level import QUIET_TYPES, Level, list_levels
    try:
        lv = Level.load(name)
    except SpriteError as e:
        return [Issue("error", f"level {name}", str(e))]
    issues = [Issue(lvl, f"level {where}", msg) for lvl, where, msg in lv.problems]
    tw, th = lv.tile_w, lv.tile_h
    W, H = lv.pixel_size
    solid = [o for o in lv.objects if o.footprint]

    def cell_of(x, y):
        return int(x // tw), int(y // th)

    spawns = lv.spawns()
    if not spawns:
        issues.append(Issue("error", f"level {name}/objects", "no spawn: put '@' in objects.rows (or an object with "
                                                              "\"type\": \"spawn\") where the player starts"))
    for s in spawns:
        cx, cy = cell_of(s.x, s.y - 1)          # the feet stand on the row above the origin
        if not (0 <= s.x < W and 0 < s.y <= H):
            issues.append(Issue("error", f"level {name}/{s.source}", f"spawn ({s.x}, {s.y}) is outside the "
                                                                     f"{W}x{H} level"))
        elif lv.collides(cx, cy):
            issues.append(Issue("error", f"level {name}/{s.source}", f"spawn is on a colliding tile "
                                                                     f"({lv.colliding_tile(cx, cy)})"))
        for o in solid:
            fx, fy, fw, fh = o.footprint
            if fx <= s.x < fx + fw and fy <= s.y - 1 < fy + fh:
                issues.append(Issue("error", f"level {name}/{s.source}", f"spawn is inside {o.name!r}'s solid "
                                                                         f"footprint {list(o.footprint)}"))
    known = list_levels()
    for o in lv.objects:
        if o.type == "door" and not o.to:
            issues.append(Issue("warn", f"level {name}/{o.source}", "door without \"to\" (the level it leads to)"))
        elif o.to and o.to not in known:
            issues.append(Issue("error", f"level {name}/{o.source}", f"door to {o.to!r}: no such level "
                                                                     f"(known: {', '.join(known)})"))
        x, y, w, h = o.rect or o.art or (o.x, o.y - 1, 1, 1)   # a point stands on the pixel above it
        if x + w <= 0 or y + h <= 0 or x >= W or y >= H:
            issues.append(Issue("warn", f"level {name}/{o.source}", f"{o.name!r} at ({o.x}, {o.y}) is outside the "
                                                                    f"{W}x{H} level"))
    for a, b in itertools.combinations(solid, 2):
        if _overlap(a.footprint, b.footprint):
            issues.append(Issue("warn", f"level {name}/objects", f"solid footprints of {a.name!r} ({a.source}) and "
                                                                 f"{b.name!r} ({b.source}) overlap"))

    if lv.view == "side":
        issues.append(Issue("info", f"level {name}", "side view: platform reachability isn't checked; playtest "
                                                     "the route (`pixelforge play`)"))
        return issues
    # top-down / overhead: flood-fill the walkable cells from the spawn
    blocked = [[lv.collides(cx, cy) for cx in range(lv.width)] for cy in range(lv.height)]
    for o in solid:
        fx, fy, fw, fh = o.footprint
        for cy in range(lv.height):
            for cx in range(lv.width):
                px, py = cx * tw + tw / 2, cy * th + th / 2
                if fx <= px < fx + fw and fy <= py < fy + fh:
                    blocked[cy][cx] = True
    start = next(((cell_of(s.x, s.y - 1)) for s in spawns), None)
    if start is None or not (0 <= start[0] < lv.width and 0 <= start[1] < lv.height):
        return issues
    seen, stack = {start}, [start]
    while stack:
        cx, cy = stack.pop()
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
            if 0 <= nx < lv.width and 0 <= ny < lv.height and (nx, ny) not in seen and not blocked[ny][nx]:
                seen.add((nx, ny))
                stack.append((nx, ny))

    def cells(o):
        if o.rect or o.footprint:
            x, y, w, h = o.rect or o.footprint
            return {(cx, cy) for cy in range(int(y // th), int((y + h - 1) // th) + 1)
                    for cx in range(int(x // tw), int((x + w - 1) // tw) + 1)}
        return {cell_of(o.x, o.y - 1)}

    unreachable = []
    for o in lv.objects:
        if o.type in QUIET_TYPES and not o.props and not (o.prop or "").startswith("chest"):
            continue
        near = {(cx + dx, cy + dy) for cx, cy in cells(o) for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))}
        if not near & seen:
            unreachable.append(f"{o.name!r} ({o.type}, {o.source})")
    if unreachable:
        issues.append(Issue("warn", f"level {name}", f"can't walk from the spawn to: {', '.join(unreachable)}"))
    return issues


def check(names: list[str], levels: list[str] | None = None, hud: bool = False) -> list[Issue]:
    """Sprites, then levels (default: none), then pixelforge.json's "hud" if `hud`."""
    out = []
    for n in names:
        out.extend(check_sprite(n))
    for n in levels or []:
        out.extend(check_level(n))
    if hud:
        from .screens import check_hud
        out.extend(Issue("warn", "pixelforge.json", m) for m in check_hud())
    return out
