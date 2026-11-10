# Design: pixelforge dashboard

Recorded from the built dashboard (`pixelforge/assets/viewer/app.css`, `app.js`). The tokens live as custom properties on `:root` in app.css. Change them there, not per component.

## Direction
A conventional dark developer tool at the craft level of Linear and Vercel. The chrome is quiet, neutral and familiar so the pixel art is the only saturated thing on screen. It's dark because the dashboard sits next to a dark Claude Code terminal, and the art is judged against neutral mid-dark grounds.

## Color
| token | value | use |
|---|---|---|
| `--bg` | #0d0e10 | app background, frame strip |
| `--side` | #111215 | sidebar and critique rail (a second neutral layer) |
| `--surface` / `--raised` | #16171a / #1c1d21 | cards and lists / buttons, menus, group heads |
| `--stage` | #141518 | behind the art |
| `--line` / `--line-2` | white 7% / 12% | hairlines / control outlines |
| `--fg` / `--fg-2` / `--fg-3` | #ededef / #a3a6ad / #82858d | text: primary, secondary, tertiary (all ≥4.5:1 on their grounds) |
| `--accent` / `--accent-fg` | #6c76f4 / #a3a9ff | the primary action, the current selection, focus rings, critique count badges. Nothing decorative |
| `--working` | #f0b429 | Claude is fixing |
| `--fixed` | #4cc38a | fixed, Claude is watching |
| `--danger` | #f2626a | errors, a sprite that won't load |

Art overlays keep pixelforge's established colors: body box #fac828 (dashed), hurtbox #28c85a, hitbox #f0283c, origin #ff00c8, onion skin red for the previous frame and blue for the next. The default checker is #1e1f23/#26272c.

## Type
Inter (Google Fonts) with a system-ui fallback, at a 13px base. Weights are 400, 500 for labels and nav, and 600 for titles. Page titles are 20px and section heads 13px/600. Numbers use tabular figures. Monospace (`--mono`) is only for error text and the live coordinate readout.

## Shape and depth
The radius is 6px on controls and 10px on cards, menus and the toolbar. Depth comes from 1px inset outlines, plus a soft offset shadow (`--pop`) on floating things only: the stage toolbar, menus and toasts. There are no hard shadows and no gradients. Transitions are 150ms, and entrances use `--ease` (expo out).

## Layout
A three-column shell: sidebar (232px) | main | critique rail (344px). The rail only appears on an asset page. Below 1180px the columns narrow. Below 900px everything stacks: the sidebar becomes a sticky top bar with a horizontally scrolling nav, and the rail moves under the stage.

## Components
- **Sidebar.** The workspace mark (a pixel diamond) and the game's name. Overview and Critiques come first, then one group per asset type (`TYPES` in app.js; a new type is one entry there), each row with a 1x thumbnail cropped to the art and an open-critique badge. The footer shows whether Claude is watching: a grey, green (watching) or pulsing amber (fixing) dot.
- **Asset page.** Tabs (animations, or Sample map / Tiles, plus In game on the right). Then the stage, with the art centred at an integer zoom that refits on resize until the user zooms. A floating toolbar holds play, step, the frame readout, zoom, ground, facing (overhead sprites) and overlays. The frame or tile strip sits at the bottom; sprite thumbnails share one crop so motion reads across them.
- **Spot selection.** Drag on the art to mark a spot: marching ants (white dashes over black). On the sample map, a single click marks that whole tile. Open critiques' spots are drawn on the stage as outlined boxes with a `#id` tag: white when open, amber when working, accent when focused.
- **Composer.** A segmented scope control (Spot / Frame / Animation / Sprite, or Spot / Tile / Tileset, or Spot / Tileset on the map), a target line showing exactly what's being critiqued, a textarea, and Send to Claude (Ctrl/⌘ ↵).
- **Critique row.** A status icon (open: dashed circle; working: half-filled amber; fixed: green check), the text, then `#id · target · age`, and Claude's note after a fix. On the right sits a thumbnail of the exact frame, tile or map area with the spot outlined. Reopen and delete appear on hover. Clicking a row jumps to its target and highlights its spot.
- **Toasts.** Bottom right, for critique saved, Claude fixed #n, and asset updated. When a fix lands on the asset you're viewing, the stage glows green once. That's the dashboard's one motion moment.
