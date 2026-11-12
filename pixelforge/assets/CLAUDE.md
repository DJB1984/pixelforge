# Sprites for this game (pixelforge)

This folder is a pixelforge project (`pixelforge.json` marks its root). Sprites are plain-text grids that you write and edit directly. The `pixelforge` command (also `python -m pixelforge`; run it anywhere inside this folder) renders them to PNGs you can **look at with the Read tool**, lints them, and exports Phaser-ready sprite sheets. Never claim art looks good without rendering it and viewing the PNG.

## Data layout
```
palettes/game.json            shared named colors (Endesga 32). Prefer these names.
sprites/<name>/sprite.json    size, origin, palette, animations
sprites/<name>/frames/*.txt   one frame or layer per file: H lines of W chars (the whole canvas)
sprites/<name>/parts/*.txt    small pieces of any size (a door, a window), placed on the canvas with "at"
sprites/<name>/glyphs.txt     a font's letters (fonts only)
levels/<name>.json            a whole level: tile rows, stamps, objects, player, camera (see Levels)
export/<name>.png|.json       generated: Phaser load.aseprite format, or a Tiled tileset for tilesets (+ index.json, pixelforge.js)
                              (+ <name>.xml for fonts, <name>_tiles.png|.json for sliced buildings,
                              levels/<name>.json: each level as a Tiled map)
export/gallery.html           generated: shareable page of every sprite (`pixelforge gallery`)
critiques.json                notes the developer left in the dashboard for you to fix (`pixelforge critiques`)
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
- A **part entry** places a small grid from `parts/` instead of a whole-canvas frame: `{"part": "window", "at": [8, 54]}`, or `"at": [[8, 54], [44, 54]]` to stamp it several times. `flip` and `replace` apply to the part itself. Use it in `layers` or as `from`.
- `loop: false` animations play once.

## Game settings: view and resolution
`pixelforge.json` says how the game looks, and `new`, `check` and the Phaser helper follow it:
- `"view"`: `"side"` (platformers), `"topdown"` (3/4 view RPGs) or `"overhead"` (bird's-eye). It picks `new`'s default class, a prop's default footprint and whether props y-sort. One sprite can override it with its own `"view"`.
- `"resolution"`: the game's screen before scaling, e.g. `[320, 180]`. `check` warns when a prop is bigger than the screen.

## Big art: build it from parts
Text grids stay accurate up to about 64px. Past that, long lines, perspective and repeated details drift. So never draw a 100px+ canvas as one hand-written grid:
- Keep the big layers simple and regular (a wall face, a roof), and use `paint` ops (`frect`, `line`, `fill`) for them.
- Draw each detail once as a small part (door, window, chimney, sign) and place it with `at`. Reuse it: the same window on every floor, the same part with `replace` for a lit window at night.
- Render the whole thing and judge it at 1x and 2x, as for any sprite. `render` zooms big canvases less, and `render S @part` shows one part on its own.
- Repetition is fine where the real thing repeats (shingles, bricks). Break up big flat areas with one or two placed details (a dormer, a crack, ivy).

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

## Props, buildings and background accents
A prop is anything that isn't a character, a tile or UI: chests, trees, signs, crates, houses, clouds, distant mountains. Give it `"type": "prop"` (scaffold: `new chest --prop --size 16x16`, or `new inn --building`). Its animations are its **states** (`closed`, `opening`, `open`; one-frame animations are fine), and the game picks one by name.
```json
{"type": "prop", "size": [64, 80], "origin": [32, 80], "footprint": [2, 16, 60, 64], "slice": [16, 16],
 "animations": {"closed": {"frames": [{"layers": ["walls", "roof", {"part": "door", "at": [26, 54]}]}]}}}
```
- `origin`: where it stands, usually the bottom-centre of its base.
- `footprint` `[x, y, w, h]`: the solid part that blocks movement. It's exported as the body. Without one, the art's bounds block.
  - **Top-down:** the footprint is the ground it covers: everything but the top edge of a roof or tree canopy. That top strip is walk-behind, so a character standing north of the house is drawn behind it. `check` warns about a solid top-down prop without a footprint.
  - **Side view:** houses are usually scenery the player walks in front of: `"solid": false`.
- `"layer"`: `back` (behind everything), `world` (the default: among the characters) or `front` (over everything, e.g. foreground leaves). `"solid"` defaults to true for world props only.
- `"scroll"`: a parallax factor for background accents. Use `0.2` for far mountains, `0.5` for mid trees and `1` for the world. Setting it puts the prop on the `back` layer.
- **Backgrounds:** don't paint whole screens. The game fills the sky with a flat color or a gradient, and you add a few accent props on top: clouds, a far skyline, hills, a moon. Keep them lower in contrast than the play area, with soft or no outlines. Reference: `sprites/cloud`.
- **Buildings, two ways:**
  - A **unique** building (inn, castle, shop) is one prop made of parts. `"slice": [16, 16]` also exports it cut into tiles (`export/<name>_tiles`), so it can be stamped into Tiled maps too. The tiles under the footprint get `collides`, and in top-down, the roof tiles above it get `above`.
  - **Generic** buildings (a village of similar houses) are a tileset kit (wall, roof, door and window tiles) plus `stamps` for ready-made arrangements (see Tilesets).
- States that only differ in a detail share layers: the open door is the same entry with `door_open` placed instead of `door`, and lit windows are a `replace` on the window part.
- References: `sprites/house` (top-down building with parts, sliced), `sprites/chest` (states built from parts), `sprites/cloud` (parallax accent).

## UI: icons, panels and fonts
- **Icons** (`new items --icons`): `"type": "icons"`, a fixed cell `size` (16×16 is typical) and `"icons": [...]`, listed like tiles: a frame id, or an entry with a `"name"` (e.g. `{"name": "heart_empty", "from": "heart", "replace": {"r": "B"}}`). They're exported as an atlas, and the game shows one by name. Icons don't animate (make an animated pickup a prop).
- **Panels and buttons**: an icon with `"nine": [left, right, top, bottom]` border widths is a nine-slice. The corners stay crisp and the edges and middle stretch to any size. `tiles S` shows each one stretched to three sizes: check that the border still reads.
- **Fonts** (`new hud --font` starts from a 5×7 font with A–Z, 0–9 and punctuation): `"type": "font"`, with `"size": [max glyph width, height]`, `"spacing"` (px between letters), `"space"` (width of a space) and `"line_height"`. The glyphs live in `glyphs.txt` as blocks: a `= A` line, then the glyph's rows, all the same length (that length is its width). Without lowercase glyphs, lowercase letters reuse the capitals. `tiles myfont "GAME OVER"` previews any text. Draw the ink white so the game can `setTint()` it.

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
- `stamps` are named multi-tile arrangements made from the kit, such as a house, a pond or a fence run: `"stamps": {"hut": {"rows": ["/^\\", "|d|"]}}`. Their legend defaults to the sample's (or give one with `"legend"`). `tiles S` draws them, and `stampPixelforgeTiles` places them in the game.
- Ground tiles must repeat without seams: `tiles S` shows each one repeated 3×3, and `check` warns when a wrapped edge jumps in brightness. Edge/transition tiles and one-row tiles like walls are expected to warn on the axis they don't repeat along.
- Use cast shadows instead of black outlines: a dark-brown row under a grass edge, navy under a riverbank. Light comes from the top-left, so don't just flip a shadowed edge to make the opposite side. Flip only the unshaded layer.
- 3/4 top-down walls: a light top surface, then the face (bricks), then a dark base row. Keep them to one tile high and mark them `collides`.
- Export gives `export/<name>.png` (a grid, 1px spacing) plus `export/<name>.json`, a **Tiled tileset**: open it in Tiled to paint real levels, then embed the tileset in the map (Phaser can't read external tilesets).
- Reference: `sprites/terrain` in the pixelforge repo.

## Levels
A level is `levels/<name>.json` (next to `sprites/`): the map as rows of characters, like a tileset's sample.
`new-level NAME [--size 40x12] [--tileset terrain]` starts one screen of ground with a spawn.
```json
{"name": "village", "view": "topdown", "tileset": "terrain",
 "background": {"color": "#3e8948"},                      // or {"gradient": ["#124e89", "#0099db"]} (top, bottom)
 "accents": [{"prop": "cloud", "at": [40, 20]}],          // background props, in parallax space
 "legend": {"W": "auto:water", "r": {"tileset": "kit", "tile": "roof"}},
 "layers": [{"name": "ground", "rows": ["gggg", "gWWg"]},
            {"name": "decor",  "rows": ["....", "...."]},
            {"name": "roofs",  "rows": ["....", "...."], "above": true}],
 "stamps": [{"stamp": "pond", "at": [4, 6]},
            {"tileset": "house_tiles", "stamp": "house", "at": [10, 2], "layer": "decor"}],
 "objects": {"legend": {"H": {"prop": "house", "snap": "left"},
                        "c": {"prop": "chest", "type": "chest", "state": "closed", "props": {"loot": "key"}},
                        "s": {"sprite": "slime", "type": "enemy"},
                        "D": {"type": "door", "to": "inn", "size": [2, 1]}},
             "rows": ["....", "@.c."],
             "list": [{"prop": "sign", "at": [123, 88], "props": {"text": "Welcome"}}]},
 "player": "knight_topdown", "camera": {"zoom": 1}}
```
- **Tile layers:** every layer is the same size. `.` and space are empty. The legend starts from the tileset's sample
  legend. A value is a tile name, `{"tileset", "tile"}` for another tileset (a sliced building's `<prop>_tiles`
  too), or `auto:<terrain>`. `above: true` layers draw over the characters (roofs, treetops).
- **Autotiling:** give the tileset `"autotile": {"water": {"base": "water", "edges": {"n": "water_n", "s": "water_s",
  "ne": "water_ne"}}}`. Each `auto:water` cell picks the most specific edge tile for the sides whose neighbour isn't
  water (`ne` before `n` before the base). The result is baked into the export, so the game never autotiles.
- **Stamps** go on the first layer (or `"layer"`). Tiles marked `above` (a sliced top-down roof) go on the first
  `above` layer, which is created if the level has none.
- **Objects:** a character in `objects.rows` puts the object's origin at that cell's bottom-centre.
  - `"snap": "left"` lines a prop's canvas up with the cell's left edge (tile-sized buildings).
  - `"offset": [dx, dy]` nudges it, and `objects.list` places objects by pixel with `"at"`.
  - `type` is yours to define (`enemy`, `item`, `npc`...); `props` passes through to the game.
  - `@` is the player spawn by default. `door` and `trigger` objects (or any with `"size"` in tiles) are areas,
    and every other object is a point.
  - A door's `"to"` is a level name. `"spawn"` names the spawn object to arrive at.
- `view` defaults to `pixelforge.json`'s. `camera.zoom` (default 1) zooms the camera inside the game's
  `resolution`, so one screen shows `resolution / zoom` world pixels.
- `check` lints levels too:
  - Errors: unknown characters, missing tilesets, tiles, props, sprites or stamps, ragged rows, layers of
    different sizes, no spawn, a spawn on a colliding tile or inside a solid footprint, and a door to a missing level.
  - Warnings: solid footprints that overlap, and, in top-down and overhead levels, doors, chests, items and objects
    with `props` that can't be walked to from the spawn. Side-view routes need a playtest.
- `export` writes `export/levels/<name>.json`: a Tiled map with the tilesets embedded and an `objects` group (open it
  in Tiled). `list` shows the levels.
- Play a level in the dashboard's `/viewer/play.html?level=NAME` (live from `levels/`). Doors lead to their level.
- In Phaser, `loadPixelforgeAll` loads the levels, and `pixelforgeLevel` builds one:
  ```js
  const level = pixelforgeLevel(this, 'village');   // { map, layers, player, objects, props, sprites, spawns, triggers }
  this.events.on('pixelforge-trigger', (obj, player) => { if (obj.type === 'door') this.scene.restart({ level: obj.to }); });
  ```
  It sets the background and accents; the layers with their properties, collision and animation (`oneway` tiles
  are planks you jump up through); props, and sprites playing idle; the player at the spawn, colliding with the
  layers and solid props; and the camera bounds, follow and zoom. Options: `player`, `spawn`, `playerOptions` (for
  the controller), and `respawn: false` (a side-view fall emits `pixelforge-fell` and goes back to the spawn
  unless you set it).
- Tiled wangsets (Tiled's own autotiling) aren't exported yet.

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
| `list` | sprites + animations, and levels |
| `new-level NAME [--size WxH] [--tileset T]` | scaffold `levels/NAME.json`: one screen of ground and a spawn |
| `new NAME [--class C]` | scaffold a character (class defaults from the view; or `--size WxH`). `--prop`, `--building`, `--tileset`, `--icons`, `--font` for the other kinds |
| `tiles S [TILE...]` | tileset preview: each tile repeated 3×3 (seams show), the sample map and stamps; for icons, nine-slices stretched; for a font, its glyphs and sample text (`tiles FONT "ANY TEXT"`) → `previews/` |
| `resize S WxH` / `resize S --class C` | re-canvas every frame, keeping the character on its origin |
| `show S ANIM I` / `show S @frame` / `show S @part` / `show S TILE` | print a frame, part or tile with x/y rulers (find exact coordinates) |
| `render S ANIM I [--onion] [--scale N] [--no-boxes]` | zoomed PNG with grid, rulers, origin mark, boxes (a prop's footprint), slice lines, 1x/2x thumbs → `previews/` |
| `sheet S [ANIM...] [--onion] [--boxes]` | all frames side by side + 1x strip: judge motion and consistency (active frames labelled) |
| `motion S [ANIM...]` | timing you can't see in stills: per-frame table (head, feet, body centre, weapon tip and reach, pixels changed, ms), notes on uneven spacing / unheld wind-up / slow smear / bob size, and a timeline chart PNG |
| `compare S [ANIM I \| @frame \| TILE] [--ref HEAD]` | before (as committed in git) / after / changed pixels. With no target: every frame, so you see everything a layer edit touched |
| `context S ANIM [I] [--on terrain:grass --on '#262b44']` | the sprite on real ground at game zoom (3x), in grayscale, and a map of silhouette edges that blend into the ground, with contrast numbers |
| `gif S [ANIM]` | animated GIF at real timing (for the user). For a tileset: the sample map, or `gif S TILE` for one tile repeated 3×3 |
| `check [S] [-v]` | lint: sizes, undefined keys, missing frames, floating pixels, feet jitter, jump cuts, palette size |
| `paint S FRAME "ops"` | edit a frame or part file: `px x y k [x y k...]; frect x0 y0 x1 y1 k; box ...; line x0 y0 x1 y1 k; fill x y k; move x0 y0 x1 y1 dx dy; shift dx dy; mirror lr\|rl; swap a b; clear` (`.` erases) |
| `dup S SRC DST [--flip h] [--offset dx dy]` | copy a frame file |
| `palette S` | swatch PNG |
| `import PNG NAME [--cell 32x32]` | PNG/sheet/atlas → frames (reuses existing palette keys) |
| `export [S...] [--all]` | sheet + JSON + Phaser helper (refuses if `check` has errors) |
| `gallery` | `export/gallery.html`: one self-contained page with every character playing every animation |
| `upgrade [--dry-run]` | after the pixelforge repo is updated (`git pull`): refresh this guide, add missing scaffolding, re-export. If it writes `CLAUDE.pixelforge-new.md`, merge that into CLAUDE.md and delete it |
| `--version` | installed pixelforge version (`pixelforge.json` records the version this game was last upgraded to) |
| `serve [--port 8000]` | the dashboard at `http://127.0.0.1:8000/`: every sprite and tileset, built live from `sprites/` (no export needed), where the developer critiques the art. Each asset has an "In game" tab (`/viewer/phaser.html` sparring, `/viewer/platformer.html` playable side-view for characters with `jump*` animations, `/viewer/tilemap.html` walkable sample map) |
| `critiques [--all]` / `critiques watch [--once]` / `critiques show ID` / `critiques done ID -m "..."` | the developer's critiques: list them, wait for new ones, picture one (`previews/critique_ID.png`), mark one fixed |

## The authoring loop (do this every time)
1. Plan the sprite: silhouette, palette ramps (3–4 shades per material), which parts are reusable layers (body / legs / weapon / effects).
2. Write or Edit the `.txt` grids. Edit individual rows rather than rewriting files. `paint` is good for lines, fills and moves.
3. `check S`. Fix every error and think about each warning.
4. `render` the frame and **Read the PNG**. Critique it honestly: silhouette at 1x, readability, stray pixels, shading direction. Fix and repeat.
5. `context S ANIM` once the sprite has shape: it has to read on the game's real ground, and still read in **grayscale**. Fix any blend-map hot spots that matter (feet, weapon, head) with value, not hue: a darker outline, or a lighter rim on the edge facing the light.
6. For animations: `sheet S ANIM --onion`, and `render ... --onion` for single frames (red ghost = previous frame, blue = next). Check that motion is continuous and that the feet stay planted. Then `motion S ANIM` and **Read its chart**: you can't watch a GIF, so judge timing from the numbers. Even steps (or deliberate easing), a held wind-up, a fast smear and a 1px idle bob are what to look for. Act on its notes or know why you're ignoring them.
7. After editing an existing sprite, `compare S`: every frame you changed is listed, so a shared layer edit can't quietly break another animation. Read the comparison PNG for the frames you didn't mean to touch.
8. `export S`, then `gallery` so the team's catalog stays current. The developer reviews the result in `serve`'s dashboard.

## Critiques from the dashboard
The developer reviews the art in `serve`'s dashboard and leaves critiques on a whole sprite or tileset, an animation, a frame or tile, or a spot they marked on it. A spot is `[x, y, w, h]` in frame pixels: the same coordinates as `show` and the boxes.
- When the developer asks you to watch for critiques, run `pixelforge critiques watch --once` in the background. It returns as soon as there are critiques, prints one line each, and marks them `working` so the dashboard shows you're on it. (With the Monitor tool, `pixelforge critiques watch` streams one line per new critique instead.)
- For each critique: `pixelforge critiques show ID`, then Read the PNG it prints (the spot is outlined in cyan) and fix the art with the normal authoring loop (check, render, look). Then run `pixelforge critiques done ID -m "what you changed"`. That marks it fixed, shows your note in the dashboard, and re-exports the sprite. Keep the note to one plain sentence about the change.
- Then start `watch --once` again, so you keep watching until the developer says stop.
- If you're asked to "fix the open critiques" without watching, `pixelforge critiques` lists them with the frame entry or tile each one points at.
- The dashboard updates by itself when frame files change, so the developer sees your fix land without reloading.

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
- Load everything at once with `loadPixelforgeAll(this)` in preload (it reads `export/index.json` and queues every
  sprite, prop, tileset, icon atlas, font and level) and `createPixelforgeAll(this)` in create (every animation).
- `createPixelforgeAnims` wraps `this.anims.createFromAseprite` and restores `loop` (Phaser otherwise plays every tag once).
- Face left with `sprite.setFlipX(true)`. Boxes mirror with it.
- Top-down: `playFacing(sprite, 'walk', 'left' | 'right' | 'up' | 'down')` picks `<sprite>_walk_<down|up|side>` and sets the flip.
- Movement and walls use the fixed physics body. Hurtboxes and hitboxes only decide who hits whom, so changing per-frame boxes never makes the character jitter.
- `/viewer/phaser.html` (via `serve`, or a sprite's "In game" tab) runs every attack against sparring dummies (front, far, behind) with boxes drawn: use it to check reach.

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
Props, stamps and UI:
```js
import { addPixelforgeProp, keepPixelforgeDepth, stampPixelforgeTiles, loadPixelforgeIcons, addPixelforgePanel,
         loadPixelforgeFont } from './export/pixelforge.js';
preload() { loadPixelforge(this, 'house'); loadPixelforge(this, 'cloud');      // props load like sprites
            loadPixelforgeIcons(this, 'ui'); loadPixelforgeFont(this, 'font'); }
create()  {
  const house = addPixelforgeProp(this, 160, 120, 'house');            // (x, y) = its origin; plays its first state
  this.physics.add.collider(hero, house);                              // solid props get a static body (the footprint)
  house.play('house_open');                                            // states are animations: <prop>_<state>
  addPixelforgeProp(this, 200, 40, 'cloud');                           // back layer, scroll factor 0.3: parallax
  keepPixelforgeDepth(this, [hero]);                                   // top-down: characters sort by y with the props
  stampPixelforgeTiles(layer, 'terrain', 'pond', 4, 6, { above: roofLayer });   // `above` tiles go over characters
  this.add.image(12, 12, 'ui', 'heart').setScrollFactor(0);
  addPixelforgePanel(this, 160, 160, 'ui', 'panel', 200, 32).setScrollFactor(0);
  this.add.bitmapText(70, 152, 'font', 'Press START').setTint(0x181425).setScrollFactor(0);
}
```
- A sliced building is also a tileset: `loadPixelforgeTiles(this, 'house_tiles')`, then `stampPixelforgeTiles(layer, 'house_tiles', 'house', tx, ty, { above })`, or paint it in Tiled.
- `/viewer/tilemap.html?prop=house` (a top-down prop's "In game" tab) stands the prop on a tileset's sample map, so you can walk around it, into its footprint and behind its roof.
- For top-down characters, collide with the feet only: `hero.body.setSize(b.width - 4, 8).setOffset(b.x + 2, b.y + b.height - 8)` with `b = pixelforgeBody(...)`, so the head can overlap the top of a wall. `addPixelforgePlayer` does this for you.

## Phaser: the player
Don't write a movement controller. `addPixelforgePlayer` is the one the dashboard, the playtests and the game
all use, so what you test is what ships:
```js
import { addPixelforgePlayer } from './export/pixelforge.js';
const hero = addPixelforgePlayer(this, 80, 160, 'princess', { run: 150, jump: 340 });   // (x, y) = its origin
this.physics.add.collider(hero, groundLayer);
hero.on('pixelforge-land', () => this.cameras.main.shake(60, 0.002));   // also pixelforge-jump, pixelforge-attack
```
- The view comes from the sprite's export (the `topdown` and `overhead` classes imply theirs), or pass `{view}`.
  - **side:** walk, run (Shift), jump with coyote time, a jump buffer and variable height (release early for a hop).
    Animations: `idle`, `walk`, `run`, `jump_rise`, `jump_fall`, `jump_land` and `attack`. A missing one falls back to a
    simpler one (`run` → `walk` → `idle`). Options: `speed` 70, `run` 135, `jump` 330, `gravity` 900 (the player's
    total, whatever the world's), `coyote` 90 and `buffer` 120 (ms).
  - **topdown:** 4 directions with `playFacing`, a feet-only body, `attack_<down|up|side>`, and depth = y. Option `speed`.
  - **overhead:** 8 directions, rotated to face where it walks, a circle body from the body box, and `attack`.
- Keys: arrows/WASD to move, Space/Up/W to jump, Shift to run, X/J to attack. They fill `hero.controller.input`.
  Set `hero.controller.override = {right: true, run: true}` to drive it from code (cutscenes, playtests).
  `null` hands control back to the keyboard.
- `hero.controller.state()` returns `{x, y, vx, vy, onGround, facing, anim}`.
