import dagre from '@dagrejs/dagre';
import type { CircuitIR, CircuitComponent, CircuitNet, Side } from './ir.js';
import { getSymbol, type Dir, type Symbol2D } from './symbols.js';
import { dark, esc, num, isFixture, fixtureMark, type Theme } from './theme.js';

const DV: Record<Dir, [number, number]> = { l: [-1, 0], r: [1, 0], u: [0, -1], d: [0, 1] };
const OPP: Record<Dir, Dir> = { l: 'r', r: 'l', u: 'd', d: 'u' };
const sideToWireDir: Record<Side, Dir> = { left: 'r', right: 'l', up: 'd', down: 'u' }; // wire leaves away from the edge
const STUB = 12, GSTUB = 14;

interface Tf { rot: number; mirror: boolean; flip: boolean }
function tp(p: [number, number], t: Tf): [number, number] {
  let [x, y] = p; if (t.mirror) x = -x; if (t.flip) y = -y;
  const a = (t.rot * Math.PI) / 180, c = Math.round(Math.cos(a) * 1e6) / 1e6, s = Math.round(Math.sin(a) * 1e6) / 1e6;
  return [x * c - y * s, x * s + y * c];
}
const dirOf = (v: [number, number]): Dir => (Math.abs(v[0]) > Math.abs(v[1]) ? (v[0] < 0 ? 'l' : 'r') : v[1] < 0 ? 'u' : 'd');

interface Placed { c: CircuitComponent; sym: Symbol2D; x: number; y: number; t: Tf; pins: Record<string, { x: number; y: number; dir: Dir }> }
interface PinRef { x: number; y: number; dir: Dir; who: string }

export interface SchematicOptions { theme?: Theme; padding?: number; showPinNames?: boolean }
export interface SchematicResult { svg: string; width: number; height: number; report: { layout: 'hinted' | 'auto'; scale: number; nets: Record<string, { pins: number; routed: boolean; global: boolean }>; unconnectedPins: string[] } }

export function renderSchematic(ir: CircuitIR, opts: SchematicOptions = {}): SchematicResult {
  const th = opts.theme ?? dark; const pad = opts.padding ?? 50;
  const netById = new Map<string, CircuitNet>(ir.nets.map((n) => [n.id, n]));
  const syms = new Map(ir.components.map((c) => [c.id, getSymbol(c)]));

  // ---------- placement ----------
  const hinted = ir.components.length > 0 && ir.components.every((c) => c.placement);
  let scale = 1; const pos = new Map<string, [number, number]>();
  if (hinted) {
    const pts = ir.components.map((c) => [c.placement!.x, c.placement!.y] as const);
    if (ir.layout?.unit) scale = ir.layout.unit;
    else {
      let md = Infinity;
      for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) md = Math.min(md, Math.hypot(pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]));
      scale = Number.isFinite(md) && md > 0 ? Math.min(400, Math.max(8, 120 / md)) : 100;
    }
    ir.components.forEach((c) => pos.set(c.id, [c.placement!.x * scale, c.placement!.y * scale]));
  } else {
    const g = new dagre.graphlib.Graph(); g.setGraph({ rankdir: 'LR', nodesep: 70, ranksep: 110, marginx: 0, marginy: 0 }); g.setDefaultEdgeLabel(() => ({}));
    ir.components.forEach((c) => { const b = syms.get(c.id)!.bbox; g.setNode(c.id, { width: Math.max(90, b[2] - b[0] + 40), height: Math.max(80, b[3] - b[1] + 30) }); });
    const byNet = new Map<string, string[]>();
    ir.components.forEach((c) => Object.values(c.pins).forEach((n) => { const nn = netById.get(n); if (nn && !(nn.global || nn.role === 'supply' || nn.role === 'ground')) byNet.set(n, [...(byNet.get(n) ?? []), c.id]); }));
    const seen = new Set<string>();
    byNet.forEach((ids) => { const u = [...new Set(ids)]; for (let i = 0; i < u.length - 1; i++) { const k = `${u[i]}|${u[i + 1]}`; if (!seen.has(k)) { seen.add(k); g.setEdge(u[i], u[i + 1]); } } });
    dagre.layout(g);
    ir.components.forEach((c) => { const n = g.node(c.id); pos.set(c.id, [n.x, n.y]); });
  }

  const placed: Placed[] = ir.components.map((c) => {
    const sym = syms.get(c.id)!; const pl = c.placement;
    const t: Tf = sym.upright ? { rot: 0, mirror: false, flip: false } : { rot: pl?.rot ?? 0, mirror: !!pl?.mirror, flip: !!pl?.flip };
    const [x, y] = pos.get(c.id)!; const pins: Placed['pins'] = {};
    for (const [name, sp] of Object.entries(sym.pins)) {
      const [px, py] = tp([sp.x, sp.y], t); const dv = tp(DV[sp.dir], t);
      pins[name] = { x: x + px, y: y + py, dir: dirOf(dv) };
    }
    return { c, sym, x, y, t, pins };
  });

  // ---------- ports ----------
  const bb = bounds(placed);
  const ports = (ir.ports ?? []).map((p, i) => {
    const side: Side = p.side ?? (p.dir === 'out' ? 'right' : 'left');
    let x: number, y: number;
    if (p.placement) { x = p.placement.x * scale; y = p.placement.y * scale; }
    else {
      const same = (ir.ports ?? []).filter((q, j) => (q.side ?? (q.dir === 'out' ? 'right' : 'left')) === side && j <= i).length;
      x = side === 'left' ? bb.x0 - 90 : side === 'right' ? bb.x1 + 90 : bb.x0 + same * 90;
      y = side === 'up' ? bb.y0 - 70 : side === 'down' ? bb.y1 + 70 : bb.y0 + same * 80;
    }
    return { p, side, x, y, dir: sideToWireDir[side] };
  });

  // ---------- collect pins per net ----------
  const byNet = new Map<string, PinRef[]>(); const unconnected: string[] = [];
  placed.forEach((pc) => Object.entries(pc.c.pins).forEach(([pin, net]) => {
    const pp = pc.pins[pin];
    if (pin === 'b' && (pc.c.type === 'nmos' || pc.c.type === 'pmos')) { const bn = netById.get(net); if (net === pc.c.pins.s || bn?.global || bn?.role === 'supply' || bn?.role === 'ground') return; } // body tied to source or to a rail: implicit (simplified symbol)
    if (!pp) { unconnected.push(`${pc.c.id}.${pin}`); return; }
    byNet.set(net, [...(byNet.get(net) ?? []), { x: pp.x, y: pp.y, dir: pp.dir, who: `${pc.c.id}.${pin}` }]);
  }));
  ports.forEach((q) => byNet.set(q.p.net, [...(byNet.get(q.p.net) ?? []), { x: q.x, y: q.y, dir: q.dir, who: `port:${q.p.id}` }]));

  // ---------- routing ----------
  const wires: string[] = [], dots: string[] = [], labels: string[] = [], globals: string[] = [];
  const ext = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  const grow = (x: number, y: number) => { ext.x0 = Math.min(ext.x0, x); ext.y0 = Math.min(ext.y0, y); ext.x1 = Math.max(ext.x1, x); ext.y1 = Math.max(ext.y1, y); };
  const segs: { o: 'v' | 'h'; c: number; lo: number; hi: number }[] = [];
  const rects = placed.map((pc) => { const [a, b, d2, e] = pc.sym.bbox; const cs = [[a, b], [d2, b], [a, e], [d2, e]].map(([px, py]) => tp([px, py], pc.t)); return { x0: pc.x + Math.min(...cs.map((q) => q[0])) - 2, x1: pc.x + Math.max(...cs.map((q) => q[0])) + 2, y0: pc.y + Math.min(...cs.map((q) => q[1])) - 2, y1: pc.y + Math.max(...cs.map((q) => q[1])) + 2 }; });
  for (const [gid, gpins] of byNet) {
    const gn = netById.get(gid); if (!(gn && (gn.global || gn.role === 'supply' || gn.role === 'ground'))) continue;
    for (const p of gpins) { const [dx, dy] = DV[p.dir]; const cx = p.x + dx * (GSTUB + 14), cy = p.y + dy * (GSTUB + 14); const hx = dx === 0 ? 16 : 18, hy = dy === 0 ? 16 : 18; rects.push({ x0: cx - hx, x1: cx + hx, y0: cy - hy, y1: cy + hy }); }
  }
  const rb = rects.reduce((m, r) => ({ x0: Math.min(m.x0, r.x0), y0: Math.min(m.y0, r.y0), x1: Math.max(m.x1, r.x1), y1: Math.max(m.y1, r.y1) }), { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity });
  const report: SchematicResult['report'] = { layout: hinted ? 'hinted' : 'auto', scale, nets: {}, unconnectedPins: unconnected };
  const line = (x1: number, y1: number, x2: number, y2: number) => { if (x1 === x2 && y1 === y2) return; wires.push(`M${num(x1)},${num(y1)} L${num(x2)},${num(y2)}`); grow(x1, y1); grow(x2, y2); };

  const order = [...byNet.entries()].sort((a, b) => spanOf(a[1]) - spanOf(b[1]));
  for (const [netId, pins] of order) {
    const net = netById.get(netId) ?? { id: netId } as CircuitNet;
    const isGround = net.role === 'ground', isSupply = net.role === 'supply', isGlobal = !!net.global || isGround || isSupply;
    report.nets[netId] = { pins: pins.length, routed: true, global: isGlobal };
    const text = esc(net.label ?? net.id);
    if (isGlobal) {
      for (const p of pins) {
        const [dx, dy] = DV[p.dir]; const ex = p.x + dx * GSTUB, ey = p.y + dy * GSTUB; line(p.x, p.y, ex, ey);
        const ang = (Math.atan2(dy, dx) * 180) / Math.PI - 90;
        if (isGround) globals.push(`<g transform="translate(${num(ex)},${num(ey)}) rotate(${num(ang)})"><path d="M0,0 L0,5 M-9,5 L9,5 M-6,9 L6,9 M-3,13 L3,13" /></g>`);
        else globals.push(`<g transform="translate(${num(ex)},${num(ey)}) rotate(${num(ang)})"><path d="M0,0 L0,5 M-9,5 L9,5" /></g>`);
        const lx = ex + dx * (isGround ? 20 : 14), ly = ey + dy * (isGround ? 20 : 14);
        const anchor = dx > 0 ? 'start' : dx < 0 ? 'end' : 'middle';
        labels.push(`<text x="${num(lx + (dx > 0 ? 2 : dx < 0 ? -2 : 0))}" y="${num(ly + (dy > 0 ? 8 : dy < 0 ? -2 : 4))}" text-anchor="${anchor}" class="net">${text}</text>`);
        grow(lx - 20, ly - 10); grow(lx + 20, ly + 10);
      }
      continue;
    }
    if (pins.length < 2) {
      for (const p of pins) { const [dx, dy] = DV[p.dir]; line(p.x, p.y, p.x + dx * STUB, p.y + dy * STUB); dots.push(`<circle cx="${num(p.x + dx * STUB)}" cy="${num(p.y + dy * STUB)}" r="3" class="open" />`); }
      report.nets[netId].routed = false; continue;
    }
    const ends = pins.map((p) => { const [dx, dy] = DV[p.dir]; return { sx: p.x, sy: p.y, ex: p.x + dx * STUB, ey: p.y + dy * STUB, dir: p.dir }; });
    const sorted = (a: number[]) => [...new Set(a)].sort((m, n) => m - n);
    const xs = ends.map((e) => e.ex), ys = ends.map((e) => e.ey);
    const med = (a: number[]) => { const q = [...a].sort((m, n) => m - n); return q[Math.floor(q.length / 2)]; };
    type Cand = { o: 'v' | 'h'; c: number; cost: number };
    const cands: Cand[] = [];
    const addCands = (o: 'v' | 'h') => {
      const own = o === 'v' ? xs : ys; const oth = o === 'v' ? ys : xs;
      const sv = sorted(own); const mids = sv.slice(1).map((v, i) => (v + sv[i]) / 2);
      const outside = o === 'v' ? [rb.x0 - 40, rb.x1 + 40] : [rb.y0 - 40, rb.y1 + 40];
      const base = [...sv, ...mids, med(own), ...outside].map((v) => Math.round(v / 5) * 5);
      const lo = Math.min(...oth), hi = Math.max(...oth);
      for (const b0 of new Set(base)) for (const off of [0, 8, -8, 16, -16, 26, -26, 36, -36, 48, -48]) {
        const c = b0 + off; let cost = Math.abs(off) * 0.5 + Math.abs(c - med(own)) * 0.02;
        const runs: { o: 'v' | 'h'; c: number; lo: number; hi: number }[] = [];
        ends.forEach((e) => { const a = o === 'v' ? e.ex : e.ey, p = o === 'v' ? e.ey : e.ex; runs.push({ o: o === 'v' ? 'h' : 'v', c: p, lo: Math.min(a, c), hi: Math.max(a, c) }); });
        runs.push({ o, c, lo, hi });
        for (const sg of runs) {
          cost += sg.hi - sg.lo;
          for (const r of rects) { const inC = o === 'v' ? (sg.o === 'v' ? sg.c > r.x0 && sg.c < r.x1 : sg.c > r.y0 && sg.c < r.y1) : (sg.o === 'h' ? sg.c > r.y0 && sg.c < r.y1 : sg.c > r.x0 && sg.c < r.x1); if (!inC) continue;
            const a0 = sg.o === 'h' ? r.x0 : r.y0, a1 = sg.o === 'h' ? r.x1 : r.y1; if (sg.lo < a1 && sg.hi > a0) cost += 400; }
          for (const q of segs) {
            if (q.o === sg.o) { const dc = Math.abs(q.c - sg.c), ov = Math.min(q.hi, sg.hi) - Math.max(q.lo, sg.lo); if (dc < 6 && ov > 2) cost += 5000; else if (dc < 24 && ov > 12) cost += 1500; }
            else if (q.c > sg.lo && q.c < sg.hi && sg.c > q.lo && sg.c < q.hi) cost += 120;
          }
        }
        cands.push({ o, c, cost });
      }
    };
    addCands('v'); addCands('h');
    if (process.env.DEBUG_ROUTE) console.error(netId, 'ends', JSON.stringify(ends.map((e) => [Math.round(e.ex), Math.round(e.ey)])), 'far:', [...cands].filter((c) => c.o === 'h' && Math.abs(c.c - 125) >= 24).sort((a, b) => a.cost - b.cost).slice(0, 4).map((c) => `${c.c}:${Math.round(c.cost)}`).join(' '), ' | best:', [...cands].sort((a, b) => a.cost - b.cost).slice(0, 3).map((c) => `${c.o}${c.c}:${Math.round(c.cost)}`).join('  '));
    const best = cands.reduce((a, b) => (b.cost < a.cost ? b : a));
    const vertical = best.o === 'v', coord = best.c;
    ends.forEach((e) => { // a run that doubles back through the pin's own lead needs no stub
      const [dx, dy] = DV[e.dir]; const rx = vertical ? Math.sign(coord - e.ex) : 0, ry = vertical ? 0 : Math.sign(coord - e.ey);
      if (rx * dx + ry * dy < 0) { e.ex = e.sx; e.ey = e.sy; } else line(e.sx, e.sy, e.ex, e.ey);
    });
    const lo = vertical ? Math.min(...ys) : Math.min(...xs), hi = vertical ? Math.max(...ys) : Math.max(...xs);
    const reg = (o: 'v' | 'h', c: number, a: number, b: number) => { if (a !== b) segs.push({ o, c, lo: Math.min(a, b), hi: Math.max(a, b) }); };
    ends.forEach((e) => { reg(Math.abs(e.sx - e.ex) > 0 ? 'h' : 'v', Math.abs(e.sx - e.ex) > 0 ? e.sy : e.sx, Math.abs(e.sx - e.ex) > 0 ? e.sx : e.sy, Math.abs(e.sx - e.ex) > 0 ? e.ex : e.ey); });
    if (vertical) {
      line(coord, lo, coord, hi); reg('v', coord, lo, hi);
      ends.forEach((e) => { line(e.ex, e.ey, coord, e.ey); reg('h', e.ey, e.ex, coord); });
    } else {
      line(lo, coord, hi, coord); reg('h', coord, lo, hi);
      ends.forEach((e) => { line(e.ex, e.ey, e.ex, coord); reg('v', e.ex, e.ey, coord); });
    }
    const jc = new Map<number, number>();
    ends.forEach((e) => { const k = vertical ? e.ey : e.ex; jc.set(k, (jc.get(k) ?? 0) + 1); });
    jc.forEach((cnt, v) => { if (cnt >= 2 || (v > lo && v < hi)) dots.push(vertical ? `<circle cx="${coord}" cy="${v}" r="2.6" class="dot" />` : `<circle cx="${v}" cy="${coord}" r="2.6" class="dot" />`); });
    if (net.label && !ports.some((q) => q.p.net === netId)) {
      const lx = vertical ? coord + 5 : lo + 4, ly = vertical ? lo - 4 : coord - 5;
      labels.push(`<text x="${num(lx)}" y="${num(ly)}" class="net">${text}</text>`); grow(lx + 30, ly - 10);
    }
  }

  // ---------- draw ----------
  const body: string[] = [];
  for (const pc of placed) {
    const { sym, x, y, t, c } = pc;
    const [a, b, d2, e] = sym.bbox;
    [[a, b], [d2, b], [a, e], [d2, e]].forEach(([px, py]) => { const [rx, ry] = tp([px, py], t); grow(x + rx, y + ry); });
    body.push(`<g transform="translate(${num(x)},${num(y)}) rotate(${t.rot}) scale(${t.mirror ? -1 : 1},${t.flip ? -1 : 1})" class="sym" data-id="${esc(c.id)}">${sym.shapes}</g>`);
    for (const tx of sym.texts) {
      const [rx, ry] = tp([tx.x, tx.y], t);
      body.push(`<text x="${num(x + rx)}" y="${num(y + ry)}" text-anchor="${tx.anchor ?? 'middle'}" class="${tx.muted ? 'pin' : 'lbl'}" font-size="${tx.size ?? 11}">${esc(tx.t)}</text>`);
    }
    if (!sym.upright) {
      const corners = [[a, b], [d2, b], [a, e], [d2, e]].map(([px, py]) => tp([px, py], t));
      const maxX = Math.max(...corners.map((q) => q[0])), minX = Math.min(...corners.map((q) => q[0]));
      const onLeft = t.mirror && t.rot === 0 || t.rot === 180 && !t.mirror;
      const lx = onLeft ? x + minX - 14 : x + maxX + 8, anc = onLeft ? 'end' : 'start';
      body.push(`<text x="${num(lx)}" y="${num(y - 2)}" text-anchor="${anc}" class="lbl" font-weight="600">${esc(c.label ?? c.id)}</text>`);
      if (c.value) body.push(`<text x="${num(lx)}" y="${num(y + 12)}" text-anchor="${anc}" class="pin">${esc(c.value)}</text>`);
      grow(lx + (anc === 'start' ? 60 : -60), y + 14);
    }
  }
  for (const q of ports) {
    const [dx, dy] = DV[OPP[q.dir]]; // direction toward the label
    body.push(`<circle cx="${num(q.x)}" cy="${num(q.y)}" r="3.4" class="port" />`);
    const lx = q.x + dx * 9, ly = q.y + dy * 9;
    body.push(`<text x="${num(lx)}" y="${num(ly + (dy > 0 ? 10 : dy < 0 ? -2 : 4))}" text-anchor="${dx > 0 ? 'start' : dx < 0 ? 'end' : 'middle'}" class="port-lbl">${esc(q.p.label ?? q.p.id)}</text>`);
    grow(q.x - 40, q.y - 12); grow(q.x + 40, q.y + 12);
  }
  if (!isFinite(ext.x0)) { ext.x0 = 0; ext.y0 = 0; ext.x1 = 200; ext.y1 = 120; }
  const x0 = ext.x0 - pad, y0 = ext.y0 - pad - (ir.title ? 18 : 0), w = ext.x1 - ext.x0 + pad * 2, h = ext.y1 - ext.y0 + pad * 2 + (ir.title ? 18 : 0);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${num(x0)} ${num(y0)} ${num(w)} ${num(h)}" width="${Math.round(w)}" height="${Math.round(h)}" font-family="${th.font}">
<style>
.bg{fill:${th.bg}} .sym{color:${th.line};fill:none;stroke:${th.line};stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}
.wire{fill:none;stroke:${th.accent2};stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.glob{fill:none;stroke:${th.muted};stroke-width:1.6;stroke-linecap:round}
.dot{fill:${th.accent2}} .open{fill:none;stroke:${th.warn};stroke-width:1.4}
.lbl{fill:${th.ink};font-size:11px} .pin{fill:${th.muted};font-size:9px} .net{fill:${th.accent};font-size:10px;font-weight:600}
.port{fill:${th.accent}} .port-lbl{fill:${th.ink};font-size:11px;font-weight:600} .title{fill:${th.ink};font-size:13px;font-weight:600}
</style>
<rect class="bg" x="${num(x0)}" y="${num(y0)}" width="${num(w)}" height="${num(h)}" />
${isFixture(ir.source) ? fixtureMark(th, x0 + w - 16, y0 + 24) : ''}
${ir.title ? `<text class="title" x="${num(x0 + 16)}" y="${num(y0 + 24)}">${esc(ir.title)}</text>` : ''}
<path class="wire" d="${wires.join(' ')}" />
<g class="glob">${globals.join('')}</g>
${dots.join('')}
${body.join('\n')}
${labels.join('\n')}
</svg>`;
  return { svg, width: w, height: h, report };
}

function bounds(placed: Placed[]) {
  const b = { x0: Infinity, y0: Infinity, x1: -Infinity, y1: -Infinity };
  placed.forEach((p) => { b.x0 = Math.min(b.x0, p.x - 40); b.y0 = Math.min(b.y0, p.y - 40); b.x1 = Math.max(b.x1, p.x + 40); b.y1 = Math.max(b.y1, p.y + 40); });
  return isFinite(b.x0) ? b : { x0: 0, y0: 0, x1: 0, y1: 0 };
}

function spanOf(p: { x: number; y: number }[]) { const xs = p.map((q) => q.x), ys = p.map((q) => q.y); return Math.max(...xs) - Math.min(...xs) + Math.max(...ys) - Math.min(...ys); }
