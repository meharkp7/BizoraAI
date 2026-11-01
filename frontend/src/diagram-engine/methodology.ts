import dagre from '@dagrejs/dagre';
import type { MethodologyIR, MethNode } from './ir.js';
import { dark, esc, num, isFixture, fixtureMark, type Theme } from './theme.js';

export interface MethodologyOptions { theme?: Theme; direction?: 'LR' | 'TB' }
const CH = 6.7;

function wrap(t: string, max: number): string[] {
  const words = t.split(/\s+/); const out: string[] = []; let cur = '';
  for (const w of words) { if ((cur + ' ' + w).trim().length > max && cur) { out.push(cur); cur = w; } else cur = (cur + ' ' + w).trim(); }
  if (cur) out.push(cur); return out.length ? out : [''];
}
interface Sized { n: MethNode; title: string[]; detail: string[]; params: string[]; w: number; h: number }
function size(n: MethNode): Sized {
  const title = wrap(n.label, 22), detail = n.detail ? wrap(n.detail, 30).slice(0, 3) : [];
  const entries = Object.entries(n.params ?? {}); const params = entries.slice(0, 3).map(([k, v]) => `${k}: ${v}`);
  if (entries.length > 3) params.push(`+${entries.length - 3} more`);
  const longest = Math.max(...title.map((l) => l.length * 1.1), ...detail.map((l) => l.length * 0.92), ...params.map((l) => l.length * 0.92), 12);
  let w = Math.max(132, longest * CH + 34), h = 22 + title.length * 17 + detail.length * 14 + params.length * 13 + (detail.length || params.length ? 4 : 0);
  if (n.kind === 'decision') { w *= 1.35; h *= 1.55; }
  if (n.kind === 'input' || n.kind === 'output') h = Math.max(h, 44);
  return { n, title, detail, params, w, h };
}
const kindColor = (k: string | undefined, th: Theme) =>
  ({ input: th.accent, output: th.accent, decision: th.warn, store: th.accent2, model: th.accent2, evaluation: th.warn, dataset: th.muted } as Record<string, string>)[k ?? ''] ?? th.line;

function rounded(pts: { x: number; y: number }[], r = 9): string {
  if (pts.length < 2) return '';
  let d = `M${num(pts[0].x)},${num(pts[0].y)}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1], b = pts[i], c = pts[i + 1];
    const l1 = Math.hypot(b.x - a.x, b.y - a.y), l2 = Math.hypot(c.x - b.x, c.y - b.y); const k = Math.min(r, l1 / 2, l2 / 2);
    const p1 = { x: b.x - ((b.x - a.x) / l1) * k, y: b.y - ((b.y - a.y) / l1) * k }, p2 = { x: b.x + ((c.x - b.x) / l2) * k, y: b.y + ((c.y - b.y) / l2) * k };
    d += ` L${num(p1.x)},${num(p1.y)} Q${num(b.x)},${num(b.y)} ${num(p2.x)},${num(p2.y)}`;
  }
  const e = pts[pts.length - 1]; return d + ` L${num(e.x)},${num(e.y)}`;
}

export function renderMethodology(ir: MethodologyIR, opts: MethodologyOptions = {}) {
  if (opts.direction) return layoutMethodology(ir, opts.theme ?? dark, opts.direction);
  const a = layoutMethodology(ir, opts.theme ?? dark, 'LR'), b = layoutMethodology(ir, opts.theme ?? dark, 'TB');
  const score = (r: { width: number; height: number }) => Math.abs(Math.log((r.width / r.height) / 1.7)); // prefer a screen-like aspect ratio
  return score(a) <= score(b) ? a : b;
}

function layoutMethodology(ir: MethodologyIR, th: Theme, dir: 'LR' | 'TB') {
  const g = new dagre.graphlib.Graph({ compound: true, multigraph: true });
  g.setGraph({ rankdir: dir, nodesep: 38, ranksep: 78, marginx: 40, marginy: 40, ranker: 'network-simplex' });
  g.setDefaultEdgeLabel(() => ({}));
  const groups = ir.groups ?? []; const gset = new Set(groups.map((x) => x.id));
  groups.forEach((gr) => g.setNode(gr.id, { label: gr.label, isGroup: true }));
  groups.forEach((gr) => { if (gr.parent && gset.has(gr.parent)) g.setParent(gr.id, gr.parent); });
  const sized = new Map(ir.nodes.map((n) => [n.id, size(n)]));
  ir.nodes.forEach((n) => { const s = sized.get(n.id)!; g.setNode(n.id, { width: s.w, height: s.h }); if (n.group && gset.has(n.group)) g.setParent(n.id, n.group); });
  const edges = ir.edges.filter((e) => sized.has(e.from) && sized.has(e.to));
  edges.forEach((e, i) => g.setEdge(e.from, e.to, { label: e.label ?? '', width: e.label ? e.label.length * 6 + 12 : 0, height: e.label ? 16 : 0, labelpos: 'c', minlen: 1 }, String(i)));
  dagre.layout(g);

  const out: string[] = []; let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const grow = (x: number, y: number) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); };
  // groups (outermost first)
  const depth = (id: string): number => { const p = groups.find((q) => q.id === id)?.parent; return p ? 1 + depth(p) : 0; };
  [...groups].sort((a, b) => depth(a.id) - depth(b.id)).forEach((gr) => {
    const n = g.node(gr.id); if (!n || !n.width) return;
    const x = n.x - n.width / 2 - 14, y = n.y - n.height / 2 - 30, w = n.width + 28, h = n.height + 44;
    grow(x, y); grow(x + w, y + h);
    out.push(`<rect x="${num(x)}" y="${num(y)}" width="${num(w)}" height="${num(h)}" rx="12" class="grp" /><text x="${num(x + 14)}" y="${num(y + 20)}" class="grp-t">${esc(gr.label.toUpperCase())}</text>`);
  });
  // edges
  const labels: string[] = [];
  edges.forEach((e, i) => {
    const ed = g.edge(e.from, e.to, String(i)); if (!ed?.points) return;
    ed.points.forEach((p: { x: number; y: number }) => grow(p.x, p.y));
    const fb = e.kind === 'feedback', ctl = e.kind === 'control';
    out.push(`<path d="${rounded(ed.points)}" class="edge ${fb ? 'fb' : ctl ? 'ctl' : ''}" marker-end="url(#${fb ? 'arf' : 'ar'})" />`);
    if (e.label && ed.x !== undefined) { const w = e.label.length * 6 + 10; labels.push(`<rect x="${num(ed.x - w / 2)}" y="${num(ed.y - 9)}" width="${num(w)}" height="17" rx="4" fill="${th.bg}" /><text x="${num(ed.x)}" y="${num(ed.y + 4)}" text-anchor="middle" class="el ${fb ? 'elf' : ''}">${esc(e.label)}</text>`); }
  });
  // nodes
  ir.nodes.forEach((n) => {
    const s = sized.get(n.id)!; const p = g.node(n.id); if (!p) return;
    const x = p.x - s.w / 2, y = p.y - s.h / 2, col = kindColor(n.kind, th); grow(x, y); grow(x + s.w, y + s.h);
    const dash = (n.confidence ?? 1) < 0.6 ? ' stroke-dasharray="5 4"' : n.kind === 'evaluation' ? ' stroke-dasharray="2 3"' : '';
    const sty = `fill="${th.panel}" stroke="${col}" stroke-width="1.7"${dash}`;
    let shape: string;
    switch (n.kind) {
      case 'input': case 'output': shape = `<rect x="${num(x)}" y="${num(y)}" width="${num(s.w)}" height="${num(s.h)}" rx="${num(s.h / 2)}" ${sty} />`; break;
      case 'decision': shape = `<polygon points="${num(p.x)},${num(y)} ${num(x + s.w)},${num(p.y)} ${num(p.x)},${num(y + s.h)} ${num(x)},${num(p.y)}" ${sty} />`; break;
      case 'store': shape = `<path d="M${num(x)},${num(y + 9)} a${num(s.w / 2)},9 0 0 1 ${num(s.w)},0 L${num(x + s.w)},${num(y + s.h - 9)} a${num(s.w / 2)},9 0 0 1 ${num(-s.w)},0 Z" ${sty} /><path d="M${num(x)},${num(y + 9)} a${num(s.w / 2)},9 0 0 0 ${num(s.w)},0" fill="none" stroke="${col}" stroke-width="1.2" />`; break;
      case 'model': shape = `<rect x="${num(x)}" y="${num(y)}" width="${num(s.w)}" height="${num(s.h)}" rx="7" ${sty} /><rect x="${num(x)}" y="${num(y)}" width="6" height="${num(s.h)}" rx="3" fill="${col}" />`; break;
      case 'dataset': shape = `<path d="M${num(x)},${num(y)} L${num(x + s.w - 14)},${num(y)} L${num(x + s.w)},${num(y + 14)} L${num(x + s.w)},${num(y + s.h)} L${num(x)},${num(y + s.h)} Z" ${sty} /><path d="M${num(x + s.w - 14)},${num(y)} L${num(x + s.w - 14)},${num(y + 14)} L${num(x + s.w)},${num(y + 14)}" fill="none" stroke="${col}" stroke-width="1.2" />`; break;
      default: shape = `<rect x="${num(x)}" y="${num(y)}" width="${num(s.w)}" height="${num(s.h)}" rx="7" ${sty} />`;
    }
    let ty = p.y - s.h / 2 + 22;
    const txt: string[] = [];
    s.title.forEach((l) => { txt.push(`<text x="${num(p.x)}" y="${num(ty)}" text-anchor="middle" class="nt">${esc(l)}</text>`); ty += 17; });
    s.detail.forEach((l) => { txt.push(`<text x="${num(p.x)}" y="${num(ty - 2)}" text-anchor="middle" class="nd">${esc(l)}</text>`); ty += 14; });
    s.params.forEach((l) => { txt.push(`<text x="${num(p.x)}" y="${num(ty - 1)}" text-anchor="middle" class="np">${esc(l)}</text>`); ty += 13; });
    const ev = n.evidence?.page ? `<text x="${num(x + s.w - 6)}" y="${num(y - 5)}" text-anchor="end" class="ev">p.${n.evidence.page}</text>` : n.evidence?.figure_id && n.evidence.figure_id !== 'fixture' ? `<text x="${num(x + s.w - 6)}" y="${num(y - 5)}" text-anchor="end" class="ev">${esc(n.evidence.figure_id)}</text>` : '';
    out.push(`<g class="node" data-node-id="${esc(n.id)}">${shape}${txt.join('')}${ev}</g>`);
  });
  out.push(...labels);
  const pad = 30, top = ir.title ? 30 : 0;
  const vx = x0 - pad, vy = y0 - pad - top, w = x1 - x0 + pad * 2, h = y1 - y0 + pad * 2 + top;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${num(vx)} ${num(vy)} ${num(w)} ${num(h)}" width="${Math.round(w)}" height="${Math.round(h)}" font-family="${th.font}">
<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="${th.muted}" /></marker>
<marker id="arf" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 Z" fill="${th.warn}" /></marker></defs>
<style>.grp{fill:${th.panel};fill-opacity:.45;stroke:${th.muted};stroke-opacity:.55;stroke-dasharray:4 4} .grp-t{fill:${th.muted};font-size:11px;font-weight:700;letter-spacing:1.4px}
.edge{fill:none;stroke:${th.muted};stroke-width:1.6} .edge.fb{stroke:${th.warn};stroke-dasharray:6 4} .edge.ctl{stroke-dasharray:2 3}
.nt{fill:${th.ink};font-size:12.5px;font-weight:600} .nd{fill:${th.muted};font-size:10.5px} .np{fill:${th.accent2};font-size:10.5px} .ev{fill:${th.muted};font-size:9.5px}
.el{fill:${th.muted};font-size:10px} .elf{fill:${th.warn}} .title{fill:${th.ink};font-size:14px;font-weight:700}</style>
<rect x="${num(vx)}" y="${num(vy)}" width="${num(w)}" height="${num(h)}" fill="${th.bg}" />
${ir.title ? `<text class="title" x="${num(vx + 18)}" y="${num(vy + 28)}">${esc(ir.title)}</text>` : ''}
${isFixture(ir.source) ? fixtureMark(th, vx + w - 16, vy + 28) : ''}
${out.join('\n')}
</svg>`;
  return { svg, width: w, height: h };
}
