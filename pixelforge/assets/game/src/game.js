import Phaser from 'phaser';

// What the player carries between levels, and an event bus for it. Scenes come and go (a door restarts
// the level scene); this object stays. Change it only through these functions, so the HUD hears about it:
//   bus.on('change', (state, key) => ...)    after every change (`key` is what changed)
//   bus.on('dead', () => ...)                health reached 0
export const bus = new Phaser.Events.EventEmitter();

const START = { health: 3, maxHealth: 3, coins: 0, inventory: [] };
export const state = structuredClone(START);

function changed(key) { bus.emit('change', state, key); }

export function reset() {
  Object.assign(state, structuredClone(START));
  changed('all');
}

export function damage(n = 1) {
  if (state.health <= 0) return;
  state.health = Math.max(0, state.health - n);
  changed('health');
  if (state.health === 0) bus.emit('dead');
}

export function heal(n = 1) {
  state.health = Math.min(state.maxHealth, state.health + n);
  changed('health');
}

export function addCoins(n = 1) {
  state.coins += n;
  changed('coins');
}

export function addItem(name) {
  state.inventory.push(name);
  changed('inventory');
}

export const hasItem = (name) => state.inventory.includes(name);
