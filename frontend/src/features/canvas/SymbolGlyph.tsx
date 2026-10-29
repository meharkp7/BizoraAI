import styles from "./SymbolGlyph.module.css";

/** 2D glyph per pack-declared symbol. The schematic vocabulary and the
 *  process/data vocabulary carry custom art; every other symbol falls
 *  back to the generic ring so new backend symbols never break a view. */
export function SymbolGlyph({ symbol, size = 14 }: { symbol: string; size?: number }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 14 14",
    "aria-hidden": true,
  } as const;
  switch (symbol) {
    case "transistor":
      // NMOS: gate bar, channel bar, three terminals, bulk arrow.
      return (
        <svg {...common}>
          <path d="M4.5 3 V11" className={styles.glyphShape} />
          <path d="M2 7 H4.5" className={styles.glyphShape} />
          <path d="M7 2.5 V11.5" className={styles.glyphShape} />
          <path d="M7 4 H12 M7 10 H12" className={styles.glyphShape} />
          <path d="M9.5 8.5 L12 10 L9.5 11.5" className={styles.glyphShape} />
        </svg>
      );
    case "bitcell":
      // Storage cell: outline with a cross for the coupled pair.
      return (
        <svg {...common}>
          <rect x="2.5" y="2.5" width="9" height="9" className={styles.glyphShape} />
          <path d="M2.5 2.5 L11.5 11.5 M11.5 2.5 L2.5 11.5" className={styles.glyphShape} />
        </svg>
      );
    case "gate":
      // Logic block: house outline, family-agnostic.
      return (
        <svg {...common}>
          <path d="M3.5 11.5 V5.5 L7 2.5 L10.5 5.5 V11.5 Z" className={styles.glyphShape} />
        </svg>
      );
    case "senseamp":
      // Amplifier triangle.
      return (
        <svg {...common}>
          <path d="M3.5 3 L10.5 7 L3.5 11 Z" className={styles.glyphShape} />
        </svg>
      );
    case "meter":
      // Instrument: dial with a needle.
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
          <path d="M7 7 L9.8 4.2" className={styles.glyphShape} />
        </svg>
      );
    case "passive":
      // Two-terminal block with leads: honest for R, C, and L alike.
      return (
        <svg {...common}>
          <rect x="4.5" y="5" width="5" height="4" className={styles.glyphShape} />
          <path d="M2.5 7 H4.5 M9.5 7 H11.5" className={styles.glyphShape} />
        </svg>
      );
    case "diode":
      // Triangle into a bar, with leads.
      return (
        <svg {...common}>
          <path d="M7 2 V3.5 M4.5 3.5 H9.5 L7 8 Z M4.5 9.5 H9.5 M7 9.5 V12" className={styles.glyphShape} />
        </svg>
      );
    case "chip":
      // Dual-inline package: body with pin stubs.
      return (
        <svg {...common}>
          <rect x="4.5" y="2.5" width="5" height="9" className={styles.glyphShape} />
          <path d="M2.5 4.5 H4.5 M2.5 7 H4.5 M2.5 9.5 H4.5 M9.5 4.5 H11.5 M9.5 7 H11.5 M9.5 9.5 H11.5" className={styles.glyphShape} />
        </svg>
      );
    case "adc":
      // Conversion block: box with a rising arrow.
      return (
        <svg {...common}>
          <rect x="3" y="3" width="8" height="8" className={styles.glyphShape} />
          <path d="M4.5 9.5 L9.5 4.5 M7 4.5 H9.5 V7" className={styles.glyphShape} />
        </svg>
      );
    case "source":
      // Supply: circle with a plus.
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
          <path d="M7 4.5 V9.5 M4.5 7 H9.5" className={styles.glyphShape} />
        </svg>
      );
    case "bias":
      // Tunable control: circle with a diagonal arrow.
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
          <path d="M4.5 9.5 L9.5 4.5 M7 4.5 H9.5 V7" className={styles.glyphShape} />
        </svg>
      );
    case "dataset":
      // Stored data: stacked discs.
      return (
        <svg {...common}>
          <ellipse cx="7" cy="4.2" rx="4" ry="1.8" className={styles.glyphShape} />
          <path d="M3 4.2 V10 c0 1 1.8 1.8 4 1.8 s4 -0.8 4 -1.8 V4.2" className={styles.glyphShape} />
          <path d="M3 7.2 c0 1 1.8 1.8 4 1.8 s4 -0.8 4 -1.8" className={styles.glyphShape} />
        </svg>
      );
    case "preprocessing":
      // Filter funnel: raw in, refined out.
      return (
        <svg {...common}>
          <path d="M3 2.5 H11 L8 6.5 V11 H6 V6.5 Z" className={styles.glyphShape} />
        </svg>
      );
    case "operation":
      // Transform: block with a through-arrow.
      return (
        <svg {...common}>
          <rect x="2.5" y="2.5" width="9" height="9" className={styles.glyphShape} />
          <path d="M5 7 H9.5 M7.8 5.2 L9.8 7 L7.8 8.8" className={styles.glyphShape} />
        </svg>
      );
    case "loss":
      // Objective: target rings.
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
          <circle cx="7" cy="7" r="1.6" className={styles.glyphShape} />
        </svg>
      );
    case "optimizer":
      // Descent: steps with a down arrow.
      return (
        <svg {...common}>
          <path d="M2.5 3 H6 V6.5 H9.5 V11.5" className={styles.glyphShape} />
          <path d="M7.5 9.5 L9.5 11.5 L11.5 9.5" className={styles.glyphShape} />
        </svg>
      );
    case "evaluation":
    case "evaluator":
      // Gauge: dial arc with a needle.
      return (
        <svg {...common}>
          <path d="M2.5 10 A4.5 4.5 0 0 1 11.5 10" className={styles.glyphShape} />
          <path d="M7 10 L9.2 6.4" className={styles.glyphShape} />
        </svg>
      );
    case "tensor":
      // Stacked slabs.
      return (
        <svg {...common}>
          <rect x="3" y="2.5" width="8" height="2.4" className={styles.glyphShape} />
          <rect x="4" y="5.8" width="8" height="2.4" className={styles.glyphShape} />
          <rect x="2" y="9.1" width="8" height="2.4" className={styles.glyphShape} />
        </svg>
      );
    case "format":
      // Document with a folded corner.
      return (
        <svg {...common}>
          <path d="M4 2.5 H9 L11 4.5 V11.5 H4 Z" className={styles.glyphShape} />
          <path d="M9 2.5 V4.5 H11" className={styles.glyphShape} />
        </svg>
      );
    case "engine":
      // Runner: hex nut.
      return (
        <svg {...common}>
          <path d="M7 2.5 L11 5 V9 L7 11.5 L3 9 V5 Z" className={styles.glyphShape} />
          <circle cx="7" cy="7" r="1.6" className={styles.glyphShape} />
        </svg>
      );
    case "channel":
      // Signal path: wave with a direction arrow.
      return (
        <svg {...common}>
          <path d="M2 7 Q3.5 4.5 5 7 T8 7 T11 7" className={styles.glyphShape} />
          <path d="M9.5 5.2 L11.5 7 L9.5 8.8" className={styles.glyphShape} />
        </svg>
      );
    case "cloud":
      // Remote service: cloud outline.
      return (
        <svg {...common}>
          <path
            d="M4 11 H9.5 a2.3 2.3 0 0 0 0.4 -4.6 A3.4 3.4 0 0 0 3.4 7.2 A2.1 2.1 0 0 0 4 11 Z"
            className={styles.glyphShape}
          />
        </svg>
      );
    case "generic":
    default:
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
        </svg>
      );
  }
}
