import Phaser from 'phaser';
import { pixelforgeLevel, enablePixelforgeHits, drawPixelforgeBoxes, installPixelforgePlay, pixelforgeFeel, pixelforgeDialog,
         spawnPixelforgeFx } from '../../export/pixelforge.js';
import { state, bus, damage, addCoins, addItem, reset } from '../game.js';
import { showHud } from './Hud.js';
import { Walker } from '../objects/Walker.js';

// Object type (a level object's "type") → the class that gives it behaviour. Add yours here.
const TYPES = { enemy: Walker };

// One scene plays every level: pixelforgeLevel builds it from export/levels/<name>.json (map, props,
// sprites, the player at the spawn, the camera), and this scene adds the rules:
//   doors ("type": "door", "to": a level, "spawn": where to arrive) restart it in the next level;
//   items ("type": "item" or "coin") are picked up on touch: props.loot "coin" (or a coin) adds coins,
//     any other loot (or the item's name) goes into the inventory;
//   chests ("type": "chest") open on touch and give their props.loot;
//   anything with props.text (a sign, an NPC, a trigger zone) opens a dialog box on touch, once per visit;
//   TYPES: sprites with those types get a behaviour object (enemies hurt on touch, die to attacks).
// Hits land with this.feel (pixelforgeFeel): a hit stop, a small shake, a flash, knockback, and the
// 'fx_hit' effect when the art has one.
// Dev only: B toggles the hit/hurt boxes, and window.pixelforgePlay drives the game for `pixelforge play`.
export class Level extends Phaser.Scene {
  constructor() { super('level'); }

  init(data) {
    this.levelName = data.level;
    this.spawnName = data.spawn;
  }

  create() {
    const level = (this.level = pixelforgeLevel(this, this.levelName, { spawn: this.spawnName }));
    const player = level.player;
    this.feel = pixelforgeFeel(this);
    this.hud = showHud(this);
    this.actors = [];
    for (const s of level.sprites) {
      const Type = TYPES[s.pixelforgeObject?.type];
      if (Type) this.actors.push((s.actor = new Type(this, s, level)));
    }
    this.pickups = level.props.filter((p) => ['item', 'coin'].includes(p.pixelforgeObject?.type));
    for (const p of this.pickups) if (p.body) p.body.enable = false;   // walk through them, don't bump into them
    this.chests = level.props.filter((p) => p.pixelforgeObject?.type === 'chest');
    this.talkers = [...level.props, ...level.sprites].filter((s) => s.pixelforgeObject?.props?.text);

    const on = (emitter, event, fn) => { emitter.on(event, fn); this.events.once('shutdown', () => emitter.off(event, fn)); };
    on(this.events, 'pixelforge-trigger', (obj) => this.trigger(obj));
    on(bus, 'dead', () => this.time.delayedCall(400, () => { reset(); this.scene.restart({ level: this.levelName, spawn: this.spawnName }); }));

    if (player) {
      const hittable = () => this.actors.filter((a) => a.hit && a.sprite.active).map((a) => a.sprite);
      enablePixelforgeHits(this, player, hittable, (target) => {
        this.feel.hitStop(50).shake(80, 1);
        if (this.textures.exists('fx_hit')) spawnPixelforgeFx(this, (player.x + target.x) / 2, target.body.center.y, 'fx_hit');
        target.actor.hit(player);
      });
      this.physics.add.overlap(player, this.actors.map((a) => a.sprite), (_, enemy) => {
        if (enemy.body.enable) this.hurt(enemy);
      });
    }

    if (import.meta.env.DEV) {
      installPixelforgePlay(this, level, { extra: () => ({ health: state.health, coins: state.coins, inventory: [...state.inventory] }) });
      this.debug = this.add.graphics().setDepth(2e5);
      this.input.keyboard.on('keydown-B', () => { this.showBoxes = !this.showBoxes; });
    }
  }

  update(time) {
    for (const a of this.actors) a.update?.(time);
    const p = this.level.player;
    if (p?.active) {
      const body = new Phaser.Geom.Rectangle(p.body.x, p.body.y, p.body.width, p.body.height);
      for (const item of this.pickups) {
        if (item.active && Phaser.Geom.Intersects.RectangleToRectangle(body, item.getBounds())) this.collect(item);
      }
      Phaser.Geom.Rectangle.Inflate(body, 2, 2);   // chests are solid: touching is enough
      for (const chest of this.chests) {
        if (!chest.opened && Phaser.Geom.Intersects.RectangleToRectangle(body, chest.getBounds())) this.open(chest);
      }
      for (const s of this.talkers) {   // walking up to a sign reads it; step away and back to read it again
        const near = s.active && Phaser.Geom.Intersects.RectangleToRectangle(body, s.getBounds());
        if (near && !s.read) this.say(s.pixelforgeObject);
        s.read = near;
      }
    }
    if (this.debug) {
      this.debug.clear();
      if (this.showBoxes && p) drawPixelforgeBoxes(this.debug, [p, ...this.level.sprites.filter((s) => s.active)]);
    }
  }

  trigger(obj) {
    if (obj.props?.text) this.say(obj);
    if (obj.type === 'door' && obj.to) {
      if (!this.cache.tilemap.exists(obj.to)) return console.warn(`door to '${obj.to}': no such level in export/`);
      this.time.delayedCall(0, () => this.scene.restart({ level: obj.to, spawn: obj.spawn }));
    }
  }

  give(loot) {
    if (!loot) return;
    if (loot === 'coin' || loot === 'coins') addCoins(1);
    else addItem(loot);
  }

  collect(item) {
    const o = item.pixelforgeObject;
    this.give(o.type === 'coin' ? 'coin' : o.props?.loot ?? o.name ?? o.prop);
    item.destroy();
  }

  open(chest) {
    chest.opened = true;
    const o = chest.pixelforgeObject, prop = o.prop;
    const anim = [`${prop}_opening`, `${prop}_open`].find((k) => this.anims.exists(k));
    if (anim) chest.play(anim);
    this.give(o.props?.loot);
  }

  // A dialog box with the object's props.text (a string, or a list of pages). The level waits while it's open.
  say(obj) {
    return pixelforgeDialog(this, { text: obj.props.text, name: obj.name, player: this.level.player });
  }

  // Touched by an enemy: lose a heart, get knocked away, blink for a second.
  hurt(enemy) {
    const p = this.level.player;
    if (this.time.now < (this.invulnerableUntil ?? 0) || state.health <= 0) return;
    this.invulnerableUntil = this.time.now + 1000;
    damage(1);
    this.feel.knockback(p, enemy, 140, { lift: 160 }).shake(120, 2);
    this.tweens.add({ targets: p, alpha: 0.3, duration: 100, yoyo: true, repeat: 4, onComplete: () => p.setAlpha(1) });
  }
}
