// Run by tests/test_phaser_helper.py (needs Node). Checks rotation-aware boxes and overlap.
import { pixelforgeBoxes, rectsOverlap } from '../pixelforge/assets/phaser/pixelforge.js';
const data = { frames: { '0': { pixelforge: { hit: [[40, 30, 10, 4]], hurt: [[24, 24, 16, 16]] } } } };
const sprite = (o) => ({ scene: { cache: { json: { get: () => data } } }, texture: { key: 'k' },
  frame: { name: '0', realWidth: 64, realHeight: 64 }, originX: 0.5, originY: 0.5,
  flipX: false, flipY: false, scaleX: 1, scaleY: 1, rotation: 0, x: 100, y: 100, ...o });
const r2 = (p) => p.points.map((q) => [Math.round(q.x * 100) / 100, Math.round(q.y * 100) / 100]);
const check = (name, got, want) => { const ok = JSON.stringify(got) === JSON.stringify(want); console.log(ok ? 'ok  ' : 'FAIL', name, ok ? '' : JSON.stringify(got)); if (!ok) process.exitCode = 1; };

// unrotated: blade 8..18 px right of centre, -2..2 vertically
check('rotation 0', r2(pixelforgeBoxes(sprite({}), 'hit')[0]), [[108, 98], [118, 98], [118, 102], [108, 102]]);
// rotated 90deg (facing down): blade now 8..18 px *below* centre
const down = pixelforgeBoxes(sprite({ rotation: Math.PI / 2 }), 'hit')[0];
check('rotation 90 bounds', [down.x, down.y, down.width, down.height].map(Math.round), [98, 108, 4, 10]);
// scale 3 + rotation 180 (facing left): blade 24..54 px left of centre
const left = pixelforgeBoxes(sprite({ rotation: Math.PI, scaleX: 3, scaleY: 3 }), 'hit')[0];
check('scale 3, rotation 180', [left.x, left.y, left.width, left.height].map(Math.round), [46, 94, 30, 12]);

// SAT: two thin parallel 45deg blades whose bounding boxes overlap but which don't touch
const diag = (cx, cy) => { const a = Math.PI / 4, c = Math.cos(a), s = Math.sin(a);
  const pts = [[-10, -1], [10, -1], [10, 1], [-10, 1]].map(([x, y]) => ({ x: cx + x * c - y * s, y: cy + x * s + y * c }));
  const xs = pts.map((p) => p.x), ys = pts.map((p) => p.y);
  return { x: Math.min(...xs), y: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: Math.max(...ys) - Math.min(...ys), points: pts }; };
const A = diag(0, 0), B = diag(5, -5), C = diag(1, -1);
const aabbOnly = A.x < B.x + B.width && B.x < A.x + A.width && A.y < B.y + B.height && B.y < A.y + A.height;
check('parallel blades: bounding boxes overlap', aabbOnly, true);
check('parallel blades: SAT says no hit', rectsOverlap(A, B), false);
check('touching blades: SAT says hit', rectsOverlap(A, C), true);
// a sword pointing down hits a body below the attacker, not one to the right
const att = sprite({ rotation: Math.PI / 2 });
const below = pixelforgeBoxes(sprite({ y: 115 }), 'hurt')[0], right = pixelforgeBoxes(sprite({ x: 115 }), 'hurt')[0];
const hit = pixelforgeBoxes(att, 'hit')[0];
check('rotated sword hits body below', rectsOverlap(hit, below), true);
check('rotated sword misses body to the right', rectsOverlap(hit, right), false);

// tilesets: string rows through a legend, then properties + collision onto a (mock) Phaser layer
import { pixelforgeRows, applyPixelforgeTileProperties } from '../pixelforge/assets/phaser/pixelforge.js';
const tsData = { pixelforge: { names: ['grass', 'water', 'wall'], properties: [{}, { collides: true, liquid: true }, { collides: true }],
                               sample: [[0, 1]] } };
const scene = { cache: { json: { get: () => tsData } } };
check('rows from strings', pixelforgeRows(scene, 't', ['gw.', ' #g'], { g: 'grass', w: 'water', '#': 'wall' }), [[0, 1, -1], [-1, 2, 0]]);
check('rows default to the sample', pixelforgeRows(scene, 't'), [[0, 1]]);
let threw = false; try { pixelforgeRows(scene, 't', ['x'], {}); } catch { threw = true; }
check('unknown legend char throws', threw, true);
// a Tiled map where this tileset starts at gid 5
const tiles = [{ index: 5, properties: {} }, { index: 6, properties: {} }, { index: -1, properties: {} }];
let collided = null;
const layer = { scene, tileset: [{ image: { key: 't' }, firstgid: 5 }], forEachTile: (fn) => tiles.forEach(fn),
                setCollision: (ids) => { collided = ids; } };
check('collision indices honour firstgid', applyPixelforgeTileProperties(layer, 't'), [6, 7]);
check('setCollision called', collided, [6, 7]);
check('tile properties copied', tiles.map((t) => t.properties), [{ name: 'grass' }, { name: 'water', collides: true, liquid: true }, {}]);

// animated tiles: index swaps on the scene clock, all tiles of one animation in step
import { animatePixelforgeTiles } from '../pixelforge/assets/phaser/pixelforge.js';
const animData = { pixelforge: { names: ['grass', 'water'], properties: [{}, {}], animations: { '1': [[1, 100], [2, 100], [3, 50]] } } };
const listeners = {};
const events = { on: (e, f) => { listeners[e] = f; }, once: () => {}, off: (e) => { delete listeners[e]; } };
const water = [{ index: 1 }, { index: 1 }], grass = { index: 0 };
const aLayer = { scene: { events, cache: { json: { get: () => animData } } }, tileset: [{ image: { key: 'a' }, firstgid: 0 }],
                 forEachTile: (fn) => [grass, ...water].forEach(fn), once: () => {} };
const stop = animatePixelforgeTiles(aLayer, 'a');
const steps = [];
for (const dt of [50, 60, 100, 50, 40]) { listeners.update(0, dt); steps.push(water.map((t) => t.index).join('')); }
check('water frames over time (in step)', steps, ['11', '22', '33', '11', '11']);
check('static tiles untouched', grass.index, 0);
stop();
check('stop removes the listener', 'update' in listeners, false);

// stamps: a building's tiles, roof (`above`) on the layer drawn over the characters
import { stampPixelforgeTiles, addPixelforgeProp, pixelforgeDepth, addPixelforgePanel } from '../pixelforge/assets/phaser/pixelforge.js';
const kit = { pixelforge: { names: ['roof', 'wall', 'door'], properties: [{ above: true }, { collides: true }, {}],
                            stamps: { hut: [[0, 0], [1, 2], [-1, 1]] } } };
const kitScene = { cache: { json: { get: () => kit } } };
const mkLayer = (firstgid) => { const put = []; return { put, scene: kitScene, tileset: [{ image: { key: 'kit' }, firstgid }],
  putTileAt: (i, x, y) => { const t = { index: i, x, y, properties: {} }; put.push(t); return t; },
  forEachTile: (fn) => put.forEach(fn), setCollision: () => {} }; };
const ground = mkLayer(1), over = mkLayer(1);
stampPixelforgeTiles(ground, 'kit', 'hut', 10, 4, { above: over });
check('stamp: walls and door on the ground layer', ground.put.map((t) => [t.index, t.x, t.y]), [[2, 10, 5], [3, 11, 5], [2, 11, 6]]);
check('stamp: roof on the above layer', over.put.map((t) => [t.index, t.x, t.y]), [[1, 10, 4], [1, 11, 4]]);
let missing = false; try { stampPixelforgeTiles(ground, 'kit', 'castle', 0, 0); } catch { missing = true; }
check('unknown stamp throws', missing, true);

// props: static body from the footprint, scroll factor and depth from the layer
const propData = { meta: { pixelforge: { animations: { house_closed: {}, house_open: {} }, body: { x: 0, y: 40, w: 64, h: 40 },
  prop: { layer: 'world', scroll: 1, solid: true, ysort: true } } } };
const calls = [];
const fakeSprite = (x, y) => ({ x, y, body: { setSize(w, h, c) { calls.push(['size', w, h, c]); return this; },
  setOffset(ox, oy) { calls.push(['offset', ox, oy]); return this; } },
  play(k) { calls.push(['play', k]); return this; }, setScrollFactor(f) { calls.push(['scroll', f]); return this; },
  setDepth(d) { calls.push(['depth', d]); return this; } });
const propScene = { cache: { json: { get: () => propData } }, anims: { exists: () => true },
  physics: { add: { staticSprite: (x, y) => { calls.push(['static']); return fakeSprite(x, y); } } },
  add: { sprite: (x, y) => { calls.push(['plain']); return fakeSprite(x, y); } } };
addPixelforgeProp(propScene, 100, 120, 'house', { state: 'open' });
check('solid prop: static body sized to the footprint', calls, [['static'], ['play', 'house_open'], ['scroll', 1], ['depth', 120],
  ['size', 64, 40, false], ['offset', 0, 40]]);
calls.length = 0;
addPixelforgeProp(propScene, 0, 0, 'house', { physics: false });
check('physics: false makes a plain sprite', calls[0], ['plain']);
check('back props sort by distance', [pixelforgeDepth({ y: 5 }, { layer: 'back', scroll: 0.2 }), pixelforgeDepth({ y: 5 }, { layer: 'back', scroll: 0.6 })], [-9980, -9940]);
check('front props draw over everything', pixelforgeDepth({ y: 5 }, { layer: 'front', scroll: 1 }), 10000);
check('side-view world props keep depth 0', pixelforgeDepth({ y: 5 }, { layer: 'world', scroll: 1, ysort: false }), 0);

// nine-slice panels pass the insets through
const panelScene = { cache: { json: { get: () => ({ meta: { pixelforge: { nine: { panel: [3, 4, 5, 6] } } } }) } },
  add: { nineslice: (...a) => a } };
check('panel insets', addPixelforgePanel(panelScene, 1, 2, 'ui', 'panel', 80, 30), [1, 2, 'ui', 'panel', 80, 30, 3, 4, 5, 6]);

// ---- loadPixelforgeAll: the index first, then every asset by kind from its filecomplete ----------
import { loadPixelforgeAll, createPixelforgeAll, addPixelforgePlayer, pixelforgeView } from '../pixelforge/assets/phaser/pixelforge.js';
{
  const queued = [], handlers = {};
  const json = {};
  const loadScene = {
    cache: { json: { get: (k) => json[k] }, tilemap: { exists: () => false }, audio: { exists: () => false } },
    textures: { exists: (n) => n === 'already' },
    load: {
      on: (e, f) => { handlers[e] = f; }, off: (e) => { delete handlers[e]; },
      json: (k, url) => queued.push(['json', k, url]), image: (k, url) => queued.push(['image', k, url]),
      aseprite: (k, png, js) => queued.push(['aseprite', k, png, js]), bitmapFont: (k, png, xml) => queued.push(['font', k, png, xml]),
      tilemapTiledJSON: (k, url) => queued.push(['level', k, url]), audio: (k, url) => queued.push(['audio', k, url]),
    },
  };
  loadPixelforgeAll(loadScene, 'x/');
  check('loadPixelforgeAll queues the index first', queued, [['json', 'pixelforge-index', 'x/index.json']]);
  queued.length = 0;
  handlers.filecomplete('other', 'json', {});
  check('other files are ignored', queued, []);
  handlers.filecomplete('pixelforge-index', 'json', { sprites: ['hero', 'already'], props: ['chest'], tilesets: ['terrain'],
    icons: ['ui'], fonts: ['font'], levels: ['village'], sounds: ['coin'] });
  check('then every asset by kind', queued, [
    ['aseprite', 'hero', 'x/hero.png', 'x/hero.json'], ['aseprite', 'chest', 'x/chest.png', 'x/chest.json'],
    ['image', 'terrain', 'x/terrain.png'], ['json', 'terrain', 'x/terrain.json'],
    ['aseprite', 'ui', 'x/ui.png', 'x/ui.json'], ['font', 'font', 'x/font.png', 'x/font.xml'],
    ['level', 'village', 'x/levels/village.json'], ['audio', 'coin', 'x/sounds/coin.wav']]);
  check('the handler removes itself', 'filecomplete' in handlers, false);

  const created = [];
  json['pixelforge-index'] = { sprites: ['hero'], props: ['chest'] };
  json.hero = { meta: { pixelforge: { animations: { hero_idle: {} } } } };
  json.chest = { meta: { pixelforge: { animations: { chest_closed: {} } } } };
  const animScene = { cache: { json: { get: (k) => json[k] } },
    anims: { exists: (k) => k === 'chest_closed', createFromAseprite: (n) => { created.push(n); return []; } } };
  createPixelforgeAll(animScene);
  check('createPixelforgeAll makes the missing anims', created, ['hero']);
}

// ---- addPixelforgePlayer: a mock Arcade world, driven through controller.override ---------------
function playerWorld(name, animations, pf = {}) {
  const listeners = {};
  const scene = {
    events: { on: (e, f) => { listeners[e] = f; }, once: () => {}, off: (e) => { delete listeners[e]; } },
    cache: { json: { get: () => ({ meta: { pixelforge: { animations, body: { x: 24, y: 18, w: 16, h: 30 }, view: 'side', ...pf } } }) } },
    anims: { exists: () => true },
    physics: { world: { gravity: { y: 0 } }, add: { sprite: (x, y) => mockSprite(scene, x, y, name) } },
  };
  const tick = (t) => listeners.update(t, 16);
  return { scene, tick, listeners };
}
function mockSprite(scene, x, y, name) {
  const ev = {};
  const s = {
    scene, x, y, active: true, flipX: false, rotation: 0, depth: 0, emitted: [], texture: { key: name },
    anims: { currentAnim: null },
    play(k) { s.anims.currentAnim = { key: typeof k === 'string' ? k : k.key }; return s; },
    setFlipX(f) { s.flipX = f; return s; }, setDepth(d) { s.depth = d; return s; }, setRotation(r) { s.rotation = r; return s; },
    setCollideWorldBounds() { return s; },
    on(e, f) { ev[e] = f; return s; }, once() { return s; }, emit(e) { s.emitted.push(e); },
    body: { velocity: { x: 0, y: 0 }, blocked: { down: true }, touching: { down: false }, size: null, offset: null, circle: null, gravity: 0,
      setSize(w, h) { this.size = [w, h]; return this; }, setOffset(ox, oy) { this.offset = [ox, oy]; return this; },
      setCircle(r, ox, oy) { this.circle = [r, ox, oy]; return this; }, setAllowGravity() { return this; },
      setGravityY(g) { this.gravity = g; return this; },
      setVelocityX(v) { this.velocity.x = v; return this; }, setVelocityY(v) { this.velocity.y = v; return this; },
      setVelocity(vx, vy) { this.velocity.x = vx; this.velocity.y = vy; return this; } },
  };
  return s;
}
{
  const anims = { p_idle: {}, p_walk: {}, p_run: {}, p_jump_rise: {}, p_jump_fall: {}, p_jump_land: {} };
  const { scene, tick } = playerWorld('p', anims);
  const p = addPixelforgePlayer(scene, 50, 100, 'p');
  const c = p.controller, body = p.body;
  check('side: body box from the export', [body.size, body.offset], [[16, 30], [24, 18]]);
  check('side: gravity on the body (world has none)', body.gravity, 900);
  check('side: starts idle', p.anims.currentAnim.key, 'p_idle');
  tick(0);
  check('no keyboard, no override: no input', c.input, { left: false, right: false, up: false, down: false, jump: false, run: false, attack: false });
  c.override = { right: true };
  tick(16);
  check('override right: walks', [body.velocity.x, p.anims.currentAnim.key, c.facing], [70, 'p_walk', 'right']);
  c.override = { left: true, run: true };
  tick(32);
  check('override left+run: runs left, flipped', [body.velocity.x, p.anims.currentAnim.key, p.flipX], [-135, 'p_run', true]);
  c.override = { jump: true };
  tick(48);
  check('jump: up velocity and event', [body.velocity.y, p.emitted.includes('pixelforge-jump')], [-330, true]);
  body.blocked.down = false;
  tick(64);
  check('rising: jump_rise', p.anims.currentAnim.key, 'p_jump_rise');
  c.override = {};
  tick(80);
  check('released early: short hop', body.velocity.y, -110);
  body.velocity.y = 50;
  tick(96);
  check('falling: jump_fall', p.anims.currentAnim.key, 'p_jump_fall');
  body.blocked.down = true; body.velocity.y = 0;
  tick(112);
  check('landing: jump_land and event', [p.anims.currentAnim.key, p.emitted.includes('pixelforge-land')], ['p_jump_land', true]);
  c.override = { right: true };
  tick(128);
  check('moving cancels the landing pose', p.anims.currentAnim.key, 'p_walk');

  // coyote time: walked off a ledge 80ms ago -> still jumps; 200ms ago -> doesn't
  c.override = {};
  tick(1000);
  body.blocked.down = false;
  tick(1060);
  c.override = { jump: true };
  body.velocity.y = 0;
  tick(1080);
  check('coyote: a jump 80ms after leaving the ground counts', body.velocity.y, -330);
  c.override = {};
  body.blocked.down = true; tick(2000);
  body.blocked.down = false; tick(2016);
  body.velocity.y = 0;
  c.override = { jump: true }; tick(2200);
  check('coyote: 200ms after leaving the ground does not', body.velocity.y, 0);
  // jump buffer: pressed 60ms before landing -> jumps on landing (still held)
  c.override = {}; tick(2300);
  c.override = { jump: true }; tick(2340);
  body.blocked.down = true; tick(2400);
  check('buffer: a press 60ms before landing jumps on landing', body.velocity.y, -330);
  body.blocked.down = false; body.velocity.y = 0;
  c.override = {}; tick(3000);
  c.override = { jump: true }; tick(3040);
  check('in the air: a press does not jump', body.velocity.y, 0);
  body.blocked.down = true; tick(3300);
  check('buffer: a press 260ms before landing does not', body.velocity.y, 0);
}
{
  const anims = { t_idle_down: {}, t_walk_down: {}, t_idle_side: {}, t_walk_side: {}, t_idle_up: {}, t_walk_up: {},
                  t_attack_side: {}, t_attack_down: {} };
  const { scene, tick } = playerWorld('t', anims);
  check('topdown view inferred from walk_down', pixelforgeView(scene, 't'), 'topdown');
  const p = addPixelforgePlayer(scene, 50, 100, 't');
  check('topdown: feet-only body', [p.body.size, p.body.offset], [[12, 8], [26, 40]]);
  p.controller.override = { left: true };
  tick(0);
  check('topdown: walk left = side flipped', [p.anims.currentAnim.key, p.flipX, p.body.velocity.x], ['t_walk_side', true, -70]);
  p.y = 123; p.controller.override = { up: true }; tick(16);
  check('topdown: walk up, depth = y', [p.anims.currentAnim.key, p.depth], ['t_walk_up', 123]);
  p.controller.override = { down: true }; tick(32);
  p.controller.override = { attack: true }; tick(48);
  check('topdown: attack in the facing direction, standing still', [p.anims.currentAnim.key, p.body.velocity.y], ['t_attack_down', 0]);
}
{
  const { scene, tick } = playerWorld('o', { o_idle: {}, o_walk: {}, o_attack: {} }, { anchor: 'center', body: { x: 24, y: 24, w: 16, h: 16 } });
  check('overhead view from the centre anchor', pixelforgeView(scene, 'o'), 'overhead');
  const p = addPixelforgePlayer(scene, 0, 0, 'o');
  check('overhead: circle body', p.body.circle, [8, 24, 24]);
  p.controller.override = { down: true, right: true }; tick(0);
  check('overhead: diagonal at the same speed, rotated to face it',
    [Math.round(p.body.velocity.x), Math.round(p.body.velocity.y), Math.round(p.rotation * 1000) / 1000, p.anims.currentAnim.key],
    [49, 49, 0.785, 'o_walk']);
  check('state() for playtests', p.controller.state(), { x: 0, y: 0, vx: 49.5, vy: 49.5, onGround: true, facing: 45, anim: 'o_walk' });
}
