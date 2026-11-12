"""Whole levels and the screens a player sees: `pixelforge level NAME [--screens | --at X,Y]`.

A level is composited the way the game draws it: background color or gradient, parallax accents,
tile layers, objects (and the player at the spawn) sorted by their base, then `above` layers. A screen
is what one camera position shows: `resolution / camera.zoom` world pixels, with accents moved by
-camera * scroll and the HUD mock (pixelforge.json "hud") on top.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from .context import edge_contrast
from .grid import TRANSPARENT
from .level import Level, LevelObject
from .model import Sprite, SpriteError, game_resolution, parse_hex, project_config
from .render import LABEL_BG, LABEL_FG, font, font_text, nine_slice, stack, to_image, zoom

GRID = (255, 255, 255, 70)
LABEL = (255, 255, 255, 255)
LABEL_SHADOW = (24, 20, 37, 200)


@dataclass
class Placed:
    image: Image.Image
    x: int            # top-left in level pixels
    y: int
    base: int         # y it sorts by (where it stands)
    label: str = ""


@dataclass
class Composite:
    level: Level
    background: Image.Image                 # level-sized
    ground: Image.Image                     # level-sized: the layers under the characters
    above: Image.Image                      # level-sized: `above` layers
    things: list[Placed] = field(default_factory=list)       # props, sprites, the player
    accents: list[tuple[Image.Image, int, int, float]] = field(default_factory=list)   # (img, x, y, scroll)
    player: tuple[Sprite, object, int, int] | None = None    # sprite, its idle grid, top-left x, y

    def world(self, cam: tuple[int, int] = (0, 0)) -> Image.Image:
        """Everything, level-sized, with the accents placed for this camera position."""
        lv = self.level
        img = self.background.copy()
        cx, cy = cam
        for a, x, y, scroll in self.accents:
            # an accent with scroll s at `at` shows on screen at at - cam * s; in level space that's at + cam * (1 - s)
            img.alpha_composite(a, (round(x + cx * (1 - scroll)), round(y + cy * (1 - scroll))))
        img.alpha_composite(self.ground)
        for t in sorted(self.things, key=lambda t: t.base) if lv.view != "side" else self.things:
            _paste(img, t.image, t.x, t.y)
        img.alpha_composite(self.above)
        return img


def _paste(img: Image.Image, part: Image.Image, x: int, y: int) -> None:
    """alpha_composite that clips parts hanging off the edge."""
    l, t = max(0, x), max(0, y)
    r, b = min(img.width, x + part.width), min(img.height, y + part.height)
    if r > l and b > t:
        img.alpha_composite(part.crop((l - x, t - y, r - x, b - y)), (l, t))


def background(bg: dict, w: int, h: int) -> Image.Image:
    color = parse_hex(bg.get("color", "#262b44"))
    img = Image.new("RGBA", (w, h), color)
    grad = bg.get("gradient")
    if grad and len(grad) == 2:
        top, bottom = parse_hex(grad[0]), parse_hex(grad[1])
        d = ImageDraw.Draw(img)
        for y in range(h):
            f = y / max(1, h - 1)
            d.line([(0, y), (w, y)], fill=tuple(round(a + (b - a) * f) for a, b in zip(top, bottom)))
    return img


_frames: dict[tuple, tuple[Sprite, object, Image.Image]] = {}


def sprite_frame(name: str, state: str | None = None) -> tuple[Sprite, object, Image.Image]:
    """The first frame a prop or character shows: its state, else idle / idle_down, else its first animation."""
    key = (name, state)
    if key not in _frames:
        s = Sprite.load(name)
        anim = state if state in s.animations else next(
            (a for a in ("idle", "idle_down", "idle_side") if a in s.animations), next(iter(s.animations)))
        g = s.frame(anim, 0)
        _frames[key] = (s, g, to_image(s, g))
    return _frames[key]


def compose(lv: Level) -> Composite:
    _frames.clear()
    W, H = lv.pixel_size
    ground, above = Image.new("RGBA", (W, H)), Image.new("RGBA", (W, H))
    tiles: dict[tuple[str, int], Image.Image] = {}
    for layer in lv.layers:
        dest = above if layer.above else ground
        for cy, row in enumerate(layer.cells):
            for cx, c in enumerate(row):
                if c is None:
                    continue
                if c not in tiles:
                    tiles[c] = lv.tilesets[c[0]].tile_image(c[1])
                dest.alpha_composite(tiles[c], (cx * lv.tile_w, cy * lv.tile_h))
    comp = Composite(lv, background(lv.background, W, H), ground, above)
    for a in lv.accents:
        try:
            s, _, img = sprite_frame(a["prop"], a.get("state"))
            ax, ay = (int(v) for v in a["at"])
        except (SpriteError, KeyError, TypeError, ValueError, StopIteration):
            continue
        comp.accents.append((img, ax - s.origin[0], ay - s.origin[1], s.scroll))
    for o in lv.objects:
        name = o.prop or o.sprite
        if name:
            s, _, img = sprite_frame(name, o.state)
            comp.things.append(Placed(img, o.x - s.origin[0], o.y - s.origin[1], o.y, o.name))
    spawn = next((o for o in lv.spawns() if o.name == "player"), next(iter(lv.spawns()), None))
    if lv.player and spawn:
        try:
            s, g, img = sprite_frame(lv.player)
        except (SpriteError, StopIteration):
            s = None
        if s is not None:
            x, y = spawn.x - s.origin[0], spawn.y - s.origin[1]
            comp.things.append(Placed(img, x, y, spawn.y, ""))
            comp.player = (s, g, x, y)
    return comp


# ---- the HUD mock (pixelforge.json "hud"), the same data addPixelforgeHud reads ----------------
def hud_image(w: int, h: int) -> Image.Image | None:
    items = project_config().get("hud")
    if not items:
        return None
    img = Image.new("RGBA", (w, h))
    for item in items:
        try:
            x, y = (int(v) for v in item.get("at", [0, 0]))
            if "panel" in item:
                sheet, icon = item["panel"].split(":", 1)
                s = Sprite.load(sheet)
                pw, ph = (int(v) for v in item["size"])
                _paste(img, nine_slice(to_image(s, s.tile(icon)), s.item_meta[icon]["nine"], pw, ph), x, y)
            elif "icon" in item:
                sheet, icon = item["icon"].split(":", 1)
                s = Sprite.load(sheet)
                one = to_image(s, s.tile(icon))
                for i in range(int(item.get("repeat", 1))):
                    _paste(img, one, x + i * int(item.get("step", one.width + 2)), y)
            elif "text" in item:
                fname, text = item["text"].split(":", 1)
                s = Sprite.load(fname)
                t = font_text(s, text)
                if item.get("tint"):
                    r, g, b, _ = parse_hex(item["tint"])
                    tinted = Image.new("RGBA", t.size, (r, g, b, 255))
                    tinted.putalpha(t.getchannel("A"))
                    t = tinted
                _paste(img, t, x, y)
        except (SpriteError, KeyError, ValueError, TypeError):
            continue   # `check` reports a broken HUD; the preview just leaves it out
    return img


def check_hud() -> list[str]:
    """Problems with pixelforge.json "hud" (for `check`)."""
    out = []
    for i, item in enumerate(project_config().get("hud") or []):
        where = f"hud[{i}]"
        kind = next((k for k in ("panel", "icon", "text") if k in item), None)
        if kind is None:
            out.append(f"{where}: needs \"icon\", \"text\" or \"panel\"")
            continue
        ref, sep, rest = str(item[kind]).partition(":")
        if not sep:
            out.append(f"{where}: {kind} must be \"sheet:{'name' if kind != 'text' else 'TEXT'}\", got {item[kind]!r}")
            continue
        try:
            s = Sprite.load(ref)
        except SpriteError as e:
            out.append(f"{where}: {e}")
            continue
        if kind == "text" and s.kind != "font":
            out.append(f"{where}: {ref!r} is a {s.kind}, not a font")
        elif kind != "text" and rest not in s.tile_names():
            out.append(f"{where}: {ref!r} has no icon {rest!r}")
        elif kind == "panel" and "nine" not in s.item_meta.get(rest, {}):
            out.append(f"{where}: {ref}:{rest} has no \"nine\" insets, so it can't stretch into a panel")
        elif kind == "panel" and "size" not in item:
            out.append(f"{where}: a panel needs \"size\": [w, h]")
    return out


# ---- screens --------------------------------------------------------------------------------
def screen_positions(lv: Level) -> list[tuple[int, int]]:
    """Camera positions that cover the level screen by screen, left to right, top to bottom (the last
    row and column are pulled back to the level's edge, as the camera's bounds do)."""
    W, H = lv.pixel_size
    sw, sh = lv.screen_size()
    xs = sorted({min(x, max(0, W - sw)) for x in range(0, W, sw)})
    ys = sorted({min(y, max(0, H - sh)) for y in range(0, H, sh)})
    return [(x, y) for y in ys for x in xs]


def centred(lv: Level, tx: int, ty: int) -> tuple[int, int]:
    """Camera position with tile (tx, ty) in the middle, kept inside the level."""
    W, H = lv.pixel_size
    sw, sh = lv.screen_size()
    cx = tx * lv.tile_w + lv.tile_w // 2 - sw // 2
    cy = ty * lv.tile_h + lv.tile_h // 2 - sh // 2
    return max(0, min(cx, W - sw)), max(0, min(cy, H - sh))


def render_screen(comp: Composite, cam: tuple[int, int], hud: Image.Image | None) -> Image.Image:
    sw, sh = comp.level.screen_size()
    world = comp.world(cam)
    out = Image.new("RGBA", (sw, sh), (0, 0, 0, 255))
    out.alpha_composite(world.crop((cam[0], cam[1], cam[0] + sw, cam[1] + sh)))
    if hud is not None:
        # the HUD is drawn at the game's resolution; a zoomed camera shows less world behind the same HUD
        z = float(comp.level.camera.get("zoom") or 1)
        h = hud if z == 1 else hud.resize((sw, sh), Image.NEAREST)
        out.alpha_composite(h)
    return out


def visible(o: LevelObject, cam: tuple[int, int], size: tuple[int, int]) -> bool:
    x, y, w, h = o.rect or o.art or (o.x, o.y - 1, 1, 1)
    return x < cam[0] + size[0] and cam[0] < x + w and y < cam[1] + size[1] and cam[1] < y + h


def screen_report(comp: Composite, cam: tuple[int, int], shot: Image.Image) -> str:
    lv = comp.level
    sw, sh = lv.screen_size()
    colors = len({px[:3] for px in shot.getdata()})
    objs = [o.name for o in lv.objects if visible(o, cam, (sw, sh)) and o.type != "spawn"]
    parts = [f"{colors} colors"]
    if comp.player:
        s, g, px, py = comp.player
        # the player where it spawned if that's on this screen, else standing in the middle of it
        spawn_here = cam[0] <= px + s.origin[0] < cam[0] + sw and cam[1] <= py + s.origin[1] <= cam[1] + sh
        if not spawn_here:
            px, py = cam[0] + sw // 2 - s.origin[0], cam[1] + sh // 2 - s.origin[1]
        world = comp.world(cam)
        bare = Image.new("RGBA", world.size)
        bare.alpha_composite(comp.background)
        bare.alpha_composite(comp.ground)
        patch = Image.new("RGBA", (s.width, s.height))
        _paste(patch, bare, -px, -py)
        e = edge_contrast(s, g, patch)
        if e.pairs:
            where = "at the spawn" if spawn_here else "mid-screen"
            parts.append(f"{s.name} vs ground {where}: median {e.median}:1, worst {e.worst}:1"
                         + (f" ({len(e.low)} low-contrast edge px)" if e.low else ""))
    parts.append("objects: " + (", ".join(objs) if objs else "none"))
    return "  ".join(parts)


# ---- the PNGs ---------------------------------------------------------------------------------
def _labelled(img: Image.Image, scale: int, lv: Level, grid: bool, labels: bool) -> Image.Image:
    big = zoom(img, scale)
    d = ImageDraw.Draw(big)
    if grid:
        sw, sh = lv.screen_size()
        W, H = lv.pixel_size
        for x in range(sw, W, sw):
            d.line([(x * scale, 0), (x * scale, H * scale)], fill=GRID, width=1)
        for y in range(sh, H, sh):
            d.line([(0, y * scale), (W * scale, y * scale)], fill=GRID, width=1)
        for i, (cx, cy) in enumerate(screen_positions(lv), 1):
            d.text((cx * scale + 4, cy * scale + 3), str(i), fill=LABEL, font=font(12), stroke_width=2,
                   stroke_fill=LABEL_SHADOW)
    if labels:
        f = font(11)
        for o in lv.objects:
            if o.rect:
                x, y, w, h = o.rect
                d.rectangle([x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1], outline=(44, 232, 245, 255))
            text = o.name if o.type in (o.name, "prop", "sprite") else f"{o.name} ({o.type})"
            if o.to:
                text += f" -> {o.to}"
            d.text((o.x * scale, o.y * scale + 2), text, fill=LABEL, font=f, anchor="ma", stroke_width=2,
                   stroke_fill=LABEL_SHADOW)
    return big


def level_overview(lv: Level, budget: int = 1400) -> tuple[Image.Image, list[str]]:
    comp = compose(lv)
    world = comp.world()
    W, H = lv.pixel_size
    scale = max(1, min(6, budget // max(W, 1)))
    sw, sh = lv.screen_size()
    head = (f"{lv.name}  {lv.width}x{lv.height} tiles of {lv.tile_w}x{lv.tile_h} = {W}x{H} px  {lv.view} view  "
            f"screens of {sw}x{sh} px: {len(screen_positions(lv))}")
    sections = [(f"{head}   (x{scale}; accents shown with the camera at 0,0)", _labelled(world, scale, lv, True, True)),
                ("1x", world)]
    lines = [head]
    for i, cam in enumerate(screen_positions(lv), 1):
        lines.append(f"  screen {i} at ({cam[0]}, {cam[1]}): {screen_report(comp, cam, render_screen(comp, cam, None))}")
    return stack(sections), lines


def screens_sheet(lv: Level, cams: list[tuple[int, int]] | None = None,
                  title: str = "") -> tuple[Image.Image, list[str]]:
    """Each screen at 1x and 2x, numbered, with the HUD on top."""
    comp = compose(lv)
    sw, sh = lv.screen_size()
    hud = hud_image(sw, sh)
    sections, lines = [], []
    positions = cams or screen_positions(lv)
    for i, cam in enumerate(positions, 1):
        shot = render_screen(comp, cam, hud)
        report = screen_report(comp, cam, shot)
        lines.append(f"screen {i} at ({cam[0]}, {cam[1]}): {report}")
        pair = Image.new("RGBA", (sw * 3 + 10, sh * 2), LABEL_BG)
        pair.alpha_composite(shot, (0, 0))
        pair.alpha_composite(zoom(shot, 2), (sw + 10, 0))
        sections.append((f"{title or lv.name}  screen {i}  camera ({cam[0]}, {cam[1]})  {report}", pair))
    return stack(sections), lines
