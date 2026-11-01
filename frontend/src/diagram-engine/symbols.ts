import type { CircuitComponent, Side } from './ir.js';

export type Dir = 'l' | 'r' | 'u' | 'd';
export interface SymPin { x: number; y: number; dir: Dir }
export interface SymText { x: number; y: number; t: string; anchor?: 'start' | 'middle' | 'end'; size?: number; muted?: boolean }
export interface Symbol2D { pins: Record<string, SymPin>; shapes: string; texts: SymText[]; bbox: [number, number, number, number]; upright?: boolean }

const P = (x: number, y: number, dir: Dir): SymPin => ({ x, y, dir });
const sideDir: Record<Side, Dir> = { left: 'l', right: 'r', up: 'u', down: 'd' };

/** Local coordinates: origin at the symbol centre, y down. All shapes are unfilled strokes (styled by the parent <g>). */
export function getSymbol(c: CircuitComponent): Symbol2D {
  switch (c.type) {
    case 'nmos':
    case 'pmos': {
      const p = c.type === 'pmos';
      const gate = p
        ? 'M-30,0 L-20,0 M-12,-14 L-12,14'
        : 'M-30,0 L-12,0 M-12,-14 L-12,14';
      const bubble = p ? '<circle cx="-16" cy="0" r="4" />' : '';
      const arrow = p
        ? '<path d="M4,0 L-2,-3.5 L-2,3.5 Z" fill="currentColor" />'
        : '<path d="M-4,0 L2,-3.5 L2,3.5 Z" fill="currentColor" />';
      return {
        pins: { g: P(-30, 0, 'l'), d: P(12, -30, 'u'), s: P(12, 30, 'd'), b: P(12, 0, 'r') },
        shapes: `<path d="${gate} M-6,-16 L-6,-8 M-6,-4 L-6,4 M-6,8 L-6,16 M-6,-12 L12,-12 L12,-30 M-6,12 L12,12 L12,30 M-6,0 L12,0" />${bubble}${arrow}`,
        texts: [], bbox: [-30, -30, 14, 30],
      };
    }
    case 'resistor':
      return { pins: { a: P(0, -30, 'u'), b: P(0, 30, 'd') }, texts: [], bbox: [-8, -30, 8, 30],
        shapes: '<path d="M0,-30 L0,-18 L6,-15 L-6,-9 L6,-3 L-6,3 L6,9 L-6,15 L0,18 L0,30" />' };
    case 'capacitor':
      return { pins: { a: P(0, -30, 'u'), b: P(0, 30, 'd') }, texts: [], bbox: [-12, -30, 12, 30],
        shapes: '<path d="M0,-30 L0,-4 M0,4 L0,30 M-12,-4 L12,-4 M-12,4 L12,4" />' };
    case 'inductor':
      return { pins: { a: P(0, -30, 'u'), b: P(0, 30, 'd') }, texts: [], bbox: [-6, -30, 12, 30],
        shapes: '<path d="M0,-30 L0,-20 a5,5 0 0 1 0,10 a5,5 0 0 1 0,10 a5,5 0 0 1 0,10 a5,5 0 0 1 0,10 L0,30" />' };
    case 'diode':
      return { pins: { a: P(0, -30, 'u'), k: P(0, 30, 'd') }, texts: [], bbox: [-10, -30, 10, 30],
        shapes: '<path d="M0,-30 L0,-10 M0,8 L0,30 M-10,8 L10,8" /><path d="M-10,-10 L10,-10 L0,8 Z" />' };
    case 'vsource':
      return { pins: { p: P(0, -30, 'u'), n: P(0, 30, 'd') }, texts: [], bbox: [-14, -30, 14, 30],
        shapes: '<path d="M0,-30 L0,-14 M0,14 L0,30 M-4,-6 L4,-6 M0,-10 L0,-2 M-4,7 L4,7" /><circle cx="0" cy="0" r="14" />' };
    case 'isource':
      return { pins: { p: P(0, -30, 'u'), n: P(0, 30, 'd') }, texts: [], bbox: [-14, -30, 14, 30],
        shapes: '<path d="M0,-30 L0,-14 M0,14 L0,30 M0,8 L0,-6" /><path d="M0,-10 L-4,-3 L4,-3 Z" fill="currentColor" /><circle cx="0" cy="0" r="14" />' };
    case 'ground':
      return { pins: { g: P(0, -12, 'u') }, texts: [], bbox: [-12, -12, 12, 10],
        shapes: '<path d="M0,-12 L0,0 M-12,0 L12,0 M-8,5 L8,5 M-4,10 L4,10" />' };
    case 'inverter':
      return { pins: { in: P(-30, 0, 'l'), out: P(30, 0, 'r') }, texts: [], bbox: [-30, -14, 30, 14],
        shapes: '<path d="M-30,0 L-14,0 M20,0 L30,0" /><path d="M-14,-14 L-14,14 L12,0 Z" /><circle cx="16" cy="0" r="4" />' };
    case 'buffer':
      return { pins: { in: P(-30, 0, 'l'), out: P(30, 0, 'r') }, texts: [], bbox: [-30, -14, 30, 14],
        shapes: '<path d="M-30,0 L-14,0 M12,0 L30,0" /><path d="M-14,-14 L-14,14 L12,0 Z" />' };
    case 'amp':
    case 'comparator': {
      const cmp = c.type === 'comparator' ? '<path d="M6,-4 L6,4 L10,4 L10,-4 L14,-4" />' : '';
      return { pins: { inp: P(-30, -10, 'l'), inn: P(-30, 10, 'l'), out: P(30, 0, 'r') }, texts: [], bbox: [-30, -24, 30, 24],
        shapes: `<path d="M-30,-10 L-18,-10 M-30,10 L-18,10 M22,0 L30,0 M-15,-10 L-9,-10 M-12,-13 L-12,-7 M-15,10 L-9,10" /><path d="M-18,-24 L-18,24 L22,0 Z" />${cmp}` };
    }
    default:
      return blockSymbol(c);
  }
}

function blockSymbol(c: CircuitComponent): Symbol2D {
  const names = Object.keys(c.pins);
  const sides: Record<Side, string[]> = { left: [], right: [], up: [], down: [] };
  names.forEach((n, i) => {
    const s = c.pin_sides?.[n] ?? (i % 2 === 0 ? 'left' : 'right');
    sides[s].push(n);
  });
  const vert = Math.max(sides.left.length, sides.right.length, 2);
  const horiz = Math.max(sides.up.length, sides.down.length, 1);
  const w = Math.max(90, horiz * 34 + 20), h = Math.max(60, vert * 24 + 16);
  const pins: Record<string, SymPin> = {}; const texts: SymText[] = []; let leads = '';
  (['left', 'right'] as const).forEach((s) => sides[s].forEach((n, i) => {
    const y = -h / 2 + ((i + 1) * h) / (sides[s].length + 1);
    const ex = s === 'left' ? -w / 2 : w / 2, px = s === 'left' ? ex - 18 : ex + 18;
    pins[n] = P(px, y, sideDir[s]); leads += `M${px},${y} L${ex},${y} `;
    texts.push({ x: ex + (s === 'left' ? 5 : -5), y: y + 3, t: n, anchor: s === 'left' ? 'start' : 'end', size: 9, muted: true });
  }));
  (['up', 'down'] as const).forEach((s) => sides[s].forEach((n, i) => {
    const x = -w / 2 + ((i + 1) * w) / (sides[s].length + 1);
    const ey = s === 'up' ? -h / 2 : h / 2, py = s === 'up' ? ey - 18 : ey + 18;
    pins[n] = P(x, py, sideDir[s]); leads += `M${x},${py} L${x},${ey} `;
    texts.push({ x, y: ey + (s === 'up' ? 12 : -5), t: n, anchor: 'middle', size: 9, muted: true });
  }));
  texts.push({ x: 0, y: 4, t: c.label ?? c.id, anchor: 'middle', size: 11 });
  return { pins, texts, upright: true, bbox: [-w / 2 - 18, -h / 2 - 18, w / 2 + 18, h / 2 + 18],
    shapes: `<rect x="${-w / 2}" y="${-h / 2}" width="${w}" height="${h}" rx="4" /><path d="${leads}" />` };
}
