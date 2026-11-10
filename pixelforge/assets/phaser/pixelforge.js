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
