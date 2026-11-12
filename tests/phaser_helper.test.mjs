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
  handlers.filecomplete('pixelforge-index', 'json', { sprites: ['hero', 'already'], props: ['chest'], fx: ['fx_hit'],
    tilesets: ['terrain'], icons: ['ui'], fonts: ['font'], levels: ['village'] });
  check('then every asset by kind', queued, [
    ['aseprite', 'hero', 'x/hero.png', 'x/hero.json'], ['aseprite', 'chest', 'x/chest.png', 'x/chest.json'],
    ['aseprite', 'fx_hit', 'x/fx_hit.png', 'x/fx_hit.json'],
    ['image', 'terrain', 'x/terrain.png'], ['json', 'terrain', 'x/terrain.json'],
    ['aseprite', 'ui', 'x/ui.png', 'x/ui.json'], ['font', 'font', 'x/font.png', 'x/font.xml'],
    ['level', 'village', 'x/levels/village.json']]);
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

// ---- pixelforgeLevel: a mock map, scene and Arcade world ----------------------------------------
import { pixelforgeLevel } from '../pixelforge/assets/phaser/pixelforge.js';
{
  const info = { name: 'v', view: 'side', size: [64, 32], tilesets: ['t'], background: { color: '#123456' },
    accents: [{ prop: 'cloud', at: [5, 6] }], player: 'hero', camera: { zoom: 2 },
    layers: [{ name: 'ground', above: false }, { name: 'roof', above: true }],
    objects: [{ id: 1, name: 'player', type: 'spawn', x: 10, y: 20 }, { id: 2, name: 'chest', type: 'chest', prop: 'chest', state: 'open', x: 40, y: 32 },
              { id: 3, name: 'door', type: 'door', to: 'inn', x: 52, y: 32, rect: [48, 16, 16, 16] }] };
  const json = {
    t: { tilewidth: 16, tileheight: 16, margin: 0, spacing: 1, pixelforge: { names: ['g'], properties: [{}], animations: {} } },
    hero: { meta: { pixelforge: { animations: { hero_idle: {} }, body: { x: 0, y: 0, w: 8, h: 8 }, view: 'side' } } },
    chest: { meta: { pixelforge: { animations: { chest_closed: {}, chest_open: {} }, body: { x: 0, y: 8, w: 16, h: 8 },
                                   prop: { layer: 'world', scroll: 1, solid: true, ysort: false } } } },
    cloud: { meta: { pixelforge: { animations: { cloud_idle: {} }, body: { x: 0, y: 0, w: 4, h: 4 },
                                   prop: { layer: 'back', scroll: 0.3, solid: false, ysort: false } } } },
  };
  const log = [], listeners = {}, emitted = [];
  const chain = (o) => new Proxy(o, { get: (t, k) => (k in t ? t[k] : () => chain(t)) });   // any other method: chainable no-op
  const mkSprite = (x, y, key, kind) => { const s = mockSprite(scene, x, y, key); s.kind = kind; log.push([kind, key, x, y]);
    s.setScrollFactor = () => s; s.body.reset = (nx, ny) => { s.x = nx; s.y = ny; }; return s; };
  const layer = (name) => chain({ name, scene, depth: 0, tileset: [{ image: { key: 't' }, firstgid: 1 }], forEachTile: () => {},
    setDepth(d) { this.depth = d; log.push(['depth', name, d]); return this; } });
  const cam = chain({ setBackgroundColor(c) { log.push(['bg', c]); return cam; }, setZoom(z) { log.push(['zoom', z]); return cam; },
    startFollow(t) { log.push(['follow', t.texture.key]); return cam; } });
  const scene = {
    cache: { json: { get: (k) => json[k] }, tilemap: { get: () => ({ data: { pixelforge: info } }) } },
    make: { tilemap: () => ({ scene, addTilesetImage: (n) => ({ name: n }), createLayer: (n) => layer(n) }) },
    cameras: { main: cam }, anims: { exists: () => true },
    events: { on: (e, f) => { (listeners[e] ??= []).push(f); }, once: () => {}, off: () => {}, emit: (...a) => emitted.push(a) },
    add: { sprite: (x, y, k) => mkSprite(x, y, k, 'plain'), graphics: () => chain({}) },
    physics: { world: { gravity: { y: 0 }, setBounds: (...a) => log.push(['bounds', ...a]) },
               add: { sprite: (x, y, k) => mkSprite(x, y, k, 'dynamic'), staticSprite: (x, y, k) => mkSprite(x, y, k, 'static'),
                      collider: (a, b) => log.push(['collider', a.texture?.key ?? a.name, b.texture?.key ?? b.name]) } },
  };
  const level = pixelforgeLevel(scene, 'v');
  check('level: background color', log.find((l) => l[0] === 'bg'), ['bg', '#123456']);
  check('level: accents and props placed', log.filter((l) => ['plain', 'static', 'dynamic'].includes(l[0])),
        [['plain', 'cloud', 5, 6], ['static', 'chest', 40, 32], ['dynamic', 'hero', 10, 20]]);
  check('level: ground under everything, roof over the characters', log.filter((l) => l[0] === 'depth'),
        [['depth', 'ground', -5000], ['depth', 'roof', 100000]]);
  check('level: side view can fall out of the bottom', log.find((l) => l[0] === 'bounds'), ['bounds', 0, 0, 64, 32, true, true, true, false]);
  check('level: player collides with each layer and the solid prop', log.filter((l) => l[0] === 'collider'),
        [['collider', 'hero', 'ground'], ['collider', 'hero', 'roof'], ['collider', 'hero', 'chest']]);
  check('level: camera zoom and follow', log.filter((l) => l[0] === 'zoom' || l[0] === 'follow'), [['zoom', 2], ['follow', 'hero']]);
  check('level: chest plays its state', level.props[0].anims.currentAnim.key, 'chest_open');
  check('level: spawns and triggers', [Object.keys(level.spawns), level.triggers.map((o) => o.name)], [['player'], ['door']]);
  const p = level.player, tickLevel = () => listeners.update.forEach((f) => f(0, 16));
  Object.assign(p.body, { x: 10, y: 10, width: 8, height: 8 });
  tickLevel();
  check('level: no trigger outside the door', emitted.length, 0);
  Object.assign(p.body, { x: 50, y: 20 });
  tickLevel(); tickLevel();
  check('level: walking into the door triggers once', emitted.map((e) => [e[0], e[1].name]), [['pixelforge-trigger', 'door']]);
  Object.assign(p.body, { x: 10, y: 10 }); tickLevel(); Object.assign(p.body, { x: 50, y: 20 }); tickLevel();
  check('level: leaving and coming back triggers again', emitted.length, 2);
  emitted.length = 0; p.y = 200; Object.assign(p.body, { x: 0, y: 0 }); tickLevel();
  check('level: falling out respawns at the spawn', [emitted.map((e) => e[0]), p.x, p.y], [['pixelforge-fell'], 10, 20]);
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

// ---- the HUD: its own scene, items from the index, set() before and after it starts ----------------
import { addPixelforgeHud, PIXELFORGE_HUD } from '../pixelforge/assets/phaser/pixelforge.js';
{
  const made = [];
  const obj = (kind, x, y, extra = {}) => {
    const o = { kind, x, y, visible: true, origin: null, tint: null, ...extra,
                setOrigin(a, b) { this.origin = [a, b]; return this; }, setVisible(v) { this.visible = v; return this; },
                setTint(t) { this.tint = t; return this; }, setText(t) { this.text = t; return this; } };
    made.push(o);
    return o;
  };
  const hudScene = {
    textures: { getFrame: () => ({ width: 16 }) },
    cache: { json: { get: (k) => (k === 'ui' ? { meta: { pixelforge: { nine: { panel: [2, 2, 2, 2] } } } } : null) } },
    add: { image: (x, y, s, f) => obj('image', x, y, { frame: f }), bitmapText: (x, y, f, t) => obj('text', x, y, { text: t }),
           nineslice: (x, y, s, f, w, h) => obj('panel', x, y, { w, h }) },
  };
  const scenes = {};
  const calls = [];
  const plugin = {
    get: (k) => scenes[k] ?? null,
    add: (k, config, start, data) => { calls.push(['add', k, start]); scenes[k] = config; config.create.call(hudScene, data); },
    launch: (k, data) => { calls.push(['launch', k]); scenes[k].create.call(hudScene, data); },
    bringToTop: (k) => calls.push(['top', k]),
  };
  const index = { hud: [{ id: 'hearts', icon: 'ui:heart', at: [4, 4], repeat: 3, step: 10 },
                        { id: 'gold', text: 'font:GOLD 1', at: [4, 18], tint: '#ff0000' },
                        { panel: 'ui:panel', at: [0, 140], size: [320, 40] }] };
  const game = { scene: plugin, cache: { json: { get: (k) => (k === 'pixelforge-index' ? index : null) } } };
  const hud = addPixelforgeHud(game);
  check('hud: its own scene, on top', calls, [['add', PIXELFORGE_HUD, true], ['top', PIXELFORGE_HUD]]);
  check('hud: hearts repeat by step, top-left origin', made.filter((o) => o.kind === 'image').map((o) => [o.x, o.y, o.origin]),
    [[4, 4, [0, 0]], [14, 4, [0, 0]], [24, 4, [0, 0]]]);
  check('hud: tinted text, stretched panel', [made[3].tint, made[4].w, made[4].h, made[4].origin], [0xff0000, 320, 40, [0, 0]]);
  hud.set('hearts', 1); hud.set('gold', 'GOLD 9');
  check('hud: set() shows n icons and changes text', [hud.items.hearts.map((o) => o.visible), hud.items.gold.text],
    [[true, false, false], 'GOLD 9']);
  made.length = 0;
  const again = addPixelforgeHud(game, [{ id: 'hp', icon: 'ui:heart', repeat: 2 }]);
  check('hud: calling it again relaunches the scene', calls.slice(-2), [['launch', PIXELFORGE_HUD], ['top', PIXELFORGE_HUD]]);
  check('hud: default step is the icon width + 2', made.map((o) => o.x), [0, 18]);
  again.set('hp', 0);
  check('hud: set(0) hides them all', again.items.hp.map((o) => o.visible), [false, false]);
}

// ---- controller.stun: physics owns the body for a while (knockback) ---------------------------------
{
  const { scene, tick } = playerWorld('k', { k_idle: {}, k_walk: {} });
  scene.time = { now: 100 };
  const p = addPixelforgePlayer(scene, 50, 100, 'k');
  p.controller.override = { right: true };
  tick(100);
  p.controller.stun(200);
  p.body.setVelocity(-140, -160);
  tick(200);
  check('stun: velocity left alone while stunned', [p.body.velocity.x, p.body.velocity.y], [-140, -160]);
  tick(301);
  check('stun: input drives it again after', p.body.velocity.x, 70);
}

// ---- installPixelforgePlay: window.pixelforgePlay over a mock game ----------------------------------
import { installPixelforgePlay } from '../pixelforge/assets/phaser/pixelforge.js';
{
  const tm = {};
  const calls = [], frames = [];
  const handlers = {};
  const player = { x: 0, on: (e, f) => { handlers[e] = f; },
                   controller: { override: null, state: () => ({ x: player.x, anim: 'p_walk' }) } };
  const game = {
    loop: { now: 1000, sleep: () => calls.push('sleep'), wake: () => calls.push('wake') },
    scene: { scenes: [{ sys: { tweens: tm } }] },
    step: (t, d) => {
      frames.push([Math.round(t), Math.round(d * 100) / 100, Math.round((tm.getDelta?.() ?? 0) * 100) / 100]);
      if (player.controller.override?.right) player.x += 1;
    },
  };
  const sceneEvents = { list: {}, on(e, f) { this.list[e] = f; }, once() {}, off(e) { delete this.list[e]; } };
  const scene = { game, time: { now: 0 }, events: sceneEvents };
  const play = installPixelforgePlay(scene, { name: 'meadow', player }, { extra: () => ({ health: 3 }) });
  check('play: on window', globalThis.pixelforgePlay === play, true);
  check('play: ready resolves to it', (await play.ready) === play, true);
  const s = play.step(100, { right: true });
  check('play: step freezes the loop, then whole 60fps frames', [calls, frames.length, frames[0].slice(0, 2)],
    [['sleep'], 6, [1017, 16.67]]);
  check('play: tweens advance one frame per step while frozen', frames[0][2], 16.67);
  check('play: input held as the override', [player.controller.override, s.x], [{ right: true }, 6]);
  check('play: state = level + controller + extra', [s.level, s.anim, s.health], ['meadow', 'p_walk', 3]);
  handlers['pixelforge-jump']();
  handlers['pixelforge-trigger']({ name: 'door', type: 'door', to: 'village' });
  sceneEvents.list['pixelforge-fell']();
  check('play: events since the last state()', play.state().events.map((e) => [e.type, e.to ?? null]),
    [['jump', null], ['trigger', 'village'], ['fell', null]]);
  check('play: then empty', play.state().events, []);
  play.release();
  check('play: release hands back the keyboard and the loop', [player.controller.override, calls.at(-1), 'getDelta' in tm],
    [null, 'wake', false]);
  const player2 = { x: 50, on: () => {}, controller: { override: null, state: () => ({ x: 50 }) } };
  const again = installPixelforgePlay(scene, { name: 'village', player: player2 });
  const st = again.state();
  check('play: a restart re-attaches the same hook', [again === play, st.level, st.x], [true, 'village', 50]);
}

// ---- effects: spawnPixelforgeFx, and the side controller's landing dust ------------------------------
import { spawnPixelforgeFx, pixelforgeFeel, pixelforgePages, buildPixelforgeDialog, pixelforgeDialog,
         PIXELFORGE_DIALOG } from '../pixelforge/assets/phaser/pixelforge.js';
const fxSprite = (x, y, k) => {
  const s = { x, y, k, ev: {}, destroyed: false, setFlipX(f) { s.flipX = f; return s; }, setRotation(r) { s.rot = r; return s; },
    setDepth(d) { s.depth = d; return s; }, once(e, f) { s.ev[e] = f; return s; }, play(c) { s.played = c; return s; },
    destroy() { s.destroyed = true; } };
  return s;
};
{
  const fxScene = { cache: { json: { get: () => ({ meta: { pixelforge: { kind: 'fx', animations: { spark_hit: {}, spark_big: {} },
    fx: { layer: 'front' } } } }) } }, anims: { exists: () => true }, add: { sprite: fxSprite } };
  const s = spawnPixelforgeFx(fxScene, 10, 20, 'spark', undefined, { flipX: true });
  check('fx: plays its first animation once, over everything', [s.played, s.depth, s.flipX], [{ key: 'spark_hit', repeat: 0 }, 10001, true]);
  s.ev.animationcomplete();
  check('fx: destroys itself when it ends', s.destroyed, true);
  check('fx: a named animation', spawnPixelforgeFx(fxScene, 0, 0, 'spark', 'big').played.key, 'spark_big');
  let threw = false; try { spawnPixelforgeFx(fxScene, 0, 0, 'spark', 'nope'); } catch { threw = true; }
  check('fx: an unknown animation throws', threw, true);
}
{
  const { scene, tick } = playerWorld('d', { d_idle: {}, d_jump_land: {} });
  const base = scene.cache.json.get;
  scene.cache.json.get = (k) => (k === 'fx_dust' ? { meta: { pixelforge: { kind: 'fx', animations: { fx_dust_land: {} } } } } : base(k));
  const dust = [];
  scene.add = { sprite: (x, y, k) => { const s = fxSprite(x, y, k); dust.push(s); return s; } };
  const p = addPixelforgePlayer(scene, 40, 100, 'd');
  p.body.blocked.down = false; tick(100);
  check('side: no dust in the air', dust.length, 0);
  p.body.blocked.down = true; tick(116);
  check('side: lands in a puff of fx_dust at the feet', dust.map((d) => [d.k, d.x, d.y, d.played.key]), [['fx_dust', 40, 100, 'fx_dust_land']]);
  scene.pixelforgeStopped = true;
  p.controller.override = { right: true };
  tick(132);
  check('a hit stop holds the controller', p.body.velocity.x, 0);
}

// ---- pixelforgeFeel: shake, hit stop, flash, knockback ------------------------------------------------
{
  const timers = [], shakes = [];
  const world = { paused: false, gravity: { y: 0 }, pause() { this.paused = true; }, resume() { this.paused = false; } };
  const actor = (playing) => ({ active: true, anims: { isPlaying: playing, paused: false, pause() { this.paused = true; }, resume() { this.paused = false; } } });
  const a = actor(true), b = actor(false);
  const scene = { events: { once() {} }, physics: { world }, children: { list: [a, b] },
    cameras: { main: { width: 320, height: 180, shake: (...args) => shakes.push(args) } },
    time: { delayedCall: (ms, f) => { const tm = { ms, f, removed: false, remove() { this.removed = true; } }; timers.push(tm); return tm; } } };
  const feel = pixelforgeFeel(scene);
  check('feel: chains', feel.shake(100, 2), feel);
  check('feel: shake measured in game pixels', shakes[0], [100, { x: 2 / 320, y: 2 / 180 }, true]);
  feel.hitStop(60);
  check('feel: hit stop pauses physics and the playing animations', [world.paused, a.anims.paused, b.anims.paused, scene.pixelforgeStopped],
    [true, true, false, true]);
  feel.hitStop(80);
  check('feel: a second hit stop extends the first', [timers[0].removed, timers[1].ms], [true, 80]);
  timers[1].f();
  check('feel: then everything resumes', [world.paused, a.anims.paused, scene.pixelforgeStopped], [false, false, false]);
  const spr = { active: true, tint: null, setTintFill(c) { this.tint = c; return this; }, clearTint() { this.tint = null; return this; } };
  feel.flash(spr, 80);
  check('feel: flash paints it white', [spr.tint, timers.at(-1).ms], [0xffffff, 80]);
  timers.at(-1).f();
  check('feel: then clears', spr.tint, null);
  const body = (g) => ({ allowGravity: g, gravity: { y: g ? 900 : 0 }, velocity: {}, setVelocity(x, y) { this.velocity = { x, y }; return this; } });
  const hero = { x: 100, y: 50, body: body(true), controller: { stun(ms) { this.stunned = ms; } } };
  feel.knockback(hero, { x: 120, y: 50 }, 140, { lift: 160 });
  check('feel: side-view knockback goes sideways and up, and stuns the controller', [hero.body.velocity, hero.controller.stunned],
    [{ x: -140, y: -160 }, 200]);
  const slime = { x: 103, y: 54, body: body(false) };
  feel.knockback(slime, { x: 100, y: 50 }, 100);
  check('feel: top-down knockback goes straight away', slime.body.velocity, { x: 60, y: 80 });
}

// ---- pixelforgeDialog: pages, typewriter, the action key ----------------------------------------------
{
  check('dialog pages: wrapped rows, `lines` per page, each string starts a page',
    pixelforgePages(['a b c', 'd'], 2, (s) => s.split(' ').join('\n')), ['a\nb', 'c', 'd']);
  check('dialog pages: nothing is one empty page', pixelforgePages(undefined, 3), ['']);

  const made = [], emitted = [], stopped = [];
  const obj = (kind, extra = {}) => { const o = { kind, destroyed: false, visible: true, setOrigin() { return o; }, destroy() { o.destroyed = true; },
    setVisible(v) { o.visible = v; return o; }, setPosition(x, y) { o.pos = [x, y]; return o; }, ...extra }; made.push(o); return o; };
  const scene = {
    scale: { width: 320, height: 180 },
    cache: { bitmapFont: { get: () => ({ data: { lineHeight: 10 } }) }, json: { get: () => ({ meta: { pixelforge: { nine: { panel: [4, 4, 4, 5] } } } }) } },
    add: {
      nineslice: (x, y, sheet, icon, w, h) => obj('panel', { box: [x, y, w, h] }),
      bitmapText: (x, y, font) => obj('text', { at: [x, y], font, text: '', setTint(c) { this.tint = c; return this; },
        setMaxWidth() { return this; }, setText(s) { this.text = s; return this; }, getTextBounds() { return { wrappedText: this.text }; } }),
      graphics: () => obj('more', { fillStyle() { return this; }, fillTriangle() { return this; } }),
    },
    scene: { stop: () => stopped.push('stop') },
  };
  let resumed = false;
  const owner = { events: { emit: (e) => emitted.push(e) }, scene: { isPaused: () => true, resume: () => { resumed = true; } } };
  const ctl = { cur: {}, prev: null, readInput() { return { attack: false, jump: false, ...this.cur }; } };
  let result = null;
  const o = { panel: 'ui:panel', font: 'font', tint: '#181425', speed: 40, lines: 3, margin: 4, padding: 6, position: 'bottom',
              text: ['Hello there', 'Bye'], name: 'sign', player: { controller: ctl } };
  const d = buildPixelforgeDialog(scene, { o, resolve: (v) => { result = v; }, owner });
  const [panel, label] = made;
  check('dialog: a box along the bottom, 3 lines tall', panel.box, [4, 134, 312, 42]);
  check('dialog: dark ink inside the padding', [label.at, label.tint], [[10, 140], 0x181425]);
  check('dialog: opening is announced', emitted, ['pixelforge-dialog']);
  d.update(100);
  check('dialog: types 40 characters a second', label.text, 'Hell');
  const press = () => { ctl.cur = { attack: true }; d.update(16); ctl.cur = {}; d.update(16); };
  press();
  check('dialog: the action key shows the whole page', label.text, 'Hello there');
  check('dialog: the more-arrow blinks on', made[2].visible, true);
  press();
  check('dialog: then turns the page', [d.page, label.text], [1, '']);
  ctl.cur = { jump: true }; d.update(1000); ctl.cur = {}; d.update(16);
  check('dialog: jump works too (finishes the page)', label.text, 'Bye');
  check('dialog: no arrow on the last page', made[2].visible, false);
  ctl.cur = { attack: true }; d.update(16);
  check('dialog: closes on the last press, resumes the level, resolves true',
    [result, resumed, stopped, emitted.at(-1), made.every((m) => m.destroyed)], [true, true, ['stop'], 'pixelforge-dialog-close', true]);
  check('dialog: the closing press is remembered, so it does not also attack', ctl.prev.attack, true);

  const calls = [];
  const levelScene = { scene: { key: 'level', get: () => null, add: (k, cfg, start, data) => calls.push(['add', k, start, data.o.speed]),
    bringToTop: (k) => calls.push(['top', k]), pause: () => calls.push(['pause']) } };
  const promise = pixelforgeDialog(levelScene, { text: 'Hi', speed: 0 });
  check('dialog: its own scene on top, and the level waits', calls, [['add', PIXELFORGE_DIALOG, true, 0], ['top', PIXELFORGE_DIALOG], ['pause']]);
  check('dialog: returns a promise', typeof promise.then, 'function');
}
