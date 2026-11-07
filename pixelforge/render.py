"""Rendering grids to PNG previews (for an AI or human to inspect), contact sheets and GIFs."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .grid import TRANSPARENT, Grid
from .boxes import anim_boxes
from .model import Sprite

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
            boxes: dict | None = None) -> Image.Image:
    """Zoomed frame with pixel grid, x/y rulers, origin marker, optional onion skins,
    optional body box / hurtbox / hitbox outlines, and real-size (1x, 2x) thumbnails."""
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
    if show_origin:
        ox, oy = sprite.origin
        cx, cy = ox * scale, oy * scale
        r = max(2, scale // 4)
        d.line([(cx - r * 2, cy), (cx + r * 2, cy)], fill=ORIGIN_COLOR, width=2)
        d.line([(cx, cy - r * 2), (cx, cy + r * 2)], fill=ORIGIN_COLOR, width=2)
    if boxes is not None:
        draw_boxes(d, sprite, boxes, scale)

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
