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
