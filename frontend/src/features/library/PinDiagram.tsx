import type { ComponentPin } from "../../lib/types.ts";
import styles from "./PinDiagram.module.css";

const ROW_HEIGHT = 22;
const BODY_WIDTH = 120;
const STUB = 26;

/** Dual-side pin diagram for parts that declare an ordered pinout. */
export function PinDiagram({ pins }: { pins: ComponentPin[] }) {
  if (pins.length === 0 || pins.length > 24) return null;
  const left = pins.filter((_, index) => index % 2 === 0);
  const right = pins.filter((_, index) => index % 2 === 1);
  const rows = Math.max(left.length, right.length);
  const height = rows * ROW_HEIGHT + 16;
  const width = BODY_WIDTH + STUB * 2 + 220;

  const row = (pin: ComponentPin, side: "left" | "right", index: number) => {
    const y = 8 + index * ROW_HEIGHT + ROW_HEIGHT / 2;
    const bodyX = side === "left" ? 110 + STUB : 110 + STUB + BODY_WIDTH;
    const labelX = side === "left" ? 106 : 114 + STUB * 2 + BODY_WIDTH;
    const anchor = side === "left" ? "end" : "start";
    const stubX = side === "left" ? bodyX - STUB : bodyX;
    return (
      <g key={`${side}-${pin.designator}-${pin.name}`}>
        <line x1={stubX} y1={y} x2={stubX + (side === "left" ? STUB : STUB)} y2={y} className={styles.stub} />
        <circle cx={side === "left" ? bodyX : bodyX} cy={y} r={2.5} className={styles.pad} />
        <text x={labelX} y={y + 4} textAnchor={anchor} className={styles.label}>
          {pin.designator} · {pin.name}
        </text>
      </g>
    );
  };

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={styles.diagram}
      role="img"
      aria-label={`Pin diagram: ${pins.map((pin) => `${pin.designator} ${pin.name}`).join(", ")}`}
    >
      <rect
        x={110 + STUB}
        y={4}
        width={BODY_WIDTH}
        height={height - 8}
        rx={4}
        className={styles.body}
      />
      {left.map((pin, index) => row(pin, "left", index))}
      {right.map((pin, index) => row(pin, "right", index))}
    </svg>
  );
}
