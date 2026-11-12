import Phaser from 'phaser';
import project from '../pixelforge.json';
import { Boot } from './scenes/Boot.js';
import { Level } from './scenes/Level.js';

// The screen comes from pixelforge.json: "resolution" is the game's size before scaling, "zoom" (default 3)
// how many screen pixels each game pixel gets. Whole zooms keep the pixels square.
const [width, height] = project.resolution ?? [320, 180];

const game = new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  width,
  height,
  zoom: project.zoom ?? 3,
  pixelArt: true,
  backgroundColor: '#181425',
  physics: {
    default: 'arcade',
    // the side view falls; the player's own gravity is set by its controller (`gravity` in playerOptions)
    arcade: { gravity: { x: 0, y: project.view === 'side' ? 900 : 0 } },
  },
  scene: [Boot, Level],
});

if (import.meta.env.DEV) window.pixelforgeGame = game;
