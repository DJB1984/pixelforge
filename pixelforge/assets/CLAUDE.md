# Sprites for this game (pixelforge)

This folder is a pixelforge project (`pixelforge.json` marks its root). Sprites are plain-text grids that you write and edit directly. The `pixelforge` command (also `python -m pixelforge`; run it anywhere inside this folder) renders them to PNGs you can **look at with the Read tool**, lints them, and exports Phaser-ready sprite sheets. Never claim art looks good without rendering it and viewing the PNG.

## Data layout
```
palettes/game.json            shared named colors (Endesga 32). Prefer these names.
sprites/<name>/sprite.json    size, origin, palette, animations
sprites/<name>/frames/*.txt   one frame or layer per file: H lines of W chars
export/<name>.png|.json       generated: Phaser load.aseprite format (+ index.json, pixelforge.js)
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
  Applied in order: `from` (base, may itself be an object) → `layers` painted bottom-to-top → `flip` → `offset` → `replace` (palette swap, e.g. white hit flash). `duration` (ms) overrides `1000/fps`.
- `loop: false` animations play once.

## Size classes: canvas vs body box
Every character uses a standard **class** from `pixelforge.json` (`"class": "humanoid"` in sprite.json) instead of its own size:

| class | canvas | body box | for |
|---|---|---|---|
| small | 32×32 | 16×16 | slimes, bats, pickups |
| humanoid | 64×48 | 16×30 | anyone holding a weapon |
| large | 96×96 | 48×64 | bosses |

The character stands in the **body box** (bottom-centre, on the origin), which is the size of a normal ~30px person. The rest of the canvas is room for weapons, smears and effects, so a big swing is never cramped. Keep idle/walk inside the body box and let attacks reach out. Never scale the character up to fill the canvas. `resize S --class C` moves an existing sprite to a new canvas, keeping it on its origin.

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
| `new NAME [--class humanoid]` | scaffold (or `--size WxH` for a one-off canvas) |
| `resize S WxH` / `resize S --class C` | re-canvas every frame, keeping the character on its origin |
| `show S ANIM I` / `show S @frame` | print a frame with x/y rulers (find exact coordinates) |
| `render S ANIM I [--onion] [--scale N] [--no-boxes]` | zoomed PNG with grid, rulers, origin mark, boxes, 1x/2x thumbs → `previews/` |
| `sheet S [ANIM...] [--onion] [--boxes]` | all frames side by side + 1x strip: judge motion and consistency (active frames labelled) |
| `gif S [ANIM]` | animated GIF at real timing (for the user) |
| `check [S] [-v]` | lint: sizes, undefined keys, missing frames, floating pixels, feet jitter, jump cuts, palette size |
| `paint S FRAME "ops"` | edit a frame file: `px x y k [x y k...]; frect x0 y0 x1 y1 k; box ...; line x0 y0 x1 y1 k; fill x y k; move x0 y0 x1 y1 dx dy; shift dx dy; mirror lr\|rl; swap a b; clear` (`.` erases) |
| `dup S SRC DST [--flip h] [--offset dx dy]` | copy a frame file |
| `palette S` | swatch PNG |
| `import PNG NAME [--cell 32x32]` | PNG/sheet/atlas → frames (reuses existing palette keys) |
| `export [S...] [--all]` | sheet + JSON + Phaser helper (refuses if `check` has errors) |
| `gallery` | `export/gallery.html`: one self-contained page with every character playing every animation |
| `serve [--port 8000]` | then open `/viewer/` (frame player) or `/viewer/phaser.html` (real Phaser test) |

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
import { loadPixelforge, createPixelforgeAnims, enablePixelforgeHits, pixelforgeBody,
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
- Movement and walls use the fixed physics body. Hurtboxes and hitboxes only decide who hits whom, so changing per-frame boxes never makes the character jitter.
- `/viewer/phaser.html` (via `serve`) runs every attack against sparring dummies (front, far, behind) with boxes drawn: use it to check reach.
