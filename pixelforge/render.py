"""Rendering grids to PNG previews (for an AI or human to inspect), contact sheets and GIFs."""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .grid import TRANSPARENT, Grid
from .boxes import anim_boxes
from .model import Sprite, SpriteError

CHECK_A = (205, 205, 205, 255)
CHECK_B = (235, 235, 235, 255)
GRID_MINOR = (0, 0, 0, 40)
GRID_MAJOR = (0, 0, 0, 110)
ORIGIN_COLOR = (255, 0, 200, 255)
LABEL_BG = (34, 34, 40, 255)
LABEL_FG = (235, 235, 235, 255)
ONION_PREV = (230, 60, 60)
ONION_NEXT = (60, 120, 230)
BODY_COLOR = (250, 200, 40, 255)    # body box (physics)
HURT_COLOR = (40, 200, 90, 255)     # hurtbox
HIT_COLOR = (240, 40, 60, 255)      # hitbox
MARK_COLOR = (44, 232, 245, 255)    # critiqued spot
SLICE_COLOR = (90, 110, 255, 150)   # where a sliced prop is cut into tiles
MISSING_COLOR = (255, 0, 255, 255)  # a character the font has no glyph for


def auto_scale(w: int, h: int, most: int = 16, budget: int = 1400) -> int:
    """Zoom that keeps a big canvas (a building) to a readable preview size."""
    return max(2, min(most, budget // max(w, h, 1)))


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def to_image(sprite: Sprite, grid: Grid) -> Image.Image:
    """1:1 RGBA image of a grid."""
    img = Image.new("RGBA", (grid.width, grid.height), (0, 0, 0, 0))
    px = img.load()
    for y, row in enumerate(grid.cells):
        for x, key in enumerate(row):
            if key != TRANSPARENT:
                px[x, y] = sprite.color(key)
    return img


def checkerboard(w: int, h: int, cell: int) -> Image.Image:
    img = Image.new("RGBA", (w, h), CHECK_A)
    d = ImageDraw.Draw(img)
    for y in range(0, h, cell):
        for x in range(0, w, cell):
            if (x // cell + y // cell) % 2:
                d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=CHECK_B)
    return img


def tinted(img: Image.Image, rgb: tuple[int, int, int], alpha: float) -> Image.Image:
    """Silhouette of img in a flat color at the given opacity (for onion skins)."""
    a = img.getchannel("A").point(lambda v: int(v * alpha))
    out = Image.new("RGBA", img.size, rgb + (0,))
    out.putalpha(a)
    return out


def zoom(img: Image.Image, scale: int) -> Image.Image:
    return img.resize((img.width * scale, img.height * scale), Image.NEAREST)


def preview(sprite: Sprite, grid: Grid, scale: int = 16, title: str = "",
            prev: Grid | None = None, nxt: Grid | None = None,
            gridlines: bool = True, rulers: bool = True, show_origin: bool = True,
            boxes: dict | None = None, marks: list | None = None,
            slices: tuple[int, int] | None = None) -> Image.Image:
    """Zoomed frame with pixel grid, x/y rulers, origin marker, optional onion skins,
    optional body box / hurtbox / hitbox outlines, optional [x, y, w, h] marks (e.g. a critiqued spot),
    optional tile cut lines (a sliced prop's `slice`), and real-size (1x, 2x) thumbnails."""
    w, h = grid.width * scale, grid.height * scale
    ruler = 22 if rulers else 0
    title_h = 22 if title else 0
    thumbs_w = grid.width * 3 + 24
    canvas = Image.new("RGBA", (ruler + w + thumbs_w, title_h + ruler + max(h, grid.height * 3 + 30) + 8), LABEL_BG)

    art = checkerboard(w, h, scale)
    if prev is not None:
        art.alpha_composite(zoom(tinted(to_image(sprite, prev), ONION_PREV, 0.35), scale))
    if nxt is not None:
        art.alpha_composite(zoom(tinted(to_image(sprite, nxt), ONION_NEXT, 0.25), scale))
    frame_img = to_image(sprite, grid)
    art.alpha_composite(zoom(frame_img, scale))

    d = ImageDraw.Draw(art)
    if gridlines and scale >= 4:
        for i in range(grid.width + 1):
            d.line([(i * scale, 0), (i * scale, h)], fill=GRID_MAJOR if i % 8 == 0 else GRID_MINOR)
        for j in range(grid.height + 1):
            d.line([(0, j * scale), (w, j * scale)], fill=GRID_MAJOR if j % 8 == 0 else GRID_MINOR)
    if slices:
        tw, th = slices
        for i in range(0, grid.width + 1, tw):
            d.line([(i * scale, 0), (i * scale, h)], fill=SLICE_COLOR, width=max(1, scale // 8))
        for j in range(0, grid.height + 1, th):
            d.line([(0, j * scale), (w, j * scale)], fill=SLICE_COLOR, width=max(1, scale // 8))
    if show_origin:
        ox, oy = sprite.origin
        cx, cy = ox * scale, oy * scale
        r = max(2, scale // 4)
        d.line([(cx - r * 2, cy), (cx + r * 2, cy)], fill=ORIGIN_COLOR, width=2)
        d.line([(cx, cy - r * 2), (cx, cy + r * 2)], fill=ORIGIN_COLOR, width=2)
    if boxes is not None:
        draw_boxes(d, sprite, boxes, scale)
    for x, y, mw, mh in marks or []:
        x0, y0, x1, y1 = x * scale, y * scale, (x + mw) * scale - 1, (y + mh) * scale - 1
        d.rectangle([x0 - 1, y0 - 1, x1 + 1, y1 + 1], outline=(0, 0, 0, 255))
        d.rectangle([x0, y0, x1, y1], outline=MARK_COLOR, width=max(1, scale // 6))

    canvas.alpha_composite(art, (ruler, title_h + ruler))
    cd = ImageDraw.Draw(canvas)
    if title:
        cd.text((6, 4), title, fill=LABEL_FG, font=font(14))
    if rulers:
        step = 1 if scale >= 14 else 2 if scale >= 8 else 4
        f = font(10 if scale >= 14 else 9)
        for i in range(0, grid.width, step):
            cd.text((ruler + i * scale + scale / 2, title_h + ruler / 2), str(i), fill=LABEL_FG, font=f, anchor="mm")
        for j in range(0, grid.height, step):
            cd.text((ruler / 2, title_h + ruler + j * scale + scale / 2), str(j), fill=LABEL_FG, font=f, anchor="mm")

    # real-size thumbnails
    tx = ruler + w + 12
    ty = title_h + ruler
    cd.text((tx, ty), "1x", fill=LABEL_FG, font=font(10))
    canvas.alpha_composite(frame_img, (tx, ty + 14))
    ty += grid.height + 22
    cd.text((tx, ty), "2x", fill=LABEL_FG, font=font(10))
    canvas.alpha_composite(zoom(frame_img, 2), (tx, ty + 14))
    return canvas


def draw_boxes(d: ImageDraw.ImageDraw, sprite: Sprite, boxes: dict, scale: int) -> None:
    """Outline the body box (yellow, dashed), hurtboxes (green) and hitboxes (red)."""
    bx, by, bw, bh = sprite.body_rect()
    x0, y0, x1, y1 = bx * scale, by * scale, (bx + bw) * scale - 1, (by + bh) * scale - 1
    dash = max(3, scale // 2)
    for t in range(x0, x1, dash * 2):
        d.line([(t, y0), (min(t + dash, x1), y0)], fill=BODY_COLOR)
        d.line([(t, y1), (min(t + dash, x1), y1)], fill=BODY_COLOR)
    for t in range(y0, y1, dash * 2):
        d.line([(x0, t), (x0, min(t + dash, y1))], fill=BODY_COLOR)
        d.line([(x1, t), (x1, min(t + dash, y1))], fill=BODY_COLOR)
    width = 2 if scale >= 6 else 1
    for kind, color in (("hurt", HURT_COLOR), ("hit", HIT_COLOR)):
        for x, y, w, h in boxes.get(kind, []):
            d.rectangle([x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1], outline=color, width=width)


def sheet(sprite: Sprite, anims: list[str], scale: int = 6, onion: bool = False,
          boxes: bool = False) -> Image.Image:
    """Contact sheet: one row per animation, one column per frame, plus a 1x strip."""
    pad, label_h, name_w = 8, 16, 0
    rows = [(a, sprite.anim_frames(a)) for a in anims]
    all_boxes = {a: anim_boxes(sprite, a) for a in anims} if boxes else {}
    max_frames = max((len(f) for _, f in rows), default=1)
    cw, ch = sprite.width * scale, sprite.height * scale
    f_small, f_name = font(11), font(13)
    name_w = max((max(int(f_name.getlength(a)), int(f_small.getlength(f"{sprite.anim(a).fps:g}fps loop")))
                  for a in anims), default=0) + pad * 2
    strip_w = sprite.width * max_frames + pad
    row_h = label_h + ch + pad
    img = Image.new("RGBA", (name_w + max_frames * (cw + pad) + strip_w + pad, pad + len(rows) * row_h), LABEL_BG)
    d = ImageDraw.Draw(img)
    for r, (aname, frames) in enumerate(rows):
        a = sprite.anim(aname)
        y0 = pad + r * row_h
        d.text((pad, y0 + label_h + ch / 2), aname, fill=LABEL_FG, font=f_name, anchor="lm")
        d.text((pad, y0 + label_h + ch / 2 + 16), f"{a.fps:g}fps{' loop' if a.loop else ''}",
               fill=(150, 150, 160, 255), font=f_small, anchor="lm")
        for i, g in enumerate(frames):
            x0 = name_w + i * (cw + pad)
            cell = checkerboard(cw, ch, scale)
            if onion and len(frames) > 1 and (i > 0 or a.loop):
                cell.alpha_composite(zoom(tinted(to_image(sprite, frames[i - 1]), ONION_PREV, 0.35), scale))
            fi = to_image(sprite, g)
            cell.alpha_composite(zoom(fi, scale))
            if boxes:
                draw_boxes(ImageDraw.Draw(cell), sprite, all_boxes[aname][i], scale)
            img.alpha_composite(cell, (x0, y0 + label_h))
            d.text((x0, y0 + 1), f"{i}  {a.duration_ms(i)}ms{'  ACTIVE' if a.active(i) else ''}",
                   fill=HIT_COLOR if a.active(i) else LABEL_FG, font=f_small)
            # 1x strip at the end of the row
            img.alpha_composite(fi, (name_w + max_frames * (cw + pad) + i * sprite.width, y0 + label_h))
    return img


def tiled(img: Image.Image, nx: int, ny: int) -> Image.Image:
    out = Image.new("RGBA", (img.width * nx, img.height * ny), (0, 0, 0, 0))
    for y in range(ny):
        for x in range(nx):
            out.alpha_composite(img, (x * img.width, y * img.height))
    return out


def map_image(sprite: Sprite, rows: list[list[int]], t_ms: int = 0) -> Image.Image:
    """1:1 image of a map given as rows of tile indices (-1 = empty), `t_ms` into its animations."""
    tw, th = sprite.width, sprite.height
    tiles = [to_image(sprite, sprite.tile(n, t_ms)) for n in sprite.tile_names()]
    out = Image.new("RGBA", (max((len(r) for r in rows), default=0) * tw or 1, len(rows) * th or 1), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, i in enumerate(row):
            if i >= 0:
                out.alpha_composite(tiles[i], (x * tw, y * th))
    return out


def tileset_preview(sprite: Sprite, names: list[str] | None = None, scale: int = 4, repeat: int = 3,
                    sample: bool = True) -> Image.Image:
    """Every tile repeated `repeat`x`repeat` (seams show up as lines), labelled with its index and
    properties; then each animated tile's frames side by side (each repeated 2x2); then the
    sprite.json sample map (zoomed, plus 1x)."""
    pad, label_h = 10, 30
    names = names or sprite.tile_names()
    cw, ch = sprite.width * repeat * scale, sprite.height * repeat * scale
    cell_w = max(cw, 120)
    per_row = max(1, min(len(names), 1200 // (cell_w + pad)))
    n_rows = -(-len(names) // per_row) if names else 0
    sample_rows = sprite.sample_map() if sample else []
    smap = zoom(map_image(sprite, sample_rows), max(1, scale // 2)) if sample_rows else None
    animated = [n for n in names if n in sprite.tile_anims]
    fw, fh = sprite.width * 2 * scale, sprite.height * 2 * scale   # one animation frame, repeated 2x2
    anim_w = max((180 + len(sprite.tile_anims[n]) * (fw + pad) for n in animated), default=0)
    width = max(pad + per_row * (cell_w + pad), anim_w + pad)
    height = pad + n_rows * (label_h + ch + pad)
    anim_y = height + (24 if animated else 0)
    height = anim_y + len(animated) * (fh + 16 + pad)
    if smap:
        width = max(width, smap.width + pad * 2 + sprite.width * len(sample_rows[0]) + pad)
        height += 24 + smap.height + pad
    img = Image.new("RGBA", (width, height), LABEL_BG)
    d = ImageDraw.Draw(img)
    f, f_small = font(13), font(10)
    for k, name in enumerate(names):
        i = sprite.tile_index(name)
        x0 = pad + (k % per_row) * (cell_w + pad)
        y0 = pad + (k // per_row) * (label_h + ch + pad)
        d.text((x0, y0), f"{i}  {name}", fill=LABEL_FG, font=f)
        props = " ".join(f"{p}={v}" if v is not True else p for p, v in sprite.tile_properties(name).items())
        if name in sprite.tile_anims:
            props = f"{len(sprite.tile_anims[name])}-frame anim  {props}"
        if props:
            d.text((x0, y0 + 16), props, fill=(150, 150, 160, 255), font=f_small)
        cell = checkerboard(cw, ch, scale * 2)
        cell.alpha_composite(zoom(tiled(to_image(sprite, sprite.tile(name)), repeat, repeat), scale))
        img.alpha_composite(cell, (x0, y0 + label_h))
    if animated:
        d.text((pad, anim_y - 20), "animated tiles (each frame repeated 2x2)", fill=LABEL_FG, font=f)
    for k, name in enumerate(animated):
        y0 = anim_y + k * (fh + 16 + pad)
        frames = sprite.tile_anims[name]
        d.text((pad, y0 + 16 + fh / 2), f"{sprite.tile_index(name)}  {name}", fill=LABEL_FG, font=f, anchor="lm")
        d.text((pad, y0 + 16 + fh / 2 + 16), f"{sum(ms for _, ms in frames)} ms loop",
               fill=(150, 150, 160, 255), font=f_small, anchor="lm")
        for j, (entry, ms) in enumerate(frames):
            x0 = 180 + j * (fw + pad)
            d.text((x0, y0), f"{j}  {ms}ms", fill=LABEL_FG, font=f_small)
            cell = checkerboard(fw, fh, scale * 2)
            cell.alpha_composite(zoom(tiled(to_image(sprite, sprite.resolve(entry)), 2, 2), scale))
            img.alpha_composite(cell, (x0, y0 + 16))
    if smap:
        y0 = height - smap.height - pad - 24
        d.text((pad, y0 + 4), "sample map (sprite.json \"sample\")", fill=LABEL_FG, font=f)
        img.alpha_composite(smap, (pad, y0 + 24))
        img.alpha_composite(map_image(sprite, sample_rows), (pad * 2 + smap.width, y0 + 24))
    extra = []
    if sample and (st := stamps_preview(sprite, max(1, scale // 2))):
        extra.append(("stamps (sprite.json \"stamps\": stampPixelforgeTiles places these)", st))
    if pn := panels_preview(sprite, max(2, scale - 1)):
        extra.append(("nine-slice panels, stretched", pn))
    return stack(extra, img) if extra else img


def stack(sections: list[tuple[str, Image.Image]], base: Image.Image | None = None, pad: int = 10) -> Image.Image:
    """Append titled image sections under `base` (or under nothing)."""
    parts = ([("", base)] if base is not None else []) + sections
    width = max(im.width + (0 if not t else pad * 2) for t, im in parts)
    height = sum(im.height + (24 + pad if t else 0) for t, im in parts) + pad
    out = Image.new("RGBA", (width, height), LABEL_BG)
    d = ImageDraw.Draw(out)
    y = 0
    for title, im in parts:
        if title:
            d.text((pad, y + 6), title, fill=LABEL_FG, font=font(13))
            out.alpha_composite(im, (pad, y + 24))
            y += im.height + 24 + pad
        else:
            out.alpha_composite(im, (0, y))
            y += im.height
    return out


def stamps_preview(sprite: Sprite, scale: int = 2) -> Image.Image | None:
    """Every tileset stamp drawn side by side (zoomed), each labelled."""
    if not sprite.stamps:
        return None
    imgs = []
    for name in sprite.stamps:
        try:
            m = map_image(sprite, sprite.stamp_map(name))
        except SpriteError:   # `check` reports it; draw the others
            continue
        cell = checkerboard(m.width * scale, m.height * scale, scale * 4)
        cell.alpha_composite(zoom(m, scale))
        imgs.append((name, cell))
    if not imgs:
        return None
    pad = 12
    out = Image.new("RGBA", (sum(i.width + pad for _, i in imgs) + pad, max(i.height for _, i in imgs) + 22 + pad), LABEL_BG)
    d = ImageDraw.Draw(out)
    x = pad
    for name, im in imgs:
        d.text((x, 2), name, fill=LABEL_FG, font=font(11))
        out.alpha_composite(im, (x, 18))
        x += im.width + pad
    return out


def nine_slice(img: Image.Image, nine: list[int], w: int, h: int) -> Image.Image:
    """Stretch an image to w x h keeping its border strips (left, right, top, bottom px) unscaled,
    the way Phaser's NineSlice draws a panel."""
    l, r, t, b = nine
    sw, sh = img.size
    xs, ys = [(0, l, 0, l), (l, sw - r, l, w - r), (sw - r, sw, w - r, w)], \
             [(0, t, 0, t), (t, sh - b, t, h - b), (sh - b, sh, h - b, h)]
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for sx0, sx1, dx0, dx1 in xs:
        for sy0, sy1, dy0, dy1 in ys:
            if sx1 > sx0 and sy1 > sy0 and dx1 > dx0 and dy1 > dy0:
                out.alpha_composite(img.crop((sx0, sy0, sx1, sy1)).resize((dx1 - dx0, dy1 - dy0), Image.NEAREST),
                                    (dx0, dy0))
    return out


def panels_preview(sprite: Sprite, scale: int = 3) -> Image.Image | None:
    """Each nine-slice icon stretched to three sizes: check that its corners and edges hold up."""
    items = [(n, m["nine"]) for n, m in sprite.item_meta.items() if "nine" in m and n in sprite.tile_names()]
    if not items:
        return None
    w, h = sprite.width, sprite.height
    sizes = [(w * 2, h), (w * 4, h * 2), (w * 3, h * 3)]
    pad = 12
    rows = []
    for name, nine in items:
        src = to_image(sprite, sprite.tile(name))
        cells = [zoom(nine_slice(src, nine, sw, sh), scale) for sw, sh in sizes]
        rows.append((name, nine, cells))
    row_h = max(c.height for _, _, cs in rows for c in cs) + 22
    width = pad + sum(c.width + pad for c in rows[0][2])
    out = Image.new("RGBA", (width, pad + len(rows) * (row_h + pad)), LABEL_BG)
    d = ImageDraw.Draw(out)
    for k, (name, nine, cells) in enumerate(rows):
        y = pad + k * (row_h + pad)
        d.text((pad, y), f"{name}  nine {nine}", fill=LABEL_FG, font=font(11))
        x = pad
        for c, (sw, sh) in zip(cells, sizes):
            out.alpha_composite(c, (x, y + 18))
            d.text((x + c.width - 4, y + 4), f"{sw}x{sh}", fill=(150, 150, 160, 255), font=font(10), anchor="ra")
            x += c.width + pad
    return out


def glyph_for(sprite: Sprite, ch: str) -> str | None:
    """The glyph that draws `ch`: lowercase falls back to the capital when the font has no lowercase."""
    if ch in sprite.glyph_widths:
        return ch
    if ch.upper() in sprite.glyph_widths and not any(c.islower() for c in sprite.glyph_widths):
        return ch.upper()
    return None


def font_text(sprite: Sprite, text: str) -> Image.Image:
    """`text` set in a bitmap font at 1x, using each glyph's width + the font's spacing (as Phaser does).
    Characters with no glyph show as a magenta block."""
    lines = text.split("\n")
    widths = []
    for line in lines:
        x = 0
        for ch in line:
            g = glyph_for(sprite, ch)
            x += sprite.space_width if ch == " " else (sprite.glyph_widths[g] if g else sprite.width) + sprite.letter_spacing
        widths.append(x)
    out = Image.new("RGBA", (max(1, max(widths, default=1)), max(1, sprite.line_height * len(lines))), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    for row, line in enumerate(lines):
        x, y = 0, row * sprite.line_height
        for ch in line:
            if ch == " ":
                x += sprite.space_width
                continue
            g = glyph_for(sprite, ch)
            if g is None:
                d.rectangle([x, y, x + sprite.width - 1, y + sprite.height - 1], fill=MISSING_COLOR)
                x += sprite.width + sprite.letter_spacing
                continue
            gw = sprite.glyph_widths[g]
            out.alpha_composite(to_image(sprite, sprite.tile(g)).crop((0, 0, gw, sprite.height)), (x, y))
            x += gw + sprite.letter_spacing
    return out


FONT_BGS = [(24, 20, 37, 255), (90, 105, 136, 255)]   # outline-dark and slate: where HUD text usually sits
FONT_SAMPLES = ["THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG", "0123456789 !?.,:;'\"-+=/()%",
                "HP 42/100   GOLD 1,350   LEVEL 3", "Press START to play"]


def font_preview(sprite: Sprite, texts: list[str] | None = None, scale: int = 4) -> Image.Image:
    """A font's glyph grid (each glyph zoomed, with its width) and sample text at 1x, 2x and zoomed,
    on dark and light backgrounds."""
    pad = 10
    chars = sprite.tile_names()
    gw, gh = sprite.width * scale, sprite.height * scale
    per_row = max(1, min(len(chars), 1100 // (gw + pad)))
    rows = -(-len(chars) // per_row) if chars else 0
    grid = Image.new("RGBA", (pad + per_row * (gw + pad), pad + rows * (gh + 16 + pad)), LABEL_BG)
    d = ImageDraw.Draw(grid)
    for k, ch in enumerate(chars):
        x0, y0 = pad + (k % per_row) * (gw + pad), pad + (k // per_row) * (gh + 16 + pad)
        d.text((x0, y0), f"{ch}  w{sprite.glyph_widths[ch]}", fill=LABEL_FG, font=font(10))
        cell = Image.new("RGBA", (gw, gh), FONT_BGS[1])   # fonts are usually light ink: show them on mid-dark
        cell.alpha_composite(zoom(to_image(sprite, sprite.tile(ch)), scale))
        grid.alpha_composite(cell, (x0, y0 + 14))
    sections = []
    for text in texts or FONT_SAMPLES:
        img = font_text(sprite, text)
        for z, bg in ((1, FONT_BGS[0]), (2, FONT_BGS[0]), (max(3, scale // 2 + 1), FONT_BGS[1])):
            panel = Image.new("RGBA", (img.width * z + 8, img.height * z + 8), bg)
            panel.alpha_composite(zoom(img, z), (4, 4))
            sections.append((f"{z}x  {text}" if z == 1 else f"{z}x", panel))
    return stack(sections, grid)


def palette_swatch(sprite: Sprite, cell: int = 40) -> Image.Image:
    items = list(sprite.palette_raw.items())
    cols = 8
    rows = max(1, (len(items) + cols - 1) // cols)
    img = Image.new("RGBA", (cols * (cell + 70), rows * (cell + 8) + 8), LABEL_BG)
    d = ImageDraw.Draw(img)
    for i, (key, raw) in enumerate(items):
        x, y = (i % cols) * (cell + 70) + 8, (i // cols) * (cell + 8) + 8
        d.rectangle([x, y, x + cell - 1, y + cell - 1], fill=sprite.palette[key], outline=(0, 0, 0, 255))
        d.text((x + cell + 6, y + 4), f"'{key}'", fill=LABEL_FG, font=font(14))
        d.text((x + cell + 6, y + 22), raw[:10], fill=(170, 170, 180, 255), font=font(10))
    return img


def tile_timeline(sprite: Sprite, names: list[str], max_ms: int = 12000) -> list[tuple[int, int]]:
    """[(start_ms, duration_ms)] covering one full cycle of every listed animated tile together
    (the least common multiple of their loop lengths, capped at max_ms), split wherever any of
    them changes frame."""
    loops = [sprite.tile_anims[n] for n in names
             if n in sprite.tile_anims and all(ms > 0 for _, ms in sprite.tile_anims[n])]
    if not loops:
        return [(0, 1000)]
    length = 1
    for frames in loops:
        length = math.lcm(length, sum(ms for _, ms in frames))
    length = min(length, max_ms)
    cuts = {0, length}
    for frames in loops:
        t = 0
        while t < length:
            for _, ms in frames:
                cuts.add(min(t, length))
                t += ms
    cuts = sorted(cuts)
    return [(a, b - a) for a, b in zip(cuts, cuts[1:]) if b > a]


def save_tiles_gif(sprite: Sprite, path: Path, tile: str | None = None, scale: int = 4,
                   bg: tuple[int, int, int] = (60, 64, 72)) -> None:
    """Animated GIF of one tile repeated 3x3, or (tile=None) of the sample map, at real timing."""
    if tile:
        rows = [[sprite.tile_index(tile)] * 3] * 3
        names = [tile]
    else:
        rows = sprite.sample_map()
        names = sorted({sprite.tile_names()[i] for r in rows for i in r if i >= 0})
    timeline = tile_timeline(sprite, names)
    frames = []
    for t, _ in timeline:
        m = map_image(sprite, rows, t)
        base = Image.new("RGBA", m.size, bg + (255,))
        base.alpha_composite(m)
        frames.append(zoom(base, scale).convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT))
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=[ms for _, ms in timeline],
                   loop=0, disposal=2, optimize=False)


def save_gif(sprite: Sprite, anim: str, path: Path, scale: int = 8,
             bg: tuple[int, int, int] = (60, 64, 72)) -> None:
    a = sprite.anim(anim)
    frames = []
    for g in sprite.anim_frames(anim):
        base = Image.new("RGBA", (sprite.width, sprite.height), bg + (255,))
        base.alpha_composite(to_image(sprite, g))
        frames.append(zoom(base, scale).convert("RGB").quantize(colors=255, method=Image.Quantize.MEDIANCUT))
    durations = [a.duration_ms(i) for i in range(len(frames))]
    extra = {"loop": 0} if a.loop else {}  # no loop key = play once
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=durations,
                   disposal=2, optimize=False, **extra)
