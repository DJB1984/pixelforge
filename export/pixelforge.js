// Phaser 3 helper for pixelforge exports (export/<name>.png + export/<name>.json).
//
//   preload() { loadPixelforge(this, 'knight'); }
//   create()  {
//     createPixelforgeAnims(this, 'knight');                 // keys: knight_idle, knight_attack, ...
//     const knight = this.add.sprite(100, 100, 'knight').play('knight_idle');
//     enablePixelforgeHits(this, knight, () => enemies, (enemy) => enemy.takeDamage(1));
//   }
//
// Remember `pixelArt: true` in the game config. No dependency on the Phaser global, so it works
// with both <script> and `import Phaser from 'phaser'` setups.

export function loadPixelforge(scene, name, baseUrl = 'export/') {
  scene.load.aseprite(name, `${baseUrl}${name}.png`, `${baseUrl}${name}.json`);
}

// Phaser's createFromAseprite plays every tag once; this restores `loop: true` from sprite.json.
export function createPixelforgeAnims(scene, name) {
  const anims = scene.anims.createFromAseprite(name);
  const info = scene.cache.json.get(name)?.meta?.pixelforge?.animations ?? {};
  for (const anim of anims) {
    if (info[anim.key]?.loop) anim.repeat = -1;
  }
  return anims;
}

// Top-down sprites name animations <action>_<down|up|side> and draw only the right-facing side.
// playFacing(knight, 'walk', 'left') plays knight_topdown_walk_side mirrored. Returns the sprite.
export function playFacing(sprite, action, facing, config = {}) {
  const dir = facing === 'left' || facing === 'right' ? 'side' : facing;
  sprite.setFlipX(facing === 'left');
  return sprite.play({ key: `${sprite.texture.key}_${action}_${dir}`, ...config }, true);
}

const meta = (sprite) => sprite.scene.cache.json.get(sprite.texture.key);

// Frame-space [x, y, w, h] -> world space, honouring origin, flips, scale and rotation (in that
// order, as Phaser draws). Returns the four corners (`points`, clockwise) plus their axis-aligned
// bounds {x, y, width, height}. Phaser mirrors and rotates a sprite around its origin, and so do
// the boxes. Parent containers are not applied.
function toWorld(sprite, [x, y, w, h]) {
  const fw = sprite.frame.realWidth, fh = sprite.frame.realHeight;
  const ox = sprite.originX * fw, oy = sprite.originY * fh;
  const lx = sprite.flipX ? ox - (x + w) : x - ox;
  const ly = sprite.flipY ? oy - (y + h) : y - oy;
  const sx = Math.abs(sprite.scaleX), sy = Math.abs(sprite.scaleY);
  const cos = Math.cos(sprite.rotation), sin = Math.sin(sprite.rotation);
  const points = [[lx, ly], [lx + w, ly], [lx + w, ly + h], [lx, ly + h]].map(([px, py]) => {
    const X = px * sx, Y = py * sy;
    return { x: sprite.x + X * cos - Y * sin, y: sprite.y + X * sin + Y * cos };
  });
  const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
  const minX = Math.min(...xs), minY = Math.min(...ys);
  return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY, points };
}

// Boxes for the sprite's current frame: kind is 'hurt' (can be hit) or 'hit' (deals damage;
// only present on active attack frames). Returns world-space rectangles.
export function pixelforgeBoxes(sprite, kind) {
  const f = meta(sprite)?.frames?.[sprite.frame.name]?.pixelforge;
  return (f?.[kind] ?? []).map((r) => toWorld(sprite, r));
}

// The fixed body box (for physics): { x, y, width, height } in frame pixels.
// e.g. sprite.body.setSize(b.width, b.height).setOffset(b.x, b.y) with Arcade physics.
export function pixelforgeBody(scene, name) {
  const b = scene.cache.json.get(name)?.meta?.pixelforge?.body;
  return b && { x: b.x, y: b.y, width: b.w, height: b.h };
}

// Overlap of two boxes from pixelforgeBoxes(). Exact for rotated boxes (separating-axis test);
// plain {x, y, width, height} rectangles are compared axis-aligned.
export function rectsOverlap(a, b) {
  const aabb = a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
  if (!aabb || !a.points || !b.points) return aabb;
  for (const poly of [a.points, b.points]) {
    for (let i = 0; i < 2; i++) {                       // a rectangle has two edge directions
      const p = poly[i], q = poly[i + 1];
      const nx = q.y - p.y, ny = p.x - q.x;             // edge normal
      const proj = (pts) => pts.map((v) => v.x * nx + v.y * ny);
      const pa = proj(a.points), pb = proj(b.points);
      if (Math.max(...pa) <= Math.min(...pb) || Math.max(...pb) <= Math.min(...pa)) return false;
    }
  }
  return true;
}

// Each frame, checks the attacker's hitboxes against every target's hurtboxes. Calls
// onHit(target, attacker) and emits 'pixelforge-hit' on the attacker at most once per target per
// swing (reset whenever an animation starts or repeats). `targets` is an array or a function
// returning one. Returns a function that turns the check off.
export function enablePixelforgeHits(scene, attacker, targets, onHit) {
  let struck = new Set();
  const reset = () => { struck = new Set(); };
  attacker.on('animationstart', reset);
  attacker.on('animationrestart', reset);
  attacker.on('animationrepeat', reset);
  const check = () => {
    if (!attacker.active) return;
    const hits = pixelforgeBoxes(attacker, 'hit');
    if (!hits.length) return;
    for (const t of (typeof targets === 'function' ? targets() : targets)) {
      if (t === attacker || !t.active || struck.has(t)) continue;
      const hurts = pixelforgeBoxes(t, 'hurt');
      if (hits.some((h) => hurts.some((u) => rectsOverlap(h, u)))) {
        struck.add(t);
        onHit?.(t, attacker);
        attacker.emit('pixelforge-hit', t);
      }
    }
  };
  // postupdate: targets walking into a held hitbox. animationupdate: fires for every frame the
  // animation passes through, even several in one slow tick, so short active frames are never skipped.
  scene.events.on('postupdate', check);
  attacker.on('animationupdate', check);
  const off = () => {
    scene.events.off('postupdate', check);
    attacker.off('animationupdate', check);
    attacker.off('animationstart', reset).off('animationrestart', reset).off('animationrepeat', reset);
  };
  attacker.once('destroy', off);
  return off;
}

// ---- tilesets (sprite.json "type": "tileset") -------------------------------------------------
// export/<name>.png is the tile grid; export/<name>.json is a Tiled tileset that also lists each
// tile's name and properties. Tile index = the tile's position in sprite.json "tiles".
//
//   preload() { loadPixelforgeTiles(this, 'terrain'); }
//   create()  {
//     const { map, layer } = pixelforgeTilemap(this, 'terrain', { rows: ['ggww', 'gddg'],
//                                                                legend: { g: 'grass', d: 'dirt', w: 'water' } });
//     this.physics.add.collider(hero, layer);            // tiles with "collides": true block
//   }

export function loadPixelforgeTiles(scene, name, baseUrl = 'export/') {
  scene.load.image(name, `${baseUrl}${name}.png`);
  scene.load.json(name, `${baseUrl}${name}.json`);
}

// Index of a named tile, for map.putTileAt(pixelforgeTileIndex(this, 'terrain', 'water'), x, y).
export function pixelforgeTileIndex(scene, name, tileName) {
  const i = scene.cache.json.get(name)?.pixelforge?.names.indexOf(tileName) ?? -1;
  if (i < 0) throw new Error(`pixelforge: tileset '${name}' has no tile '${tileName}'`);
  return i;
}

// Adds the tileset to any tilemap, including one made in Tiled (embed the tileset there: Phaser
// can't read external ones). `tilesetName` is its name inside the Tiled map.
export function addPixelforgeTileset(map, name, tilesetName = name) {
  const d = map.scene.cache.json.get(name);
  return map.addTilesetImage(tilesetName, name, d.tilewidth, d.tileheight, d.margin, d.spacing);
}

// Copies each tile's name and sprite.json properties onto tile.properties and turns on collision
// for tiles with "collides": true. Returns the colliding tile indices.
export function applyPixelforgeTileProperties(layer, name) {
  const pf = layer.scene.cache.json.get(name)?.pixelforge;
  const ts = layer.tileset.find((t) => t.image?.key === name);
  if (!pf || !ts) return [];
  layer.forEachTile((tile) => {
    const id = tile.index - ts.firstgid;
    if (id >= 0 && id < pf.names.length) tile.properties = { ...tile.properties, name: pf.names[id], ...pf.properties[id] };
  });
  const collide = pf.properties.flatMap((p, i) => (p.collides ? [i + ts.firstgid] : []));
  if (collide.length) layer.setCollision(collide);
  // "oneway": true (with "collides"): a plank you jump up through and land on
  layer.forEachTile((tile) => { if (tile.properties?.oneway && tile.collides) tile.setCollision?.(false, false, true, false); });
  return collide;
}

// Plays animated tiles (sprite.json "frames") by swapping tile indices on one shared clock, so all
// the water on a layer ripples in step. pixelforgeTilemap calls it for you. For a Tiled map, call it
// after applyPixelforgeTileProperties. It animates the tiles on the layer when it is called (re-run
// it after putTileAt). An animating tile's index changes; look it up by tile.properties.name instead.
// Returns a function that stops the animation.
export function animatePixelforgeTiles(layer, name) {
  const scene = layer.scene;
  const pf = scene.cache.json.get(name)?.pixelforge;
  const ts = layer.tileset.find((t) => t.image?.key === name);
  const anims = [];
  for (const [id, frames] of Object.entries(pf?.animations ?? {})) {
    if (!ts) break;
    const base = Number(id) + ts.firstgid, tiles = [];
    layer.forEachTile((t) => { if (t.index === base) tiles.push(t); });
    if (tiles.length) anims.push({ tiles, current: base, frames: frames.map(([slot, ms]) => [slot + ts.firstgid, ms]),
                                   total: frames.reduce((sum, [, ms]) => sum + ms, 0) });
  }
  if (!anims.length) return () => {};
  let elapsed = 0;
  const tick = (time, delta) => {
    elapsed += delta;
    for (const a of anims) {
      let t = elapsed % a.total, index = a.frames[0][0];
      for (const [slot, ms] of a.frames) { if (t < ms) { index = slot; break; } t -= ms; }
      if (index !== a.current) {
        a.current = index;
        for (const tile of a.tiles) tile.index = index;
      }
    }
  };
  scene.events.on('update', tick);
  const stop = () => { scene.events.off('update', tick); scene.events.off('shutdown', stop); };
  scene.events.once('shutdown', stop);
  layer.once('destroy', stop);
  return stop;
}

// Rows of tile indices (-1 = empty) from index arrays, or from strings read through `legend`
// ({ char: tileName }; ' ' and '.' are empty). Default: the tileset's sprite.json "sample" map.
export function pixelforgeRows(scene, name, rows, legend = {}) {
  const pf = scene.cache.json.get(name)?.pixelforge;
  const index = (c) => {
    if (c === ' ' || c === '.') return -1;
    if (!(c in legend)) throw new Error(`pixelforge: map character '${c}' is not in the legend`);
    return pixelforgeTileIndex(scene, name, legend[c]);
  };
  return (rows ?? pf?.sample ?? []).map((row) => (typeof row === 'string' ? [...row].map(index) : row));
}

// A whole map in one call: { map, tileset, layer, stopAnimation }. Properties, collision and tile
// animation are applied.
export function pixelforgeTilemap(scene, name, { rows, legend, x = 0, y = 0 } = {}) {
  const d = scene.cache.json.get(name);
  const map = scene.make.tilemap({ data: pixelforgeRows(scene, name, rows, legend),
                                   tileWidth: d.tilewidth, tileHeight: d.tileheight });
  const tileset = addPixelforgeTileset(map, name);
  const layer = map.createLayer(0, tileset, x, y);
  applyPixelforgeTileProperties(layer, name);
  const stopAnimation = animatePixelforgeTiles(layer, name);
  return { map, tileset, layer, stopAnimation };
}

// Places a stamp (sprite.json "stamps": a prebuilt arrangement such as a house made from kit tiles,
// or a whole sliced building from <prop>_tiles) with its top-left tile at (tx, ty). Empty cells keep
// what's under them. Tiles marked `above` (a top-down roof) go on `above` if given: a layer drawn over
// the characters, so they walk behind the roof. Properties and collision are re-applied. Returns the
// tiles placed.
export function stampPixelforgeTiles(layer, name, stamp, tx, ty, { above } = {}) {
  const pf = layer.scene.cache.json.get(name)?.pixelforge;
  const rows = pf?.stamps?.[stamp];
  if (!rows) throw new Error(`pixelforge: tileset '${name}' has no stamp '${stamp}' (known: ${Object.keys(pf?.stamps ?? {}).join(', ')})`);
  const firstgid = (l) => l.tileset.find((t) => t.image?.key === name)?.firstgid ?? 0;
  const placed = [];
  rows.forEach((row, y) => row.forEach((i, x) => {
    if (i < 0) return;
    const target = above && pf.properties[i]?.above ? above : layer;
    placed.push(target.putTileAt(i + firstgid(target), tx + x, ty + y));
  }));
  applyPixelforgeTileProperties(layer, name);
  if (above) applyPixelforgeTileProperties(above, name);
  return placed;
}

// ---- props (sprite.json "type": "prop"): objects, buildings, background accents -------------
// A prop's animations are its states (chest_closed, chest_open...). Its export carries how it sits in
// the game: layer (back | world | front), scroll (parallax factor), solid + footprint (collision), and
// ysort (top-down world props are drawn in order of their base, so characters walk behind them).
//
//   preload() { loadPixelforge(this, 'house'); }
//   create()  {
//     const house = addPixelforgeProp(this, 160, 120, 'house');       // (x, y) = its origin: the base
//     this.physics.add.collider(hero, house);                         // solid props get a static body
//   }
//   update()  { hero.setDepth(hero.y); }                              // top-down: sort characters too

const PROP_DEPTH = { back: -10000, world: 0, front: 10000 };

// Depth for a prop: back-layer props sort by scroll (farther = lower), world props by their base
// when they y-sort, front props above everything.
export function pixelforgeDepth(sprite, info) {
  if (info.layer === 'back') return PROP_DEPTH.back + info.scroll * 100;
  if (info.layer === 'front') return PROP_DEPTH.front;
  return info.ysort ? sprite.y : 0;
}

// Creates the prop at (x, y), plays `state` (default: its first animation), sets scroll factor and
// depth, and gives solid props an Arcade static body covering the footprint (when the scene has
// Arcade physics and `physics` isn't false). Returns the sprite; prop info is on sprite.pixelforge.
export function addPixelforgeProp(scene, x, y, name, { state, physics = true } = {}) {
  const pf = scene.cache.json.get(name)?.meta?.pixelforge;
  if (!pf) throw new Error(`pixelforge: '${name}' isn't loaded (loadPixelforge(this, '${name}') in preload)`);
  const info = pf.prop ?? { layer: 'world', scroll: 1, solid: false, ysort: false };
  const keys = Object.keys(pf.animations);
  if (!keys.every((k) => scene.anims.exists(k))) createPixelforgeAnims(scene, name);
  const solid = physics && info.solid && scene.physics?.add;
  const sprite = solid ? scene.physics.add.staticSprite(x, y, name) : scene.add.sprite(x, y, name);
  sprite.pixelforge = info;
  const key = state ? `${name}_${state}` : keys[0];
  if (key) sprite.play(key);
  sprite.setScrollFactor(info.scroll);
  sprite.setDepth(pixelforgeDepth(sprite, info));
  if (solid) {
    const b = pf.body;   // the footprint, in frame pixels
    sprite.body.setSize(b.w, b.h, false).setOffset(b.x, b.y);
  }
  return sprite;
}

// Every frame, sets each sprite's depth to its y (its feet), so characters and y-sorted props overlap
// correctly in a top-down game. `sprites` is an array or a function returning one. Returns a stop function.
export function keepPixelforgeDepth(scene, sprites) {
  const tick = () => { for (const s of (typeof sprites === 'function' ? sprites() : sprites)) if (s.active) s.setDepth(s.y); };
  scene.events.on('update', tick);
  return () => scene.events.off('update', tick);
}

// ---- UI: icon atlases ("type": "icons") and bitmap fonts ("type": "font") -------------------
//   preload() { loadPixelforgeIcons(this, 'items'); loadPixelforgeFont(this, 'font'); }
//   create()  {
//     this.add.image(20, 20, 'items', 'potion');                       // any icon by name
//     addPixelforgePanel(this, 160, 90, 'items', 'panel', 120, 48);   // nine-slice, stretched
//     this.add.bitmapText(8, 8, 'font', 'HP 10/10');
//   }

export function loadPixelforgeIcons(scene, name, baseUrl = 'export/') {
  scene.load.aseprite(name, `${baseUrl}${name}.png`, `${baseUrl}${name}.json`);   // a JSON-hash atlas, cached
}

// A nine-slice panel/button from an icon with "nine": [left, right, top, bottom] (Phaser 3.60+):
// the corners stay crisp and only the edges and middle stretch.
export function addPixelforgePanel(scene, x, y, name, icon, width, height) {
  const nine = scene.cache.json.get(name)?.meta?.pixelforge?.nine?.[icon];
  if (!nine) throw new Error(`pixelforge: icon '${icon}' in '${name}' has no "nine" insets`);
  const [l, r, t, b] = nine;
  return scene.add.nineslice(x, y, name, icon, width, height, l, r, t, b);
}

export function loadPixelforgeFont(scene, name, baseUrl = 'export/') {
  scene.load.bitmapFont(name, `${baseUrl}${name}.png`, `${baseUrl}${name}.xml`);
}

// ---- everything at once: export/index.json ----------------------------------------------------
//   preload() { loadPixelforgeAll(this); }          // every sprite, prop, tileset, icon atlas, font...
//   create()  { createPixelforgeAll(this); }        // ...and every animation
// The index is loaded first; its filecomplete handler queues the rest (Phaser lets a loader grow
// while it runs). The parsed index stays in the JSON cache as 'pixelforge-index'.

export const PIXELFORGE_INDEX = 'pixelforge-index';

export function loadPixelforgeAll(scene, baseUrl = 'export/') {
  const cached = scene.cache.json.get(PIXELFORGE_INDEX);
  if (cached) return queuePixelforgeIndex(scene, cached, baseUrl);
  const onFile = (key, type, data) => {
    if (key !== PIXELFORGE_INDEX) return;
    scene.load.off('filecomplete', onFile);
    queuePixelforgeIndex(scene, data, baseUrl);
  };
  scene.load.on('filecomplete', onFile);
  scene.load.json(PIXELFORGE_INDEX, `${baseUrl}index.json`);
}

// Queues every asset an index lists (skipping ones already loaded). Returns the names queued.
export function queuePixelforgeIndex(scene, index, baseUrl = 'export/') {
  const queued = [];
  const each = (group, load, loaded) => {
    for (const name of index?.[group] ?? []) {
      if (loaded(name)) continue;
      load(scene, name, baseUrl);
      queued.push(name);
    }
  };
  const tex = (n) => scene.textures?.exists(n);
  each('sprites', loadPixelforge, tex);
  each('props', loadPixelforge, tex);
  each('tilesets', loadPixelforgeTiles, tex);
  each('icons', loadPixelforgeIcons, tex);
  each('fonts', loadPixelforgeFont, tex);
  each('levels', loadPixelforgeLevel, (n) => scene.cache.tilemap?.exists(n));
  return queued;
}

// A level (export/levels/<name>.json, a Tiled map with its tilesets embedded). pixelforgeLevel builds it.
export function loadPixelforgeLevel(scene, name, baseUrl = 'export/') {
  scene.load.tilemapTiledJSON(name, `${baseUrl}levels/${name}.json`);
}

// Animations for every sprite and prop in the loaded index. Returns their names.
export function createPixelforgeAll(scene) {
  const index = scene.cache.json.get(PIXELFORGE_INDEX) ?? {};
  const names = [...(index.sprites ?? []), ...(index.props ?? [])];
  for (const name of names) {
    const tags = Object.keys(scene.cache.json.get(name)?.meta?.pixelforge?.animations ?? {});
    if (!tags.every((k) => scene.anims.exists(k))) createPixelforgeAnims(scene, name);
  }
  return names;
}

// ---- the player --------------------------------------------------------------------------------
// One controller for the dashboard, the playtests and the real game, so they all play the same:
//
//   const hero = addPixelforgePlayer(this, 80, 160, 'princess');      // view from the export
//   this.physics.add.collider(hero, groundLayer);
//   hero.on('pixelforge-land', () => dust());                          // also pixelforge-jump, -attack
//
// side:     walk, run (Shift), coyote time, jump buffer, variable jump height; idle/walk/run/
//           jump_rise/jump_fall/jump_land/attack picked from the motion (each falls back to a simpler one)
// topdown:  4-direction walk with playFacing, feet-only body, attack_<dir>, depth = y
// overhead: 8-direction, rotated to face where it goes, circle body from the body box, attack
// Input: sprite.controller.input = {left, right, up, down, jump, run, attack}, read from the keyboard
// (arrows/WASD, Space/Up/W jump, Shift run, X/J attack) unless controller.override is set: an object
// of the same keys (missing ones are false). Playtests drive the player that way.

export const PLAYER_DEFAULTS = {
  side: { speed: 70, run: 135, jump: 330, gravity: 900, coyote: 90, buffer: 120 },
  topdown: { speed: 70 },
  overhead: { speed: 70 },
};
const NO_INPUT = { left: false, right: false, up: false, down: false, jump: false, run: false, attack: false };
const INPUT_KEYS = { left: ['LEFT', 'A'], right: ['RIGHT', 'D'], up: ['UP', 'W'], down: ['DOWN', 'S'],
                     jump: ['SPACE'], run: ['SHIFT'], attack: ['X', 'J'] };

// Which controller a sprite gets: its export's view (the topdown and overhead classes imply theirs).
export function pixelforgeView(scene, name) {
  const pf = scene.cache.json.get(name)?.meta?.pixelforge ?? {};
  if (pf.anchor === 'center') return 'overhead';
  if (`${name}_walk_down` in (pf.animations ?? {})) return 'topdown';
  return pf.view ?? 'side';
}

export class PixelforgeController {
  constructor(sprite, name, view, opts = {}) {
    this.sprite = sprite;
    this.name = name;
    this.view = view;
    this.opts = { ...PLAYER_DEFAULTS[view], ...opts };
    this.input = { ...NO_INPUT };
    this.override = null;
    this.prev = { ...NO_INPUT };
    this.facing = view === 'topdown' ? 'down' : 'right';
    this.busy = null;            // a one-shot animation (land, attack) that plays out unless interrupted
    this.airborne = false;
    this.lastGround = -1e9;
    this.jumpQueued = -1e9;
    const tags = Object.keys(sprite.scene.cache.json.get(name)?.meta?.pixelforge?.animations ?? {});
    const first = tags[0];
    const pick = (...actions) => actions.map((a) => `${name}_${a}`).find((k) => tags.includes(k));
    this.tags = tags;
    this.anim = {
      idle: pick('idle') ?? first, walk: pick('walk', 'idle') ?? first, run: pick('run', 'walk', 'idle') ?? first,
      rise: pick('jump_rise', 'jump', 'idle') ?? first, fall: pick('jump_fall', 'jump_rise', 'jump', 'idle') ?? first,
      land: pick('jump_land'), attack: pick('attack'),
    };
    const kb = sprite.scene.input?.keyboard;
    this.keys = kb ? kb.addKeys(Object.values(INPUT_KEYS).flat().join(',')) : null;
    sprite.on('animationcomplete', (a) => { if (a.key === this.busy) this.busy = null; });
  }

  readInput() {
    if (this.override) return { ...NO_INPUT, ...this.override };
    if (!this.keys) return { ...NO_INPUT };
    const out = {};
    for (const [k, codes] of Object.entries(INPUT_KEYS)) out[k] = codes.some((c) => this.keys[c]?.isDown);
    return out;
  }

  update(time) {
    const s = this.sprite;
    if (!s.active || !s.body) return;
    this.input = this.readInput();
    if (this.view === 'side') this.updateSide(time, this.input);
    else if (this.view === 'overhead') this.updateOverhead(this.input);
    else this.updateTopdown(this.input);
    this.prev = this.input;
  }

  play(key) {
    if (key) this.sprite.play(key, true);   // keeps playing if it already is
  }

  get onGround() {
    const b = this.sprite.body;
    return !!(b?.blocked?.down || b?.touching?.down);
  }

  updateSide(time, input) {
    const s = this.sprite, body = s.body, o = this.opts, A = this.anim;
    const dir = (input.right ? 1 : 0) - (input.left ? 1 : 0);
    const onGround = this.onGround;
    const jumpHeld = input.jump || input.up;
    if (jumpHeld && !(this.prev.jump || this.prev.up)) this.jumpQueued = time;
    if (onGround) this.lastGround = time;
    // forgiving jumps: a press just before landing, or just after walking off a ledge, still counts
    if (time - this.jumpQueued < o.buffer && time - this.lastGround < o.coyote) {
      body.setVelocityY(-o.jump);
      this.jumpQueued = this.lastGround = -1e9;
      this.busy = null;
      s.emit('pixelforge-jump', s);
    }
    if (!jumpHeld && body.velocity.y < -o.jump / 3) body.setVelocityY(-o.jump / 3);   // short hop on release

    const attacking = !!this.busy && this.busy === A.attack;
    body.setVelocityX(attacking && onGround ? 0 : dir * (input.run ? o.run : o.speed));
    if (dir) { s.setFlipX(dir < 0); this.facing = dir < 0 ? 'left' : 'right'; }
    if (input.attack && !this.prev.attack && A.attack && !attacking) {
      this.busy = A.attack;
      s.play(A.attack);
      s.emit('pixelforge-attack', s);
    }
    const nowAttacking = !!this.busy && this.busy === A.attack;
    if (!onGround) {
      if (!nowAttacking) { this.busy = null; this.play(body.velocity.y < 0 ? A.rise : A.fall); }
    } else if (this.airborne) {
      s.emit('pixelforge-land', s);
      if (A.land && !nowAttacking) { this.busy = A.land; s.play(A.land); }
    } else if (this.busy && dir && this.busy === A.land) {
      this.busy = null;   // moving cancels the landing pose
    }
    if (onGround && !this.busy) this.play(dir ? (input.run ? A.run : A.walk) : A.idle);
    this.airborne = !onGround;
  }

  updateTopdown(input) {
    const s = this.sprite, o = this.opts;
    const vx = (input.right ? 1 : 0) - (input.left ? 1 : 0), vy = (input.down ? 1 : 0) - (input.up ? 1 : 0);
    if (input.attack && !this.prev.attack && !this.busy) {
      const dir = this.facing === 'left' || this.facing === 'right' ? 'side' : this.facing;
      const key = `${this.name}_attack_${dir}`;
      if (this.tags.includes(key)) {
        this.busy = key;
        playFacing(s, 'attack', this.facing);
        s.emit('pixelforge-attack', s);
      }
    }
    if (this.busy) {
      s.body.setVelocity(0, 0);
    } else {
      s.body.setVelocity(vx * o.speed, vy * o.speed);
      if (vx || vy) this.facing = vx ? (vx > 0 ? 'right' : 'left') : (vy > 0 ? 'down' : 'up');
      playFacing(s, vx || vy ? 'walk' : 'idle', this.facing);
    }
    s.setDepth(s.y);
  }

  updateOverhead(input) {
    const s = this.sprite, o = this.opts, A = this.anim;
    const vx = (input.right ? 1 : 0) - (input.left ? 1 : 0), vy = (input.down ? 1 : 0) - (input.up ? 1 : 0);
    const len = Math.hypot(vx, vy) || 1;
    if (input.attack && !this.prev.attack && !this.busy && A.attack) {
      this.busy = A.attack;
      s.play(A.attack);
      s.emit('pixelforge-attack', s);
    }
    if (this.busy) {
      s.body.setVelocity(0, 0);
    } else {
      s.body.setVelocity((vx / len) * o.speed, (vy / len) * o.speed);
      if (vx || vy) { s.setRotation(Math.atan2(vy, vx)); this.facing = Math.round(Math.atan2(vy, vx) * 180 / Math.PI); }
      this.play(vx || vy ? A.walk : A.idle);
    }
  }

  // What a playtest reads: position, velocity, ground contact, facing and the current animation.
  state() {
    const s = this.sprite, b = s.body;
    return { x: Math.round(s.x * 100) / 100, y: Math.round(s.y * 100) / 100,
             vx: Math.round((b?.velocity?.x ?? 0) * 100) / 100, vy: Math.round((b?.velocity?.y ?? 0) * 100) / 100,
             onGround: this.onGround, facing: this.facing, anim: s.anims?.currentAnim?.key ?? null };
  }
}

// Creates the player at (x, y) (its origin: the feet, or the centre for overhead sprites) with an
// Arcade body fitted to its view, and runs its controller every frame. opts: view, speed, run, jump,
// gravity (side; total gravity on the player, whatever the world's), coyote, buffer (ms),
// collideWorldBounds (default true). Returns the sprite; the controller is sprite.controller.
export function addPixelforgePlayer(scene, x, y, name, opts = {}) {
  const pf = scene.cache.json.get(name)?.meta?.pixelforge;
  if (!pf) throw new Error(`pixelforge: '${name}' isn't loaded (loadPixelforge(this, '${name}') in preload)`);
  const view = opts.view ?? pixelforgeView(scene, name);
  if (!(view in PLAYER_DEFAULTS)) throw new Error(`pixelforge: view '${view}' must be side, topdown or overhead`);
  if (!Object.keys(pf.animations).every((k) => scene.anims.exists(k))) createPixelforgeAnims(scene, name);
  const sprite = scene.physics.add.sprite(x, y, name);
  const b = pixelforgeBody(scene, name);
  const body = sprite.body;
  if (view === 'side') {
    body.setSize(b.width, b.height).setOffset(b.x, b.y);
    const gravity = opts.gravity ?? PLAYER_DEFAULTS.side.gravity;
    body.setAllowGravity(true);
    body.setGravityY(gravity - (scene.physics.world?.gravity?.y ?? 0));
  } else if (view === 'topdown') {
    // collide with the feet only, so the head can overlap the top edge of a wall
    body.setSize(b.width - 4, 8).setOffset(b.x + 2, b.y + b.height - 8);
    body.setAllowGravity(false);
  } else {
    const r = Math.min(b.width, b.height) / 2;
    body.setCircle(r, b.x + b.width / 2 - r, b.y + b.height / 2 - r);
    body.setAllowGravity(false);
  }
  if (opts.collideWorldBounds ?? true) sprite.setCollideWorldBounds?.(true);
  const controller = new PixelforgeController(sprite, name, view, opts);
  sprite.controller = controller;
  const tick = (time) => controller.update(time);
  scene.events.on('update', tick);
  const stop = () => { scene.events.off('update', tick); scene.events.off('shutdown', stop); };
  scene.events.once('shutdown', stop);
  sprite.once('destroy', stop);
  const start = controller.anim.idle ?? (view === 'topdown' ? `${name}_idle_down` : undefined);
  if (view === 'topdown') playFacing(sprite, 'idle', 'down'); else if (start) sprite.play(start);
  return sprite;
}

// ---- levels (levels/<name>.json, exported as Tiled maps with the tilesets embedded) -------------
//   preload() { loadPixelforgeAll(this); }                    // or loadPixelforgeLevel + each asset it uses
//   create()  {
//     const level = pixelforgeLevel(this, 'village');           // map, player, props, camera: all set up
//     this.events.on('pixelforge-trigger', (obj) => { if (obj.type === 'door') this.scene.restart({ level: obj.to }); });
//   }

const hexColor = (s) => parseInt(String(s).replace('#', '').slice(0, 6), 16);

// The level's own description (view, background, accents, player, camera, layers, objects), as exported.
export function pixelforgeLevelInfo(scene, name) {
  const pf = scene.cache.tilemap.get(name)?.data?.pixelforge;
  if (!pf) throw new Error(`pixelforge: level '${name}' isn't loaded (loadPixelforgeLevel(this, '${name}') in preload)`);
  return pf;
}

// Builds a whole level: background color (or {"gradient": [top, bottom]}) and accent props; tile layers
// with properties, collision and animation (`above` layers over the characters); props and sprites at
// their spots; the player at the spawn (opts.spawn names one; default "player") through
// addPixelforgePlayer (opts.player overrides the level's, opts.playerOptions go to the controller),
// colliding with the layers and solid props; camera bounds, follow and zoom. Door and trigger zones emit
// 'pixelforge-trigger' (object, player) on the scene's events when the player walks in. A side-view
// player who falls out of the level emits 'pixelforge-fell' and goes back to the spawn
// (opts.respawn: false to handle it yourself).
// Returns { map, layers, player, objects, props, sprites, spawns, triggers, accents, info }.
export function pixelforgeLevel(scene, name, opts = {}) {
  const info = pixelforgeLevelInfo(scene, name);
  const [W, H] = info.size;
  const map = scene.make.tilemap({ key: name });
  const tilesets = info.tilesets.map((t) => addPixelforgeTileset(map, t));
  const cam = scene.cameras.main;
  const bg = info.background ?? {};
  if (bg.color) cam.setBackgroundColor(bg.color);
  if (bg.gradient) {
    const [top, bottom] = bg.gradient.map(hexColor);
    scene.add.graphics().setScrollFactor(0, 1).setDepth(-20000)
      .fillGradientStyle(top, top, bottom, bottom, 1).fillRect(-10000, 0, 20000 + W, H);
  }
  const accents = (info.accents ?? []).map((a) => addPixelforgeProp(scene, a.at[0], a.at[1], a.prop,
                                                                    { state: a.state, physics: false }));
  const layers = {};
  info.layers.forEach((l, i) => {
    const layer = map.createLayer(l.name, tilesets, 0, 0);
    for (const t of info.tilesets) applyPixelforgeTileProperties(layer, t);
    for (const t of info.tilesets) animatePixelforgeTiles(layer, t);
    layer.setDepth(l.above ? 1e5 : -5000 + i);
    layers[l.name] = layer;
  });

  const objects = info.objects ?? [];
  const props = [], sprites = [], triggers = [], spawns = {};
  for (const o of objects) {
    if (o.type === 'spawn') spawns[o.name] = o;
    if (o.rect) triggers.push(o);
    if (o.prop) {
      const s = addPixelforgeProp(scene, o.x, o.y, o.prop, { state: o.state });
      s.pixelforgeObject = o;
      props.push(s);
    } else if (o.sprite) {
      const s = addPixelforgeSprite(scene, o.x, o.y, o.sprite);
      s.pixelforgeObject = o;
      sprites.push(s);
    }
  }

  const arcade = scene.physics?.world;
  if (arcade) arcade.setBounds(0, 0, W, H, true, true, true, info.view !== 'side');   // side: you can fall out
  cam.setBounds(0, 0, W, H).setZoom(info.camera?.zoom ?? 1);
  let player = null;
  const playerName = opts.player ?? info.player;
  if (playerName && arcade) {
    const spawn = spawns[opts.spawn] ?? spawns.player ?? Object.values(spawns)[0] ?? { x: 0, y: 0 };
    player = addPixelforgePlayer(scene, spawn.x, spawn.y, playerName, { view: info.view, ...opts.playerOptions });
    for (const layer of Object.values(layers)) scene.physics.add.collider(player, layer);
    for (const p of props) if (p.body) scene.physics.add.collider(player, p);
    cam.startFollow(player, true);
    const inside = new Set();
    const tick = () => {
      if (!player.active) return;
      const b = player.body;
      for (const o of triggers) {
        const [x, y, w, h] = o.rect;
        const hit = b.x < x + w && x < b.x + b.width && b.y < y + h && y < b.y + b.height;
        if (hit && !inside.has(o)) {
          inside.add(o);
          scene.events.emit('pixelforge-trigger', o, player);
          player.emit('pixelforge-trigger', o);
        } else if (!hit) inside.delete(o);
      }
      if (info.view === 'side' && player.y > H + 64 && opts.respawn !== false) {
        scene.events.emit('pixelforge-fell', player);
        player.body.reset(spawn.x, spawn.y);   // moves the sprite too, and stops it
      }
    };
    scene.events.on('update', tick);
    scene.events.once('shutdown', () => scene.events.off('update', tick));
  }
  if (info.view !== 'side') keepPixelforgeDepth(scene, sprites);
  return { map, layers, player, objects, props, sprites, spawns, triggers, accents, info };
}

// A character standing in a level (an NPC or an enemy): an immovable Arcade sprite (a plain one without
// physics) with its body box, playing idle. Game code gives it behaviour.
export function addPixelforgeSprite(scene, x, y, name) {
  const pf = scene.cache.json.get(name)?.meta?.pixelforge;
  if (!pf) throw new Error(`pixelforge: '${name}' isn't loaded (loadPixelforge(this, '${name}') in preload)`);
  if (!Object.keys(pf.animations).every((k) => scene.anims.exists(k))) createPixelforgeAnims(scene, name);
  const s = scene.physics?.add ? scene.physics.add.sprite(x, y, name) : scene.add.sprite(x, y, name);
  if (s.body) {
    const b = pixelforgeBody(scene, name);
    s.body.setSize(b.width, b.height).setOffset(b.x, b.y);
    s.body.setAllowGravity(false);
    s.body.setImmovable(true);
  }
  const tags = Object.keys(pf.animations);
  const idle = [`${name}_idle`, `${name}_idle_down`].find((k) => tags.includes(k)) ?? tags[0];
  if (idle) s.play(idle);
  return s;
}

// Debug overlay: call every frame with a Graphics object, e.g. in update():
//   debug.clear(); drawPixelforgeBoxes(debug, [knight, ...enemies]);
// Body box yellow, hurtboxes green, hitboxes red.
export function drawPixelforgeBoxes(graphics, sprites) {
  for (const s of sprites) {
    const b = meta(s)?.meta?.pixelforge?.body;
    if (b) {
      const r = toWorld(s, [b.x, b.y, b.w, b.h]);
      graphics.lineStyle(1, 0xfac828, 0.9).strokePoints(r.points, true);
    }
    for (const r of pixelforgeBoxes(s, 'hurt')) graphics.lineStyle(1, 0x28c85a, 1).strokePoints(r.points, true);
    for (const r of pixelforgeBoxes(s, 'hit')) graphics.lineStyle(2, 0xf0283c, 1).strokePoints(r.points, true);
  }
}
