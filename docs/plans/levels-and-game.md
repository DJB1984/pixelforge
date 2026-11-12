# Plan: whole levels, a game starter, screen previews, playtesting

Written 2026-11-11 against pixelforge 0.8.0 (`origin/main` 8f3fadf). The goal is for pixelforge + Phaser to let
Claude build a whole game: **write a level as text, see whole screens, play it, fix it**. Today Claude can make
every asset, but it can't put them together, look at the result, or play it.

Follow the phases in order. Each phase ends with tests passing, the guide updated, a commit and a push of the
work branch. Don't merge to `main` or tag unless the user says to. Ask at the end of a phase whether to release it.

---

## 0. Before starting (every session)

1. `EnterWorktree` (name e.g. `levels`). It branches from `origin/main`. While this plan lives only on branch
   `plan-levels-and-game`, run `git fetch origin` then `git reset --hard origin/plan-levels-and-game` in the fresh
   worktree (it's `main` plus this file), or `git merge origin/plan-levels-and-game` if `main` has moved past it.
   The shared checkout at `C:\Users\davis\dev\claude projects\pixel_art` may hold another session's uncommitted
   work: don't touch it.
2. Read `CLAUDE.md` (dev notes) and `pixelforge/assets/CLAUDE.md` (the per-game guide). Skim the modules this
   phase touches: `model.py`, `export.py`, `validate.py`, `render.py`, `server.py`,
   `assets/phaser/pixelforge.js`, `assets/viewer/{app.js,tilemap.html,platformer.html}`.
3. Run the tests **from the worktree root**: `python -m unittest discover -s tests -t tests`. The editable install
   points at the shared checkout, so running Python from anywhere else imports the *wrong* pixelforge. The same
   goes for `python -m pixelforge ...`: always run it from the worktree root.
4. Find the phase to do next: `git log --oneline origin/main` and this file's checkboxes (tick them as you go and
   commit the ticks).

### Gotchas learned building 0.7.0
- The worktree guard rejects bash heredocs that run Python, `git -C <shared checkout>`, and long `&&` chains with git
  in them. Write helper scripts to `$CLAUDE_JOB_DIR/tmp/*.py`, run them with `python <path>` from the worktree root,
  and keep git commands simple (one per call, `git -C <worktree>` is fine).
- `gh` isn't installed: push the branch and give the user the `.../pull/new/<branch>` URL.
- Phaser in the viewer pages: `https://cdn.jsdelivr.net/npm/phaser@3.90.0/dist/phaser.min.js`.
  - For an Arcade `StaticBody`: `body.setSize(w, h, false).setOffset(x, y)`.
  - `scrollFactor(0)` objects under a zoomed camera drift off-screen: draw the HUD in its own scene/camera at zoom 1.
- Browser checks (Claude in Chrome):
  - Start the dashboard in the background from the worktree: `python -m pixelforge serve --port 8765`.
  - A screenshot right after navigating can be blank: wait or re-take it.
  - Add `?v=N` to dodge the cache.
  - Read game state with `javascript_tool` (expose `window.pixelforgeGame` and friends).
  - Stop the server afterwards: PowerShell `Get-CimInstance Win32_Process ... | Stop-Process`.
- `export/` is committed. Before committing, run `python -m pixelforge upgrade`, which re-exports everything and
  rebuilds `export/gallery.html`.
- Node-side helper tests live in `tests/phaser_helper.test.mjs`. They're mock-scene checks with the
  `check(name, got, want)` pattern, run by `tests/test_phaser_helper.py`.
- Release (only when the user says): bump `__version__` in `pixelforge/__init__.py` (minor for features), update
  `pixelforge/assets/CLAUDE.md`, commit, then:
  - `git push origin <branch>:main` (fast-forward; if `main` moved, rebase on it first),
  - `git tag -a v<ver> -m "..." <sha>`,
  - `git push origin v<ver>`.

---

## Phase 1: Shared game runtime in `pixelforge.js`
Everything after this (level Play tab, game starter, playtests) uses one player controller and one loader, so the
dashboard, the playtest and the real game behave identically.

- [x] **`loadPixelforgeAll(scene, baseUrl = 'export/')`**: queues `index.json`, then, in its `filecomplete`
  handler, every asset by kind. `sprites`/`props` use `loadPixelforge`, `tilesets` use `loadPixelforgeTiles`,
  `icons` `loadPixelforgeIcons`, `fonts` `loadPixelforgeFont`, and later `levels`. Adding files during
  a load is supported in Phaser 3. Also add **`createPixelforgeAll(scene)`**, which creates the anims for every
  sprite and prop in the cached index.
- [x] **`addPixelforgePlayer(scene, x, y, name, opts)`** returns the sprite with `.controller`. It reads
  `opts.view` (default: the export's `meta.pixelforge.view`) and has three modes:
  - **side**: lift the logic out of `assets/viewer/platformer.html`: walk/run (Shift), coyote time, jump buffer,
    variable jump height, and animation choice from motion (`idle/walk/run/jump_rise/jump_fall/jump_land/attack`,
    with fallbacks). Gravity, speed and jump come from opts.
  - **topdown**: 4-direction walk with `playFacing`, a feet-only body (as `tilemap.html` does), and
    `attack_<dir>`. Depth = y every frame.
  - **overhead**: 8-direction, rotate to face the velocity, `body.setCircle` from the body box, `attack`.
  - Input goes through `controller.input = {left, right, up, down, jump, run, attack}`, filled from the keyboard
    (arrows/WASD, Space/Up/W jump, Shift run, X/J attack) **unless `controller.override` is set**. The override is
    how playtests drive it.
  - Emits `pixelforge-land`, `pixelforge-attack`, `pixelforge-jump`.
- [x] Refactor `platformer.html` and `tilemap.html` to use `addPixelforgePlayer`, so behaviour stays the same and
  the inline controller code goes away.
  - `platformer.html` also gains `?prop=` (stand a side-view prop on its ground) so side-view props get an
    "In game" tab. Update `hasGame()` in `app.js`: side-view props → `platformer.html?prop=`.
- [x] Node tests: loader queues the right files from a mock index; controller picks anims from velocity/onGround;
  the override replaces keyboard input; coyote/buffer timing.
- [x] Guide: a "Phaser: the player" section; update the Phaser usage block.

**Done when** both viewer pages play exactly as before (check in Chrome), the knight and the princess both work,
and the tests pass.

---

## Phase 2: Levels as text (the core)
New module `pixelforge/level.py`, with `levels/<name>.json` at the project root (a sibling of `sprites/`).

### Format
```json
{
  "name": "village",
  "view": "topdown",
  "tileset": "terrain",
  "background": {"color": "#63c74d"},
  "accents": [{"prop": "cloud", "at": [40, 20]}],
  "legend": {"g": "grass", "~": "auto:water", "#": "wall"},
  "layers": [
    {"name": "ground", "rows": ["gggg~~~~gggg", "..."]},
    {"name": "decor",  "rows": ["..f......t.."]},
    {"name": "above",  "rows": ["............"], "above": true}
  ],
  "stamps": [{"stamp": "pond", "at": [4, 6], "layer": "ground"},
             {"tileset": "house_tiles", "stamp": "house", "at": [10, 2]}],
  "objects": {
    "legend": {"H": {"prop": "house", "snap": "left"},
               "c": {"prop": "chest", "state": "closed", "props": {"loot": "key"}},
               "s": {"sprite": "slime", "type": "enemy"},
               "@": {"type": "spawn", "name": "player"},
               "D": {"type": "door", "to": "inn", "size": [1, 1]}},
    "rows": ["............", "..@...c....."],
    "list": [{"prop": "sign", "at": [123, 88], "props": {"text": "Welcome"}}]
  },
  "player": "knight_topdown",
  "camera": {"zoom": 3}
}
```
- **Tile layers:**
  - Rows are characters through `legend`. The legend defaults to the tileset's sample legend, and values can be
    `"tile"`, `{"tileset": "kit", "tile": "roof"}` or `"auto:<terrain>"` (see autotiling).
  - `' '`/`.` = empty. Every layer has the same size.
  - `"above": true` layers draw over characters.
- **Objects:** the char in `objects.rows` puts the object's origin at that cell's **bottom-centre**.
  - `"snap": "left"` aligns the prop's canvas left edge to the cell's left edge (for tile-sized buildings), and
    `"offset": [dx, dy]` nudges it.
  - `objects.list` places objects by pixel. `type` is free-form (`enemy`, `spawn`, `door`, `trigger`, `item`...).
    `props` passes through to the game.
- `view` and `camera.zoom` default from `pixelforge.json`; `resolution` comes from `pixelforge.json`.

### Autotiling (small gap: autotiling)
- [x] Add a tileset key `"autotile": {"water": {"base": "water", "edges": {"n": "water_n", "s": "water_s",
  "e": "...", "w": "...", "ne": "...", ...}}}`.
- [x] When building a level, each `auto:water` cell takes a 4-bit mask of which N/S/E/W neighbours aren't water,
  then picks the most specific edge tile that exists (`ne` > `n` > base).
- [x] Bake the result into the exported map, so the game doesn't need to know about autotiling. Tiled wangset export
  is out of scope (note it as later).

### Python
- [x] `level.py`: `Level.load(name)` (validates the shape, resolves the legend, stamps and autotiles into per-layer
  index grids, and resolves objects to pixel positions); `list_levels()`.
- [x] `check` lints levels too, with errors for:
  - unknown chars, missing tilesets/tiles/props/sprites/stamps, ragged rows, layers of different sizes;
  - a level with no `spawn`, or a spawn on a colliding tile or inside a solid footprint;
  - a door `to` a missing level.
- [x] `check` also warns when objects' solid footprints overlap each other, and for **reachability** (top-down and
  overhead): flood-fill from the spawn over cells that aren't colliding and aren't covered by solid footprints,
  then list unreachable doors, items and chests. Side view: just an info line (platform reachability is out of
  scope).
- [x] Export `export/levels/<name>.json` as a Tiled map (orthogonal JSON):
  - tile layers as gids, with the tilesets **embedded** (Phaser can't read external ones);
  - one `objectgroup` "objects" (each object with name, class=type, x, y, w, h, and properties `prop`/`sprite`/
    `state` plus custom `props`);
  - map properties carrying `background`, `accents`, `player`, `camera`, `view`.
- [x] Add `levels` to `export/index.json`, and make `export --all` / `upgrade` include levels.
- [x] CLI: `new-level NAME [--size 40x23] [--tileset terrain]` scaffolds one screen of ground plus a spawn, and
  `list` shows levels.

### Phaser
- [x] `loadPixelforgeLevel(scene, name)` (also called by `loadPixelforgeAll`) does `tilemapTiledJSON` from
  `levels/<name>.json`.
- [x] `pixelforgeLevel(scene, name, {player})` does all of this and returns
  `{map, layers, player, objects, props, sprites, spawns, triggers}`:
  - background color (or a gradient drawn as a fixed `Graphics`), and accents through `addPixelforgeProp`;
  - layers with properties, collision and animation; `above` layers at depth 1e5;
  - props, and sprites at their spots playing idle;
  - the player at `spawn` via `addPixelforgePlayer`, with colliders against layers and solid props;
  - camera bounds/follow/zoom;
  - door/trigger zones that emit `pixelforge-trigger` (object) on overlap.
- [x] Node tests with a mock map.

### Demo
- [x] `levels/village.json`: top-down, on terrain, with the house, chest, knight_topdown, a pond stamp, a door and
  2 screens wide.
- [x] `levels/meadow.json`: side view, with the princess. This needs a small **side-view tileset** `platforms`
  (16×16: grass-topped ground, dirt fill, left/right ledges, a floating platform, a one-way plank) drawn with the
  authoring loop, plus cloud accents.

**Done when** both levels pass `check`, export, and load in Phaser via `pixelforgeLevel` (verify in Chrome:
collisions, roof walk-behind, the door trigger fires, the princess runs and jumps across `meadow`).

---

## Phase 3: See whole screens, and the Levels page in the dashboard
### Screens (CLI)
- [ ] `level NAME` → `previews/level_<name>.png`: the whole level at 1x and zoomed to fit ~1400px, composited like
  the game (background, parallax accents, tile layers, objects y-sorted, `above` layers), with a faint grid of
  screen-sized rectangles (`resolution` / zoom) and object labels.
- [ ] `level NAME --screens` → `previews/level_<name>_screens.png`: each camera-sized screen at 1x and 2x, as the
  player would see it.
  - Parallax accents are offset by `-cam * scroll`, the HUD is drawn on top (below), and each screen is numbered.
  - Per screen it reports: colors on screen, the player sprite's contrast against the ground under it (reuse
    `context.py`), and objects visible.
- [ ] `level NAME --at X,Y` renders one screen centred on a tile.
- [ ] **HUD mock** (optional `"hud"` in `pixelforge.json`), the same data the starter's HUD scene reads:
  ```json
  "hud": [{"icon": "ui:heart", "at": [4, 4], "repeat": 3, "step": 10},
          {"text": "font:GOLD 120", "at": [4, 18]},
          {"panel": "ui:panel", "at": [0, 140], "size": [320, 40]}]
  ```
  Add Phaser `addPixelforgeHud(scene)`, which builds it (in its own scene).

### Dashboard
- [ ] Server: levels in `/api/project` (type `level`), `levels/*.json` in `project_sig`/`asset_sig`,
  `/live/levels/<name>.json` (the Tiled map built live) and `/live/level/<name>.png` (the rendered level,
  cached by signature). Add `levels` to `/live/index.json`.
- [ ] `app.js`: a **Levels** section in `TYPES` (first in the nav).
  - The level page shows the rendered level with zoom/pan, a "screens" overlay toggle, a "Screen N" stepper, and
    an object list (click → highlight).
  - Critiques target `{"asset": name, "level": true, "region": [x, y, w, h]}` in level pixels. Extend
    `critiques.py` (`clean_target`, `details`, `render_target`) for levels: details list the tiles and objects
    under the region.
  - A **Play** tab with `/viewer/play.html?level=NAME&embed=1`.
- [ ] `assets/viewer/play.html`: loads everything from `/live/`, does `pixelforgeLevel` + `addPixelforgeHud`,
  and shows controls help. It exposes `window.pixelforgeGame` and `window.pixelforgePlay` (see Phase 5).
- [ ] Gallery: a levels section (the rendered PNG plus a screen strip).

**Done when** Claude can run `level village --screens`, Read the PNG, and judge composition; and the developer can
open the level in the dashboard, pin a critique on a spot, and play it.

---

## Phase 4: Game starter (`pixelforge game`)
- [ ] `pixelforge game [--force]`, run in a pixelforge project root, scaffolds a Phaser + Vite game around the art
  folder. It never overwrites existing files without `--force`, and the files are game-owned (not managed by
  `upgrade`).
  - `package.json`: `phaser@3.90.0`, `vite` pinned to a release at least 2 weeks old; scripts `dev`, `build`.
  - `vite.config.js`: `publicDir: 'export'`, so URLs are `/<name>.png` with `baseUrl ''`, and
    `server.port: 5173`.
  - `index.html`
  - `src/main.js`: config from `pixelforge.json` (resolution, `pixelArt: true`, `zoom`, Arcade physics with
    gravity for the side view).
  - `src/scenes/Boot.js`: `loadPixelforgeAll` + a progress bar.
  - `src/scenes/Level.js`: `pixelforgeLevel(this, startLevel)`. It handles door triggers → load the next level, and
    a dev-only `window.pixelforgePlay` hook.
  - `src/scenes/Hud.js`: `addPixelforgeHud`.
  - `src/game.js`: a small state object (health, coins, inventory) with an event bus.
  - Import the helper from `../export/pixelforge.js`, and pixelforge.json via Vite's JSON import.
  - A `.gitignore` for `node_modules/` and `dist/`.
- [ ] Guide: a "Building the game" section. `npm install && npm run dev` runs the game; `pixelforge serve` is the
  art dashboard. The game reads `export/`, so run `export` after art changes (an auto-exporting watch mode is out
  of scope). Describe how to add enemies (an object type → a class in `src/`), items and doors.
- [ ] Test: scaffold into a temp dir; files exist; `package.json` is valid; re-running doesn't overwrite. If Node
  and npm are installed, `npx vite build` succeeds (skip otherwise; a slow test is fine behind an env flag).

**Done when** a fresh `pixelforge init --view topdown` + `new` art + `new-level` + `pixelforge game` +
`npm install && npm run dev` gives a walkable game in the browser (verify in Chrome).

---

## Phase 5: Playtesting by Claude (`pixelforge play`)
- [ ] Add an optional dependency in `pyproject.toml`:
  `[project.optional-dependencies] play = ["playwright>=1.40"]`. When it's missing, the command explains
  `pip install -e ".[play]" && playwright install chromium`.
- [ ] Add `window.pixelforgePlay` to `play.html` and the starter's Level scene:
  - `ready` (a promise);
  - `freeze()`: `game.loop.sleep()`, then step manually with `game.step(t, 1000/60)` for determinism;
  - `step(ms, input)` sets `player.controller.override` and advances frames;
  - `state()` → `{x, y, vx, vy, onGround, facing, anim, health?, events: [...]}`, where events are triggers,
    hits, lands and attacks since the last call.
- [ ] `pixelforge play LEVEL [--script FILE|"..."] [--url URL] [--shot-every 250ms]`:
  - With no `--url`, it starts the dashboard server in a thread on a free port and opens `play.html?level=..&test=1`
    in headless Chromium (Playwright). The script language has one action per line or `;`:
    `right 1.5s`, `right+run 800ms`, `jump`, `right+jump 300ms`, `wait 1s`, `attack`, `shot`,
    `expect onGround`, `expect x > 200`, `expect trigger door`.
  - Outputs go to `previews/play_<level>/`: `NN.png` canvas screenshots, a contact sheet
    `previews/play_<level>.png` (frames with time and state), and `log.json`.
  - It prints a summary with notes: stuck (input held for 1s and no movement), fell out of the world, never
    landed, expectations passed/failed (exit code 1 on failure), and triggers fired.
  - With `--url http://localhost:5173`, it drives the real game through the same hook.
- [ ] Tests: script parser unit tests; summary-note logic on a canned log; an integration test that runs `meadow`
  for 2s, skipped unless Playwright is installed.
- [ ] Guide: "Playtest every level change": the loop is `level --screens` → `play` with a script that walks the
  intended route → read the contact sheet → fix.

**Done when** `pixelforge play meadow --script "right+run 2s; jump; right 1s; shot"` produces a contact sheet
showing the princess crossing the gap, with a passing `expect`.

---

## Phase 6: Smaller gaps
- [ ] **Effects:** `"type": "fx"`: like a prop, but animations are one-shot, there are no hurtboxes, and the
  layer defaults to `front`. Add `spawnPixelforgeFx(scene, x, y, name, anim?)`, which plays the effect and then
  destroys it. Demo `sprites/fx_hit` (spark, 4 frames) and `fx_dust` (landing puff); the side-view controller spawns
  `fx_dust` on land when it exists.
- [ ] **Variants:** sprite.json `"variants": {"slime_blue": {"palette": {"g": "blue", "G": "navy"}}}` exports
  each variant as its own sheet with tags renamed (`slime_blue_idle`). It's listed in `list`, the gallery and the
  dashboard (grouped under the base sprite), and usable in levels.
- [ ] **Game feel:** `pixelforgeFeel(scene)` → `shake(ms, px)`, `hitStop(ms)` (pause physics and anims briefly),
  `flash(sprite, ms)` (`setTintFill` white), `knockback(target, from, speed)`. Use them in the starter's
  attack → hit example.
- [ ] **Dialog box:** `pixelforgeDialog(scene, {panel: 'ui:panel', font: 'font', text, speed})` makes a nine-slice
  box with typewriter text that pages on the action key. It returns a promise and is triggered by a `sign`/NPC
  object's `props.text` in the starter.
- [ ] Node tests for each helper; guide sections.

---

## Release suggestion
Phases 1–3 make 0.9.0 (the big one: levels you can see and play), Phase 4 is 0.10.0, Phase 5 0.11.0, and
Phase 6 0.12.0. Ask the user before each merge/tag. Sound effects are out of scope (the user's call, 2026-11-11).
