import type { Block, StructureIR } from './ir.js';
import { dark, esc, num, isFixture, fixtureMark, type Theme } from './theme.js';

export interface Box3D { id: string; label: string; kind: string; x: number; y: number; z: number; w: number; d: number; h: number; color: string; level: number; part?: string }
export interface Annotation { text: string; x: number; y: number; z: number; anchor: 'start' | 'middle' | 'end' }
export interface Scene { title: string; boxes: Box3D[]; annotations: Annotation[]; notes: string[]; bounds: { w: number; d: number; h: number }; focus?: { x: number; y: number; z: number }; detail?: Scene }
// Axes: x = east, y = south, z = up. (Three.js: map to (x, z, y).)

const KIND_COLOR: Record<string, string> = { chip: '#6f6758', board: '#2f6b4f', array: '#d58d57', cell: '#d58d57', periphery: '#5fa598', module: '#7f9fd0', layer: '#b48ad0', part: '#e2b24c', region: '#8f8a7e' };
const PALETTE = ['#d58d57', '#5fa598', '#7f9fd0', '#b48ad0', '#e2b24c', '#c9776b'];
const colorOf = (k: string) => KIND_COLOR[k] ?? '#9a9488';
const MAX_AXIS = 32;

const shapeDims = (shape: number[]) => {
  const ch = shape[shape.length - 1] ?? 8, rest = shape.slice(0, -1).reduce((a, b) => a * b, 1);
  return { w: Math.min(16, Math.max(3, 1.6 + Math.log2(Math.max(2, ch)) * 1.1)), d: Math.min(34, Math.max(9, 4 + Math.log2(Math.max(2, rest * ch)) * 1.15)) };
};

export function buildStructureScene(ir: StructureIR): Scene {
  const root = ir.root, kids = root.children ?? [];
  const scene: Scene = { title: ir.title ?? root.label, boxes: [], annotations: [], notes: [], bounds: { w: 0, d: 0, h: 0 } };
  const arr = kids.find((k) => k.kind === 'array');
  if (arr) buildArrayScene(scene, root, arr, kids);
  else if (kids.length && kids.every((k) => k.tensor_shape || k.kind === 'layer')) buildLayerRow(scene, root, kids);
  else buildGrid(scene, root, kids);
  const b = { w: 0, d: 0, h: 0 };
  scene.boxes.forEach((x) => { b.w = Math.max(b.w, x.x + x.w); b.d = Math.max(b.d, x.y + x.d); b.h = Math.max(b.h, x.z + x.h); });
  scene.bounds = b; return scene;
}

function buildArrayScene(sc: Scene, root: Block, arr: Block, kids: Block[]) {
  const cell = arr.children?.[0];
  const c = typeof arr.count === 'number' ? { rows: 1, cols: arr.count } : arr.count ?? { rows: 1, cols: 1 };
  if (arr.count === undefined) sc.notes.push('Array size not stated in the source; drawn as a single cell.');
  const f = cell?.dims?.w ? 10 / cell.dims.w : 1;
  const cw = 10, cd = cell?.dims?.d ? cell.dims.d * f : 10, ch = cell?.dims?.h ? cell.dims.h * f : 6;
  const rows = Math.min(c.rows, MAX_AXIS), cols = Math.min(c.cols, MAX_AXIS);
  if (rows < c.rows || cols < c.cols) sc.notes.push(`Showing ${rows}x${cols} of ${c.rows}x${c.cols} cells.`);
  const gap = 2, AW = cols * cw + (cols - 1) * gap, AD = rows * cd + (rows - 1) * gap;
  const per = kids.filter((k) => k !== arr && k.kind !== 'cell');
  const posOf = (k: Block): 'left' | 'right' | 'top' | 'bottom' => (typeof k.pos === 'string' && ['left', 'right', 'top', 'bottom'].includes(k.pos) ? (k.pos as 'left') : 'bottom');
  const thick = (k: Block, axis: 'w' | 'd') => (k.dims?.[axis] ? k.dims[axis]! * f : 13);
  const side = { left: 0, right: 0, top: 0, bottom: 0 } as Record<string, number>;
  per.forEach((k) => { const p = posOf(k); side[p] = Math.max(side[p], p === 'left' || p === 'right' ? thick(k, 'w') : thick(k, 'd')); });
  const M = 8, G = 3;
  const ax = M + side.left + (side.left ? G : 0), ay = M + side.top + (side.top ? G : 0);
  const totalW = ax + AW + (side.right ? G + side.right : 0) + M, totalD = ay + AD + (side.bottom ? G + side.bottom : 0) + M;
  const plateH = 1.4;
  sc.boxes.push({ id: root.id, label: root.label, kind: root.kind, x: 0, y: 0, z: 0, w: totalW, d: totalD, h: plateH, color: colorOf(root.kind), level: 0 });
  sc.annotations.push({ text: root.label, x: totalW / 2, y: totalD + 5, z: 0, anchor: 'middle' });
  for (let r = 0; r < rows; r++) for (let q = 0; q < cols; q++)
    sc.boxes.push({ id: `${arr.id}[${r},${q}]`, label: cell?.label ?? 'cell', kind: 'cell', x: ax + q * (cw + gap), y: ay + r * (cd + gap), z: plateH, w: cw, d: cd, h: ch, color: colorOf('cell'), level: 1 });
  sc.focus = { x: ax + cw / 2, y: ay + cd / 2, z: plateH + ch };
  sc.annotations.push({ text: `${arr.label}${arr.count !== undefined ? `  ${c.rows} x ${c.cols}` : ''}`, x: ax + AW / 2, y: ay - 4, z: plateH + ch + 1, anchor: 'middle' });
  per.forEach((k) => {
    const p = posOf(k); const ph = Math.max(2.5, ch * 0.7);
    const horiz = p === 'left' || p === 'right'; const t = horiz ? thick(k, 'w') : thick(k, 'd');
    const x = p === 'left' ? ax - G - t : p === 'right' ? ax + AW + G : ax, y = p === 'top' ? ay - G - t : p === 'bottom' ? ay + AD + G : ay;
    sc.boxes.push({ id: k.id, label: k.label, kind: k.kind, x, y, z: plateH, w: horiz ? t : AW, d: horiz ? AD : t, h: ph, color: colorOf(k.kind), level: 1, part: k.part });
    const lx = p === 'left' ? x - 1.5 : p === 'right' ? x + t + 1.5 : x + AW / 2, ly = p === 'top' ? y - 2 : p === 'bottom' ? y + t + 4 : y + AD / 2;
    sc.annotations.push({ text: k.label, x: lx, y: ly, z: plateH + ph, anchor: p === 'left' ? 'end' : p === 'right' ? 'start' : 'middle' });
  });
  // detail scene: what is inside one repeated cell
  const parts = cell?.children ?? [];
  if (parts.length) {
    const n = parts.length, cols2 = n <= 3 ? n : Math.ceil(n / 2), rows2 = Math.ceil(n / cols2);
    const d: Scene = { title: `${cell!.label} (detail)`, boxes: [], annotations: [], notes: [], bounds: { w: 0, d: 0, h: 0 } };
    const bw = 16, bd = 20, g2 = 5, W = cols2 * bw + (cols2 + 1) * g2, D = rows2 * bd + (rows2 + 1) * g2;
    d.boxes.push({ id: cell!.id, label: cell!.label, kind: 'cell', x: 0, y: 0, z: 0, w: W, d: D, h: 1.4, color: '#6f6758', level: 0 });
    parts.forEach((p, i) => {
      const r = Math.floor(i / cols2), q = i % cols2, x = g2 + q * (bw + g2), y = g2 + r * (bd + g2);
      d.boxes.push({ id: p.id, label: p.label, kind: p.kind, x, y, z: 1.4, w: bw, d: bd, h: 7, color: PALETTE[i % PALETTE.length], level: 1, part: p.part });
      d.annotations.push({ text: p.label, x: x + bw / 2, y: y + bd / 2, z: 8.6, anchor: 'middle' });
    });
    d.bounds = { w: W, d: D, h: 8.4 }; sc.detail = d;
  }
}

function buildLayerRow(sc: Scene, root: Block, kids: Block[]) {
  let x = 6; const gap = 12; const y0 = 6; let maxD = 0;
  kids.forEach((k, i) => {
    const sd = k.tensor_shape ? shapeDims(k.tensor_shape) : { w: 6, d: 14 };
    const w = k.dims?.w ?? sd.w, d = k.dims?.d ?? sd.d, h = k.dims?.h ?? Math.min(9, Math.max(4, d * 0.3));
    sc.boxes.push({ id: k.id, label: k.label, kind: k.kind, x, y: y0 + (34 - d) / 2, z: 1.2, w, d, h, color: PALETTE[i % PALETTE.length], level: 1 });
    sc.annotations.push({ text: k.label, x: x + w / 2, y: y0 + (34 - d) / 2 + d + 3, z: 1.2, anchor: 'middle' });
    if (k.tensor_shape) sc.annotations.push({ text: `[${k.tensor_shape.join(' x ')}]`, x: x + w / 2, y: y0 + (34 - d) / 2 + d + 8.5, z: 1.2, anchor: 'middle' });
    x += w + gap; maxD = Math.max(maxD, d);
  });
  sc.boxes.unshift({ id: root.id, label: root.label, kind: 'region', x: 0, y: 0, z: 0, w: x + 4, d: 46, h: 1.2, color: '#6f6758', level: 0 });
  sc.annotations.push({ text: root.label, x: (x + 4) / 2, y: -3, z: 0, anchor: 'middle' });
}

function buildGrid(sc: Scene, root: Block, kids: Block[]) {
  const n = Math.max(1, kids.length), cols = Math.ceil(Math.sqrt(n)); const cell = 22, gap = 6;
  const rows = Math.ceil(n / cols), W = cols * (cell + gap) + gap, D = rows * (cell + gap) + gap + 6;
  const plate = ['chip', 'board', 'module', 'region'].includes(root.kind);
  if (plate) sc.boxes.push({ id: root.id, label: root.label, kind: root.kind, x: 0, y: 0, z: 0, w: W, d: D, h: 1.4, color: colorOf(root.kind), level: 0 });
  kids.forEach((k, i) => {
    const r = Math.floor(i / cols), q = i % cols, w = k.dims?.w ?? 16, d = k.dims?.d ?? 14, h = k.dims?.h ?? 7;
    const x = gap + q * (cell + gap) + (cell - w) / 2, y = gap + 6 + r * (cell + gap) + (cell - d) / 2;
    sc.boxes.push({ id: k.id, label: k.label, kind: k.kind, x, y, z: plate ? 1.4 : 0, w, d, h, color: colorOf(k.kind), level: 1, part: k.part });
    sc.annotations.push({ text: k.label, x: x + w / 2, y: y + d + 3, z: plate ? 1.4 : 0, anchor: 'middle' });
  });
  if (!kids.length) sc.notes.push('No sub-structure was extracted; nothing to draw.');
}

// ------------------------------------------------------------------ isometric preview (no WebGL needed)
const C30 = Math.cos(Math.PI / 6), S30 = 0.5;
const iso = (x: number, y: number, z: number): [number, number] => [(x - y) * C30, (x + y) * S30 - z];
function shade(hex: string, k: number): string {
  const v = parseInt(hex.slice(1), 16), r = Math.round(((v >> 16) & 255) * k), g = Math.round(((v >> 8) & 255) * k), b = Math.round((v & 255) * k);
  return `#${[r, g, b].map((c) => Math.min(255, c).toString(16).padStart(2, '0')).join('')}`;
}
function drawScene(sc: Scene, th: Theme, scale: number, ox: number, oy: number) {
  const out: string[] = []; const P = (x: number, y: number, z: number) => { const [a, b] = iso(x, y, z); return `${num(ox + a * scale)},${num(oy + b * scale)}`; };
  const boxes = [...sc.boxes].sort((a, b) => a.level - b.level || (a.x + a.w / 2 + a.y + a.d / 2) - (b.x + b.w / 2 + b.y + b.d / 2) || a.z - b.z);
  const sw = Math.max(0.25, Math.min(0.9, scale * 0.12));
  for (const b of boxes) {
    const { x, y, z, w, d, h } = b; const st = `stroke="${shade(b.color, 0.45)}" stroke-width="${num(sw)}" stroke-linejoin="round"`;
    out.push(`<polygon points="${P(x, y + d, z)} ${P(x + w, y + d, z)} ${P(x + w, y + d, z + h)} ${P(x, y + d, z + h)}" fill="${shade(b.color, 0.78)}" ${st} />`);
    out.push(`<polygon points="${P(x + w, y, z)} ${P(x + w, y + d, z)} ${P(x + w, y + d, z + h)} ${P(x + w, y, z + h)}" fill="${shade(b.color, 0.6)}" ${st} />`);
    out.push(`<polygon points="${P(x, y, z + h)} ${P(x + w, y, z + h)} ${P(x + w, y + d, z + h)} ${P(x, y + d, z + h)}" fill="${b.color}" ${st} />`);
  }
  for (const a of sc.annotations) { const [px, py] = P(a.x, a.y, a.z).split(',').map(Number); out.push(`<text x="${num(px)}" y="${num(py)}" text-anchor="${a.anchor}" class="al">${esc(a.text)}</text>`); }
  return out.join('\n');
}
function projBox(sc: Scene) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const b of sc.boxes) for (const [x, y, z] of [[b.x, b.y, b.z], [b.x + b.w, b.y, b.z], [b.x, b.y + b.d, b.z], [b.x + b.w, b.y + b.d, b.z], [b.x, b.y, b.z + b.h], [b.x + b.w, b.y + b.d, b.z + b.h], [b.x + b.w, b.y, b.z + b.h], [b.x, b.y + b.d, b.z + b.h]] as const) {
    const [a, c] = iso(x, y, z); x0 = Math.min(x0, a); x1 = Math.max(x1, a); y0 = Math.min(y0, c); y1 = Math.max(y1, c);
  }
  return { x0, y0, x1, y1 };
}

export function renderStructureIso(ir: StructureIR, opts: { theme?: Theme } = {}) {
  const th = opts.theme ?? dark; const sc = buildStructureScene(ir);
  const mb = projBox(sc), mw = mb.x1 - mb.x0, mh = mb.y1 - mb.y0;
  const mainW = sc.detail ? 700 : 880; const s1 = Math.min(mainW / mw, 560 / mh);
  const pad = 70, top = 56;
  const mainOx = pad - mb.x0 * s1, mainOy = top + pad - mb.y0 * s1;
  let W = pad * 2 + mw * s1, H = top + pad * 2 + mh * s1, detailSvg = '', conn = '';
  if (sc.detail) {
    const db = projBox(sc.detail), dw = db.x1 - db.x0, dh = db.y1 - db.y0; const s2 = Math.min(300 / dw, 280 / dh);
    const dx0 = pad + mw * s1 + 90, dOx = dx0 - db.x0 * s2, dOy = top + pad + 20 - db.y0 * s2;
    detailSvg = `<g>${drawScene(sc.detail, th, s2, dOx, dOy)}</g><text x="${num(dx0)}" y="${num(top + pad - 14)}" class="cap">${esc(sc.detail.title)}</text>`;
    W = dx0 + dw * s2 + pad; H = Math.max(H, top + pad * 2 + dh * s2 + 40);
    if (sc.focus) { const [fx, fy] = iso(sc.focus.x, sc.focus.y, sc.focus.z); conn = `<path d="M${num(mainOx + fx * s1)},${num(mainOy + fy * s1)} L${num(dx0 - 12)},${num(top + pad + 4)}" class="conn" /><circle cx="${num(mainOx + fx * s1)}" cy="${num(mainOy + fy * s1)}" r="3" fill="${th.accent}" />`; }
  }
  const notes = sc.notes.map((n, i) => `<text x="${pad}" y="${num(H - 14 - i * 14)}" class="note">${esc(n)}</text>`).join('');
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${num(W)} ${num(H)}" width="${Math.round(W)}" height="${Math.round(H)}" font-family="${th.font}">
<style>.al{fill:${th.ink};font-size:11px;font-weight:600;paint-order:stroke;stroke:${th.bg};stroke-width:3px;stroke-linejoin:round} .cap{fill:${th.ink};font-size:12px;font-weight:700}
.title{fill:${th.ink};font-size:14px;font-weight:700} .note{fill:${th.muted};font-size:10.5px} .conn{stroke:${th.accent};stroke-width:1;stroke-dasharray:4 3;fill:none}</style>
<rect width="100%" height="100%" fill="${th.bg}" />
<text x="18" y="30" class="title">${esc(sc.title)}</text>${isFixture(ir.source) ? fixtureMark(th, W - 16, 30) : ''}
<g>${drawScene(sc, th, s1, mainOx, mainOy)}</g>${conn}${detailSvg}${notes}
</svg>`;
  return { svg, scene: sc, width: W, height: H };
}
