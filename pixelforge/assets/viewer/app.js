// pixelforge dashboard. Everything comes from `pixelforge serve`:
//   /api/project  every asset, built live from sprites/ (no export needed)
//   /api/state    polled: source revision, critiques, whether Claude is watching
//   /api/critiques  POST a critique; `pixelforge critiques watch` hands it to Claude
// Routes: #/  ·  #/critiques  ·  #/a/<asset>[/<anim | tile | ~map | ~game>[/<frame>]]

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const enc = encodeURIComponent;
const MAC = /Mac|iPhone|iPad/.test(navigator.platform);
const PROMPT = 'Watch for pixelforge critiques and fix them';
const POLL_MS = 1500;
const REPEAT_PAUSE_MS = 500;

// ---------- icons (Lucide paths, 24px grid) ----------
const ICONS = {
  grid: '<rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/>',
  msg: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  box: '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z"/><path d="m3.3 7 8.7 5 8.7-5"/><path d="M12 22V12"/>',
  tiles: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/><path d="M15 3v18"/>',
  play: '<path d="M6 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L7.5 3.64A1 1 0 0 0 6 4.5z"/>',
  pause: '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
  left: '<path d="m15 18-6-6 6-6"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  undo: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
  game: '<line x1="6" x2="10" y1="11" y2="11"/><line x1="8" x2="8" y1="9" y2="13"/><line x1="15" x2="15.01" y1="12" y2="12"/><line x1="18" x2="18.01" y1="10" y2="10"/><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"/>',
  sliders: '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/>',
  image: '<rect width="18" height="18" x="3" y="3" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>',
  film: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
  map: '<path d="M14.106 5.553a2 2 0 0 0 1.788 0l3.659-1.83A1 1 0 0 1 21 4.619v12.764a1 1 0 0 1-.553.894l-4.553 2.277a2 2 0 0 1-1.788 0l-4.212-2.106a2 2 0 0 0-1.788 0l-3.659 1.83A1 1 0 0 1 3 19.381V6.618a1 1 0 0 1 .553-.894l4.553-2.277a2 2 0 0 1 1.788 0z"/><path d="M15 5.764v15"/><path d="M9 3.236v15"/>',
  copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
  ground: '<path d="M2 20h20"/><path d="m5 20 4-8 3 4 2-3 5 7"/><circle cx="16" cy="6" r="2"/>',
  compass: '<circle cx="12" cy="12" r="10"/><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z"/>',
  alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
  wifi: '<path d="M12 20h.01"/><path d="M8.5 16.429a5 5 0 0 1 7 0"/><path d="M5 12.859a10 10 0 0 1 5.17-2.69"/><path d="M19 12.859a10 10 0 0 0-2.007-1.523"/><path d="M2 8.82a15 15 0 0 1 4.177-2.643"/><path d="M22 8.82a15 15 0 0 0-11.288-3.764"/><path d="m2 2 20 20"/>',
};
const icon = (n, cls = '') => `<svg class="i ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n]}</svg>`;
const STATUS_LABEL = { open: 'Open', working: 'Claude is fixing', fixed: 'Fixed' };
function stIcon(st) {
  const lbl = `role="img" aria-label="${STATUS_LABEL[st]}"`;
  if (st === 'fixed') return `<svg class="st-ico" viewBox="0 0 14 14" ${lbl}><circle cx="7" cy="7" r="6" fill="var(--fixed)"/><path d="m4.3 7.2 1.8 1.8 3.6-3.8" fill="none" stroke="#0d0e10" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  if (st === 'working') return `<svg class="st-ico" viewBox="0 0 14 14" ${lbl}><circle cx="7" cy="7" r="5.6" fill="none" stroke="var(--working)" stroke-width="1.5"/><path d="M7 3.4a3.6 3.6 0 0 1 0 7.2z" fill="var(--working)"/></svg>`;
  return `<svg class="st-ico" viewBox="0 0 14 14" ${lbl}><circle cx="7" cy="7" r="5.6" fill="none" stroke="var(--open)" stroke-width="1.5" stroke-dasharray="2.2 1.6"/></svg>`;
}
const MARK = `<svg viewBox="0 0 14 14" width="14" height="14" aria-hidden="true" shape-rendering="crispEdges">
  <rect x="5" y="1" width="4" height="2" fill="#a3a9ff"/><rect x="3" y="3" width="8" height="2" fill="#a3a9ff"/>
  <rect x="1" y="5" width="12" height="4" fill="#6c76f4"/><rect x="3" y="9" width="8" height="2" fill="#4a52c9"/>
  <rect x="5" y="11" width="4" height="2" fill="#4a52c9"/></svg>`;

// ---------- state ----------
const S = {
  project: null, assets: new Map(), crits: [], watching: false, rev: null, online: true,
  route: { page: 'overview' },
  view: { zoom: null, zoomFor: null, bg: 'check', boxes: false, origin: false, onion: false, grid: false, repeat: true, angle: 0, spin: false },
  play: { playing: true, frame: 0, acc: 0 },
  sel: null,            // [x, y, w, h] marked on the stage, in art pixels
  scope: null,          // composer scope picked by hand; null = follow the stage
  focus: null,          // critique highlighted on the stage
  pendingFocus: null,
  railFilter: 'active',
  draft: '',
  menu: null,
  lv: { for: null, screen: 0, obj: null, screens: true },   // the level page: current screen, highlighted object
};
let animators = [];

const TYPES = [   // asset types the dashboard knows; new kinds slot in here
  { type: 'level', label: 'Levels', icon: 'map', noun: 'level' },
  { type: 'sprite', label: 'Sprites', icon: 'box', noun: 'sprite' },
  { type: 'prop', label: 'Props & buildings', icon: 'box', noun: 'prop' },
  { type: 'fx', label: 'Effects', icon: 'box', noun: 'effect' },
  { type: 'tileset', label: 'Tilesets', icon: 'tiles', noun: 'tileset', cells: 'tiles' },
  { type: 'icons', label: 'UI & icons', icon: 'image', noun: 'icon set', cells: 'icons' },
  { type: 'font', label: 'Fonts', icon: 'tiles', noun: 'font', cells: 'glyphs' },
];
const typeLabel = (t) => TYPES.find((x) => x.type === t)?.label ?? 'Assets';
const cap = (s) => s[0].toUpperCase() + s.slice(1);
const typeInfo = (a) => TYPES.find((x) => x.type === a?.type) ?? TYPES[0];
// sprites, props and effects have animations (a prop's are its states); the other kinds are grids of named cells
const animated = (a) => a?.type === 'sprite' || a?.type === 'prop' || a?.type === 'fx';

// ---------- data ----------
async function api(path, opts = {}) {
  const r = await fetch(path, { cache: 'no-store', ...opts, headers: opts.body ? { 'Content-Type': 'application/json' } : undefined });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `${r.status} ${r.statusText}`);
  return data;
}
const loadImage = (src) => new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = src; });

async function loadProject() {
  const p = await api('/api/project');
  const changed = [];
  const next = new Map();
  await Promise.all(p.assets.map(async (a) => {
    const prev = S.assets.get(a.name);
    if (a.type !== 'error') {
      if (prev?.rev === a.rev && prev.img) a.img = prev.img;
      else { a.img = await loadImage(a.sheet); if (prev) changed.push(a.name); }
    } else if (prev && prev.type !== 'error') changed.push(a.name);
    next.set(a.name, a);
  }));
  S.assets = next;
  S.project = p;
  S.rev = p.rev;
  return changed;
}

async function poll() {
  try {
    const st = await api('/api/state');
    const wasOffline = !S.online;
    S.online = true;
    const before = new Map(S.crits.map((c) => [c.id, c]));
    let critChange = st.critiques.length !== before.size || st.watching !== S.watching;
    for (const c of st.critiques) {
      const b = before.get(c.id);
      if (!b || b.updated !== c.updated) critChange = true;
      if (b && b.status !== 'fixed' && c.status === 'fixed') toast(`Claude fixed #${c.id}`, 'check');
    }
    S.crits = st.critiques;
    S.watching = st.watching;
    if (st.rev !== S.rev) {
      const changed = await loadProject();
      render({ keep: true });
      const here = S.route.page === 'asset' && changed.includes(S.route.name);
      if (here) landed();
      if (changed.length && !here) toast(`${changed.join(', ')} updated`, 'check');
    } else if (critChange || wasOffline) {
      refreshCrits();
      if (wasOffline) renderTop();
    }
  } catch {
    if (S.online) { S.online = false; renderTop(); }
  }
  setTimeout(poll, POLL_MS);
}

// ---------- helpers ----------
const assetOf = (name) => S.assets.get(name);
const idleOf = (a) => a.anims.find((x) => x.name === 'idle' || x.name === 'idle_down') ?? a.anims[0];
const activeCrits = (pred = () => true) => S.crits.filter((c) => c.status !== 'fixed' && pred(c));
const critsFor = (name) => S.crits.filter((c) => c.target.asset === name);
const fmtFps = (f) => (f % 1 ? f.toFixed(1) : String(f));
function ago(iso) {
  const s = (Date.now() - Date.parse(iso)) / 1000;
  if (s < 45) return 'now';
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}
function targetText(t, withAsset = true) {
  const p = withAsset ? [t.asset] : [];
  if (t.anim) p.push(t.anim);
  if (t.frame != null) p.push(`frame ${t.frame}`);   // 0-based, like `pixelforge show`
  if (t.tile) p.push(t.tile);
  if (t.map) p.push('sample map');
  if (t.region) p.push(`${t.region[2]}×${t.region[3]} spot`);
  if (!withAsset && !p.length) p.push(`whole ${typeInfo(assetOf(t.asset)).noun}`);
  return p.join(' › ');
}
const targetIcon = (t) => (t.region ? 'scan' : t.level ? 'map' : t.frame != null || t.tile ? 'image' : t.anim ? 'film' : t.map ? 'map' : 'box');

function toast(msg, ico) {
  const el = document.createElement('div');
  el.className = 'toast';
  el.innerHTML = `${ico ? icon(ico) : ''}<span>${esc(msg)}</span>`;
  $('#toasts').append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 300); }, 2600);
}
function landed() {
  const w = $('.stage-wrap');
  if (!w) return;
  w.classList.remove('landed');
  void w.offsetWidth;
  w.classList.add('landed');
}

// ---------- painting ----------
let checkerPattern = null;
const patterns = new Map();
const scratch = document.createElement('canvas');

function sizeCanvas(c, w, h) {
  if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  const ctx = c.getContext('2d');
  ctx.imageSmoothingEnabled = false;
  return ctx;
}

function groundChoices() {
  const list = [{ id: 'check', label: 'Checker' }, { id: 'dark', label: 'Dark', color: '#0d0e10' }, { id: 'light', label: 'Light', color: '#e8e8ec' }];
  for (const a of S.assets.values()) {
    if (a.type !== 'tileset') continue;
    a.tiles.map((t, i) => ({ t, i })).filter(({ t }) => !t.props.collides && !/_[nsew]$/.test(t.name)).slice(0, 3)
      .forEach(({ t, i }) => list.push({ id: `tile:${a.name}:${i}`, label: t.name, group: a.name }));
  }
  return list;
}

function paintBg(ctx, W, H, z, id) {
  if (id?.startsWith('tile:')) {
    const [, ts, ti] = id.split(':');
    const a = assetOf(ts);
    if (a?.img) {
      const key = `${id}@${z}@${a.rev}`;
      let pat = patterns.get(key);
      if (!pat) {
        const c = document.createElement('canvas');
        const cx = sizeCanvas(c, a.w * z, a.h * z);
        const [sx, sy] = slotXY(a, +ti);
        cx.drawImage(a.img, sx, sy, a.w, a.h, 0, 0, a.w * z, a.h * z);
        pat = ctx.createPattern(c, 'repeat');
        patterns.set(key, pat);
      }
      ctx.fillStyle = pat;
      ctx.fillRect(0, 0, W, H);
      return;
    }
  }
  if (id === 'dark' || id === 'light') {
    ctx.fillStyle = id === 'dark' ? '#0d0e10' : '#e8e8ec';
    ctx.fillRect(0, 0, W, H);
    return;
  }
  if (!checkerPattern) {
    const c = document.createElement('canvas');
    const cx = sizeCanvas(c, 16, 16);
    cx.fillStyle = '#1e1f23'; cx.fillRect(0, 0, 16, 16);
    cx.fillStyle = '#26272c'; cx.fillRect(0, 0, 8, 8); cx.fillRect(8, 8, 8, 8);
    checkerPattern = ctx.createPattern(c, 'repeat');
  }
  ctx.fillStyle = checkerPattern;
  ctx.fillRect(0, 0, W, H);
}

function slotAt(a, i, t) {
  const seq = a.anims?.[String(i)];
  if (!seq) return i;
  const total = seq.reduce((s, x) => s + x[1], 0);
  let m = t % total;
  for (const [slot, ms] of seq) { if (m < ms) return slot; m -= ms; }
  return seq[0][0];
}
const slotXY = (a, s) => [(s % a.cols) * (a.w + a.spacing), Math.floor(s / a.cols) * (a.h + a.spacing)];

function tinted(a, f, color) {
  const cx = sizeCanvas(scratch, a.w, a.h);
  cx.globalCompositeOperation = 'source-over';
  cx.clearRect(0, 0, a.w, a.h);
  cx.drawImage(a.img, f.x, f.y, a.w, a.h, 0, 0, a.w, a.h);
  cx.globalCompositeOperation = 'source-atop';
  cx.fillStyle = color;
  cx.fillRect(0, 0, a.w, a.h);
  cx.globalCompositeOperation = 'source-over';
  return scratch;
}

function strokeRect(ctx, x, y, w, h, color, width, dash, offset = 0) {
  ctx.setLineDash(dash ?? []);
  ctx.lineDashOffset = offset;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.strokeRect(x + width / 2, y + width / 2, w - width, h - width);
  ctx.setLineDash([]);
}

// critique spots and the live selection, in art pixels offset by (ox, oy)
function paintMarks(ctx, z, marks, sel, ox = 0, oy = 0, ants = 0) {
  ctx.font = '600 11px Inter, system-ui, sans-serif';
  for (const m of marks) {
    const [x, y, w, h] = m.region;
    const X = (x + ox) * z, Y = (y + oy) * z, W = w * z, H = h * z;
    const color = m.focus ? '#a3a9ff' : m.status === 'working' ? '#f0b429' : '#ffffff';
    strokeRect(ctx, X - 2, Y - 2, W + 4, H + 4, 'rgba(0,0,0,.75)', 4);
    strokeRect(ctx, X - 1, Y - 1, W + 2, H + 2, color, 2);
    const tag = `#${m.id}`;
    const tw = ctx.measureText(tag).width + 8;
    const ty = Y - 19 >= 0 ? Y - 19 : Y + H + 3;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(X - 1, ty, tw, 16, 3);
    ctx.fill();
    ctx.fillStyle = '#0d0e10';
    ctx.fillText(tag, X + 3, ty + 12);
  }
  if (sel) {
    const [x, y, w, h] = sel;
    const X = (x + ox) * z, Y = (y + oy) * z;
    strokeRect(ctx, X - 1, Y - 1, w * z + 2, h * z + 2, '#000', 2);
    strokeRect(ctx, X - 1, Y - 1, w * z + 2, h * z + 2, '#fff', 2, [5, 4], -ants);
  }
}

function paintGrid(ctx, z, W, H, cell = 1) {
  if (z < 4) return;
  ctx.fillStyle = 'rgba(0,0,0,.22)';
  for (let x = 0; x <= W; x += cell) ctx.fillRect(x * z, 0, 1, H * z);
  for (let y = 0; y <= H; y += cell) ctx.fillRect(0, y * z, W * z, 1);
}

function paintFrame(canvas, a, anim, fi, o) {
  const z = o.zoom, w = a.w, h = a.h;
  const rotated = a.anchor === 'center' && (o.angle || o.spin);
  const W = rotated ? Math.ceil(Math.hypot(w, h)) : w, H = rotated ? W : h;
  const ctx = sizeCanvas(canvas, W * z, H * z);
  paintBg(ctx, W * z, H * z, z, o.bg);
  const [ox, oy] = a.origin;
  ctx.save();
  if (rotated) {
    ctx.translate(W * z / 2, H * z / 2);
    ctx.rotate(o.angle);
    ctx.translate(-ox * z, -oy * z);
  }
  const f = anim.frames[fi], n = anim.frames.length;
  if (o.onion && n > 1) {
    const prev = fi > 0 || anim.loop ? anim.frames[(fi - 1 + n) % n] : null;
    const next = fi < n - 1 || anim.loop ? anim.frames[(fi + 1) % n] : null;
    ctx.globalAlpha = 0.35;
    if (prev) ctx.drawImage(tinted(a, prev, '#e64646'), 0, 0, w * z, h * z);
    ctx.globalAlpha = 0.28;
    if (next) ctx.drawImage(tinted(a, next, '#3c78e6'), 0, 0, w * z, h * z);
    ctx.globalAlpha = 1;
  }
  ctx.drawImage(a.img, f.x, f.y, w, h, 0, 0, w * z, h * z);
  if (o.grid) paintGrid(ctx, z, w, h);
  const lw = Math.max(1, Math.round(z / 4));
  if (o.boxes) {
    const [bx, by, bw, bh] = a.body;
    strokeRect(ctx, bx * z, by * z, bw * z, bh * z, '#fac828', lw, [lw * 3, lw * 2]);
    for (const b of f.hurt) strokeRect(ctx, b[0] * z, b[1] * z, b[2] * z, b[3] * z, '#28c85a', lw);
    for (const b of f.hit) strokeRect(ctx, b[0] * z, b[1] * z, b[2] * z, b[3] * z, '#f0283c', lw * 2);
  }
  if (o.origin) {
    ctx.strokeStyle = '#ff00c8';
    ctx.lineWidth = Math.max(1, z / 4);
    ctx.beginPath();
    if (a.anchor === 'center') {
      ctx.moveTo((ox - 2) * z, oy * z); ctx.lineTo((ox + 2) * z, oy * z);
      ctx.moveTo(ox * z, (oy - 2) * z); ctx.lineTo(ox * z, (oy + 2) * z);
    } else {
      ctx.moveTo(0, oy * z - ctx.lineWidth / 2); ctx.lineTo(w * z, oy * z - ctx.lineWidth / 2);
      ctx.moveTo(ox * z, (oy - 3) * z); ctx.lineTo(ox * z, oy * z);
    }
    ctx.stroke();
  }
  ctx.restore();
  if (!rotated) paintMarks(ctx, z, o.marks ?? [], o.sel, 0, 0, o.ants);
}

function paintTile(canvas, a, i, t, o) {
  const z = o.zoom, n = o.repeat ?? 3, w = a.w, h = a.h;
  const ctx = sizeCanvas(canvas, w * n * z, h * n * z);
  paintBg(ctx, canvas.width, canvas.height, z, 'check');
  const [sx, sy] = slotXY(a, slotAt(a, i, t));
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) ctx.drawImage(a.img, sx, sy, w, h, x * w * z, y * h * z, w * z, h * z);
  const c = (n - 1) / 2;
  if (o.grid) paintGrid(ctx, z, w * n, h * n);
  if (n > 1) strokeRect(ctx, c * w * z, c * h * z, w * z, h * z, 'rgba(255,255,255,.35)', 1, [3, 3]);
  paintMarks(ctx, z, o.marks ?? [], o.sel, c * w, c * h, o.ants);
}

function mapSize(a) { return [Math.max(0, ...a.sample.map((r) => r.length)) * a.w, a.sample.length * a.h]; }

function paintMap(canvas, a, t, o) {
  const z = o.zoom;
  const [W, H] = mapSize(a);
  const ctx = sizeCanvas(canvas, W * z, H * z);
  paintBg(ctx, W * z, H * z, z, 'check');
  a.sample.forEach((row, y) => row.forEach((i, x) => {
    if (i < 0) return;
    const [sx, sy] = slotXY(a, slotAt(a, i, t));
    ctx.drawImage(a.img, sx, sy, a.w, a.h, x * a.w * z, y * a.h * z, a.w * z, a.h * z);
  }));
  if (o.grid) paintGrid(ctx, z, W, H, a.w);
  paintMarks(ctx, z, o.marks ?? [], o.sel, 0, 0, o.ants);
}

// a small picture of what a critique points at, its spot outlined
function paintThumb(canvas, c) {
  const t = c.target, a = assetOf(t.asset);
  const D = canvas.width;
  const ctx = sizeCanvas(canvas, D, D);
  ctx.clearRect(0, 0, D, D);
  if (!a?.img) return;
  const src = document.createElement('canvas');
  let region = t.region, cw, ch;
  if (a.type === 'level') {
    cw = a.w; ch = a.h;
    sizeCanvas(src, cw, ch).drawImage(a.img, 0, 0);
  } else if (animated(a)) {
    const anim = a.anims.find((x) => x.name === t.anim) ?? idleOf(a);
    const f = anim.frames[t.frame ?? 0];
    cw = a.w; ch = a.h;
    sizeCanvas(src, cw, ch).drawImage(a.img, f.x, f.y, cw, ch, 0, 0, cw, ch);
  } else if (t.map && a.sample.length) {
    [cw, ch] = mapSize(a);
    paintMap(src, a, 0, { zoom: 1 });
  } else {
    const i = Math.max(0, a.tiles.findIndex((x) => x.name === t.tile));
    cw = a.w; ch = a.h;
    const [sx, sy] = slotXY(a, i);
    sizeCanvas(src, cw, ch).drawImage(a.img, sx, sy, cw, ch, 0, 0, cw, ch);
  }
  // crop: around the spot with some context, else the opaque part of the art
  let [x0, y0, x1, y1] = [0, 0, cw, ch];
  if (region) {
    const pad = Math.max(6, Math.max(region[2], region[3]));
    [x0, y0, x1, y1] = [region[0] - pad, region[1] - pad, region[0] + region[2] + pad, region[1] + region[3] + pad];
  } else if (animated(a)) {
    const px = src.getContext('2d').getImageData(0, 0, cw, ch).data;
    let mx = cw, my = ch, Mx = 0, My = 0;
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) if (px[(y * cw + x) * 4 + 3]) { mx = Math.min(mx, x); my = Math.min(my, y); Mx = Math.max(Mx, x + 1); My = Math.max(My, y + 1); }
    if (Mx > mx) [x0, y0, x1, y1] = [mx - 2, my - 2, Mx + 2, My + 2];
  }
  const side = Math.max(x1 - x0, y1 - y0);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const sx = Math.round(cx - side / 2), sy = Math.round(cy - side / 2);
  const z = D / side;
  ctx.drawImage(src, sx, sy, side, side, 0, 0, D, D);
  if (region) {
    const X = (region[0] - sx) * z, Y = (region[1] - sy) * z;
    strokeRect(ctx, X - 2, Y - 2, region[2] * z + 4, region[3] * z + 4, 'rgba(0,0,0,.7)', 3);
    strokeRect(ctx, X - 1, Y - 1, region[2] * z + 2, region[3] * z + 2, c.status === 'fixed' ? '#4cc38a' : '#fff', 2);
  }
}

// draw a sprite frame or a tile fitted into a small square canvas (nav rows, frame strip)
const bboxes = new Map();
function opaqueBox(a, f) {
  const key = `${a.name}@${a.rev}@${f.x},${f.y}`;
  if (bboxes.has(key)) return bboxes.get(key);
  const cx = sizeCanvas(scratch, a.w, a.h);
  cx.clearRect(0, 0, a.w, a.h);
  cx.drawImage(a.img, f.x, f.y, a.w, a.h, 0, 0, a.w, a.h);
  const px = cx.getImageData(0, 0, a.w, a.h).data;
  let mx = a.w, my = a.h, Mx = 0, My = 0;
  for (let y = 0; y < a.h; y++) for (let x = 0; x < a.w; x++) if (px[(y * a.w + x) * 4 + 3]) { mx = Math.min(mx, x); my = Math.min(my, y); Mx = Math.max(Mx, x + 1); My = Math.max(My, y + 1); }
  const box = Mx > mx ? [mx, my, Mx - mx, My - my] : [0, 0, a.w, a.h];
  bboxes.set(key, box);
  return box;
}

function paintFit(canvas, a, { anim, fi = 0, tile, t = 0, size, crop = false, box = null }) {
  const D = size;
  const ctx = sizeCanvas(canvas, D, D);
  ctx.clearRect(0, 0, D, D);
  if (!a?.img) return;
  let sx, sy, bx = 0, by = 0, bw = a.w, bh = a.h;
  if (a.type === 'level') {   // a square from the middle of the first screen, what the player sees first
    const [cx, cy] = a.screens[0] ?? [0, 0];
    bw = bh = Math.min(a.w, a.h, a.screen[1]);
    sx = Math.max(0, Math.min(a.w - bw, cx + Math.round((Math.min(a.w, a.screen[0]) - bw) / 2)));
    sy = Math.max(0, Math.min(a.h - bh, cy));
  } else if (animated(a)) {
    const f = (anim ?? idleOf(a)).frames[fi];
    sx = f.x; sy = f.y;
    if (box) [bx, by, bw, bh] = box;
    else if (crop) [bx, by, bw, bh] = opaqueBox(a, f);
  } else [sx, sy] = slotXY(a, slotAt(a, tile ?? 0, t));
  const fit = Math.min(D / bw, D / bh);
  const s = fit >= 1 ? Math.floor(fit) : fit;
  const w = bw * s, h = bh * s;
  ctx.drawImage(a.img, sx + bx, sy + by, bw, bh, Math.floor((D - w) / 2), Math.floor((D - h) / 2), w, h);
}

// ---------- shell ----------
function renderWs() {
  const p = S.project;
  $('#ws').innerHTML = `<span class="ws-mark">${MARK}</span><span style="min-width:0">
    <div class="ws-name">${esc(p?.game ?? 'pixelforge')}</div><div class="ws-ver">pixelforge ${esc(p?.version ?? '')}</div></span>`;
}

function renderNav() {
  const r = S.route;
  const open = activeCrits().length;
  let html = `<a class="nav-item ${r.page === 'overview' ? 'on' : ''}" href="#/">${icon('grid')}Overview</a>
    <a class="nav-item ${r.page === 'critiques' ? 'on' : ''}" href="#/critiques">${icon('msg')}Critiques${open ? `<span class="count">${open}</span>` : ''}</a>`;
  const groups = [...TYPES.map((t) => ({ ...t, items: [...S.assets.values()].filter((a) => a.type === t.type) })),
                  { type: 'error', label: 'Not loading', items: [...S.assets.values()].filter((a) => a.type === 'error') }];
  for (const g of groups) {
    if (!g.items.length) continue;
    html += `<div class="nav-head">${g.label}</div>`;
    for (const a of g.items) {
      const n = activeCrits((c) => c.target.asset === a.name);
      const working = n.some((c) => c.status === 'working');
      html += `<a class="asset-row ${r.page === 'asset' && r.name === a.name ? 'on' : ''} ${a.variantOf ? 'variant' : ''}" href="#/a/${enc(a.name)}"
        ${a.variantOf ? `title="A palette variant of ${esc(a.variantOf)}"` : ''}>
        ${a.type === 'error' ? `<span class="warn" style="width:24px;display:grid;place-items:center">${icon('alert')}</span>` : `<canvas width="48" height="48" data-nav="${esc(a.name)}"></canvas>`}
        <span class="nm">${esc(a.name)}</span>${n.length ? `<span class="badge ${working ? 'working' : ''}" title="${n.length} open">${n.length}</span>` : ''}</a>`;
    }
  }
  $('#nav').innerHTML = html;
  for (const c of $$('canvas[data-nav]')) paintFit(c, assetOf(c.dataset.nav), { size: 48, crop: true });
}

function renderWatch() {
  const el = $('#watch');
  const working = S.crits.filter((c) => c.status === 'working');
  const open = S.crits.filter((c) => c.status === 'open').length;
  el.className = 'watch';
  if (working.length) {
    el.classList.add('busy');
    el.innerHTML = `<span class="dot"></span><span class="lbl">Claude is fixing ${working.map((c) => `#${c.id}`).join(', ')}
      ${open ? `<span class="sub">${open} more waiting</span>` : ''}</span>`;
  } else if (S.watching) {
    el.classList.add('on');
    el.innerHTML = `<span class="dot"></span><span class="lbl">Claude is watching</span>`;
  } else {
    el.innerHTML = `<span class="dot"></span><span class="lbl">Claude isn't watching
      <span class="sub">${open ? `${open} waiting · ` : ''}<button class="link" id="copy-prompt" title="Copies “${PROMPT}” to paste into Claude Code">Copy prompt</button></span></span>`;
    $('#copy-prompt').onclick = async () => {
      try { await navigator.clipboard.writeText(PROMPT); toast('Copied. Paste it into Claude Code', 'check'); }
      catch { toast(PROMPT); }
    };
  }
}

function propChips(a) {
  const p = a.prop;
  const chips = [p.layer, p.solid ? 'solid' : '', p.scroll !== 1 ? `scroll ${p.scroll}` : '', p.slice ? `sliced ${p.slice[0]}×${p.slice[1]}` : ''];
  return chips.filter(Boolean).map((c) => `<span class="chip">${esc(c)}</span>`).join('');
}

function renderTop() {
  const r = S.route;
  let crumbs = '', meta = '';
  if (r.page === 'overview') crumbs = `<span class="here">Overview</span>`;
  else if (r.page === 'critiques') crumbs = `<span class="here">Critiques</span>`;
  else {
    const a = assetOf(r.name);
    crumbs = `<a href="#/">${typeLabel(a?.type)}</a><span class="sep">/</span><span class="here">${esc(r.name)}</span>`;
    if (a?.type === 'level') meta = `<span class="chip">${esc(a.view)}</span><span class="chip num">${a.cells[0]}×${a.cells[1]} tiles</span>` +
      `<span class="chip num">${a.screens.length} screen${a.screens.length === 1 ? '' : 's'}</span>`;
    else if (animated(a)) meta = `${a.variantOf ? `<a class="chip" href="#/a/${enc(a.variantOf)}" title="Its frames are ${esc(a.variantOf)}'s, recolored">variant of ${esc(a.variantOf)}</a>` : ''}` +
      `${a.class ? `<span class="chip">${esc(a.class)}</span>` : ''}${a.prop ? propChips(a) : ''}${a.fx ? `<span class="chip">plays once · ${esc(a.fx.layer)}</span>` : ''}<span class="chip num">${a.w}×${a.h}</span>`;
    else if (a && a.type !== 'error') meta = `<span class="chip num">${a.tiles.length} ${typeInfo(a).cells}</span><span class="chip num">${a.w}×${a.h}</span>`;
  }
  $('#top').innerHTML = `<nav class="crumbs" aria-label="Breadcrumb">${crumbs}</nav>` +
    (S.online ? `<div class="meta">${meta}</div>` : `<div class="offline">${icon('wifi', 'i-sm')}Can't reach pixelforge serve. Retrying…</div>`);
}

// ---------- critique rows ----------
function critRow(c, { withAsset = true, thumb = true } = {}) {
  return `<div class="crit ${c.status} ${S.focus === c.id ? 'focus' : ''}" data-id="${c.id}" tabindex="0" role="button"
      aria-label="Critique ${c.id}: ${esc(c.text)}">
    <div class="st">${stIcon(c.status)}</div>
    ${thumb ? `<canvas class="thumb" width="88" height="88" data-thumb="${c.id}"></canvas>` : ''}
    <div class="txt">${esc(c.text)}</div>
    <div class="tgt">${icon(targetIcon(c.target), 'i-sm')}<span>#${c.id} · ${esc(targetText(c.target, withAsset))}</span>
      <time class="num" datetime="${esc(c.updated)}" title="${esc(new Date(c.updated).toLocaleString())}">${ago(c.updated)}</time></div>
    ${c.note ? `<div class="note">${icon('check', 'i-sm')}<span>${esc(c.note)}</span></div>` : ''}
    <div class="acts">
      ${c.status === 'fixed' ? `<button class="btn icon" data-act="reopen" title="Reopen" aria-label="Reopen critique ${c.id}">${icon('undo', 'i-sm')}</button>` : ''}
      <button class="btn icon" data-act="delete" title="Delete" aria-label="Delete critique ${c.id}">${icon('trash', 'i-sm')}</button>
    </div></div>`;
}

function wireCrits(root) {
  for (const c of $$('canvas[data-thumb]', root)) {
    const crit = S.crits.find((x) => x.id === +c.dataset.thumb);
    if (crit) paintThumb(c, crit);
  }
  for (const row of $$('.crit', root)) {
    const id = +row.dataset.id;
    const go = (e) => {
      if (e.target.closest('[data-act]')) return;
      const c = S.crits.find((x) => x.id === id);
      if (c) openCrit(c);
    };
    row.onclick = go;
    row.onkeydown = (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(e); } };
    for (const b of $$('[data-act]', row)) b.onclick = async (e) => {
      e.stopPropagation();
      try {
        if (b.dataset.act === 'delete') {
          await api(`/api/critiques/${id}`, { method: 'DELETE' });
          S.crits = S.crits.filter((x) => x.id !== id);
          if (S.focus === id) S.focus = null;
          toast(`Deleted #${id}`);
        } else {
          const c = await api(`/api/critiques/${id}`, { method: 'POST', body: JSON.stringify({ status: 'open' }) });
          S.crits = S.crits.map((x) => (x.id === id ? c : x));
          toast(`Reopened #${id}`);
        }
        refreshCrits();
      } catch (err) { toast(err.message, 'alert'); }
    };
  }
}

function openCrit(c) {
  const t = c.target, a = assetOf(t.asset);
  let hash = `#/a/${enc(t.asset)}`;
  if (animated(a) && t.anim) hash += `/${enc(t.anim)}${t.frame != null ? `/${t.frame}` : ''}`;
  else if (t.tile) hash += `/${enc(t.tile)}`;
  else if (t.map) hash += '/~map';
  if (location.hash === hash) {
    S.focus = S.focus === c.id ? null : c.id;
    refreshCrits();
  } else {
    S.pendingFocus = c.id;
    location.hash = hash;
  }
}

// ---------- pages ----------
function overviewPage(page) {
  const assets = [...S.assets.values()];
  const active = activeCrits().sort((a, b) => b.id - a.id);
  const broken = assets.filter((a) => a.type === 'error');
  let html = `<div class="wrap"><h1 class="page-title">${esc(S.project.game)}</h1>
    <p class="page-sub">${assets.length} asset${assets.length === 1 ? '' : 's'}${active.length ? ` · ${active.length} critique${active.length === 1 ? '' : 's'} open` : ''}</p>`;
  if (!assets.length) {
    html += `<div class="section list empty"><h3>No art yet</h3>Ask Claude to draw a character, or run <code>pixelforge new hero</code>.</div></div>`;
    page.innerHTML = html;
    return;
  }
  if (active.length) {
    html += `<section class="section"><div class="section-head"><h2>Open critiques</h2><span class="n">${active.length}</span>
      <a href="#/critiques">View all</a></div><div class="list wide">${active.slice(0, 5).map((c) => critRow(c)).join('')}</div></section>`;
  }
  for (const t of TYPES) {
    const items = assets.filter((a) => a.type === t.type);
    if (!items.length) continue;
    html += `<section class="section"><div class="section-head"><h2>${t.label}</h2><span class="n">${items.length}</span></div><div class="grid">`;
    for (const a of items) {
      const n = activeCrits((c) => c.target.asset === a.name).length;
      const noun = a.type === 'prop' ? 'state' : 'animation';
      const sub = a.variantOf ? `variant of ${a.variantOf} · ${a.anims.length} ${noun}${a.anims.length === 1 ? '' : 's'}` : a.type === 'level' ? `${a.cells[0]}×${a.cells[1]} tiles · ${a.view} · ${a.objects.length} object${a.objects.length === 1 ? '' : 's'}`
        : animated(a) ? `${a.anims.length} ${noun}${a.anims.length === 1 ? '' : 's'}${a.class ? ` · ${a.class}` : ''}${a.prop ? ` · ${a.prop.layer}` : ''}`
        : `${a.tiles.length} ${typeInfo(a).cells} · ${a.w}×${a.h}`;
      html += `<a class="tile" href="#/a/${enc(a.name)}"><div class="art"><canvas data-card="${esc(a.name)}"></canvas></div>
        <div class="info"><div><div class="nm">${esc(a.name)}</div><div class="sub">${esc(sub)}</div></div>
        ${n ? `<span class="badge">${n}</span>` : ''}</div></a>`;
    }
    html += `</div></section>`;
  }
  if (broken.length) {
    html += `<section class="section"><div class="section-head"><h2>Not loading</h2><span class="n">${broken.length}</span></div><div class="grid">` +
      broken.map((a) => `<a class="tile broken" href="#/a/${enc(a.name)}"><div class="art mono">${esc(a.error)}</div>
        <div class="info"><div class="nm">${esc(a.name)}</div></div></a>`).join('') + `</div></section>`;
  }
  page.innerHTML = html + '</div>';
  wireCrits(page);
  for (const c of $$('canvas[data-card]', page)) {
    const a = assetOf(c.dataset.card);
    if (a.type === 'level') {   // the whole level, fitted into the card
      const z = Math.min(208 / a.w, 150 / a.h);
      const s = z >= 1 ? Math.floor(z) : z;
      sizeCanvas(c, Math.round(a.w * s), Math.round(a.h * s)).drawImage(a.img, 0, 0, Math.round(a.w * s), Math.round(a.h * s));
    } else if (animated(a)) {
      const anim = idleOf(a);
      const z = Math.max(1, Math.floor(Math.min(208 / a.w, 150 / a.h)));
      const p = { frame: 0, acc: 0 };
      const draw = () => paintFrame(c, a, anim, p.frame, { zoom: z, bg: 'check', angle: 0 });
      draw();
      animators.push((dt) => {
        p.acc += dt;
        const hold = anim.frames[p.frame].d + (!anim.loop && p.frame === anim.frames.length - 1 ? REPEAT_PAUSE_MS : 0);
        if (p.acc >= hold) { p.acc -= hold; p.frame = (p.frame + 1) % anim.frames.length; draw(); }
      });
    } else if (a.sample.length) {
      const [, H] = mapSize(a);
      const z = Math.max(1, Math.round(168 / H));
      let last = -1;
      animators.push((dt, t) => { const k = Math.floor(t / 50); if (k !== last) { last = k; paintMap(c, a, t, { zoom: z }); } });
    } else if (a.type === 'tileset') {
      paintTile(c, a, 0, 0, { zoom: 3, repeat: 3 });
    } else {   // icons, glyphs: the first few side by side
      const n = Math.min(a.tiles.length, 6), z = Math.max(1, Math.floor(Math.min(200 / (n * (a.w + 2)), 140 / a.h)));
      const ctx = sizeCanvas(c, n * (a.w + 2) * z, a.h * z);
      for (let i = 0; i < n; i++) { const [sx, sy] = slotXY(a, i); ctx.drawImage(a.img, sx, sy, a.w, a.h, i * (a.w + 2) * z, 0, a.w * z, a.h * z); }
    }
  }
}

function critiquesPage(page) {
  const by = (st) => S.crits.filter((c) => c.status === st).sort((a, b) => (st === 'fixed' ? b.updated.localeCompare(a.updated) : b.id - a.id));
  const groups = [['open', 'Open'], ['working', 'Claude is fixing'], ['fixed', 'Fixed']].map(([st, label]) => ({ st, label, items: by(st) }));
  const counts = groups.filter((g) => g.items.length).map((g) => `${g.items.length} ${g.label.toLowerCase()}`).join(' · ');
  let html = `<div class="wrap"><h1 class="page-title">Critiques</h1><p class="page-sub">${counts || 'Nothing yet'}</p><div class="section">`;
  if (!S.crits.length) {
    html += `<div class="list empty"><h3>No critiques yet</h3>Open a sprite or tileset, mark what's wrong, and send it to Claude.</div>`;
  } else {
    html += `<div class="list wide">` + groups.filter((g) => g.items.length).map((g) =>
      `<div class="group-head">${stIcon(g.st)}${g.label}<span class="n num">${g.items.length}</span></div>` +
      g.items.map((c) => critRow(c)).join('')).join('') + `</div>`;
  }
  page.innerHTML = html + '</div></div>';
  wireCrits(page);
}

// ----- asset page -----
function errorPage(page, a) {
  page.innerHTML = `<div class="error-box"><h3>${esc(a.name)} doesn't load</h3><pre>${esc(a.error)}</pre></div>`;
}

function stageMarks(match) {
  return activeCrits((c) => c.target.region && match(c.target)).map((c) => ({ id: c.id, region: c.target.region, status: c.status, focus: S.focus === c.id }))
    .concat(S.focus ? S.crits.filter((c) => c.id === S.focus && c.status === 'fixed' && c.target.region && match(c.target))
      .map((c) => ({ id: c.id, region: c.target.region, status: c.status, focus: true })) : []);
}

function zoomControls() {
  return `<button class="btn icon" data-z="-1" title="Zoom out" aria-label="Zoom out">${icon('minus')}</button>
    <span class="zoom num" id="zoom-read"></span>
    <button class="btn icon" data-z="1" title="Zoom in" aria-label="Zoom in">${icon('plus')}</button>`;
}

function zoomKey(key) {
  if (S.view.zoomFor !== key) { S.view.zoom = null; S.view.zoomFor = key; S.view.userZoom = false; }
  return key;
}

function fitZoom(w, h) {
  const st = $('.stage');
  if (!st) return 4;
  return Math.max(1, Math.min(24, Math.floor(Math.min((st.clientWidth - 48) / w, (st.clientHeight - 40) / h))));
}

function assetPage(page) {
  const r = S.route, a = assetOf(r.name);
  if (!a) {
    page.innerHTML = `<div class="wrap"><div class="list empty"><h3>No asset called “${esc(r.name)}”</h3><a href="#/" style="color:var(--accent-fg)">Back to overview</a></div></div>`;
    return;
  }
  if (a.type === 'error') return errorPage(page, a);
  if (a.type === 'level') levelPage(page, a);
  else if (animated(a)) spritePage(page, a);
  else tilesetPage(page, a);
}

function stageShell(hasStrip) {
  return `<div class="asset"><div class="tabs" id="tabs"></div>
    <div class="stage-wrap"><div class="stage" id="stage"><canvas id="stage-canvas"></canvas></div>
      <div class="toolbar" id="toolbar"></div><div id="selinfo"></div></div>
    ${hasStrip ? '<div class="strip" id="strip"></div>' : ''}</div>`;
}

function gameShell(src) {
  return `<div class="asset"><div class="tabs" id="tabs"></div><div class="stage-wrap"><iframe class="game" src="${src}" title="In-game test"></iframe></div></div>`;
}

// sprite ---------------------------------------------------------------
let stage = null;   // { draw, surface: { w, h, wrap, mapCell }, step, canStep }

function spritePage(page, a) {
  const r = S.route;
  if (r.sub === '~game' && hasGame(a)) {
    // top-down props walk the tilemap, side-view props stand in the platformer; characters that jump
    // get the platformer playground; the rest spar with dummies
    const jumps = a.anims.some((x) => /^jump(_|$)/.test(x.name));
    const src = a.type === 'prop' ? `${a.view === 'side' ? 'platformer' : 'tilemap'}.html?prop=${enc(a.name)}`
      : `${jumps ? 'platformer' : 'phaser'}.html?sprite=${enc(a.name)}`;
    page.innerHTML = gameShell(`${src}&embed=1`);
    renderSpriteTabs(a, null);
    stage = null;
    return;
  }
  const anim = a.anims.find((x) => x.name === r.sub) ?? idleOf(a);
  const n = anim.frames.length;
  const key = zoomKey(a.name);
  S.play.frame = Math.min(S.play.frame, n - 1);
  page.innerHTML = stageShell(true);
  renderSpriteTabs(a, anim);
  const canvas = $('#stage-canvas');
  const center = a.anchor === 'center';
  let ants = 0;
  const marks = () => stageMarks((t) => t.anim === anim.name && t.frame === S.play.frame);
  const draw = () => {
    if (!canvas.isConnected) return;
    if (!S.view.zoom) S.view.zoom = fitZoom(center ? Math.hypot(a.w, a.h) : a.w, center ? Math.hypot(a.w, a.h) : a.h);
    paintFrame(canvas, a, anim, S.play.frame, { ...S.view, marks: marks(), sel: S.sel, ants });
    $('#zoom-read').textContent = `${S.view.zoom}×`;
    $('#stage').classList.toggle('rotating', center && !!(S.view.angle || S.view.spin));
  };
  const hold = (i) => anim.frames[i].d + (i === n - 1 && !anim.loop ? REPEAT_PAUSE_MS : 0);
  const readout = () => {
    const f = anim.frames[S.play.frame];
    $('#readout').innerHTML = `Frame <b>${S.play.frame}</b> · ${f.d} ms`;
    $('#play').innerHTML = icon(S.play.playing ? 'pause' : 'play');
    $('#play').setAttribute('aria-label', S.play.playing ? 'Pause' : 'Play');
    $$('.fr', $('#strip')).forEach((el, k) => el.classList.toggle('on', k === S.play.frame));
  };
  const seek = (i) => {
    S.play.frame = (i + n) % n;
    S.play.acc = 0;
    if (S.sel) S.sel = null;
    draw(); readout(); updateComposer(); renderSelInfo();
    $('.fr.on', $('#strip'))?.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (!S.play.playing) history.replaceState(null, '', `#/a/${enc(a.name)}/${enc(anim.name)}/${S.play.frame}`);
  };
  const setPlaying = (on) => {
    S.play.playing = on;
    if (on && S.play.frame === n - 1 && !anim.loop && !S.view.repeat) S.play.frame = 0;
    if (on) { S.sel = null; renderSelInfo(); history.replaceState(null, '', `#/a/${enc(a.name)}/${enc(anim.name)}`); }
    else history.replaceState(null, '', `#/a/${enc(a.name)}/${enc(anim.name)}/${S.play.frame}`);
    draw(); readout(); updateComposer();
  };
  stage = {
    draw, surface: { w: a.w, h: a.h }, rotated: () => center && !!(S.view.angle || S.view.spin),
    unrotate: () => { S.view.angle = 0; S.view.spin = false; },
    step: (d) => { setPlaying(false); seek(S.play.frame + d); },
    togglePlay: () => setPlaying(!S.play.playing),
    pause: () => { if (S.play.playing) setPlaying(false); },
    nav: (d) => { const i = a.anims.indexOf(anim) + d; if (a.anims[i]) location.hash = `#/a/${enc(a.name)}/${enc(a.anims[i].name)}`; },
  };

  $('#toolbar').innerHTML = `
    <button class="btn icon" id="play" title="Play / pause (space)"></button>
    <button class="btn icon" id="prev" title="Previous frame (←)" aria-label="Previous frame">${icon('left')}</button>
    <span class="readout num" id="readout"></span>
    <button class="btn icon" id="next" title="Next frame (→)" aria-label="Next frame">${icon('right')}</button>
    <span class="sep"></span>${zoomControls()}<span class="sep"></span>
    <button class="btn icon" id="ground" title="Ground" aria-label="Ground" aria-haspopup="menu">${icon('ground')}</button>
    ${center ? `<button class="btn icon ${S.view.angle || S.view.spin ? 'on' : ''}" id="facing" title="Facing (rotated by the engine)" aria-label="Facing" aria-haspopup="menu">${icon('compass')}</button>` : ''}
    <button class="btn icon ${S.view.boxes || S.view.origin || S.view.onion || S.view.grid ? 'on' : ''}" id="viewopts" title="Overlays" aria-label="Overlays" aria-haspopup="menu">${icon('sliders')}</button>`;
  $('#play').onclick = () => stage.togglePlay();
  $('#prev').onclick = () => stage.step(-1);
  $('#next').onclick = () => stage.step(1);
  wireZoom(draw);
  $('#ground').onclick = (e) => groundMenu(e.currentTarget, draw);
  if (center) $('#facing').onclick = (e) => facingMenu(e.currentTarget, draw);
  $('#viewopts').onclick = (e) => overlayMenu(e.currentTarget, draw, !anim.loop);

  // every thumbnail shows the same crop (all frames' art together), so motion reads across the strip
  const stripBox = anim.frames.map((f) => opaqueBox(a, f)).reduce((u, b) => {
    const x0 = Math.min(u[0], b[0]), y0 = Math.min(u[1], b[1]);
    return [x0, y0, Math.max(u[0] + u[2], b[0] + b[2]) - x0, Math.max(u[1] + u[3], b[1] + b[3]) - y0];
  });
  $('#strip').innerHTML = anim.frames.map((f, k) => {
    const nc = activeCrits((c) => c.target.anim === anim.name && c.target.frame === k).length;
    return `<button class="fr" data-k="${k}" aria-label="Frame ${k}"><canvas width="112" height="112" style="width:56px;height:56px"></canvas>
      <span class="lbl">${f.active ? '<i class="hit" title="Active: deals damage"></i>' : ''}<span>${k}</span><span>· ${f.d}ms</span></span>
      ${nc ? `<span class="cdot badge">${nc}</span>` : ''}</button>`;
  }).join('');
  $$('.fr', $('#strip')).forEach((el, k) => {
    paintFit($('canvas', el), a, { anim, fi: k, size: 112, box: stripBox });
    el.onclick = () => { setPlaying(false); seek(k); };
  });

  wireSelection(canvas, () => stage.surface);
  draw(); readout();
  animators.push((dt, t) => {
    if (S.view.spin && center) { S.view.angle = (S.view.angle + dt * 0.0015) % (Math.PI * 2); draw(); }
    if (S.sel) { const k = Math.floor(t / 90); if (k !== ants) { ants = k; draw(); } }
    if (!S.play.playing) return;
    if (!anim.loop && !S.view.repeat && S.play.frame === n - 1) return;
    S.play.acc += dt;
    let moved = false;
    while (S.play.acc >= hold(S.play.frame)) { S.play.acc -= hold(S.play.frame); S.play.frame = (S.play.frame + 1) % n; moved = true; }
    if (moved) { draw(); readout(); }
  });
  observeStage(draw, key);
}

function renderSpriteTabs(a, anim) {
  const el = $('#tabs');
  if (!el) return;
  el.innerHTML = a.anims.map((x) => {
    const nc = activeCrits((c) => c.target.asset === a.name && c.target.anim === x.name).length;
    return `<a class="tab ${anim === x ? 'on' : ''}" href="#/a/${enc(a.name)}/${enc(x.name)}">${esc(x.name)}
      ${nc ? `<span class="badge">${nc}</span>` : `<span class="n">${x.frames.length}</span>`}</a>`;
  }).join('') + (hasGame(a) ? `<span class="spacer"></span><a class="tab ${anim ? '' : 'on'}" href="#/a/${enc(a.name)}/~game">${icon('game')}In game</a>` : '');
}

// characters spar in phaser.html; top-down props stand on a tileset's sample map in tilemap.html,
// side-view props on the platformer's ground
const hasGame = (a) => a.type !== 'fx' && (a.type !== 'prop' || a.view === 'side' || [...S.assets.values()].some((x) => x.type === 'tileset'));

// tileset --------------------------------------------------------------
function tilesetPage(page, a) {
  const r = S.route;
  const hasMap = a.sample.length > 0;
  const view = r.sub === '~game' && a.type === 'tileset' ? 'game' : (r.sub && r.sub[0] !== '~') ? 'tile' : hasMap ? 'map' : 'tile';
  r.view = view;
  if (view === 'game') {
    page.innerHTML = gameShell(`tilemap.html?tileset=${enc(a.name)}&embed=1`);
    renderTileTabs(a, view);
    stage = null;
    return;
  }
  const key = zoomKey(`${a.name}:${view}`);
  const ti = Math.max(0, a.tiles.findIndex((t) => t.name === r.sub));
  r.tile = a.tiles[ti]?.name;
  page.innerHTML = stageShell(view === 'tile');
  renderTileTabs(a, view);
  const canvas = $('#stage-canvas');
  let ants = 0, lastK = -1;
  const draw = (t = performance.now()) => {
    if (!canvas.isConnected) return;
    if (view === 'map') {
      const [W, H] = mapSize(a);
      if (!S.view.zoom) S.view.zoom = fitZoom(W, H);
      paintMap(canvas, a, t, { zoom: S.view.zoom, grid: S.view.grid, marks: stageMarks((x) => x.map), sel: S.sel, ants });
    } else {
      const rep = a.type === 'tileset' ? 3 : 1;   // icons and glyphs don't repeat edge to edge
      if (!S.view.zoom) S.view.zoom = fitZoom(a.w * rep, a.h * rep);
      paintTile(canvas, a, ti, t, { zoom: S.view.zoom, repeat: rep, grid: S.view.grid, marks: stageMarks((x) => x.tile === r.tile), sel: S.sel, ants });
    }
    $('#zoom-read').textContent = `${S.view.zoom}×`;
  };
  const tileNames = a.tiles.map((t) => t.name);
  stage = view === 'map'
    ? { draw, surface: { ...(([w, h]) => ({ w, h }))(mapSize(a)), mapCell: [a.w, a.h] }, togglePlay() {}, pause() {}, step() {}, nav() {} }
    : { draw, surface: { w: a.w, h: a.h, wrap: true }, togglePlay() {}, pause() {},
        step: (d) => { const n = tileNames[(ti + d + tileNames.length) % tileNames.length]; location.hash = `#/a/${enc(a.name)}/${enc(n)}`; },
        nav() {} };
  $('#toolbar').innerHTML = `${view === 'tile' ? `<button class="btn icon" id="prev" title="Previous tile (←)" aria-label="Previous tile">${icon('left')}</button>
      <span class="readout num"><b>${ti + 1}</b> / ${a.tiles.length} · ${esc(r.tile)}</span>
      <button class="btn icon" id="next" title="Next tile (→)" aria-label="Next tile">${icon('right')}</button><span class="sep"></span>` : ''}
    ${zoomControls()}<span class="sep"></span>
    <button class="btn icon ${S.view.grid ? 'on' : ''}" id="gridbtn" title="${view === 'map' ? 'Tile grid' : 'Pixel grid'}" aria-pressed="${S.view.grid}" aria-label="Grid">${icon('tiles')}</button>`;
  if (view === 'tile') { $('#prev').onclick = () => stage.step(-1); $('#next').onclick = () => stage.step(1); }
  wireZoom(draw);
  $('#gridbtn').onclick = (e) => { S.view.grid = !S.view.grid; e.currentTarget.classList.toggle('on', S.view.grid); e.currentTarget.setAttribute('aria-pressed', S.view.grid); draw(); };
  if (view === 'tile') {
    $('#strip').innerHTML = a.tiles.map((t, k) => {
      const nc = activeCrits((c) => c.target.asset === a.name && c.target.tile === t.name).length;
      return `<a class="fr ${k === ti ? 'on' : ''}" href="#/a/${enc(a.name)}/${enc(t.name)}" title="${esc(t.name)}${t.props.collides ? ' · collides' : ''}">
        <canvas width="96" height="96" style="width:48px;height:48px" data-tile="${k}"></canvas><span class="lbl"><span>${esc(t.name)}</span></span>
        ${nc ? `<span class="cdot badge">${nc}</span>` : ''}</a>`;
    }).join('');
    $('.fr.on', $('#strip'))?.scrollIntoView({ block: 'nearest', inline: 'center' });
  }
  const thumbs = $$('canvas[data-tile]');
  const drawThumbs = (t) => thumbs.forEach((c) => paintFit(c, a, { tile: +c.dataset.tile, t, size: 96 }));
  wireSelection(canvas, () => stage.surface);
  draw(); drawThumbs(0);
  animators.push((dt, t) => {
    const k = Math.floor(t / 50);
    if (k === lastK) return;
    lastK = k;
    ants = Math.floor(t / 90);
    draw(t);
    if (k % 5 === 0) drawThumbs(t);
  });
  observeStage(draw, key);
}

function renderTileTabs(a, view) {
  const el = $('#tabs');
  if (!el) return;
  const nMap = activeCrits((c) => c.target.asset === a.name && c.target.map).length;
  const nTiles = activeCrits((c) => c.target.asset === a.name && c.target.tile).length;
  const first = S.route.tile ?? a.tiles[0]?.name;
  el.innerHTML = (a.sample.length ? `<a class="tab ${view === 'map' ? 'on' : ''}" href="#/a/${enc(a.name)}/~map">${icon('map')}Sample map${nMap ? `<span class="badge">${nMap}</span>` : ''}</a>` : '') +
    `<a class="tab ${view === 'tile' ? 'on' : ''}" href="#/a/${enc(a.name)}/${enc(first ?? '')}">${icon('tiles')}${typeInfo(a).cells[0].toUpperCase() + typeInfo(a).cells.slice(1)}${nTiles ? `<span class="badge">${nTiles}</span>` : `<span class="n">${a.tiles.length}</span>`}</a>` +
    (a.type === 'tileset' ? `<span class="spacer"></span><a class="tab ${view === 'game' ? 'on' : ''}" href="#/a/${enc(a.name)}/~game">${icon('game')}In game</a>` : '');
}

// level ----------------------------------------------------------------
// The level as the game composites it (rendered by the server), with the camera-sized screens, the
// objects, critique spots and the selection drawn over it. Play runs play.html.
const objBox = (o) => o.rect ?? o.art ?? [o.x - 4, o.y - 8, 8, 8];
const objLabel = (o) => (o.type === o.name || o.type === 'prop' || o.type === 'sprite' ? o.name : `${o.name} (${o.type})`) + (o.to ? ` → ${o.to}` : '');

function paintLevel(canvas, a, o) {
  const z = o.zoom, W = a.w * z, H = a.h * z;
  const ctx = sizeCanvas(canvas, W, H);
  ctx.drawImage(a.img, 0, 0, W, H);
  if (o.grid) {
    ctx.fillStyle = 'rgba(0,0,0,.25)';
    for (let x = 0; x <= a.w; x += a.tile[0]) ctx.fillRect(x * z, 0, 1, H);
    for (let y = 0; y <= a.h; y += a.tile[1]) ctx.fillRect(0, y * z, W, 1);
  }
  for (const ob of a.objects) if (ob.rect) {   // doors and triggers: always visible, they're invisible in game
    const [x, y, w, h] = ob.rect;
    strokeRect(ctx, x * z, y * z, w * z, h * z, 'rgba(44,232,245,.8)', 1, [4, 3]);
  }
  if (S.lv.screens) {
    const [sw, sh] = a.screen;
    ctx.font = '600 12px Inter, system-ui, sans-serif';
    a.screens.forEach(([x, y], i) => {
      const cur = i === S.lv.screen;
      strokeRect(ctx, x * z, y * z, Math.min(sw, a.w - x) * z, Math.min(sh, a.h - y) * z, cur ? '#fff' : 'rgba(255,255,255,.4)', cur ? 2 : 1, cur ? [] : [6, 4]);
      ctx.fillStyle = 'rgba(13,14,16,.75)';
      ctx.fillRect(x * z + 4, y * z + 4, 20, 18);
      ctx.fillStyle = cur ? '#fff' : 'rgba(255,255,255,.7)';
      ctx.fillText(String(i + 1), x * z + 9, y * z + 18);
    });
  }
  const hi = a.objects[S.lv.obj];
  if (hi) {
    const [x, y, w, h] = objBox(hi);
    strokeRect(ctx, x * z - 2, y * z - 2, w * z + 4, h * z + 4, 'rgba(0,0,0,.75)', 4);
    strokeRect(ctx, x * z - 1, y * z - 1, w * z + 2, h * z + 2, '#2ce8f5', 2);
    ctx.font = '600 11px Inter, system-ui, sans-serif';
    const tag = objLabel(hi), tw = ctx.measureText(tag).width + 8;
    const ty = y * z - 19 >= 0 ? y * z - 19 : (y + h) * z + 3;
    ctx.fillStyle = '#2ce8f5';
    ctx.beginPath(); ctx.roundRect(x * z - 1, ty, tw, 16, 3); ctx.fill();
    ctx.fillStyle = '#0d0e10';
    ctx.fillText(tag, x * z + 3, ty + 12);
  }
  paintMarks(ctx, z, o.marks ?? [], o.sel, 0, 0, o.ants);
}

// scroll the stage so level pixels (x, y, w, h) are in view (centred when they fit)
function revealLevel(x, y, w, h) {
  const st = $('#stage'), z = S.view.zoom, c = $('#stage-canvas');
  if (!st || !c) return;
  const ox = c.offsetLeft, oy = c.offsetTop;
  st.scrollLeft = ox + (x + w / 2) * z - st.clientWidth / 2;
  st.scrollTop = oy + (y + h / 2) * z - st.clientHeight / 2;
}

function levelPage(page, a) {
  const r = S.route;
  const view = r.sub === '~game' ? 'game' : 'level';
  r.view = view;
  if (view === 'game') {
    page.innerHTML = gameShell(`play.html?level=${enc(a.name)}&embed=1`);
    renderLevelTabs(a, view);
    stage = null;
    return;
  }
  if (S.lv.for !== a.name) S.lv = { ...S.lv, for: a.name, screen: 0, obj: null };
  S.lv.screen = Math.min(S.lv.screen, a.screens.length - 1);
  if (S.lv.obj != null && !a.objects[S.lv.obj]) S.lv.obj = null;
  const key = zoomKey(`${a.name}:level`);
  page.innerHTML = stageShell(true);
  $('#stage').classList.add('pan');
  renderLevelTabs(a, view);
  const canvas = $('#stage-canvas');
  let ants = 0;
  const draw = () => {
    if (!canvas.isConnected) return;
    if (!S.view.zoom) S.view.zoom = Math.min(4, fitZoom(a.w, a.h));
    paintLevel(canvas, a, { zoom: S.view.zoom, grid: S.view.grid, marks: stageMarks((x) => x.level), sel: S.sel, ants });
    $('#zoom-read').textContent = `${S.view.zoom}×`;
  };
  const go = (i) => {
    S.lv.screen = (i + a.screens.length) % a.screens.length;
    $('#screen-read').innerHTML = `Screen <b>${S.lv.screen + 1}</b> / ${a.screens.length}`;
    draw();
    revealLevel(...a.screens[S.lv.screen], ...a.screen);
    updateComposer();
  };
  stage = { draw, surface: { w: a.w, h: a.h, mapCell: a.tile }, togglePlay() {}, pause() {}, step: (d) => go(S.lv.screen + d), nav() {} };
  $('#toolbar').innerHTML = `<button class="btn icon" id="prev" title="Previous screen (←)" aria-label="Previous screen">${icon('left')}</button>
      <span class="readout num" id="screen-read">Screen <b>${S.lv.screen + 1}</b> / ${a.screens.length}</span>
      <button class="btn icon" id="next" title="Next screen (→)" aria-label="Next screen">${icon('right')}</button><span class="sep"></span>
    ${zoomControls()}<span class="sep"></span>
    <button class="btn icon ${S.lv.screens ? 'on' : ''}" id="screensbtn" title="Screens: what one camera position shows (${a.screen[0]}×${a.screen[1]})" aria-pressed="${S.lv.screens}" aria-label="Screens">${icon('grid')}</button>
    <button class="btn icon ${S.view.grid ? 'on' : ''}" id="gridbtn" title="Tile grid" aria-pressed="${S.view.grid}" aria-label="Tile grid">${icon('tiles')}</button>`;
  $('#prev').onclick = () => stage.step(-1);
  $('#next').onclick = () => stage.step(1);
  wireZoom(() => { draw(); revealLevel(...a.screens[S.lv.screen], ...a.screen); });
  const toggle = (id, get, set) => { $(id).onclick = (e) => { set(!get()); e.currentTarget.classList.toggle('on', get()); e.currentTarget.setAttribute('aria-pressed', get()); draw(); }; };
  toggle('#screensbtn', () => S.lv.screens, (v) => { S.lv.screens = v; });
  toggle('#gridbtn', () => S.view.grid, (v) => { S.view.grid = v; });
  // the strip: every object, pictured from the level itself; click to highlight (again to clear)
  $('#strip').innerHTML = (a.errors.length ? `<div class="lv-err" title="${esc(a.errors.join('\n'))}">${icon('alert', 'i-sm')}<span>${a.errors.length} problem${a.errors.length === 1 ? '' : 's'}: ${esc(a.errors[0])}</span></div>` : '') +
    a.objects.map((o, k) => `<button class="fr ${k === S.lv.obj ? 'on' : ''}" data-obj="${k}" title="${esc(objLabel(o))} at ${o.x}, ${o.y}">
      <canvas width="96" height="96" style="width:48px;height:48px" data-objc="${k}"></canvas>
      <span class="lbl"><span>${esc(o.name)}</span></span>${o.type !== o.name && o.type !== 'prop' && o.type !== 'sprite' ? `<span class="type">${esc(o.type)}${o.to ? ` → ${esc(o.to)}` : ''}</span>` : ''}</button>`).join('');
  for (const c of $$('canvas[data-objc]')) {
    const o = a.objects[+c.dataset.objc];
    const [x, y, w, h] = objBox(o);
    const side = Math.max(w, h, 16) + 8;
    const sx = Math.round(x + w / 2 - side / 2), sy = Math.round(y + h / 2 - side / 2);
    const ctx = sizeCanvas(c, 96, 96);
    ctx.fillStyle = '#0d0e10'; ctx.fillRect(0, 0, 96, 96);
    ctx.drawImage(a.img, sx, sy, side, side, 0, 0, 96, 96);
    if (o.rect) strokeRect(ctx, (x - sx) * 96 / side, (y - sy) * 96 / side, w * 96 / side, h * 96 / side, '#2ce8f5', 2, [4, 3]);
  }
  for (const b of $$('[data-obj]')) b.onclick = () => {
    const k = +b.dataset.obj;
    S.lv.obj = S.lv.obj === k ? null : k;
    $$('[data-obj]').forEach((x) => x.classList.toggle('on', +x.dataset.obj === S.lv.obj));
    draw();
    if (S.lv.obj != null) revealLevel(...objBox(a.objects[k]));
  };
  wireSelection(canvas, () => stage.surface);
  draw();
  if (S.focus) {   // opened from a critique: show its spot
    const c = S.crits.find((x) => x.id === S.focus);
    if (c?.target.region) revealLevel(...c.target.region);
  } else revealLevel(...a.screens[S.lv.screen], ...a.screen);
  animators.push((dt, t) => { const k = Math.floor(t / 90); if (S.sel && k !== ants) { ants = k; draw(); } });
  observeStage(draw, key);
}

function renderLevelTabs(a, view) {
  const el = $('#tabs');
  if (!el) return;
  const n = activeCrits((c) => c.target.asset === a.name).length;
  el.innerHTML = `<a class="tab ${view === 'level' ? 'on' : ''}" href="#/a/${enc(a.name)}">${icon('map')}Level${n ? `<span class="badge">${n}</span>` : ''}</a>
    <span class="spacer"></span><a class="tab ${view === 'game' ? 'on' : ''}" href="#/a/${enc(a.name)}/~game">${icon('game')}Play</a>`;
}

// stage controls -------------------------------------------------------
function wireZoom(draw) {
  for (const b of $$('[data-z]')) b.onclick = () => {
    const steps = [1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24];
    const z = S.view.zoom ?? 4;
    const i = steps.findIndex((s) => s >= z);
    S.view.userZoom = true;
    S.view.zoom = +b.dataset.z > 0 ? steps[Math.min(steps.length - 1, (steps[i] === z ? i + 1 : i))] : steps[Math.max(0, (i < 0 ? steps.length : i) - 1)];
    draw();
  };
}

let stageObserver = null;
function observeStage(draw, name) {
  stageObserver?.disconnect();
  const el = $('.stage');
  if (!el) return;
  let first = true;
  stageObserver = new ResizeObserver(() => {
    if (first) { first = false; return; }
    if (S.view.zoomFor === name && !S.view.userZoom) { S.view.zoom = null; draw(); }
  });
  stageObserver.observe(el);
}

function wireSelection(canvas, surface) {
  let drag = null;
  const toArt = (e) => {
    const r = canvas.getBoundingClientRect();
    const z = S.view.zoom;
    return [Math.floor((e.clientX - r.left) / r.width * canvas.width / z), Math.floor((e.clientY - r.top) / r.height * canvas.height / z)];
  };
  canvas.onpointerdown = (e) => {
    if (e.button !== 0) return;
    if (stage.rotated?.()) { stage.unrotate(); stage.draw(); }
    const s = surface();
    let [x, y] = toArt(e);
    let base = [0, 0];
    if (s.wrap) { base = [Math.floor(x / s.w) * s.w, Math.floor(y / s.h) * s.h]; x -= base[0]; y -= base[1]; }
    if (x < 0 || y < 0 || x >= s.w || y >= s.h) return;
    stage.pause();
    drag = { x, y, base, s, moved: false };
    S.focus = null;
    S.sel = [x, y, 1, 1];
    canvas.setPointerCapture(e.pointerId);
    stage.draw();
  };
  canvas.onpointermove = (e) => {
    if (!drag) return;
    let [x, y] = toArt(e);
    x = Math.max(0, Math.min(drag.s.w - 1, x - drag.base[0]));
    y = Math.max(0, Math.min(drag.s.h - 1, y - drag.base[1]));
    if (x !== drag.x || y !== drag.y) drag.moved = true;
    S.sel = [Math.min(x, drag.x), Math.min(y, drag.y), Math.abs(x - drag.x) + 1, Math.abs(y - drag.y) + 1];
    stage.draw();
    renderSelInfo();
  };
  const end = () => {
    if (!drag) return;
    const { s, moved } = drag;
    drag = null;
    if (!moved && s.mapCell) {          // a click on the map marks that whole tile
      const [cw, ch] = s.mapCell;
      S.sel = [Math.floor(S.sel[0] / cw) * cw, Math.floor(S.sel[1] / ch) * ch, cw, ch];
    }
    S.scope = null;
    stage.draw();
    renderSelInfo();
    refreshCritsLight();
    updateComposer();
    $('#crit-text')?.focus({ preventScroll: true });
  };
  canvas.onpointerup = end;
  canvas.onpointercancel = end;
}

function renderSelInfo() {
  const el = $('#selinfo');
  if (!el) return;
  if (!S.sel) { el.innerHTML = ''; return; }
  const [x, y, w, h] = S.sel;
  el.innerHTML = `<div class="selinfo">${icon('scan', 'i-sm')}<span><b class="num">${w}×${h}</b> at <span class="num">${x}, ${y}</span></span>
    <button class="btn icon ghost" id="clear-sel" title="Clear (Esc)" aria-label="Clear spot">${icon('x', 'i-sm')}</button></div>`;
  $('#clear-sel').onclick = clearSel;
}
function clearSel() {
  S.sel = null;
  renderSelInfo();
  stage?.draw();
  updateComposer();
}

// menus ----------------------------------------------------------------
function openMenu(anchor, html, wire) {
  closeMenu();
  const m = document.createElement('div');
  m.className = 'menu';
  m.setAttribute('role', 'menu');
  m.innerHTML = html;
  document.body.append(m);
  const r = anchor.getBoundingClientRect();
  const mw = m.offsetWidth, mh = m.offsetHeight;
  m.style.left = `${Math.max(8, Math.min(innerWidth - mw - 8, r.left + r.width / 2 - mw / 2))}px`;
  m.style.top = `${r.top - mh - 8 > 8 ? r.top - mh - 8 : r.bottom + 8}px`;
  S.menu = m;
  wire(m);
  $('button', m)?.focus({ preventScroll: true });
  setTimeout(() => addEventListener('pointerdown', outside), 0);
}
function outside(e) { if (S.menu && !S.menu.contains(e.target)) closeMenu(); }
function closeMenu() { S.menu?.remove(); S.menu = null; removeEventListener('pointerdown', outside); }

function groundMenu(anchor, draw) {
  const list = groundChoices();
  let html = '<div class="menu-label">Ground</div>', group = null;
  for (const g of list) {
    if (g.group && g.group !== group) { group = g.group; html += `<div class="menu-sep"></div><div class="menu-label">${esc(group)}</div>`; }
    html += `<button class="menu-item" role="menuitemradio" aria-checked="${S.view.bg === g.id}" data-bg="${esc(g.id)}">
      <canvas class="sw" width="16" height="16" data-sw="${esc(g.id)}"></canvas>${esc(g.label)}${S.view.bg === g.id ? `<span class="check">${icon('check', 'i-sm')}</span>` : ''}</button>`;
  }
  openMenu(anchor, html, (m) => {
    for (const c of $$('canvas[data-sw]', m)) { const ctx = sizeCanvas(c, 16, 16); paintBg(ctx, 16, 16, 1, c.dataset.sw); }
    for (const b of $$('[data-bg]', m)) b.onclick = () => { S.view.bg = b.dataset.bg; closeMenu(); draw(); };
  });
}

function overlayMenu(anchor, draw, oneShot) {
  const items = [['boxes', 'Hit and hurt boxes'], ['origin', 'Origin'], ['onion', 'Onion skin'], ['grid', 'Pixel grid']];
  if (oneShot) items.push(['repeat', 'Repeat (plays once in game)']);
  const html = '<div class="menu-label">Overlays</div>' + items.map(([k, l]) =>
    `<button class="menu-item" role="menuitemcheckbox" aria-checked="${!!S.view[k]}" data-k="${k}">${l}${S.view[k] ? `<span class="check">${icon('check', 'i-sm')}</span>` : ''}</button>`).join('');
  openMenu(anchor, html, (m) => {
    for (const b of $$('[data-k]', m)) b.onclick = () => {
      S.view[b.dataset.k] = !S.view[b.dataset.k];
      draw();
      anchor.classList.toggle('on', S.view.boxes || S.view.origin || S.view.onion || S.view.grid);
      overlayMenu(anchor, draw, oneShot);
    };
  });
}

function facingMenu(anchor, draw) {
  const opts = [['spin', 'Spinning'], ...[0, 45, 90, 135, 180, 225, 270, 315].map((d) => [d, `${d}°`])];
  const cur = S.view.spin ? 'spin' : Math.round(S.view.angle * 180 / Math.PI);
  const html = '<div class="menu-label">Facing</div>' + opts.map(([v, l]) =>
    `<button class="menu-item" role="menuitemradio" aria-checked="${v === cur}" data-v="${v}">${l}${v === cur ? `<span class="check">${icon('check', 'i-sm')}</span>` : ''}</button>`).join('');
  openMenu(anchor, html, (m) => {
    for (const b of $$('[data-v]', m)) b.onclick = () => {
      S.view.spin = b.dataset.v === 'spin';
      if (!S.view.spin) S.view.angle = +b.dataset.v * Math.PI / 180;
      if (S.view.spin || S.view.angle) S.sel = null;
      anchor.classList.toggle('on', S.view.spin || !!S.view.angle);
      closeMenu(); renderSelInfo(); draw();
    };
  });
}

// ---------- rail: composer + this asset's critiques ----------
function scopesFor() {
  const r = S.route, a = assetOf(r.name);
  if (!a || a.type === 'error' || r.sub === '~game') return [];
  const spot = { id: 'spot', label: 'Spot', icon: 'scan', disabled: !S.sel, title: S.sel ? 'The marked spot' : 'Drag on the art to mark a spot' };
  const whole = { id: 'asset', label: cap(typeInfo(a).noun), icon: a.type === 'level' ? 'map' : animated(a) ? 'box' : 'tiles' };
  if (a.type === 'level') return [spot, { id: 'screen', label: `Screen ${S.lv.screen + 1}`, icon: 'grid', title: 'What the camera shows at this screen' }, whole];
  if (animated(a)) return [spot, { id: 'frame', label: 'Frame', icon: 'image' }, { id: 'anim', label: a.type === 'prop' ? 'State' : 'Animation', icon: 'film' }, whole];
  if (r.view === 'map') return [spot, whole];
  return [spot, { id: 'tile', label: cap(typeInfo(a).cells.replace(/s$/, '')), icon: 'image' }, whole];
}

function currentScope() {
  const list = scopesFor();
  const ok = (id) => list.some((s) => s.id === id && !s.disabled);
  if (S.scope && ok(S.scope)) return S.scope;
  if (S.sel) return 'spot';
  const a = assetOf(S.route.name);
  if (a?.type === 'level') return 'asset';
  if (animated(a)) return S.play.playing ? 'anim' : 'frame';
  return S.route.view === 'map' ? 'asset' : list.length ? 'tile' : 'asset';
}

function targetFor(scope) {
  const r = S.route, a = assetOf(r.name);
  const t = { asset: a.name };
  if (a.type === 'level') {   // a spot or a whole screen, in level pixels
    t.level = true;
    if (scope === 'spot') t.region = S.sel;
    if (scope === 'screen') {
      const [x, y] = a.screens[S.lv.screen];
      t.region = [x, y, Math.min(a.screen[0], a.w - x), Math.min(a.screen[1], a.h - y)];
    }
    return t;
  }
  if (animated(a)) {
    const anim = a.anims.find((x) => x.name === r.sub) ?? idleOf(a);
    if (scope !== 'asset') t.anim = anim.name;
    if (scope === 'frame' || scope === 'spot') t.frame = S.play.frame;
  } else if (r.view === 'map') {
    if (scope === 'spot') t.map = true;
  } else if (scope !== 'asset') t.tile = r.tile;
  if (scope === 'spot') t.region = S.sel;
  return t;
}

function renderRail() {
  const rail = $('#rail');
  const a = assetOf(S.route.name);
  if (S.route.page !== 'asset' || !a || a.type === 'error') { rail.innerHTML = ''; return; }
  const game = S.route.sub === '~game';
  rail.innerHTML = (game ? '' : `<div class="composer">
      <div class="scopes" id="scopes" role="radiogroup" aria-label="What the critique is about"></div>
      <div class="target" id="target"></div>
      <div class="field"><label class="sr" for="crit-text">Critique</label>
        <textarea id="crit-text" placeholder="What should Claude fix?" rows="3"></textarea>
        <div class="row"><span class="err" id="crit-err" role="alert"></span>
          <button class="btn primary" id="send">Send to Claude <span class="kbd">${MAC ? '⌘' : 'Ctrl'} ↵</span></button></div></div>
    </div>`) + `<div class="rail-list" id="rail-list"></div>`;
  if (!game) {
    const ta = $('#crit-text');
    ta.value = S.draft;
    ta.oninput = () => { S.draft = ta.value; $('#crit-err').textContent = ''; updateComposer(); };
    $('#send').onclick = send;
  }
  updateComposer();
  renderRailList();
}

function updateComposer() {
  const box = $('#scopes');
  if (!box) return;
  const list = scopesFor(), cur = currentScope();
  box.innerHTML = list.map((s) => `<button class="scope ${s.id === cur ? 'on' : ''}" role="radio" aria-checked="${s.id === cur}" data-scope="${s.id}"
      ${s.disabled ? 'disabled' : ''} title="${esc(s.title ?? '')}">${icon(s.icon, 'i-sm')}${s.label}</button>`).join('');
  for (const b of $$('[data-scope]', box)) b.onclick = () => {
    S.scope = b.dataset.scope;
    if (S.scope === 'frame') stage?.pause();
    if (S.scope === 'anim' && S.sel) clearSel();
    updateComposer();
  };
  const t = targetFor(cur);
  $('#target').innerHTML = `${icon(targetIcon(t), 'i-sm')}<b>${esc(targetText(t, false))}</b>` +
    (!S.sel && list.some((s) => s.id === 'spot') ? `<span class="hint">· or drag on the art</span>` : '');
  const btn = $('#send');
  btn.disabled = !($('#crit-text')?.value.trim());
}

async function send() {
  const ta = $('#crit-text');
  const text = ta?.value.trim();
  if (!text) { ta?.focus(); return; }
  const btn = $('#send');
  btn.disabled = true;
  try {
    const c = await api('/api/critiques', { method: 'POST', body: JSON.stringify({ target: targetFor(currentScope()), text }) });
    S.crits.push(c);
    ta.value = '';
    S.draft = '';
    S.sel = null;
    S.scope = null;
    S.focus = c.id;
    S.railFilter = 'active';
    renderSelInfo();
    refreshCrits();
    toast(S.watching ? `Sent #${c.id} to Claude` : `Saved #${c.id}. Claude picks it up when it's watching`, 'check');
  } catch (err) {
    $('#crit-err').textContent = err.message;
  } finally {
    updateComposer();
  }
}

function renderRailList() {
  const el = $('#rail-list');
  if (!el) return;
  const a = assetOf(S.route.name);
  const mine = critsFor(a.name);
  const active = mine.filter((c) => c.status !== 'fixed').sort((x, y) => y.id - x.id);
  const fixed = mine.filter((c) => c.status === 'fixed').sort((x, y) => y.updated.localeCompare(x.updated));
  const shown = S.railFilter === 'fixed' ? fixed : active;
  el.innerHTML = `<div class="rail-head"><h2>Critiques</h2><div class="seg" role="tablist">
      <button role="tab" aria-selected="${S.railFilter === 'active'}" class="${S.railFilter === 'active' ? 'on' : ''}" data-f="active">Open <span class="num">${active.length || ''}</span></button>
      <button role="tab" aria-selected="${S.railFilter === 'fixed'}" class="${S.railFilter === 'fixed' ? 'on' : ''}" data-f="fixed">Fixed <span class="num">${fixed.length || ''}</span></button></div></div>` +
    (shown.length ? shown.map((c) => critRow(c, { withAsset: false })).join('')
      : `<div class="empty">${S.railFilter === 'fixed' ? 'Nothing fixed yet.' : `No open critiques on ${esc(a.name)}.`}</div>`);
  for (const b of $$('[data-f]', el)) b.onclick = () => { S.railFilter = b.dataset.f; renderRailList(); };
  wireCrits(el);
}

// critiques changed (poll, send, delete): update everything that shows them, keep the stage running
function refreshCrits() {
  renderNav();
  renderWatch();
  const r = S.route;
  if (r.page === 'overview' || r.page === 'critiques') { renderPage(); return; }
  refreshCritsLight();
  renderRailList();
  updateComposer();
}
function refreshCritsLight() {
  const r = S.route, a = assetOf(r.name);
  if (!a || a.type === 'error') return;
  if (a.type === 'level') renderLevelTabs(a, r.view);
  else if (animated(a)) {
    const anim = a.anims.find((x) => x.name === r.sub) ?? (r.sub === '~game' ? null : idleOf(a));
    renderSpriteTabs(a, anim);
    if (anim) $$('.fr', $('#strip')).forEach((el, k) => {
      const nc = activeCrits((c) => c.target.asset === a.name && c.target.anim === anim.name && c.target.frame === k).length;
      $('.cdot', el)?.remove();
      if (nc) el.insertAdjacentHTML('beforeend', `<span class="cdot badge">${nc}</span>`);
    });
  } else renderTileTabs(a, r.view);
  stage?.draw();
}

// ---------- routing ----------
function parseRoute() {
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent);
  if (parts[0] === 'critiques') return { page: 'critiques' };
  if (parts[0] === 'a' && parts[1]) return { page: 'asset', name: parts[1], sub: parts[2] ?? null, frame: parts[3] != null ? +parts[3] : null };
  return { page: 'overview' };
}

function renderPage() {
  animators = [];
  stage = null;
  stageObserver?.disconnect();
  const page = $('#page');
  const r = S.route;
  if (r.page === 'critiques') critiquesPage(page);
  else if (r.page === 'asset') assetPage(page);
  else overviewPage(page);
}

function render({ keep = false } = {}) {
  const prev = S.route;
  const r = parseRoute();
  const sameAsset = prev.page === 'asset' && r.page === 'asset' && prev.name === r.name;
  if (!keep) {
    if (!(sameAsset && prev.sub === r.sub && r.frame == null)) S.play = { playing: r.frame == null, frame: r.frame ?? 0, acc: 0 };
    S.sel = null;
    S.scope = null;
    S.focus = S.pendingFocus;
    S.pendingFocus = null;
    if (!sameAsset) S.railFilter = 'active';
    closeMenu();
  }
  S.route = r;
  $('#app').classList.toggle('no-rail', r.page !== 'asset' || !assetOf(r.name) || assetOf(r.name).type === 'error');
  renderWs();
  renderNav();
  renderWatch();
  renderTop();
  const scroll = $('#page').scrollTop;
  renderPage();
  if (keep) $('#page').scrollTop = scroll;
  if (keep && $('#crit-text')) { updateComposer(); renderRailList(); }
  else renderRail();
  renderSelInfo();
  const a = assetOf(r.name);
  document.title = [r.page === 'asset' ? r.name : r.page === 'critiques' ? 'Critiques' : null, S.project?.game, 'pixelforge'].filter(Boolean).join(' · ');
  if (animated(a) && r.sub && r.sub !== '~game' && !a.anims.some((x) => x.name === r.sub)) history.replaceState(null, '', `#/a/${enc(a.name)}`);
}

addEventListener('hashchange', () => render());
addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && S.menu) { closeMenu(); return; }
  const typing = /^(TEXTAREA|INPUT|SELECT)$/.test(e.target.tagName);
  if (typing) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); send(); }
    if (e.key === 'Escape') e.target.blur();
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey || S.route.page !== 'asset' || !stage) return;
  if (e.target.closest?.('.crit, .menu')) return;
  if (e.key === ' ') { e.preventDefault(); stage.togglePlay(); }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); stage.step(-1); }
  else if (e.key === 'ArrowRight') { e.preventDefault(); stage.step(1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); stage.nav(-1); }
  else if (e.key === 'ArrowDown') { e.preventDefault(); stage.nav(1); }
  else if (e.key === 'Escape') { if (S.sel) clearSel(); else if (S.focus) { S.focus = null; refreshCrits(); } }
  else if (e.key === 'c') { const ta = $('#crit-text'); if (ta) { e.preventDefault(); ta.focus(); } }
});

let last = 0;
function tick(t) {
  const dt = last ? Math.min(t - last, 250) : 0;
  last = t;
  for (const fn of animators) fn(dt, t);
  requestAnimationFrame(tick);
}

async function boot() {
  try {
    const [, st] = await Promise.all([loadProject(), api('/api/state')]);
    S.crits = st.critiques;
    S.watching = st.watching;
  } catch (err) {
    S.online = false;
    $('#page').innerHTML = `<div class="error-box"><h3>Can't load the project</h3><pre>${esc(err.message)}\n\nStart the dashboard with: pixelforge serve</pre></div>`;
    renderTop();
    setTimeout(boot, 2000);
    return;
  }
  // links from the old viewer: /viewer/?sprite=knight and #/knight/attack
  const legacy = new URLSearchParams(location.search).get('sprite');
  if (legacy && !location.hash) history.replaceState(null, '', `#/a/${enc(legacy)}`);
  const old = location.hash.match(/^#\/([^/]+)(\/.*)?$/);
  if (old && old[1] !== 'a' && old[1] !== 'critiques' && S.assets.has(decodeURIComponent(old[1]))) history.replaceState(null, '', `#/a/${old[1]}${old[2] ?? ''}`);
  render();
  requestAnimationFrame(tick);
  setTimeout(poll, POLL_MS);
}
boot();
