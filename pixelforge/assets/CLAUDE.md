# Sprites for this game (pixelforge)

This folder is a pixelforge project (`pixelforge.json` marks its root). Sprites are plain-text grids that you write and edit directly. The `pixelforge` command (also `python -m pixelforge`; run it anywhere inside this folder) renders them to PNGs you can **look at with the Read tool**, lints them, and exports Phaser-ready sprite sheets. Never claim art looks good without rendering it and viewing the PNG.

## Data layout
```
palettes/game.json            shared named colors (Endesga 32). Prefer these names.
sprites/<name>/sprite.json    size, origin, palette, animations
sprites/<name>/frames/*.txt   one frame or layer per file: H lines of W chars
export/<name>.png|.json       generated: Phaser load.aseprite format, or a Tiled tileset for tilesets (+ index.json, pixelforge.js)
export/gallery.html           generated: shareable page of every sprite (`pixelforge gallery`)
previews/                     generated: renders, sheets, GIFs (gitignored)
```
- **Grid chars** are palette keys. `.` = transparent. Use mnemonic keys (`k` outline, `s`/`S` skin light/shadow, `m`/`d` mid/dark metal...). A palette value is `#rrggbb[aa]` or a name from `game.json`.
- **origin** `[x, y]` is in pixel-*edge* coordinates: `[16, 32]` = bottom-centre of a 32x32 frame. Feet stand on row `y-1`. Exported as the Phaser pivot.
- **Animation frames** are a frame id string, or an object built from other frames, so near-duplicate frames never need copy-pasting:
  ```json
  {"from": "body", "layers": ["legs_pass_a", "sword"], "flip": "h", "offset": [0, -1],
   "replace": {"k": "w"}, "duration": 120}
  ```
  Applied in order: `from` (base, may itself be an object) → `layers` painted bottom-to-top → `flip` → `offset` → `roll` (offset that wraps around the edges) → `replace` (palette swap, e.g. white hit flash). `duration` (ms) overrides `1000/fps`.
- `loop: false` animations play once.

## Size classes: canvas vs body box
Every character uses a standard **class** from `pixelforge.json` (`"class": "humanoid"` in sprite.json) instead of its own size:

| class | canvas | body box | for |
|---|---|---|---|
| small | 32×32 | 16×16 | slimes, bats, pickups |
| humanoid | 64×48 | 16×30 | anyone holding a weapon |
| large | 96×96 | 48×64 | bosses |
| topdown | 64×64, feet at y=52 | 16×30 | top-down (3/4 view) characters: room to swing in all four directions |
| overhead | 64×64, centre (32,32) | 16×16 | bird's-eye characters, drawn facing east and rotated in the engine |

The character stands in the **body box** (bottom-centre, on the origin), which is the size of a normal ~30px person. The rest of the canvas is room for weapons, smears and effects, so a big swing is never cramped. Keep idle/walk inside the body box and let attacks reach out. Never scale the character up to fill the canvas. `resize S --class C` moves an existing sprite to a new canvas, keeping it on its origin.

## Top-down characters
- Use the 3/4 view (seen from slightly above and in front), class `topdown`.
- Draw three directions: `down` (facing the camera), `up` (back) and `side` (facing right). Left is `side` mirrored at runtime.
- Name animations `<action>_<direction>`: `idle_down`, `walk_up`, `attack_side`... `playFacing()` relies on this.
- Prefix layers by view (`front_head`, `back_torso`, `side_body`) and keep proportions identical across views: same helmet size, same height, same sword length.
- Front and back views are near-symmetric. Shade them from the top-left anyway rather than mirroring the shading.
- A top-down walk is a 4-frame step-left / pass / step-right / pass with a 1px body bob. Arms and weapon ride on the body layer.
- Each attack swings in its own direction: `attack_down` arcs across the front below the feet, `attack_up` arcs over the head. The sword arm needs its own layer, on a torso layer with that arm removed.
- Reference: `sprites/knight_topdown` in the pixelforge repo.

## Overhead (bird's-eye) characters
- Use class `overhead` (`anchor: center`): the origin is the rotation centre, not the feet.
- Draw **one direction only: facing east** (right). The engine rotates the sprite to face anywhere: `sprite.rotation = Math.atan2(vy, vx)`. Don't draw extra directions or use `flipX`.
- What shows from straight above: the helmet dome on top of everything, pauldrons either side (north and south when facing east), the cape behind (west), weapons and arms in front. Feet only peek out ahead of or behind the body while walking.
- Shade domes as lit spheres with the light from the north-west, and keep highlights to a 2–3 pixel glint.
- Walk: alternate a boot peeking ahead on each side, with a 1px counter-twist of the shoulders (the opposite pauldron moves forward).
- Attacks read best as horizontal arcs around the centre. The smear sweeps from behind one shoulder, across the front, to the other side.
- Give the cape and plume `none` roles. From above they hang outside the body and shouldn't count as hittable.
- Hitboxes rotate with the sprite. `enablePixelforgeHits` tests rotated boxes exactly.
- For physics, use a circle that doesn't care about rotation: `body.setCircle(8, 24, 24)` for the 16×16 body box.
- `render` and `sheet` show the unrotated art. `/viewer/phaser.html` shows it rotating and spars at 0° and 135°.
- Reference: `sprites/knight_overhead`.

## Tilesets (terrain, floors, walls)
A tileset is a sprite folder with `"type": "tileset"`. Its frames are tiles instead of animation frames. Make one with `new terrain --tileset` (16×16 tiles by default, or `--size 32x32`).
```json
{"type": "tileset", "size": [16, 16], "columns": 8, "palette": {...},
 "tiles": ["grass", "dirt",
           {"name": "dirt_n", "from": "dirt", "layers": ["edge_n"]},
           {"name": "dirt_s", "from": "dirt", "layers": [{"from": "edge_n", "flip": "v"}]}],
 "properties": {"water*": {"collides": true, "liquid": true}, "wall": {"collides": true}},
 "sample": {"legend": {"g": "grass", "d": "dirt", "n": "dirt_n"}, "rows": ["gggg", "nnnn", "dddd"]}}
```
- **Tile index = position in `tiles`**, which is the number Phaser and Tiled use. Add new tiles at the end, because reordering renumbers every map that uses the tileset.
- A `tiles` item is a frame id (the tile is named after it) or a frame entry object with a `"name"`. Build edges and variants from a base tile plus overlay layers, just like animation frames.
- **Animated tiles** (water, lava, torches, flowers in the wind) give the item `"frames"`: a list of frame entries timed by `"fps"` (default 4) or each entry's `"duration"`. Other keys on the item (`layers`, `replace`...) are painted on top of every frame. `"frames": "water"` reuses an earlier animated tile's frames so the two stay in step, e.g. `{"name": "water_n", "frames": "water", "layers": ["bank_n"]}` for a shore.
  ```json
  {"name": "water", "fps": 4, "frames": [
    {"from": "water", "layers": ["deep", "waves"]},
    {"from": "water", "layers": [{"from": "deep", "roll": [1, 0]}, "waves_b"]}]}
  ```
  `roll: [dx, dy]` is an `offset` that wraps around the tile edges, so moving waves stay seamless. Keep tile motion subtle: 3–4 frames, 200–300ms each, with a few pixels changing per frame. The extra frames are exported after the named tiles, so tile numbers don't change. `tiles S` shows every frame, and `gif S` / `gif S TILE` play the sample map or one tile.
- `properties` maps tile-name globs to properties (every match merges, later patterns win). `collides: true` is what the Phaser helper turns into collision. Any other keys reach `tile.properties` in the game.
- `sample` is a small test map (`' '`/`.` = empty). It's rendered by `tiles`, shown in the gallery, and walkable in `/viewer/tilemap.html`. Put every tile and every transition you care about in it.
- Ground tiles must repeat without seams: `tiles S` shows each one repeated 3×3, and `check` warns when a wrapped edge jumps in brightness. Edge/transition tiles and one-row tiles like walls are expected to warn on the axis they don't repeat along.
- Use cast shadows instead of black outlines: a dark-brown row under a grass edge, navy under a riverbank. Light comes from the top-left, so don't just flip a shadowed edge to make the opposite side. Flip only the unshaded layer.
- 3/4 top-down walls: a light top surface, then the face (bricks), then a dark base row. Keep them to one tile high and mark them `collides`.
- Export gives `export/<name>.png` (a grid, 1px spacing) plus `export/<name>.json`, a **Tiled tileset**: open it in Tiled to paint real levels, then embed the tileset in the map (Phaser can't read external tilesets).
- Reference: `sprites/terrain` in the pixelforge repo.

## Hurtboxes and hitboxes
Boxes are computed from the art on export, so nobody draws them by hand:
```json
"roles": {"smear_trail": "none", "sword*": "hit", "smear": "hit"},
"hit_pad": 1, "hurt_pad": -1
```
- `roles` maps frame-file globs (first match wins) to `hurt` (can be hit; the default), `hit` (deals damage) or `none` (decoration, e.g. the trailing part of a smear behind the character).
- **Active frames** (`"active": true` on a frame entry) are the only frames where hitboxes exist. Mark the swing itself (the smear and the thrust), not the wind-up or recovery.
- Pads grow or shrink the boxes for game feel. Slightly generous hitboxes and slightly smaller hurtboxes feel fair.
- So put weapons and effects in their **own layer files**. A weapon baked into the body layer can't get a hit role.
- `render` and `sheet --boxes` outline the body box (yellow, dashed), hurtboxes (green) and hitboxes (red).

## Commands
| | |
|---|---|
| `list` | sprites + animations |
| `new NAME [--class humanoid]` | scaffold (or `--size WxH` for a one-off canvas; `--tileset [--size 16x16]` for terrain) |
| `tiles S [TILE...]` | tileset preview: each tile repeated 3×3 (seams show) + the sample map → `previews/` |
| `resize S WxH` / `resize S --class C` | re-canvas every frame, keeping the character on its origin |
| `show S ANIM I` / `show S @frame` / `show S TILE` | print a frame (or a tileset's tile) with x/y rulers (find exact coordinates) |
| `render S ANIM I [--onion] [--scale N] [--no-boxes]` | zoomed PNG with grid, rulers, origin mark, boxes, 1x/2x thumbs → `previews/` |
| `sheet S [ANIM...] [--onion] [--boxes]` | all frames side by side + 1x strip: judge motion and consistency (active frames labelled) |
| `gif S [ANIM]` | animated GIF at real timing (for the user). For a tileset: the sample map, or `gif S TILE` for one tile repeated 3×3 |
| `check [S] [-v]` | lint: sizes, undefined keys, missing frames, floating pixels, feet jitter, jump cuts, palette size |
| `paint S FRAME "ops"` | edit a frame file: `px x y k [x y k...]; frect x0 y0 x1 y1 k; box ...; line x0 y0 x1 y1 k; fill x y k; move x0 y0 x1 y1 dx dy; shift dx dy; mirror lr\|rl; swap a b; clear` (`.` erases) |
| `dup S SRC DST [--flip h] [--offset dx dy]` | copy a frame file |
| `palette S` | swatch PNG |
| `import PNG NAME [--cell 32x32]` | PNG/sheet/atlas → frames (reuses existing palette keys) |
| `export [S...] [--all]` | sheet + JSON + Phaser helper (refuses if `check` has errors) |
| `gallery` | `export/gallery.html`: one self-contained page with every character playing every animation |
| `upgrade [--dry-run]` | after the pixelforge repo is updated (`git pull`): refresh this guide, add missing scaffolding, re-export. If it writes `CLAUDE.pixelforge-new.md`, merge that into CLAUDE.md and delete it |
| `--version` | installed pixelforge version (`pixelforge.json` records the version this game was last upgraded to) |
| `serve [--port 8000]` | then open `http://127.0.0.1:8000/`: browse every character → animation → frame, with boxes. `/viewer/phaser.html` is the real Phaser test, and `/viewer/tilemap.html` lets a top-down character walk each tileset's sample map |

## The authoring loop (do this every time)
1. Plan the sprite: silhouette, palette ramps (3–4 shades per material), which parts are reusable layers (body / legs / weapon / effects).
2. Write or Edit the `.txt` grids. Edit individual rows rather than rewriting files. `paint` is good for lines, fills and moves.
3. `check S`. Fix every error and think about each warning.
4. `render` the frame and **Read the PNG**. Critique it honestly: silhouette at 1x, readability, stray pixels, shading direction. Fix and repeat.
5. For animations: `sheet S ANIM --onion`, and `render ... --onion` for single frames (red ghost = previous frame, blue = next). Check that motion is continuous and that the feet stay planted.
6. `export S`, then `gallery` so the team's catalog stays current. Optionally `serve` and check `/viewer/phaser.html` in the browser.

## Pixel-art rules
- Readable silhouette at 1x first, details second. Chunky proportions (big head/helmet) read best at 32px.
- One light source, from the top-left: highlights on top/left edges, shadows bottom/right. No pillow shading (darkening every edge evenly).
- 1px dark outline (`outline` #181425); selective outline (lighter outline on lit edges) is a nice upgrade. Avoid doubled 2px lines and orphan pixels.
- Lines: use consistent step lengths (1:1, 2:1) to avoid jaggies. Avoid banding (parallel shade bands of the same width).
- Keep each sprite ≤ ~16 colors, drawn from `palettes/game.json` for a cohesive game.
- Body parts that animate separately (legs, arms, weapons) go in separate layer files so they can be recombined.

## Animation rules
- Feet stay on the origin row unless the character jumps. `check` flags jitter.
- idle: 2–4 frames, 300–500ms each, with small breathing (head/torso 1px down) and secondary motion (plume, cape).
- walk: 4–8 frames at 8–12fps: contact → down (body +1) → passing (body −1, lifted foot) → mirrored. Shade the far limb darker so left and right are distinguishable.
- attack: anticipation (wind-up, hold longer) → smear frame (fast, short duration) → follow-through/recovery. Non-looping. Mark only the smear and strike frames `"active": true`. Weapons stay the same length in every animation.
- hurt: 1–2 frames, `replace` to a flash color plus a 1px knockback `offset`.
- Change only what needs to move. Most frames should be composed from shared layers with `offset`.

## Phaser usage
```js
import { loadPixelforge, createPixelforgeAnims, enablePixelforgeHits, pixelforgeBody, playFacing,
         drawPixelforgeBoxes } from './export/pixelforge.js';
// game config: pixelArt: true
preload() { loadPixelforge(this, 'knight', 'export/'); }
create()  {
  createPixelforgeAnims(this, 'knight');                       // keys: knight_idle, knight_attack, ...
  const knight = this.physics.add.sprite(200, 150, 'knight').play('knight_idle');   // origin = feet
  const b = pixelforgeBody(this, 'knight');                    // fixed physics box from the body box
  knight.body.setSize(b.width, b.height).setOffset(b.x, b.y);
  enablePixelforgeHits(this, knight, () => enemies, (enemy) => enemy.takeDamage(1));  // once per swing
}
update()  { debug.clear(); drawPixelforgeBoxes(debug, [knight, ...enemies]); }       // optional overlay
```
- `createPixelforgeAnims` wraps `this.anims.createFromAseprite` and restores `loop` (Phaser otherwise plays every tag once).
- Face left with `sprite.setFlipX(true)`. Boxes mirror with it.
- Top-down: `playFacing(sprite, 'walk', 'left' | 'right' | 'up' | 'down')` picks `<sprite>_walk_<down|up|side>` and sets the flip.
- Movement and walls use the fixed physics body. Hurtboxes and hitboxes only decide who hits whom, so changing per-frame boxes never makes the character jitter.
- `/viewer/phaser.html` (via `serve`) runs every attack against sparring dummies (front, far, behind) with boxes drawn: use it to check reach.

Tilesets:
```js
import { loadPixelforgeTiles, pixelforgeTilemap, pixelforgeTileIndex, addPixelforgeTileset,
         applyPixelforgeTileProperties, animatePixelforgeTiles } from './export/pixelforge.js';
preload() { loadPixelforgeTiles(this, 'terrain'); }
create()  {
  const { map, layer } = pixelforgeTilemap(this, 'terrain', {          // omit rows to get the sample map
    rows: ['gggg', 'nnnn', 'dddd'], legend: { g: 'grass', n: 'dirt_n', d: 'dirt' } });
  this.physics.add.collider(hero, layer);                              // "collides": true tiles block
  map.putTileAt(pixelforgeTileIndex(this, 'terrain', 'water'), 2, 1);  // look tiles up by name
}
// A map made in Tiled: const m = this.make.tilemap({ key: 'level1' });
//   const layer = m.createLayer('ground', addPixelforgeTileset(m, 'terrain'));
//   applyPixelforgeTileProperties(layer, 'terrain'); animatePixelforgeTiles(layer, 'terrain');
```
- `pixelforgeTilemap` plays animated tiles for you (Phaser doesn't animate tiles on its own). An animating tile's `index` changes from frame to frame, so identify tiles by `tile.properties.name`. Tiles added later with `putTileAt` only animate after you call `animatePixelforgeTiles(layer, name)` again.
- For top-down characters, collide with the feet only: `hero.body.setSize(b.width - 4, 8).setOffset(b.x + 2, b.y + b.height - 8)` with `b = pixelforgeBody(...)`, so the head can overlap the top of a wall.
