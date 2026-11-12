# pixelforge (tool repo)

This repo is the pixelforge tool **and** a demo project (the knight). Games use it with
`pip install -e "<path to this folder>"` and then `pixelforge init` in their own art folder.
That copies the guide below into the game as its CLAUDE.md.

## Developing the tool
`pixelforge/grid.py` (Grid ops) · `model.py` (project root discovery, sprite.json loading, frame resolution) ·
`render.py` · `validate.py` · `export.py` · `importer.py` · `gallery.py` · `__main__.py` (CLI) ·
`level.py` (levels/<name>.json: legend, autotiling, stamps, objects, Tiled map export; lint in `validate.check_level`) ·
`screens.py` (`level` command: a level composited like the game, its screens, the pixelforge.json "hud" mock).
Dashboard: `server.py` (`serve`: live builds from sprites/, `/api/project`, `/api/state`, critique API) ·
`critiques.py` (critiques.json store, targets, `watch` hand-off to Claude, `show` pictures) ·
`assets/viewer/index.html` + `app.js` + `app.css` (no build step). Its product brief is PRODUCT.md, its look DESIGN.md.
Inspection for an AI that sees stills, not motion: `motion.py` (per-frame measurements, spacing/timing notes,
timeline chart) · `compare.py` (git ref vs working tree, pixel diff) · `context.py` (on real ground, grayscale, edge contrast).
`pixelforge/assets/` ships with the package: `viewer/`, `phaser/pixelforge.js`, `gallery.html` template,
default `game.json` palette, `font_5x7.txt` (the starter font `new --font` copies), and `CLAUDE.md`
(the per-game guide; keep it in sync with CLI changes).
`game.py` scaffolds the Phaser + Vite starter (`pixelforge game`) from `assets/game/` (game-owned files, never
upgraded; anything shared belongs in `pixelforge.js`). `project.py` handles `init`/`upgrade`. The per-game guide is the only managed file: pixelforge.json
records its name and sha256 so `upgrade` replaces it only when unedited. This repo sets `"guide": null`,
because its CLAUDE.md is this file, not a copy of the guide.
Tests: `python -m unittest discover -s tests -t tests`.

## Releasing
Every game shares the editable install, so a change reaches all of them on their next `git pull`.
1. Tests pass. If the CLI or data format changed, update `pixelforge/assets/CLAUDE.md` in the same change.
2. Bump `__version__` in `pixelforge/__init__.py` (pyproject reads it). Use minor for features, patch for fixes.
3. Commit, then `git tag -a v<version> -m "..."` and push the tag. Games run `pixelforge upgrade` after pulling.

## Making art (applies to this repo's demo sprites too)
@pixelforge/assets/CLAUDE.md
