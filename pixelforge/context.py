"""A sprite in context: standing on real ground tiles at game zoom, in color and in grayscale, with
the parts of its silhouette that blend into the ground marked.

Grayscale is the classic value check: if the character only separates from the grass by hue, it
will be hard to read in motion. The contrast numbers measure that along the silhouette edge, where
each edge pixel meets the ground pixel next to it.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

from PIL import Image, ImageDraw

from .grid import TRANSPARENT, Grid
from .model import Sprite, SpriteError, list_sprites, parse_hex
from .render import LABEL_BG, LABEL_FG, font, tiled, to_image, zoom

LOW_CONTRAST = 1.8   # edge pixel vs the ground next to it, as a WCAG-style luminance ratio
MUTED = (150, 150, 160, 255)
BLEND = (255, 0, 200, 255)


def luminance(rgba) -> float:
    """Relative luminance (WCAG): perceived brightness of an sRGB color, 0..1."""
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgba[:3]
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


@dataclass
class Ground:
    label: str
    patch: Image.Image   # at least as big as the sprite canvas


def ground(spec: str, w: int, h: int) -> Ground:
    """'#rrggbb', 'tileset' (its first tile) or 'tileset:tile', filled over a w x h canvas."""
    if spec.startswith("#"):
        return Ground(spec, Image.new("RGBA", (w, h), parse_hex(spec)))
    name, _, tile = spec.partition(":")
    ts = Sprite.load(name)
    if ts.kind != "tileset":
        raise SpriteError(f"--on {spec!r}: {name} is not a tileset")
    tile = tile or ts.tile_names()[0]
    img = to_image(ts, ts.tile(tile))
    return Ground(f"{name}:{tile}", tiled(img, -(-w // img.width), -(-h // img.height)).crop((0, 0, w, h)))


def default_grounds(w: int, h: int) -> list[Ground]:
    """The first tile of every tileset, or a mid-gray if the project has none."""
    names = list_sprites("tileset")
    out = [ground(n, w, h) for n in names if Sprite.load(n).tiles]
    return out or [Ground("#5a6988", Image.new("RGBA", (w, h), parse_hex("#5a6988")))]


@dataclass
class EdgeStats:
    pairs: int
    low: list[tuple[int, int]]   # sprite pixels whose contrast with the ground beside them is low
    median: float
    worst: float


def edge_contrast(sprite: Sprite, g: Grid, patch: Image.Image) -> EdgeStats:
    """Every silhouette edge pixel against each transparent 4-neighbour's ground pixel."""
    bg = patch.load()
    values, low = [], set()
    for y, row in enumerate(g.cells):
        for x, c in enumerate(row):
            if c == TRANSPARENT:
                continue
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < g.width and 0 <= ny < g.height and g.cells[ny][nx] == TRANSPARENT:
                    v = contrast(sprite.color(c), bg[nx, ny])
                    values.append(v)
                    if v < LOW_CONTRAST:
                        low.add((x, y))
    if not values:
        return EdgeStats(0, [], 0.0, 0.0)
    return EdgeStats(len(values), sorted(low), round(statistics.median(values), 1), round(min(values), 2))


def context_sheet(sprite: Sprite, frames: list[tuple[str, Grid]], grounds: list[Ground],
                  scale: int = 3) -> tuple[Image.Image, list[str]]:
    """Per ground: a row in color, a row in grayscale and a row marking low-contrast edge pixels."""
    pad, label_h = 10, 18
    cw, ch = sprite.width * scale, sprite.height * scale
    row_h = label_h + ch + pad
    group_h = 22 + 3 * row_h
    img = Image.new("RGBA", (pad + 110 + len(frames) * (cw + pad), pad + len(grounds) * group_h), LABEL_BG)
    d = ImageDraw.Draw(img)
    report = []
    for gi, gr in enumerate(grounds):
        y0 = pad + gi * group_h
        stats = [edge_contrast(sprite, g, gr.patch) for _, g in frames]
        pairs = sum(s.pairs for s in stats)
        low = sum(len(s.low) for s in stats)
        edge_px = sum(len({(x, y) for y, r in enumerate(g.cells) for x, c in enumerate(r) if c != TRANSPARENT
                           and any(g.get(x + dx, y + dy) == TRANSPARENT
                                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}) for _, g in frames)
        medians = [s.median for s in stats if s.pairs]
        worst = min((s.worst for s in stats if s.pairs), default=0)
        pct = 100 * low / edge_px if edge_px else 0
        line = (f"on {gr.label}: silhouette contrast median {statistics.median(medians) if medians else 0:g}:1, "
                f"worst {worst:g}:1; {low} of {edge_px} edge pixels ({pct:.0f}%) blend in (< {LOW_CONTRAST}:1)")
        report.append(line)
        d.text((pad, y0), line, fill=LABEL_FG, font=font(12))
        for r, (label, note, kind) in enumerate((("color", "", "color"),
                                                 ("grayscale", "values only: does it still stand out?", "gray"),
                                                 ("blend map", f"magenta = edge pixels under {LOW_CONTRAST}:1", "blend"))):
            ry = y0 + 22 + r * row_h
            d.text((pad, ry + label_h + ch / 2), label, fill=MUTED, font=font(11), anchor="lm")
            if note:
                d.text((pad + 110, ry + 2), note, fill=MUTED, font=font(10))
            for k, ((flabel, g), st) in enumerate(zip(frames, stats)):
                x0 = pad + 110 + k * (cw + pad)
                if r == 0:
                    d.text((x0, ry + 2), flabel, fill=LABEL_FG, font=font(10))
                scene = gr.patch.crop((0, 0, sprite.width, sprite.height)).copy()
                scene.alpha_composite(to_image(sprite, g))
                if kind == "gray":
                    scene = scene.convert("L").convert("RGBA")
                elif kind == "blend":
                    scene = scene.convert("L").point(lambda v: v * 45 // 100).convert("RGBA")
                    px = scene.load()
                    for x, y in st.low:
                        px[x, y] = BLEND
                img.alpha_composite(zoom(scene, scale), (x0, ry + label_h))
    return img, report
