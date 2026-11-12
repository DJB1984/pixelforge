// An enemy that walks back and forth: what a level's `"type": "enemy"` sprites become (see TYPES in
// scenes/Level.js). It turns at walls, at ledges (side view) and `range` tiles from where it started,
// hurts the player on touch, and takes `hp` hits from the player's attack. Its level object's "props"
// tune it: {"hp": 2, "speed": 30, "range": 3}.
//
// Make your own enemy the same way: a class taking (scene, sprite, level) with an update(time), and
// hit(from) if the player can hurt it. Add it to TYPES under its object type.
export class Walker {
  constructor(scene, sprite, level) {
    const props = sprite.pixelforgeObject?.props ?? {};
    this.scene = scene;
    this.sprite = sprite;
    this.level = level;
    this.hp = props.hp ?? 2;
    this.speed = props.speed ?? 30;
    this.range = (props.range ?? 3) * level.map.tileWidth;
    this.home = sprite.x;
    this.dir = 1;
    this.recoverAt = 0;
    const name = sprite.texture.key, has = (a) => scene.anims.exists(`${name}_${a}`);
    this.side = level.info.view === 'side';
    this.walk = ['walk', 'walk_side', 'idle'].find(has);
    this.walk &&= `${name}_${this.walk}`;
    sprite.body.setImmovable(false);   // knockback moves it; it's still never pushed by the player (no collider)
  }

  // A tile that blocks at a world point, on any layer.
  solidAt(x, y) {
    return Object.values(this.level.layers).some((l) => l.getTileAtWorldXY(x, y)?.collides);
  }

  update(time) {
    const s = this.sprite, b = s.body;
    if (!s.active || time < this.recoverAt) return;
    const front = s.x + this.dir * (b.width / 2 + 1);
    const wall = this.solidAt(front, b.bottom - 4);
    const ledge = this.side && !this.solidAt(front, b.bottom + 1);
    const far = (s.x - this.home) * this.dir >= this.range;
    if (wall || ledge || far) this.dir = -this.dir;
    b.setVelocity(this.dir * this.speed, 0);
    s.setFlipX(this.dir < 0);
    if (this.walk) s.play(this.walk, true);
  }

  // Struck by the player's attack (`from` is the player).
  hit(from) {
    const s = this.sprite;
    this.hp -= 1;
    this.recoverAt = this.scene.time.now + 250;
    this.scene.feel.flash(s).knockback(s, from, 120);   // the level scene's pixelforgeFeel
    if (this.hp <= 0) {
      s.body.enable = false;
      this.scene.tweens.add({ targets: s, alpha: 0, duration: 200, onComplete: () => s.destroy() });
    }
  }
}
