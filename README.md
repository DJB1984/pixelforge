# pixelforge

Free, text-based pixel art + animation pipeline built for an AI (Claude) to author and self-check, exporting sprite sheets for Phaser.

## Install once
```
pip install -e "C:\Users\davis\dev\claude projects\pixel_art"
```
This gives you `python -m pixelforge` everywhere, and a `pixelforge` command if Python's user Scripts folder is on your PATH.
Editable install: changes to this repo apply to every game straight away.

For `pixelforge play` (Claude playtests levels in a headless browser), add the optional extra once:
```
pip install -e "C:\Users\davis\dev\claude projects\pixel_art[play]"
playwright install chromium
```

## Per game
```
cd my-game/art
pixelforge init --name "My Game"     # pixelforge.json, sprites/, palettes/, CLAUDE.md
```
Then ask Claude, e.g. *"make a 32x32 slime enemy with idle, hop and hurt animations"* or *"make a 16x16 dungeon tileset: floor, cracked floor, walls, a door"*. The CLAUDE.md that `init` wrote tells it the format, the render → look → fix loop and the pixel-art rules.

```
pixelforge export --all      # export/<name>.png + .json + pixelforge.js (for Phaser; tilesets export as Tiled tilesets)
pixelforge gallery           # export/gallery.html: one file, every character and tileset, send it to anyone
pixelforge serve             # the dashboard: http://127.0.0.1:8000/
```

## Reviewing art
`pixelforge serve` opens a dashboard of every sprite and tileset in the game, built live from the text grids, so you see
Claude's edits as they land. Mark what's wrong (drag on the art to mark a spot, or pick a frame, animation, tile or the
whole asset), type a critique, and send it. In Claude Code, say *"watch for pixelforge critiques and fix them"* (the
dashboard's **Copy prompt** link copies that). Claude picks each critique up, fixes the art and leaves a note on it, and the
dashboard shows the critique as fixed. Critiques are kept in `critiques.json` at the art root.

## Updating
```
cd pixelforge && git pull        # the editable install picks it up immediately, for every game
cd my-game/art && pixelforge upgrade
```
`upgrade` brings one game up to the installed version:
- Refreshes its Claude guide (`CLAUDE.md`) if nobody edited it. If someone did, it leaves that file alone and writes `CLAUDE.pixelforge-new.md` next to it to merge by hand.
- Adds any missing standard pieces (folders, palette, size classes) without touching the game's own files.
- Re-exports every sprite and rebuilds the gallery.
- Records the version in `pixelforge.json`.

`--dry-run` shows what would change. Re-run `pip install -e .` only if an update adds dependencies.
To hold a game on a known version, check out a release tag in the tool repo, e.g. `git checkout v0.3.0`.

This repo is also a demo project (the knight). Its `CLAUDE.md` covers working on the tool itself.
