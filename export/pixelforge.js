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

const meta = (sprite) => sprite.scene.cache.json.get(sprite.texture.key);

// Frame-space [x, y, w, h] -> world-space {x, y, width, height}, honouring origin, scale and flips.
// Phaser mirrors a flipped sprite around its origin, so boxes are mirrored the same way.
function toWorld(sprite, [x, y, w, h]) {
  const fw = sprite.frame.realWidth, fh = sprite.frame.realHeight;
  const ox = sprite.originX * fw, oy = sprite.originY * fh;
  const lx = sprite.flipX ? ox - (x + w) : x - ox;
  const ly = sprite.flipY ? oy - (y + h) : y - oy;
  const sx = Math.abs(sprite.scaleX), sy = Math.abs(sprite.scaleY);
  return { x: sprite.x + lx * sx, y: sprite.y + ly * sy, width: w * sx, height: h * sy };
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

export function rectsOverlap(a, b) {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
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

// Debug overlay: call every frame with a Graphics object, e.g. in update():
//   debug.clear(); drawPixelforgeBoxes(debug, [knight, ...enemies]);
// Body box yellow, hurtboxes green, hitboxes red.
export function drawPixelforgeBoxes(graphics, sprites) {
  for (const s of sprites) {
    const b = meta(s)?.meta?.pixelforge?.body;
    if (b) {
      const r = toWorld(s, [b.x, b.y, b.w, b.h]);
      graphics.lineStyle(1, 0xfac828, 0.9).strokeRect(r.x, r.y, r.width, r.height);
    }
    for (const r of pixelforgeBoxes(s, 'hurt')) graphics.lineStyle(1, 0x28c85a, 1).strokeRect(r.x, r.y, r.width, r.height);
    for (const r of pixelforgeBoxes(s, 'hit')) graphics.lineStyle(2, 0xf0283c, 1).strokeRect(r.x, r.y, r.width, r.height);
  }
}
