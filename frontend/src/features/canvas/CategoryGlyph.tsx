import type { ArchetypeGeometry } from "./graph3d.ts";
import { archetypeFor } from "./graph3d.ts";
import styles from "./CategoryGlyph.module.css";

/** Flat glyph per 3D archetype so library cards match the scene shapes. */
export function CategoryGlyph({
  category,
  size = 14,
}: {
  category: string;
  size?: number;
}) {
  return <GeometryGlyph geometry={archetypeFor(category)} size={size} />;
}

export function GeometryGlyph({
  geometry,
  size = 14,
}: {
  geometry: ArchetypeGeometry;
  size?: number;
}) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 14 14",
    "aria-hidden": true,
  } as const;
  switch (geometry) {
    case "box":
      return (
        <svg {...common}>
          <rect x="2.5" y="2.5" width="9" height="9" className={styles.glyphShape} />
        </svg>
      );
    case "slab":
      return (
        <svg {...common}>
          <rect x="1.5" y="5" width="11" height="4" className={styles.glyphShape} />
        </svg>
      );
    case "cylinder":
      return (
        <svg {...common}>
          <ellipse cx="7" cy="4" rx="4.5" ry="2" className={styles.glyphShape} />
          <path d="M2.5 4 v6 c0 1.1 2 2 4.5 2 s4.5 -0.9 4.5 -2 v-6" className={styles.glyphShape} />
        </svg>
      );
    case "cone":
      return (
        <svg {...common}>
          <path d="M7 2 L11.5 12 L2.5 12 Z" className={styles.glyphShape} />
        </svg>
      );
    case "torus":
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
          <circle cx="7" cy="7" r="1.8" className={styles.glyphShape} />
        </svg>
      );
    case "octahedron":
      return (
        <svg {...common}>
          <path d="M7 1.5 L12 7 L7 12.5 L2 7 Z" className={styles.glyphShape} />
        </svg>
      );
    case "tetrahedron":
      return (
        <svg {...common}>
          <path d="M7 2 L12 12 L2 12 Z" className={styles.glyphShape} />
          <path d="M7 2 L7 12" className={styles.glyphShape} />
        </svg>
      );
    case "icosahedron":
      return (
        <svg {...common}>
          <path d="M7 1.5 L11.5 4.5 L11.5 9.5 L7 12.5 L2.5 9.5 L2.5 4.5 Z" className={styles.glyphShape} />
        </svg>
      );
    case "dodecahedron":
      return (
        <svg {...common}>
          <path d="M7 1.5 L10.5 4 L9.5 8.5 L4.5 8.5 L3.5 4 Z" className={styles.glyphShape} />
          <path d="M4.5 8.5 L7 12.5 L9.5 8.5" className={styles.glyphShape} />
        </svg>
      );
    case "sphere":
    default:
      return (
        <svg {...common}>
          <circle cx="7" cy="7" r="4.5" className={styles.glyphShape} />
        </svg>
      );
  }
}
