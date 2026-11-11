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
