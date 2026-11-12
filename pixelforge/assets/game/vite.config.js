import { defineConfig } from 'vite';

// export/ (what `pixelforge export` writes) is served as the site root: export/knight.png is /knight.png,
// so the game loads its art with baseUrl ''. `npm run build` copies it into dist/ next to the game.
export default defineConfig({
  base: './',
  publicDir: 'export',
  server: { port: 5173 },
  build: { outDir: 'dist', assetsInlineLimit: 0, chunkSizeWarningLimit: 2000 },
});
