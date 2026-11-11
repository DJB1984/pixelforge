"""Before/after: a sprite as committed in git next to the working tree, with every changed pixel marked.

The committed copy (sprite.json, frames, the game palette and pixelforge.json) is extracted into a
temporary project and loaded there, so the "before" image is exactly what that commit exported.
Frames are aligned on their origins, so a resized sprite still lines up.
"""
from __future__ import annotations

import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from .model import MARKER, Sprite, SpriteError, root, set_root
from .render import LABEL_BG, LABEL_FG, checkerboard, font, to_image, zoom

ADDED = (40, 200, 90, 255)
REMOVED = (240, 40, 60, 255)
RECOLORED = (250, 200, 40, 255)


def _git(cwd: Path, *args: str) -> bytes:
    try:
        r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, timeout=30)
    except FileNotFoundError:
        raise SpriteError("git is not installed, so there is nothing to compare against") from None
    if r.returncode:
        raise SpriteError(f"git {' '.join(args)}: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout


@contextmanager
def sprite_at(name: str, ref: str = "HEAD"):
    """Yields the sprite as committed at `ref`, or None if it didn't exist there."""
    proj = root()
    prefix = _git(proj, "rev-parse", "--show-prefix").decode().strip()   # project folder inside the repo
    top = Path(_git(proj, "rev-parse", "--show-toplevel").decode().strip())
    try:
        _git(proj, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    except SpriteError:
        raise SpriteError(f"{ref!r} is not a commit in this repository (try HEAD, HEAD~1, a branch or a tag)") from None
    files = _git(top, "ls-tree", "-r", "--name-only", ref, "--", f"{prefix}sprites/{name}/").decode().splitlines()
    if not files:
        yield None
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for f in files:
            out = tmp / f[len(prefix):]
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(_git(top, "show", f"{ref}:{f}"))
        for extra in ("palettes/game.json", MARKER):
            out = tmp / extra
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                out.write_bytes(_git(top, "show", f"{ref}:{prefix}{extra}"))
            except SpriteError:   # not committed then: use today's
                if (proj / extra).is_file():
                    out.write_bytes((proj / extra).read_bytes())
        set_root(tmp)
        try:
            before = Sprite.load(name)
        finally:
            set_root(proj)
        yield before   # frames load lazily from tmp, which lives until the caller is done


def align(b: Image.Image | None, b_origin, a: Image.Image | None, a_origin):
    """Both images on one canvas with their origins at the same point. Returns (before, after);
    a missing side becomes a blank image."""
    sides = [(img, o) for img, o in ((b, b_origin), (a, a_origin)) if img is not None]
    left = max(o[0] for _, o in sides)
    top = max(o[1] for _, o in sides)
    w = max(img.width - o[0] for img, o in sides) + left
    h = max(img.height - o[1] for img, o in sides) + top
    out = []
    for img, o in ((b, b_origin), (a, a_origin)):
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if img is not None:
            canvas.alpha_composite(img, (left - o[0], top - o[1]))
        out.append(canvas)
    return out[0], out[1]


@dataclass
class Diff:
    added: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    recolored: list = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.added) + len(self.removed) + len(self.recolored)

    def summary(self) -> str:
        if not self.total:
            return "unchanged"
        pts = self.added + self.removed + self.recolored
        xs, ys = [x for x, _ in pts], [y for _, y in pts]
        return (f"{self.total} px changed (+{len(self.added)} added, -{len(self.removed)} removed, "
                f"~{len(self.recolored)} recolored) within x {min(xs)}-{max(xs)}, y {min(ys)}-{max(ys)}")


def diff(before: Image.Image, after: Image.Image) -> Diff:
    out = Diff()
    pb, pa = before.load(), after.load()
    for y in range(before.height):
        for x in range(before.width):
            b, a = pb[x, y], pa[x, y]
            if b == a or (b[3] == 0 and a[3] == 0):
                continue
            (out.added if b[3] == 0 else out.removed if a[3] == 0 else out.recolored).append((x, y))
    return out


def diff_image(before: Image.Image, after: Image.Image, d: Diff) -> Image.Image:
    """The new frame dimmed to gray, with added (green), removed (red) and recolored (yellow) pixels."""
    gray = after.convert("LA").convert("RGBA")
    gray.putalpha(gray.getchannel("A").point(lambda v: v * 35 // 100))
    px = gray.load()
    for pts, color in ((d.added, ADDED), (d.removed, REMOVED), (d.recolored, RECOLORED)):
        for x, y in pts:
            px[x, y] = color
    return gray


def triptych(before: Image.Image, after: Image.Image, scale: int, title: str, ref: str) -> tuple[Image.Image, Diff]:
    d = diff(before, after)
    pad, label_h = 10, 18
    w, h = before.width * scale, before.height * scale
    thumbs = before.width * 2 + pad
    img = Image.new("RGBA", (pad + 3 * (w + pad) + thumbs + pad, 24 + label_h + h + pad), LABEL_BG)
    dr = ImageDraw.Draw(img)
    dr.text((pad, 4), f"{title}   {d.summary()}", fill=LABEL_FG, font=font(13))
    panels = ((f"before ({ref})", before), ("after (working tree)", after),
              ("changes: green added, red removed, yellow recolored", diff_image(before, after, d)))
    for k, (label, im) in enumerate(panels):
        x0 = pad + k * (w + pad)
        dr.text((x0, 24), label, fill=LABEL_FG, font=font(11))
        cell = checkerboard(w, h, scale)
        cell.alpha_composite(zoom(im, scale))
        if scale >= 6:
            cd = ImageDraw.Draw(cell)
            for i in range(0, before.width + 1, 8):
                cd.line([(i * scale, 0), (i * scale, h)], fill=(0, 0, 0, 70))
            for j in range(0, before.height + 1, 8):
                cd.line([(0, j * scale), (w, j * scale)], fill=(0, 0, 0, 70))
        img.alpha_composite(cell, (x0, 24 + label_h))
    tx = pad + 3 * (w + pad)
    dr.text((tx, 24), "1x", fill=LABEL_FG, font=font(11))
    img.alpha_composite(before, (tx, 24 + label_h))
    img.alpha_composite(after, (tx + before.width + 4, 24 + label_h))
    return img, d


def _frames(s: Sprite | None) -> dict[str, list[tuple[str, Image.Image]]]:
    """{group: [(label, image), ...]}: animations for sprites, one group of tiles for tilesets."""
    if s is None:
        return {}
    if s.tiled:
        return {"tiles": [(n, to_image(s, s.tile(n))) for n in s.tile_names()]}
    return {a: [(f"{a}[{i}]", to_image(s, g)) for i, g in enumerate(s.anim_frames(a))] for a in s.animations}


def compare_all(before: Sprite | None, after: Sprite, scale: int, ref: str,
                limit: int = 16) -> tuple[list[str], Image.Image | None]:
    """Every animation frame (or tile) of the sprite against `ref`: report lines plus a stacked
    image of the changed frames (at most `limit`)."""
    if before is None:
        return [f"{after.name} is not in {ref}: it's new"], None
    lines, panels, same = [], [], 0
    fb, fa = _frames(before), _frames(after)
    for group in list(fa) + [g for g in fb if g not in fa]:
        if group not in fb:
            lines.append(f"{group}: new ({len(fa[group])} frames)")
            continue
        if group not in fa:
            lines.append(f"{group}: removed")
            continue
        bl, al = fb[group], fa[group]
        if group != "tiles" and len(bl) != len(al):
            lines.append(f"{group}: {len(bl)} -> {len(al)} frames")
        b_by = dict(bl) if group == "tiles" else {str(i): im for i, (_, im) in enumerate(bl)}
        a_items = al if group == "tiles" else [(str(i), im) for i, (_, im) in enumerate(al)]
        for key, a_img in a_items:
            label = key if group == "tiles" else f"{group}[{key}]"
            if key not in b_by:
                lines.append(f"{label}: new")
                continue
            b_img, a_img2 = align(b_by[key], before.origin, a_img, after.origin)
            d = diff(b_img, a_img2)
            if not d.total:
                same += 1
                continue
            lines.append(f"{label}: {d.summary()}")
            if len(panels) < limit:
                panels.append(triptych(b_img, a_img2, scale, label, ref)[0])
        if group == "tiles":
            lines += [f"{k}: removed" for k in b_by if k not in dict(al)]
    lines.append(f"{same} frame(s) unchanged")
    if not panels:
        return lines, None
    out = Image.new("RGBA", (max(p.width for p in panels), sum(p.height for p in panels)), LABEL_BG)
    y = 0
    for p in panels:
        out.alpha_composite(p, (0, y))
        y += p.height
    return lines, out
