import Phaser from 'phaser';
import { loadPixelforgeAll, createPixelforgeAll, PIXELFORGE_INDEX } from '../../export/pixelforge.js';

// Loads everything `pixelforge export` wrote (export/index.json lists it) with a progress bar, makes every
// animation, then starts the first level: ?level=NAME in the URL, else a level called "start", else the
// first one in the index.
export class Boot extends Phaser.Scene {
  constructor() { super('boot'); }

  preload() {
    const { width, height } = this.scale;
    const w = Math.round(width / 2), x = Math.round((width - w) / 2), y = Math.round(height / 2);
    this.add.rectangle(x, y, w, 6).setOrigin(0, 0.5).setStrokeStyle(1, 0x5a6988);
    const bar = this.add.rectangle(x + 1, y, 0, 4, 0xfeae34).setOrigin(0, 0.5);
    this.load.on('progress', (p) => { bar.width = Math.round((w - 2) * p); });
    loadPixelforgeAll(this, '');
  }

  create() {
    createPixelforgeAll(this);
    const levels = this.cache.json.get(PIXELFORGE_INDEX)?.levels ?? [];
    const asked = new URLSearchParams(location.search).get('level');
    const first = [asked, 'start'].find((n) => levels.includes(n)) ?? levels[0];
    if (!first) {
      this.add.text(8, 8, 'No levels yet.\nRun: pixelforge new-level start\nthen: pixelforge export',
                    { fontFamily: 'monospace', fontSize: '10px', color: '#c0cbdc' });
      return;
    }
    this.scene.start('level', { level: first });
  }
}
