# pixelforge (tool repo)

This repo is the pixelforge tool **and** a demo project (the knight). Games use it with
`pip install -e "<path to this folder>"` and then `pixelforge init` in their own art folder.
That copies the guide below into the game as its CLAUDE.md.

## Developing the tool
`pixelforge/grid.py` (Grid ops) · `model.py` (project root discovery, sprite.json loading, frame resolution) ·
`render.py` · `validate.py` · `export.py` · `importer.py` · `gallery.py` · `__main__.py` (CLI).
`pixelforge/assets/` ships with the package: `viewer/`, `phaser/pixelforge.js`, `gallery.html` template,
default `game.json` palette, and `CLAUDE.md` (the per-game guide; keep it in sync with CLI changes).
Tests: `python -m unittest discover -s tests -t tests`.

## Making art (applies to this repo's demo sprites too)
@pixelforge/assets/CLAUDE.md
