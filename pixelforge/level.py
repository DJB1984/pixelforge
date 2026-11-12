"""Levels: levels/<name>.json, a whole map written as rows of characters.

Tile layers are rows read through a legend (tile names, other tilesets' tiles, or `auto:<terrain>`
cells that pick their edge tile from their neighbours), plus stamps (prebuilt arrangements from a
tileset, or a sliced building). Objects are characters in `objects.rows` (origin at the cell's
bottom-centre) or pixel positions in `objects.list`. `Level.load` resolves all of it into per-layer
tile grids and objects in pixels; `export_level` writes a Tiled map that Phaser loads.
"""
from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .model import SpriteError, Sprite, VIEWS, game_resolution, game_view, list_sprites, rel, root, sprite_folder

DIRS = "nsew"
# every combination of n s e w, written in that order: "n", "ne", "nse", "nsew"...
EDGE_KEYS = ["".join(c) for k in range(1, 5) for c in itertools.combinations(DIRS, k)]
DEFAULT_OBJECT_LEGEND = {"@": {"type": "spawn", "name": "player"}}
ZONE_TYPES = ("door", "trigger")        # objects that are an area, not a point
QUIET_TYPES = ("prop", "decor", "spawn", "enemy", "sprite")   # not listed when unreachable


class LevelError(SpriteError):
    pass


def levels_dir() -> Path:
    return root() / "levels"


def list_levels() -> list[str]:
    d = levels_dir()
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


# ---- tilesets a level can use: tileset sprites and sliced buildings (<prop>_tiles) ---------------
@dataclass
class Tileset:
    name: str
    data: dict            # the Tiled tileset `export` writes, with its "pixelforge" block
    image: Image.Image
    autotile: dict = field(default_factory=dict)

    @property
    def pf(self) -> dict:
        return self.data["pixelforge"]

    @property
    def names(self) -> list[str]:
        return self.pf["names"]

    @property
    def tile_size(self) -> tuple[int, int]:
        return self.data["tilewidth"], self.data["tileheight"]

    def index(self, tile: str) -> int:
        try:
            return self.names.index(tile)
        except ValueError:
            raise LevelError(f"tileset {self.name!r} has no tile {tile!r}") from None

    def props(self, i: int) -> dict:
        return self.pf["properties"][i]

    def tile_image(self, i: int) -> Image.Image:
        tw, th = self.tile_size
        cols, sp = self.data["columns"], self.data["spacing"]
        x, y = (i % cols) * (tw + sp), (i // cols) * (th + sp)
        return self.image.crop((x, y, x + tw, y + th))


def tileset_names() -> list[str]:
    """Everything a level can name as a tileset."""
    out = []
    for n in list_sprites():
        try:
            s = Sprite.load(n)
        except SpriteError:
            continue
        if s.kind == "tileset":
            out.append(n)
        elif s.kind == "prop" and s.slice:
            out.append(f"{n}_tiles")
    return out


def sample_legend(tileset: str) -> dict:
    """A tileset's sample-map legend: a level's legend starts from it."""
    if tileset not in list_sprites():
        return {}
    return dict((Sprite.load(tileset).sample or {}).get("legend") or {})


def load_tileset(name: str) -> Tileset:
    from .export import build_slices, build_tileset
    sprites = list_sprites()
    if name in sprites:
        s = Sprite.load(name)
        if s.kind != "tileset":
            raise LevelError(f"{name!r} is a {s.kind}, not a tileset")
        img, data = build_tileset(s)
        return Tileset(name, data, img, s.autotile)
    if name.endswith("_tiles") and name[:-6] in sprites:
        s = Sprite.load(name[:-6])
        if s.kind == "prop" and s.slice:
            img, data = build_slices(s)
            return Tileset(name, data, img)
    raise LevelError(f"no tileset {name!r}. Known: {', '.join(tileset_names()) or '(none)'}")


# ---- the level ------------------------------------------------------------------------------------
@dataclass
class LevelObject:
    id: int
    name: str
    type: str
    x: int                      # origin in level pixels: where a prop or sprite stands (or the point)
    y: int
    source: str                 # where it was written, for messages
    prop: str | None = None
    sprite: str | None = None
    state: str | None = None
    to: str | None = None       # doors: the level they lead to
    props: dict = field(default_factory=dict)
    rect: tuple[int, int, int, int] | None = None        # zones (doors, triggers): the area
    footprint: tuple[int, int, int, int] | None = None   # solid props: the blocking area in level pixels
    art: tuple[int, int, int, int] | None = None         # props/sprites: the canvas in level pixels
    spawn: str | None = None    # doors: the spawn to arrive at in `to`

    def to_dict(self) -> dict:
        d = {"id": self.id, "name": self.name, "type": self.type, "x": self.x, "y": self.y}
        for k in ("prop", "sprite", "state", "to", "spawn"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.rect:
            d["rect"] = list(self.rect)
        if self.footprint:
            d["footprint"] = list(self.footprint)
        if self.props:
            d["props"] = self.props
        return d


@dataclass
class LevelLayer:
    name: str
    above: bool
    cells: list[list[tuple[str, int] | None]]   # (tileset, tile index) per cell, None = empty


@dataclass
class Level:
    name: str
    path: Path
    raw: dict
    view: str
    tileset: str                       # the default tileset
    tile_w: int
    tile_h: int
    width: int                         # in tiles
    height: int
    layers: list[LevelLayer]
    objects: list[LevelObject]
    tilesets: dict[str, Tileset]       # every tileset the level uses, the default first
    problems: list[tuple[str, str, str]] = field(default_factory=list)   # (level, where, message)

    @property
    def pixel_size(self) -> tuple[int, int]:
        return self.width * self.tile_w, self.height * self.tile_h

    @property
    def background(self) -> dict:
        return self.raw.get("background") or {}

    @property
    def accents(self) -> list[dict]:
        return self.raw.get("accents") or []

    @property
    def player(self) -> str | None:
        return self.raw.get("player")

    @property
    def camera(self) -> dict:
        return {"zoom": 1, **(self.raw.get("camera") or {})}

    def screen_size(self) -> tuple[int, int]:
        """World pixels one screen shows: the game's resolution through the camera's zoom."""
        rw, rh = game_resolution()
        z = float(self.camera.get("zoom") or 1)
        return round(rw / z), round(rh / z)

    def spawns(self) -> list[LevelObject]:
        return [o for o in self.objects if o.type == "spawn"]

    def tile_at(self, layer: LevelLayer, cx: int, cy: int) -> tuple[Tileset, int] | None:
        c = layer.cells[cy][cx] if 0 <= cy < self.height and 0 <= cx < self.width else None
        return (self.tilesets[c[0]], c[1]) if c else None

    def tile_name(self, cell: tuple[str, int] | None) -> str | None:
        return self.tilesets[cell[0]].names[cell[1]] if cell else None

    def colliding_tile(self, cx: int, cy: int) -> str | None:
        """The name of a tile with "collides" at this cell, on any layer."""
        for layer in self.layers:
            t = self.tile_at(layer, cx, cy)
            if t and t[0].props(t[1]).get("collides"):
                return t[0].names[t[1]]
        return None

    def collides(self, cx: int, cy: int) -> bool:
        return self.colliding_tile(cx, cy) is not None

    def errors(self) -> list[str]:
        return [f"{where}: {msg}" for lvl, where, msg in self.problems if lvl == "error"]

    # ---- loading ------------------------------------------------------------------------------
    @classmethod
    def load(cls, name: str) -> "Level":
        path = levels_dir() / f"{name}.json"
        if not path.is_file():
            raise LevelError(f"no level {name!r} (looked for {rel(path)}). Known: {', '.join(list_levels()) or '(none)'}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise LevelError(f"{rel(path)}: invalid JSON: {e}") from None
        if not isinstance(raw, dict):
            raise LevelError(f"{rel(path)}: a level is a JSON object")
        return _Loader(name, path, raw).build()


class _Loader:
    def __init__(self, name: str, path: Path, raw: dict):
        self.name, self.path, self.raw = name, path, raw
        self.problems: list[tuple[str, str, str]] = []
        self.tilesets: dict[str, Tileset] = {}
        self.missing: set[str] = set()

    def err(self, where: str, msg: str, level: str = "error") -> None:
        self.problems.append((level, f"{self.name}/{where}" if where else self.name, msg))

    def ts(self, name: str) -> Tileset | None:
        if name in self.tilesets:
            return self.tilesets[name]
        if name in self.missing:
            return None
        try:
            self.tilesets[name] = load_tileset(name)
        except SpriteError as e:
            self.missing.add(name)
            self.err("tileset", str(e))
            return None
        return self.tilesets[name]

    # legend value -> ("tile", tileset, index) | ("auto", tileset, terrain) | None (reported)
    def legend_spec(self, char: str, value, where: str):
        ts_name, tile, auto = self.default, None, None
        if isinstance(value, str):
            if value.startswith("auto:"):
                auto = value[5:]
            else:
                tile = value
        elif isinstance(value, dict):
            ts_name = value.get("tileset", self.default)
            tile, auto = value.get("tile"), value.get("auto")
            if isinstance(tile, str) and tile.startswith("auto:"):
                tile, auto = None, tile[5:]
        if not (tile or auto):
            self.err(where, f"legend {char!r}: {value!r} must be a tile name, \"auto:<terrain>\" or "
                            f"{{\"tileset\": ..., \"tile\": ...}}")
            return None
        ts = self.ts(ts_name)
        if ts is None:
            return None
        if auto:
            if auto not in ts.autotile:
                self.err(where, f"legend {char!r}: tileset {ts_name!r} has no autotile terrain {auto!r} "
                                f"(known: {', '.join(ts.autotile) or 'none; add \"autotile\" to its sprite.json'})")
                return None
            return ("auto", ts_name, auto)
        try:
            return ("tile", ts_name, ts.index(tile))
        except LevelError as e:
            self.err(where, f"legend {char!r}: {e}")
            return None

    def build(self) -> Level:
        raw = self.raw
        view = raw.get("view") or game_view()
        if view not in VIEWS:
            self.err("view", f"{view!r} must be one of {', '.join(VIEWS)}")
            view = game_view()
        self.default = raw.get("tileset")
        if not isinstance(self.default, str):
            raise LevelError(f"{self.name}: \"tileset\" (the default tileset's name) is required")
        base = self.ts(self.default)
        if base is None:
            raise LevelError(f"{self.name}: {self.problems[-1][2]}")
        tw, th = base.tile_size

        legend_raw = {**sample_legend(self.default), **(raw.get("legend") or {})}
        legend = {}
        for c, v in legend_raw.items():
            if len(c) != 1 or c in " .":
                self.err("legend", f"key {c!r} must be one character other than space and '.'")
                continue
            legend[c] = v

        layers_raw = raw.get("layers")
        if not isinstance(layers_raw, list) or not layers_raw:
            raise LevelError(f"{self.name}: \"layers\" must be a non-empty list of {{\"name\", \"rows\"}}")
        sizes = []
        for i, l in enumerate(layers_raw):
            rows = l.get("rows") if isinstance(l, dict) else None
            if not (isinstance(rows, list) and all(isinstance(r, str) for r in rows)):
                raise LevelError(f"{self.name}: layers[{i}] needs \"rows\": a list of strings")
            sizes.append((max((len(r) for r in rows), default=0), len(rows)))
        width, height = max(w for w, _ in sizes), max(h for _, h in sizes)
        if not width or not height:
            raise LevelError(f"{self.name}: the layers are empty")

        specs: dict[str, object] = {}
        layers: list[LevelLayer] = []
        auto_cells: list[tuple[LevelLayer, int, int, tuple]] = []
        names_seen: set[str] = set()
        for i, l in enumerate(layers_raw):
            lname = l.get("name") or f"layer{i}"
            where = f"layers/{lname}"
            if lname in names_seen:
                self.err(where, "two layers have this name")
            names_seen.add(lname)
            rows = l["rows"]
            if (len(rows[0]) if rows else 0, len(rows)) != (width, height) or len({len(r) for r in rows}) > 1:
                lens = sorted({len(r) for r in rows})
                self.err(where, f"{len(rows)} rows of length {lens}; every layer must be {width}x{height} "
                                f"(the largest) with equal rows")
            cells: list[list] = [[None] * width for _ in range(height)]
            layer = LevelLayer(lname, bool(l.get("above")), cells)
            unknown: dict[str, tuple[int, int]] = {}
            for y, row in enumerate(rows):
                for x, c in enumerate(row):
                    if c in " .":
                        continue
                    if c not in legend:
                        unknown.setdefault(c, (x, y))
                        continue
                    if c not in specs:
                        specs[c] = self.legend_spec(c, legend[c], "legend")
                    spec = specs[c]
                    if spec is None:
                        continue
                    if spec[0] == "tile":
                        cells[y][x] = (spec[1], spec[2])
                    else:
                        auto_cells.append((layer, x, y, spec))
            for c, (x, y) in unknown.items():
                self.err(where, f"{c!r} at column {x}, row {y} is not in the legend")
            layers.append(layer)

        # autotiles: a cell's edges are the sides whose neighbour isn't the same terrain
        groups: dict[tuple[int, str], set[tuple[int, int]]] = {}
        for layer, x, y, spec in auto_cells:
            groups.setdefault((id(layer), spec[2]), set()).add((x, y))
        for layer, x, y, (_, ts_name, terrain) in auto_cells:
            ts = self.tilesets[ts_name]
            at = ts.autotile[terrain]
            members = {at["base"], *at.get("edges", {}).values()}
            same = groups[(id(layer), terrain)]

            def is_same(nx, ny):
                if not (0 <= nx < width and 0 <= ny < height):
                    return True   # the terrain carries on past the edge of the map
                if (nx, ny) in same:
                    return True
                cell = layer.cells[ny][nx]
                return bool(cell) and cell[0] == ts_name and ts.names[cell[1]] in members
            edges = "".join(d for d, (dx, dy) in zip(DIRS, ((0, -1), (0, 1), (1, 0), (-1, 0))) if not is_same(x + dx, y + dy))
            layer.cells[y][x] = (ts_name, ts.index(pick_edge(at, edges)))

        self.stamps(layers, width, height)
        objects = self.objects(width, height, tw, th)
        for n, ts in self.tilesets.items():
            if ts.tile_size != (tw, th):
                self.err("tileset", f"{n!r} has {ts.tile_size[0]}x{ts.tile_size[1]} tiles; the level's tileset "
                                    f"{self.default!r} has {tw}x{th}")
        used = {self.default} | {c[0] for l in layers for row in l.cells for c in row if c}
        tilesets = {n: t for n, t in self.tilesets.items() if n in used}
        return Level(self.name, self.path, raw, view, self.default, tw, th, width, height, layers, objects,
                     tilesets, self.problems)

    def stamps(self, layers: list[LevelLayer], width: int, height: int) -> None:
        by_name = {l.name: l for l in layers}
        for i, st in enumerate(self.raw.get("stamps") or []):
            where = f"stamps[{i}]"
            if not isinstance(st, dict) or not isinstance(st.get("stamp"), str):
                self.err(where, "a stamp is {\"stamp\": name, \"at\": [x, y]} (+ \"tileset\", \"layer\")")
                continue
            ts_name = st.get("tileset", self.default)
            ts = self.ts(ts_name)
            if ts is None:
                continue
            rows = ts.pf.get("stamps", {}).get(st["stamp"])
            if rows is None:
                self.err(where, f"tileset {ts_name!r} has no stamp {st['stamp']!r} "
                                f"(known: {', '.join(ts.pf.get('stamps', {})) or 'none'})")
                continue
            try:
                ax, ay = (int(v) for v in st.get("at", [0, 0]))
            except (TypeError, ValueError):
                self.err(where, f"\"at\" must be [x, y] in tiles, got {st.get('at')!r}")
                continue
            target = by_name.get(st.get("layer", layers[0].name))
            if target is None:
                self.err(where, f"no layer {st.get('layer')!r}")
                continue
            above = next((l for l in layers if l.above), None)
            if above is None and any(ts.props(i).get("above") for r in rows for i in r if i >= 0):
                # a top-down roof needs a layer drawn over the characters
                above = LevelLayer("above", True, [[None] * width for _ in range(height)])
                layers.append(above)
                by_name["above"] = above
            off = 0
            for y, row in enumerate(rows):
                for x, idx in enumerate(row):
                    if idx < 0:
                        continue
                    cx, cy = ax + x, ay + y
                    if not (0 <= cx < width and 0 <= cy < height):
                        off += 1
                        continue
                    dest = above if above is not None and ts.props(idx).get("above") else target
                    dest.cells[cy][cx] = (ts_name, idx)
            if off:
                self.err(where, f"{off} tile(s) of {st['stamp']!r} fall outside the {width}x{height} map", "warn")

    def objects(self, width: int, height: int, tw: int, th: int) -> list[LevelObject]:
        o = self.raw.get("objects") or {}
        legend = {**DEFAULT_OBJECT_LEGEND, **(o.get("legend") or {})}
        out: list[LevelObject] = []
        rows = o.get("rows") or []
        if rows and (len(rows) > height or max(len(r) for r in rows) > width):
            self.err("objects/rows", f"{max(len(r) for r in rows)}x{len(rows)} is bigger than the "
                                     f"{width}x{height} map")
        unknown: dict[str, tuple[int, int]] = {}
        for cy, row in enumerate(rows):
            for cx, c in enumerate(row):
                if c in " .":
                    continue
                spec = legend.get(c)
                if not isinstance(spec, dict):
                    unknown.setdefault(c, (cx, cy))
                    continue
                obj = self.object(len(out) + 1, spec, f"objects/rows ({cx},{cy}) {c!r}", cell=(cx, cy), tw=tw, th=th)
                if obj:
                    out.append(obj)
        for c, (x, y) in unknown.items():
            self.err("objects/rows", f"{c!r} at column {x}, row {y} is not in objects.legend")
        for i, spec in enumerate(o.get("list") or []):
            if not isinstance(spec, dict):
                self.err(f"objects/list[{i}]", "each object is a JSON object")
                continue
            obj = self.object(len(out) + 1, spec, f"objects/list[{i}]", tw=tw, th=th)
            if obj:
                out.append(obj)
        return out

    def object(self, oid: int, spec: dict, where: str, cell=None, tw=16, th=16) -> LevelObject | None:
        prop, sprite = spec.get("prop"), spec.get("sprite")
        otype = spec.get("type") or ("prop" if prop else "sprite" if sprite else "trigger")
        dx, dy = (int(v) for v in spec.get("offset", [0, 0]))
        s = None
        for kind, n in (("prop", prop), ("sprite", sprite)):
            if n is None:
                continue
            if n not in list_sprites():
                self.err(where, f"no {kind} {n!r}")
                return None
            s = Sprite.load(n)
            if s.kind == "fx":
                self.err(where, f"{n!r} is an effect; the game spawns those (spawnPixelforgeFx), levels don't place them")
                return None
            if (kind == "prop") != (s.kind == "prop"):
                self.err(where, f"{n!r} is a {s.kind}; use \"{'prop' if s.kind == 'prop' else 'sprite'}\": {n!r}")
                return None
        if cell is not None:
            cx, cy = cell
            x, y = cx * tw + tw // 2, (cy + 1) * th
            if spec.get("snap") == "left" and s is not None:
                x = cx * tw + s.origin[0]
            elif spec.get("snap") not in (None, "left"):
                self.err(where, f"snap {spec['snap']!r}: only \"left\" is supported", "warn")
        else:
            try:
                x, y = (int(v) for v in spec["at"])
            except (KeyError, TypeError, ValueError):
                self.err(where, "needs \"at\": [x, y] in level pixels")
                return None
        x, y = x + dx, y + dy
        state = spec.get("state")
        if s is not None and state is not None and state not in s.animations:
            self.err(where, f"{s.name!r} has no state {state!r} (known: {', '.join(s.animations)})")
        obj = LevelObject(oid, spec.get("name") or prop or sprite or otype, otype, x, y, where, prop=prop,
                          sprite=sprite, state=state, to=spec.get("to"), spawn=spec.get("spawn"),
                          props=dict(spec.get("props") or {}))
        if s is not None:
            left, top = x - s.origin[0], y - s.origin[1]
            obj.art = (left, top, s.width, s.height)
            if s.kind == "prop" and s.solid:
                fx, fy, fw, fh = s.body_rect()
                obj.footprint = (left + fx, top + fy, fw, fh)
        elif "size" in spec or otype in ZONE_TYPES:
            try:
                w, h = (int(v) for v in spec.get("size", [1, 1]))
            except (TypeError, ValueError):
                self.err(where, f"\"size\" must be [w, h] in tiles, got {spec.get('size')!r}")
                w, h = 1, 1
            if cell is not None:
                obj.rect = (cell[0] * tw + dx, cell[1] * th + dy, w * tw, h * th)
            else:
                obj.rect = (x - w * tw // 2, y - h * th, w * tw, h * th)
        return obj


def pick_edge(at: dict, edges: str) -> str:
    """The most specific edge tile that exists for these open sides (e.g. "ne" > "n" > base)."""
    have = at.get("edges", {})
    if not edges:
        return at["base"]
    for k in range(len(edges), 0, -1):
        for combo in itertools.combinations(edges, k):
            key = "".join(combo)
            if key in have:
                return have[key]
    return at["base"]


# ---- export: a Tiled map ----------------------------------------------------------------------
def _prop(name: str, value) -> dict:
    if isinstance(value, bool):
        return {"name": name, "type": "bool", "value": value}
    if isinstance(value, int):
        return {"name": name, "type": "int", "value": value}
    if isinstance(value, float):
        return {"name": name, "type": "float", "value": value}
    return {"name": name, "type": "string", "value": value if isinstance(value, str) else json.dumps(value)}


def level_data(lv: Level) -> dict:
    """The level as a Tiled map (orthogonal JSON) with every tileset embedded (Phaser can't read
    external ones). The "pixelforge" block is what pixelforgeLevel reads: Tiled ignores it."""
    firstgid, tilesets = {}, []
    gid = 1
    for n, ts in lv.tilesets.items():
        firstgid[n] = gid
        d = {k: v for k, v in ts.data.items() if k not in ("type", "version", "tiledversion", "pixelforge")}
        tilesets.append({"firstgid": gid, **d, "image": f"../{ts.data['image']}"})
        gid += ts.data["tilecount"]
    layers = []
    for i, l in enumerate(lv.layers):
        data = [firstgid[c[0]] + c[1] if c else 0 for row in l.cells for c in row]
        layers.append({"type": "tilelayer", "id": i + 1, "name": l.name, "x": 0, "y": 0, "width": lv.width,
                       "height": lv.height, "opacity": 1, "visible": True, "data": data,
                       "properties": [_prop("above", l.above)]})
    objs = []
    for o in lv.objects:
        props = [_prop(k, v) for k, v in (("prop", o.prop), ("sprite", o.sprite), ("state", o.state), ("to", o.to),
                                          ("spawn", o.spawn)) if v is not None]
        props += [_prop(k, v) for k, v in o.props.items()]
        t = {"id": o.id, "name": o.name, "type": o.type, "class": o.type, "visible": True, "rotation": 0,
             "properties": props}
        if o.rect:
            t.update(x=o.rect[0], y=o.rect[1], width=o.rect[2], height=o.rect[3])
        else:
            t.update(x=o.x, y=o.y, width=0, height=0, point=True)
        objs.append(t)
    layers.append({"type": "objectgroup", "id": len(layers) + 1, "name": "objects", "x": 0, "y": 0,
                   "opacity": 1, "visible": True, "draworder": "topdown", "objects": objs})
    meta = {"name": lv.name, "view": lv.view, "background": lv.background, "accents": lv.accents,
            "player": lv.player, "camera": lv.camera}
    return {
        "type": "map", "version": "1.10", "tiledversion": "1.10.2", "orientation": "orthogonal",
        "renderorder": "right-down", "infinite": False, "width": lv.width, "height": lv.height,
        "tilewidth": lv.tile_w, "tileheight": lv.tile_h, "nextlayerid": len(layers) + 1,
        "nextobjectid": len(lv.objects) + 1, "layers": layers, "tilesets": tilesets,
        "properties": [_prop(k, v) for k, v in meta.items() if v not in (None, {}, [])],
        "pixelforge": {**meta, "tileset": lv.tileset, "tilesets": list(lv.tilesets),
                       "layers": [{"name": l.name, "above": l.above} for l in lv.layers],
                       "objects": [o.to_dict() for o in lv.objects],
                       "size": list(lv.pixel_size), "screen": list(lv.screen_size())},
    }


def export_level(lv: Level, out_dir: Path | None = None) -> Path:
    from .export import export_dir
    out = (out_dir or export_dir()) / "levels"
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{lv.name}.json"
    p.write_text(json.dumps(level_data(lv), indent=1) + "\n", encoding="utf-8")
    return p


# ---- scaffolding --------------------------------------------------------------------------------
def default_player(view: str) -> str | None:
    """The character a new level is played with: the first one drawn for this view, else the first one."""
    chars = list_sprites("sprite", with_variants=False)
    def fits(n):
        meta = json.loads((sprite_folder(n) / "sprite.json").read_text(encoding="utf-8"))
        own = meta.get("view") or (meta.get("class") if meta.get("class") in ("topdown", "overhead") else "side")
        return own == view
    return next((n for n in chars if fits(n)), chars[0] if chars else None)


def new_level(name: str, size: tuple[int, int] | None = None, tileset: str | None = None,
              player: str | None = None) -> Path:
    """One screen of ground plus a spawn in the middle: a level to build on."""
    p = levels_dir() / f"{name}.json"
    if p.exists():
        raise LevelError(f"{rel(p)} already exists")
    sets = tileset_names()
    tileset = tileset or next((t for t in sets if not t.endswith("_tiles")), None)
    if tileset is None:
        raise LevelError("no tileset to build the level from; make one first (`pixelforge new terrain --tileset`)")
    ts = load_tileset(tileset)
    tw, th = ts.tile_size
    view = game_view()
    if size is None:
        rw, rh = game_resolution()
        size = (max(4, -(-rw // tw)), max(4, -(-rh // th)))
    w, h = size
    ground_char = next(iter(sample_legend(tileset)), None)
    level: dict = {"name": name, "view": view, "tileset": tileset, "background": {"color": "#262b44"}}
    if ground_char is None:
        ground_char = "g"
        level["legend"] = {"g": ts.names[0]}
    if view == "side":
        rows = ["." * w] * (h - 2) + [ground_char * w] * 2
        spawn_row = h - 3
    else:
        rows = [ground_char * w] * h
        spawn_row = h // 2
    objects = ["." * w] * h
    objects[spawn_row] = "." * (w // 2) + "@" + "." * (w - w // 2 - 1)
    level["layers"] = [{"name": "ground", "rows": rows}]
    level["objects"] = {"rows": objects}
    player = player or default_player(view)
    if player:
        level["player"] = player
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(level, indent=2) + "\n", encoding="utf-8")   # one map row per line
    return p
