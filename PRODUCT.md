# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Plain HTML/CSS/JS with no build step, shipped inside the pixelforge package (`pixelforge/assets/viewer/`) and served by `pixelforge serve` (Python stdlib `http.server`, default `http://127.0.0.1:8000/`). Every game gets it through the shared editable install after `git pull`. No Node is needed in games. Server-side additions (e.g. endpoints to save critiques) go in `pixelforge/__main__.py`'s `_Handler`.

## Users
One person: the game's developer, reviewing art that Claude authors. They open the dashboard on localhost while a Claude Code session works in the same project. Their job is to look at every asset in the game, spot what's wrong, and tell the AI precisely enough that it can fix it without back-and-forth. There are no logins and no other reviewers for now.

## Product Purpose
pixelforge is a text-grid pixel-art pipeline that an AI (Claude) authors and self-checks, exporting Phaser-ready sheets so the game needs no paid AI art. The dashboard is the human half of that loop. It shows everything in the game, lets the developer critique it in place, and gets those critiques to the AI, which fixes the art. Success: the developer finds a problem, critiques it in seconds, and sees the corrected art appear without writing a prompt or naming files and coordinates by hand.

## Positioning
The art is plain text that Claude writes and edits, and the dashboard is a review surface whose critiques go straight into the AI that owns that text. It is not a pixel editor: the human points and describes, and the AI draws.

## Operating Context
- The developer has the dashboard open next to a running Claude Code session in the game's art folder (the folder with `pixelforge.json`).
- The asset types today are character sprites (classes: small, humanoid, large, topdown, overhead; with animations, frames, layers and hurt/hit boxes) and tilesets (tiles, animated tiles, sample map). UI art and effects/particles are expected later, so the dashboard's structure must accept new asset types without a redesign.
- Data comes from `export/index.json`, `export/<name>.json|png` and the sprite folders. `pixelforge export` / `gallery` regenerate them. `export/gallery.html` is a separate, self-contained shareable page.
- Existing inspection aids: body/hurt/hit box overlays, origin mark, onion skin, rotation preview for overhead sprites, `/viewer/phaser.html` (sparring test), `/viewer/tilemap.html` (walk a character on a tileset's sample map).

## Capabilities and Constraints
- **Dashboard home** at the server root: everything in the game, grouped by asset type (sprites, tilesets; later UI art and effects). Sprites and tilesets are equal citizens in one browser, not separate pages.
- **Critiques** can target a spot or region on a frame, a whole frame, an animation, or a whole sprite/tileset.
- **Live hand-off:** critiques live in `critiques.json` at the art root (statuses: open → working → fixed). Claude Code runs `pixelforge critiques watch --once` in the background. It returns with every open critique and marks each one working. Claude then fixes the art and runs `pixelforge critiques done ID -m "note"`. The watcher's heartbeat (`previews/.critiques-watch`) tells the dashboard whether Claude is watching. The dashboard builds assets live from `sprites/` and polls `/api/state`, so fixes appear without an export or a reload.
- **After a fix:** the dashboard shows the updated art and marks the critique resolved. No before/after comparison or threaded conversation is required.
- **Inspection aids stay but are tucked away:** the default view shows the art. Boxes, origin and onion skin are opt-in toggles, and the Phaser and tilemap tests live behind an "in game" view per item.
- The viewer must keep working with no build step, from the package's assets folder, for every game.

## Brand Commitments
Name: pixelforge (lowercase). Look: a conventional dark dev-tool dashboard at the craft level of Linear and Vercel (chosen 2026-11-10 over themed directions). Keep it familiar and quiet, and let the art be the only loud thing on screen.

## Evidence on Hand
Demo project in this repo: `sprites/knight`, `knight_topdown`, `knight_overhead`, and the `terrain` tileset, with exports in `export/`. There are no other users, testimonials or metrics, and none should be invented.

## Product Principles
1. **Art first, text last.** The asset is the interface. Cut instructional copy, command reminders and explanations that the developer already knows. The current UI has far too much of it.
2. **Point, don't describe.** A critique should carry its exact target (sprite, animation, frame, region) so the AI never has to guess where the problem is.
3. **One place for everything in the game.** Every asset type lives in one consistent hierarchy, and a new type slots in without a new page.
4. **Close the loop visibly.** Open, in-progress and fixed critiques are always obvious, and fixed art shows up without a manual refresh ritual.
5. **Depth on demand.** Technical inspection (boxes, origin, in-game tests) is one toggle away, never in the way.
