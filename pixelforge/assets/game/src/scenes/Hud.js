import { addPixelforgeHud } from '../../export/pixelforge.js';
import { bus, state } from '../game.js';

// The HUD is pixelforge.json's "hud": addPixelforgeHud runs it as its own scene on top (zoom 1, never
// scrolls), the same picture `pixelforge level NAME --screens` draws. This file says which item shows
// which part of the game state: one line per HUD item that has an "id". A repeated icon shows that many
// copies (hearts); text shows the string.
export const HUD_BINDINGS = {
  hearts: (s) => s.health,
  health: (s) => s.health,
  coins: (s) => String(s.coins),
  gold: (s) => String(s.coins),
};

// Call in the level scene's create; it rebuilds the HUD after every level restart.
export function showHud(scene) {
  const hud = addPixelforgeHud(scene);
  const refresh = () => {
    for (const [id, value] of Object.entries(HUD_BINDINGS)) hud.set(id, value(state));
  };
  refresh();
  bus.on('change', refresh);
  scene.events.once('shutdown', () => bus.off('change', refresh));
  return hud;
}
