export interface Theme {
  name: string; bg: string; panel: string; ink: string; muted: string; line: string; accent: string; accent2: string; warn: string; font: string;
}
const font = "'DejaVu Sans','Helvetica Neue',Arial,sans-serif";
export const dark: Theme = { name: 'dark', bg: '#1c1915', panel: '#26221c', ink: '#ece5d6', muted: '#a49b88', line: '#d8cfba', accent: '#d58d57', accent2: '#79b4a8', warn: '#e2b24c', font };
export const light: Theme = { name: 'light', bg: '#fbf9f4', panel: '#ffffff', ink: '#26221c', muted: '#7b7566', line: '#3a342a', accent: '#b8652b', accent2: '#2a7a6f', warn: '#a87a14', font };
export const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
export const num = (n: number) => (Math.round(n * 100) / 100).toString();

/** Test fixtures are marked so canned diagrams can never be mistaken for output extracted from a paper. */
export const isFixture = (src?: { figure_id?: string }) => src?.figure_id === 'fixture';
export const fixtureMark = (th: Theme, x: number, y: number, anchor: 'start' | 'end' = 'end') =>
  `<text x="${num(x)}" y="${num(y)}" text-anchor="${anchor}" font-size="11" font-weight="700" fill="${th.warn}" letter-spacing="0.6">TEST FIXTURE · NOT FROM A PAPER</text>`;
