"""Loading sprites (sprite.json + frames/*.txt) and resolving frame entries into Grids."""
from __future__ import annotations

import fnmatch
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .grid import TRANSPARENT, Grid, GridError

MARKER = "pixelforge.json"  # marks a game's art root; created by `pixelforge init`
ASSETS = Path(__file__).resolve().parent / "assets"
_root: Path | None = None


def find_root(start: Path | None = None) -> Path:
    """$PIXELFORGE_ROOT, else the nearest folder at or above `start` (default: cwd) holding
    pixelforge.json, else `start` itself."""
    env = os.environ.get("PIXELFORGE_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / MARKER).is_file():
            return d
    return here


def root() -> Path:
    global _root
    if _root is None:
        _root = find_root()
    return _root


def set_root(path: Path | str | None) -> None:
    global _root
    _root = Path(path).resolve() if path else None


def project_config() -> dict:
    p = root() / MARKER
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def rel(p: Path) -> str:
    try:
        return str(p.relative_to(root()))
    except ValueError:
        return str(p)

RGBA = tuple[int, int, int, int]


class SpriteError(ValueError):
    pass


def sprites_dir() -> Path:
    return root() / "sprites"


def palettes_dir() -> Path:
    return root() / "palettes"


def list_sprites() -> list[str]:
    d = sprites_dir()
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if (p / "sprite.json").is_file())


def parse_hex(value: str) -> RGBA:
    v = value.lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) not in (6, 8):
        raise SpriteError(f"bad hex color {value!r}")
    try:
        r, g, b = (int(v[i:i + 2], 16) for i in (0, 2, 4))
        a = int(v[6:8], 16) if len(v) == 8 else 255
    except ValueError:
        raise SpriteError(f"bad hex color {value!r}") from None
    return r, g, b, a


def to_hex(rgba: RGBA) -> str:
    r, g, b, a = rgba
    return f"#{r:02x}{g:02x}{b:02x}" + ("" if a == 255 else f"{a:02x}")


def load_game_palette(name: str = "game") -> dict[str, RGBA]:
    path = palettes_dir() / f"{name}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: parse_hex(v) for k, v in data.get("colors", {}).items()}


# Standard canvases. The character stands in the body box (bottom-centre, on the origin);
# the rest of the canvas is room for weapons, smears and effects. Override in pixelforge.json "classes".
DEFAULT_CLASSES = {
    "small": {"size": [32, 32], "body": [16, 16]},
    "humanoid": {"size": [64, 48], "body": [16, 30]},
    "large": {"size": [96, 96], "body": [48, 64]},
}
ROLES = {"hurt": "u", "hit": "x", "none": "n"}  # role -> char in a role grid
ENTRY_KEYS = {"from", "layers", "flip", "offset", "replace", "duration", "active"}


def size_classes() -> dict[str, dict]:
    return {**DEFAULT_CLASSES, **project_config().get("classes", {})}


@dataclass
class Animation:
    name: str
    fps: float
    loop: bool
    frames: list  # raw entries: str | dict

    def duration_ms(self, i: int) -> int:
        entry = self.frames[i]
        if isinstance(entry, dict) and "duration" in entry:
            return int(entry["duration"])
        return round(1000 / self.fps)

    def active(self, i: int) -> bool:
        """Active frames are the ones whose hitboxes deal damage."""
        entry = self.frames[i]
        return isinstance(entry, dict) and bool(entry.get("active"))


@dataclass
class Sprite:
    name: str
    path: Path
    width: int
    height: int
    origin: tuple[int, int]
    palette_raw: dict[str, str]
    palette: dict[str, RGBA]
    animations: dict[str, Animation]
    size_class: str | None = None
    body: tuple[int, int] = (16, 30)          # body box width, height
    roles: dict[str, str] = field(default_factory=dict)  # frame-id glob -> hurt | hit | none
    hit_pad: int = 0
    hurt_pad: int = 0
    _frame_cache: dict[str, Grid] = field(default_factory=dict, repr=False)

    # ---- loading ----------------------------------------------------------------------
    @classmethod
    def load(cls, name: str) -> "Sprite":
        path = sprites_dir() / name
        meta_path = path / "sprite.json"
        if not meta_path.is_file():
            known = ", ".join(list_sprites()) or "(none)"
            raise SpriteError(f"no sprite {name!r} (looked for {meta_path}). Known: {known}")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SpriteError(f"{meta_path}: invalid JSON: {e}") from None

        size_class = meta.get("class")
        cdef: dict = {}
        if size_class is not None:
            classes = size_classes()
            if size_class not in classes:
                raise SpriteError(f"unknown class {size_class!r}; known: {', '.join(classes)}")
            cdef = classes[size_class]
        w, h = meta.get("size", cdef.get("size", [32, 32]))
        # origin is a point on pixel *edges*: [16, 32] = bottom-centre of a 32x32 frame
        origin = tuple(meta.get("origin", [w // 2, h]))
        body = tuple(meta.get("body", cdef.get("body", [w // 2, h])))
        roles = dict(meta.get("roles", {}))
        for pattern, role in roles.items():
            if role not in ROLES:
                raise SpriteError(f"roles[{pattern!r}] = {role!r}; must be one of {', '.join(ROLES)}")
        game = load_game_palette(meta.get("game_palette", "game"))
        palette_raw = dict(meta.get("palette", {}))
        palette: dict[str, RGBA] = {}
        for key, value in palette_raw.items():
            if len(key) != 1 or key == TRANSPARENT or key.isspace():
                raise SpriteError(f"palette key {key!r} must be a single non-space char other than '.'")
            if value.startswith("#"):
                palette[key] = parse_hex(value)
            elif value in game:
                palette[key] = game[value]
            else:
                raise SpriteError(f"palette key {key!r}: {value!r} is not a hex color or a name in palettes/game.json")

        anims = {}
        for aname, a in meta.get("animations", {}).items():
            frames = a.get("frames", [])
            anims[aname] = Animation(aname, float(a.get("fps", 8)), bool(a.get("loop", True)), frames)
        return cls(meta.get("name", name), path, w, h, origin, palette_raw, palette, anims,
                   size_class, body, roles, int(meta.get("hit_pad", 0)), int(meta.get("hurt_pad", 0)))

    def body_rect(self) -> tuple[int, int, int, int]:
        """Body box as (x, y, w, h) in frame pixels, centred on the origin, standing on it."""
        bw, bh = self.body
        return self.origin[0] - bw // 2, self.origin[1] - bh, bw, bh

    def role_of(self, frame_id: str) -> str:
        for pattern, role in self.roles.items():
            if fnmatch.fnmatchcase(frame_id, pattern):
                return role
        return "hurt"

    # ---- frames -----------------------------------------------------------------------
    def frame_path(self, frame_id: str) -> Path:
        return self.path / "frames" / f"{frame_id}.txt"

    def frame_ids(self) -> list[str]:
        d = self.path / "frames"
        return sorted(p.stem for p in d.glob("*.txt")) if d.is_dir() else []

    def load_frame(self, frame_id: str, strict: bool = True) -> Grid:
        if strict and frame_id in self._frame_cache:
            return self._frame_cache[frame_id]
        p = self.frame_path(frame_id)
        if not p.is_file():
            raise SpriteError(f"frame file not found: {rel(p)}")
        try:
            g = Grid.parse(p.read_text(encoding="utf-8"), self.width, self.height, strict=strict)
        except GridError as e:
            raise SpriteError(f"{rel(p)}: {e}") from None
        if strict:
            self._frame_cache[frame_id] = g
        return g

    def resolve(self, entry) -> Grid:
        """Turn a frame entry (id string or build-object) into a Grid.

        Object keys, applied in this order:
          from     base frame (id or nested entry); default blank
          layers   list of entries painted on top, bottom to top
          flip     "h" | "v"
          offset   [dx, dy]
          replace  {"old_key": "new_key", ...} palette swap (e.g. hit flash)
        plus `duration` (ms) and `active` (hitboxes deal damage), which don't change pixels.
        """
        return self._resolve(entry, 0)[0]

    def resolve_roles(self, entry) -> tuple[Grid, Grid]:
        """(pixels, roles): the roles grid holds ROLES chars saying which layer role each visible
        pixel came from, after all layering/flips/offsets."""
        return self._resolve(entry, 0)

    def _resolve(self, entry, depth: int) -> tuple[Grid, Grid]:
        if depth > 16:
            raise SpriteError("frame entries nested too deeply (cycle?)")
        if isinstance(entry, str):
            g = self.load_frame(entry)
            mark = ROLES[self.role_of(entry)]
            return g, Grid(g.width, g.height, [[mark if c != TRANSPARENT else TRANSPARENT for c in row]
                                               for row in g.cells])
        if not isinstance(entry, dict):
            raise SpriteError(f"frame entry must be a string or object, got {entry!r}")
        unknown = set(entry) - ENTRY_KEYS
        if unknown:
            raise SpriteError(f"unknown frame entry keys {sorted(unknown)} in {entry!r}")
        if "from" in entry:
            g, r = self._resolve(entry["from"], depth + 1)
        else:
            g, r = Grid.blank(self.width, self.height), Grid.blank(self.width, self.height)
        for layer in entry.get("layers", []):
            lg, lr = self._resolve(layer, depth + 1)
            g, r = g.composite(lg), r.composite(lr)
        if "flip" in entry:
            try:
                g, r = g.flip(entry["flip"]), r.flip(entry["flip"])
            except GridError as e:
                raise SpriteError(str(e)) from None
        if "offset" in entry:
            dx, dy = (int(v) for v in entry["offset"])
            g, r = g.offset(dx, dy), r.offset(dx, dy)
        for old, new in entry.get("replace", {}).items():
            g = g.replace(old, new)
        return g, r

    def anim(self, name: str) -> Animation:
        if name not in self.animations:
            known = ", ".join(self.animations) or "(none)"
            raise SpriteError(f"sprite {self.name!r} has no animation {name!r}. Known: {known}")
        return self.animations[name]

    def anim_frames(self, name: str) -> list[Grid]:
        return [self.resolve(e) for e in self.anim(name).frames]

    def frame(self, anim: str, index: int) -> Grid:
        a = self.anim(anim)
        if not -len(a.frames) <= index < len(a.frames):
            raise SpriteError(f"{anim!r} has {len(a.frames)} frames; index {index} out of range")
        return self.resolve(a.frames[index])

    def color(self, key: str) -> RGBA:
        if key == TRANSPARENT:
            return 0, 0, 0, 0
        return self.palette.get(key, (255, 0, 255, 255))  # magenta = undefined key


def describe_entry(entry) -> str:
    return entry if isinstance(entry, str) else json.dumps(entry, separators=(",", ":"))
