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


def list_sprites(kind: str | None = None) -> list[str]:
    """Every sprite folder, or only those of one kind ("sprite" = characters/items, "tileset")."""
    d = sprites_dir()
    if not d.is_dir():
        return []
    names = sorted(p.name for p in d.iterdir() if (p / "sprite.json").is_file())
    return names if kind is None else [n for n in names if sprite_kind(n) == kind]


def sprite_kind(name: str) -> str:
    try:
        meta = json.loads((sprites_dir() / name / "sprite.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "sprite"  # let Sprite.load report the problem
    return meta.get("type", "sprite") if isinstance(meta, dict) else "sprite"


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
    # top-down (3/4 view): feet above the bottom edge so downward swings have room too
    "topdown": {"size": [64, 64], "origin": [32, 52], "body": [16, 30]},
    # overhead (bird's-eye): drawn facing east (right), rotated in the engine around its centre
    "overhead": {"size": [64, 64], "origin": [32, 32], "body": [16, 16], "anchor": "center"},
}
ROLES = {"hurt": "u", "hit": "x", "none": "n"}  # role -> char in a role grid
ENTRY_KEYS = {"from", "layers", "flip", "offset", "roll", "replace", "duration", "active"}
PART_KEYS = {"part", "at", "flip", "replace", "duration", "active"}   # a small grid placed on the canvas
# sprite: characters (animations). prop: objects, buildings and background accents (animations are
# states). tileset: terrain tiles. icons: a UI atlas of named images. font: a bitmap font.
KINDS = ("sprite", "prop", "tileset", "icons", "font")
TILED_KINDS = ("tileset", "icons", "font")   # made of named same-size cells instead of animations
TILE_COLUMNS = 8  # default tileset sheet width, in tiles
VIEWS = ("side", "topdown", "overhead")
PROP_LAYERS = ("back", "world", "front")
DEFAULT_RESOLUTION = (320, 180)
VIEW_CLASS = {"side": "humanoid", "topdown": "topdown", "overhead": "overhead"}  # `new` default per view


def size_classes() -> dict[str, dict]:
    return {**DEFAULT_CLASSES, **project_config().get("classes", {})}


def game_view() -> str:
    """The game's camera: "side" (platformers), "topdown" (3/4 view) or "overhead" (bird's-eye)."""
    v = project_config().get("view", "side")
    if v not in VIEWS:
        raise SpriteError(f"pixelforge.json \"view\": {v!r} must be one of {', '.join(VIEWS)}")
    return v


def game_resolution() -> tuple[int, int]:
    """The game's base resolution in pixels (before the engine scales it up)."""
    r = project_config().get("resolution", DEFAULT_RESOLUTION)
    try:
        w, h = (int(v) for v in r)
    except (TypeError, ValueError):
        raise SpriteError(f"pixelforge.json \"resolution\": {r!r} must be [width, height]") from None
    return w, h


def _rect(value, what: str) -> tuple[int, int, int, int]:
    try:
        x, y, w, h = (int(v) for v in value)
    except (TypeError, ValueError):
        raise SpriteError(f"{what} must be [x, y, w, h], got {value!r}") from None
    if w < 1 or h < 1:
        raise SpriteError(f"{what} {value!r} needs a positive width and height")
    return x, y, w, h


def part_positions(entry: dict) -> list[tuple[int, int]]:
    """A part entry's "at": [x, y] or a list of them (stamp it several times). Default [0, 0]."""
    at = entry.get("at", [0, 0])
    try:
        if at and isinstance(at[0], (list, tuple)):
            return [(int(x), int(y)) for x, y in at]
        x, y = at
        return [(int(x), int(y))]
    except (TypeError, ValueError):
        raise SpriteError(f"part {entry.get('part')!r}: \"at\" must be [x, y] or [[x, y], ...], got {at!r}") from None


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
    anchor: str = "feet"   # "feet": origin is where it stands; "center": origin is the rotation centre
    # tilesets ("type": "tileset"): tiles[i] = (name, frame entry); i is the tile's index in Phaser
    kind: str = "sprite"
    tiles: list[tuple[str, object]] = field(default_factory=list)
    tile_props: dict[str, dict] = field(default_factory=dict)  # tile-name glob -> properties
    columns: int = TILE_COLUMNS
    sample: dict | None = None  # {"legend": {char: tile name}, "rows": [str, ...]}
    tile_anims: dict[str, list[tuple[object, int]]] = field(default_factory=dict)  # name -> [(entry, ms)]
    view: str = "side"
    # props ("type": "prop"): how the object sits in the game
    footprint: tuple[int, int, int, int] | None = None  # solid part [x, y, w, h]; None = the art's bounds
    layer: str = "world"     # back (behind everything, e.g. parallax accents) | world | front
    scroll: float = 1.0      # parallax scroll factor: 0.2 = far away, 1 = moves with the world
    solid: bool = False      # blocks movement (Arcade static body from the footprint)
    slice: tuple[int, int] | None = None  # also export the first frame cut into tiles of this size
    stamps: dict = field(default_factory=dict)  # tilesets: name -> {"legend": {...}, "rows": [...]}
    item_meta: dict[str, dict] = field(default_factory=dict)  # icons: name -> {"nine": [l, r, t, b]}
    # tilesets: terrain -> {"base": tile, "edges": {"n": tile, "ne": tile, ...}}; levels pick edges by neighbours
    autotile: dict[str, dict] = field(default_factory=dict)
    # fonts ("type": "font")
    glyph_widths: dict[str, int] = field(default_factory=dict)
    letter_spacing: int = 1
    space_width: int = 3
    line_height: int = 0
    font_problems: list[str] = field(default_factory=list)
    _frame_cache: dict[str, Grid] = field(default_factory=dict, repr=False)

    @property
    def tiled(self) -> bool:
        """Made of named same-size cells (tileset, icons, font) rather than animations."""
        return self.kind in TILED_KINDS

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
        origin = tuple(meta.get("origin", cdef.get("origin", [w // 2, h])))
        body = tuple(meta.get("body", cdef.get("body", [w // 2, h])))
        anchor = meta.get("anchor", cdef.get("anchor", "feet"))
        if anchor not in ("feet", "center"):
            raise SpriteError(f"anchor {anchor!r} must be 'feet' or 'center'")
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
        kind = meta.get("type", "sprite")
        if kind not in KINDS:
            raise SpriteError(f"type {kind!r} must be one of {', '.join(KINDS)}")
        # the topdown/overhead classes are only for those views, so they imply it
        view = meta.get("view") or (size_class if size_class in ("topdown", "overhead") else game_view())
        if view not in VIEWS:
            raise SpriteError(f"view {view!r} must be one of {', '.join(VIEWS)}")
        item_meta: dict[str, dict] = {}
        tiles, tile_anims = _parse_tiles(meta.get("icons" if kind == "icons" else "tiles", []), item_meta)
        tile_props = dict(meta.get("properties", {}))
        for pattern, props in tile_props.items():
            if not isinstance(props, dict):
                raise SpriteError(f"properties[{pattern!r}] must be an object, e.g. {{\"collides\": true}}")
        columns = int(meta.get("columns", 16 if kind == "font" else TILE_COLUMNS))
        if columns < 1:
            raise SpriteError("columns must be at least 1")
        stamps = dict(meta.get("stamps", {}))
        for sname, st in stamps.items():
            if not (isinstance(st, dict) and isinstance(st.get("rows"), list)):
                raise SpriteError(f"stamps[{sname!r}] must be {{\"rows\": [...]}} (plus an optional \"legend\")")
        autotile = meta.get("autotile", {})
        if not isinstance(autotile, dict) or not all(isinstance(v, dict) and isinstance(v.get("base"), str)
                                                     for v in autotile.values()):
            raise SpriteError("autotile must be {\"terrain\": {\"base\": tile, \"edges\": {\"n\": tile, ...}}}")
        s = cls(meta.get("name", name), path, w, h, origin, palette_raw, palette, anims,
                size_class, body, roles, int(meta.get("hit_pad", 0)), int(meta.get("hurt_pad", 0)), anchor,
                kind, tiles, tile_props, columns, meta.get("sample"), tile_anims, view, stamps=stamps,
                item_meta=item_meta, autotile=autotile)
        if kind == "prop":
            s._load_prop(meta)
        if kind == "font":
            s._load_font(meta)
        return s

    def _load_prop(self, meta: dict) -> None:
        if meta.get("footprint") is not None:
            self.footprint = _rect(meta["footprint"], "footprint")
        self.scroll = float(meta.get("scroll", 1))
        self.layer = meta.get("layer", "world" if self.scroll == 1 else "back")
        if self.layer not in PROP_LAYERS:
            raise SpriteError(f"layer {self.layer!r} must be one of {', '.join(PROP_LAYERS)}")
        self.solid = bool(meta.get("solid", self.layer == "world"))
        if meta.get("slice") is not None:
            try:
                tw, th = (int(v) for v in meta["slice"])
            except (TypeError, ValueError):
                raise SpriteError(f"slice must be [tile_width, tile_height], got {meta['slice']!r}") from None
            if tw < 1 or th < 1:
                raise SpriteError("slice tile size must be positive")
            self.slice = (tw, th)

    def _load_font(self, meta: dict) -> None:
        """Glyphs come from one text file of blocks: a `= A` line, then the glyph's rows."""
        p = self.path / meta.get("glyphs", "glyphs.txt")
        if not p.is_file():
            raise SpriteError(f"font glyph file not found: {rel(p)}")
        glyphs, self.font_problems = parse_glyphs(p.read_text(encoding="utf-8"), self.width, self.height)
        self.letter_spacing = int(meta.get("spacing", 1))
        self.space_width = int(meta.get("space", max(2, self.width // 2 + 1)))
        self.line_height = int(meta.get("line_height", self.height + 2))
        for ch, g in glyphs.items():
            fid = f"glyph_{ord(ch):x}"
            self._frame_cache[fid] = Grid.blank(self.width, self.height).paste(g, 0, 0)  # left-aligned in its cell
            self.tiles.append((ch, fid))
            self.glyph_widths[ch] = min(g.width, self.width)

    # ---- tilesets ---------------------------------------------------------------------
    def tile_names(self) -> list[str]:
        return [n for n, _ in self.tiles]

    def tile_index(self, name: str) -> int:
        for i, (n, _) in enumerate(self.tiles):
            if n == name:
                return i
        known = ", ".join(self.tile_names()) or "(none)"
        raise SpriteError(f"tileset {self.name!r} has no tile {name!r}. Known: {known}")

    def tile(self, name: str, t_ms: int = 0) -> Grid:
        """The tile as it looks `t_ms` into its animation (static tiles ignore t_ms)."""
        return self.resolve(self.tile_entry_at(name, t_ms))

    def tile_frames(self, name: str) -> list[tuple[object, int]]:
        """[(entry, ms)]: an animated tile's frames, or [(entry, 0)] for a static one."""
        return self.tile_anims.get(name) or [(self.tiles[self.tile_index(name)][1], 0)]

    def tile_entry_at(self, name: str, t_ms: int) -> object:
        frames = self.tile_frames(name)
        total = sum(ms for _, ms in frames)
        if total <= 0:
            return frames[0][0]
        t = t_ms % total
        for entry, ms in frames:
            if t < ms:
                return entry
            t -= ms
        return frames[-1][0]

    def tile_properties(self, name: str) -> dict:
        """Every matching `properties` glob, merged in order (later patterns win). Icons add their
        nine-slice insets, font glyphs their advance width."""
        out: dict = dict(self.item_meta.get(name, {}))
        if self.kind == "font" and name in self.glyph_widths:
            out["advance"] = self.glyph_widths[name] + self.letter_spacing
        for pattern, props in self.tile_props.items():
            if fnmatch.fnmatchcase(name, pattern):
                out.update(props)
        return out

    def rows_to_indices(self, rows: list[str], legend: dict, where: str) -> list[list[int]]:
        """Map rows written as characters (through `legend`) to tile indices (-1 = ' ' or '.')."""
        out = []
        for y, row in enumerate(rows):
            line = []
            for x, c in enumerate(row):
                if c in " .":
                    line.append(-1)
                elif c in legend:
                    line.append(self.tile_index(legend[c]))
                else:
                    raise SpriteError(f"{where} row {y}, column {x}: {c!r} is not in the legend")
            out.append(line)
        return out

    def sample_map(self) -> list[list[int]]:
        """The sprite.json "sample" map as rows of tile indices (-1 = empty, for ' ' or '.')."""
        if not self.sample:
            return []
        return self.rows_to_indices(self.sample.get("rows", []), self.sample.get("legend", {}), "sample")

    def stamp_legend(self, name: str) -> dict:
        return self.stamps[name].get("legend") or (self.sample or {}).get("legend", {})

    def stamp_map(self, name: str) -> list[list[int]]:
        """A tileset stamp (a prebuilt arrangement such as a house made from kit tiles) as tile indices.
        Its legend defaults to the sample map's."""
        if name not in self.stamps:
            known = ", ".join(self.stamps) or "(none)"
            raise SpriteError(f"tileset {self.name!r} has no stamp {name!r}. Known: {known}")
        return self.rows_to_indices(self.stamps[name]["rows"], self.stamp_legend(name), f"stamp {name!r}")

    def art_bounds(self) -> tuple[int, int, int, int] | None:
        """(x, y, w, h) of the first animation's first frame, or None if there is nothing drawn."""
        first = next(iter(self.animations.values()), None)
        if not first or not first.frames:
            return None
        try:
            bb = self.resolve(first.frames[0]).bbox()
        except SpriteError:
            return None
        return bb and (bb[0], bb[1], bb[2] - bb[0] + 1, bb[3] - bb[1] + 1)

    def body_rect(self) -> tuple[int, int, int, int]:
        """Body box as (x, y, w, h) in frame pixels: standing on the origin (anchor "feet") or
        centred on it (anchor "center"). A prop's body is its footprint (default: its art's bounds)."""
        if self.kind == "prop":
            return self.footprint or self.art_bounds() or (0, 0, self.width, self.height)
        bw, bh = self.body
        top = self.origin[1] - (bh // 2 if self.anchor == "center" else bh)
        return self.origin[0] - bw // 2, top, bw, bh

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

    # ---- parts: small grids of any size, placed on the canvas with "at" -------------------
    def part_path(self, part_id: str) -> Path:
        return self.path / "parts" / f"{part_id}.txt"

    def part_ids(self) -> list[str]:
        d = self.path / "parts"
        return sorted(p.stem for p in d.glob("*.txt")) if d.is_dir() else []

    def layer_path(self, layer_id: str) -> Path:
        """A frame file, or failing that a part file, with this id (for `paint`, `show @id`...)."""
        p = self.frame_path(layer_id)
        return p if p.is_file() or not self.part_path(layer_id).is_file() else self.part_path(layer_id)

    def load_layer(self, layer_id: str, strict: bool = True) -> Grid:
        """`load_frame`, or the part file of that id at its own size."""
        if self.frame_path(layer_id).is_file() or not self.part_path(layer_id).is_file():
            return self.load_frame(layer_id, strict)
        return self.load_part(layer_id, strict)

    def load_part(self, part_id: str, strict: bool = True) -> Grid:
        key = f"part:{part_id}"
        if strict and key in self._frame_cache:
            return self._frame_cache[key]
        p = self.part_path(part_id)
        if not p.is_file():
            raise SpriteError(f"part file not found: {rel(p)}")
        try:
            g = Grid.parse(p.read_text(encoding="utf-8"), strict=strict)   # its own size: every row equally long
        except GridError as e:
            raise SpriteError(f"{rel(p)}: {e}") from None
        if g.width == 0 or g.height == 0:
            raise SpriteError(f"{rel(p)}: part is empty")
        if strict:
            self._frame_cache[key] = g
        return g

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
          roll     [dx, dy]  offset that wraps around the edges (seamless tile animation)
          replace  {"old_key": "new_key", ...} palette swap (e.g. hit flash)
        plus `duration` (ms) and `active` (hitboxes deal damage), which don't change pixels.

        A part entry {"part": "window", "at": [x, y] | [[x, y], ...], "flip": "h", "replace": {...}}
        places parts/window.txt (any size) on a blank canvas, once per position; flip and replace
        apply to the part itself. Use it as a layer, or as `from`.
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
        if "part" in entry:
            return self._resolve_part(entry)
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
        if "roll" in entry:
            dx, dy = (int(v) for v in entry["roll"])
            g, r = g.roll(dx, dy), r.roll(dx, dy)
        for old, new in entry.get("replace", {}).items():
            g = g.replace(old, new)
        return g, r

    def _resolve_part(self, entry: dict) -> tuple[Grid, Grid]:
        unknown = set(entry) - PART_KEYS
        if unknown:
            raise SpriteError(f"unknown part entry keys {sorted(unknown)} in {entry!r} (a part takes "
                              f"at, flip and replace; wrap it in {{\"layers\": [...]}} to offset or roll it)")
        pid = entry["part"]
        if not isinstance(pid, str):
            raise SpriteError(f"\"part\" must be a part file name, got {pid!r}")
        p = self.load_part(pid)
        mark = ROLES[self.role_of(pid)]
        pr = Grid(p.width, p.height, [[mark if c != TRANSPARENT else TRANSPARENT for c in row] for row in p.cells])
        if "flip" in entry:
            try:
                p, pr = p.flip(entry["flip"]), pr.flip(entry["flip"])
            except GridError as e:
                raise SpriteError(str(e)) from None
        for old, new in entry.get("replace", {}).items():
            p = p.replace(old, new)
        g, r = Grid.blank(self.width, self.height), Grid.blank(self.width, self.height)
        for x, y in part_positions(entry):
            g, r = g.paste(p, x, y), r.paste(pr, x, y)
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


ITEM_META_KEYS = ("nine",)   # per-item data that isn't drawing (icons: nine-slice insets)


def _parse_tiles(items: list, item_meta: dict | None = None
                 ) -> tuple[list[tuple[str, object]], dict[str, list[tuple[object, int]]]]:
    """`tiles` items -> ([(name, first-frame entry)], {name: [(entry, ms), ...]} for animated tiles).

    An item is a frame id (also the tile's name), or an object with a "name" plus frame-entry keys.
    With "frames" (a list of entries, timed by "fps" or each entry's "duration") the tile animates;
    the object's other keys (layers, flip, replace...) apply on top of every frame. "frames": "water"
    reuses an earlier animated tile's frames, so the two stay in step (e.g. a shore over the water)."""
    tiles: list[tuple[str, object]] = []
    anims: dict[str, list[tuple[object, int]]] = {}
    for t in items:
        if isinstance(t, str):
            tiles.append((t, t))
            continue
        if not (isinstance(t, dict) and isinstance(t.get("name"), str)):
            raise SpriteError(f"tiles item {t!r} must be a frame id or an object with a \"name\"")
        name, frames = t["name"], t.get("frames")
        rest = {k: v for k, v in t.items() if k not in ("name", "frames", "fps", *ITEM_META_KEYS)}
        if "nine" in t:
            try:
                nine = [int(v) for v in t["nine"]]
            except (TypeError, ValueError):
                nine = []
            if len(nine) != 4 or min(nine) < 0:
                raise SpriteError(f"{name!r}: \"nine\" must be [left, right, top, bottom] border widths")
            if item_meta is not None:
                item_meta[name] = {"nine": nine}
        if frames is None:
            tiles.append((name, rest or name))
            continue
        if "from" in rest or "part" in rest:
            raise SpriteError(f"tile {name!r}: use \"frames\" or \"from\"/\"part\", not both")
        if isinstance(frames, str):
            if frames not in anims:
                raise SpriteError(f"tile {name!r}: \"frames\": {frames!r} must name an animated tile listed before it")
            seq = [(e, ms) for e, ms in anims[frames]]
        elif isinstance(frames, list) and frames:
            step = round(1000 / float(t.get("fps", 4)))
            seq = [(f, int(f["duration"]) if isinstance(f, dict) and "duration" in f else step) for f in frames]
        else:
            raise SpriteError(f"tile {name!r}: \"frames\" must be a non-empty list or an animated tile's name")
        seq = [({"from": e, **rest} if rest else e, ms) for e, ms in seq]
        anims[name] = seq
        tiles.append((name, seq[0][0]))
    return tiles, anims


def parse_glyphs(text: str, max_w: int, height: int) -> tuple[dict[str, Grid], list[str]]:
    """A font's glyph file -> ({char: grid}, problems). Each glyph is a `= X` line (X is the one
    character it draws) followed by `height` rows, all the same length (the glyph's width, at most
    max_w). Lines before the first `=` and blank lines between glyphs are ignored."""
    glyphs: dict[str, Grid] = {}
    problems: list[str] = []
    blocks: list[tuple[int, str, list[str]]] = []
    for n, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if line.startswith("= "):
            blocks.append((n, line[2:], []))
        elif blocks and line.strip():
            blocks[-1][2].append(line.rstrip())
    for n, ch, rows in blocks:
        where = f"line {n} (glyph {ch!r})"
        if len(ch) != 1:
            problems.append(f"{where}: `= ` must be followed by exactly one character")
            continue
        if ch in glyphs:
            problems.append(f"{where}: {ch!r} is defined twice")
        if len(rows) != height:
            problems.append(f"{where}: {len(rows)} rows, expected {height}")
        widths = {len(r) for r in rows}
        if len(widths) > 1:
            problems.append(f"{where}: rows have different lengths {sorted(widths)}")
        w = max(widths, default=0)
        if w > max_w:
            problems.append(f"{where}: {w} pixels wide, wider than the font's cell ({max_w}); raise \"size\"")
        if w == 0:
            continue
        glyphs[ch] = Grid.parse("\n".join(rows[:height]), w, height, strict=False)
    return glyphs, problems


def describe_entry(entry) -> str:
    return entry if isinstance(entry, str) else json.dumps(entry, separators=(",", ":"))
