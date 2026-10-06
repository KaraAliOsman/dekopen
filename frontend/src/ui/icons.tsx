/** Iconos DEKOPEN — monolínea 1,5 px, extremos cuadrados, uniones a inglete
 * (la misma mano que dibuja el perfil). 16×16 por defecto; los iconos son
 * apoyo de la etiqueta, nunca la sustituyen.
 *
 * OpeningGlyph implementa la gramática §3.6: la línea parte de las
 * esquinas del lado de bisagra y el vértice apunta a la manilla;
 * continuo = hacia el observador, discontinuo = alejándose; abatimiento
 * desde abajo; oscilobatiente = ambos símbolos; corredera = flecha
 * paralela al carril; fijo = silencio. */
import { type SVGProps } from "react";

import {
  glyphPaths,
  leafPrimitives,
  leafSpecsForBay,
  type GlyphPrimitive,
} from "../features/canvas/openingSymbols";

export type IconName =
  | "check"
  | "cross"
  | "warn"
  | "person"
  | "draft"
  | "quote"
  | "station"
  | "plus"
  | "minus"
  | "search"
  | "filter"
  | "copy"
  | "download"
  | "print"
  | "edit"
  | "trash"
  | "arrow-right"
  | "arrow-left"
  | "arrow-down"
  | "arrow-up"
  | "chevron-down"
  | "chevron-up"
  | "chevron-right"
  | "external"
  | "info"
  | "lock"
  | "clock"
  | "calendar"
  | "trace"
  | "menu"
  | "close"
  | "sun"
  | "moon"
  | "logout"
  | "star"
  | "station-cut"
  | "station-mill"
  | "station-weld"
  | "station-clean"
  | "station-crimp"
  | "station-assembly"
  | "station-hardware"
  | "station-glaze"
  | "station-qc"
  | "station-pack";

const PATHS: Record<IconName, React.ReactNode> = {
  check: <path d="M2.5 8.5l3.5 3.5 7.5-8" />,
  cross: <path d="M4 4l8 8M12 4l-8 8" />,
  warn: (
    <>
      <path d="M8 2.5L14.5 13H1.5z" />
      <path d="M8 7v3" />
      <path d="M8 11.5v.01" />
    </>
  ),
  person: (
    <>
      <circle cx="8" cy="5.5" r="2.5" />
      <path d="M3.5 13.5c1-2.5 2.5-3.5 4.5-3.5s3.5 1 4.5 3.5" />
    </>
  ),
  draft: (
    <>
      <path d="M3.5 2.5h6l3 3v8h-9z" />
      <path d="M9.5 2.5v3h3" />
    </>
  ),
  quote: (
    <>
      <rect x="2.5" y="2.5" width="11" height="11" />
      <path d="M5.5 6h5M5.5 8.5h5M5.5 11h3" />
    </>
  ),
  station: (
    <>
      <rect x="2" y="6" width="12" height="6" />
      <path d="M5 6V3.5h6V6" />
    </>
  ),
  plus: <path d="M8 3v10M3 8h10" />,
  minus: <path d="M3 8h10" />,
  search: (
    <>
      <circle cx="7" cy="7" r="4.5" />
      <path d="M10.5 10.5L14 14" />
    </>
  ),
  filter: <path d="M2.5 4.5h11L9.5 9v4l-3 1.5V9z" />,
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" />
      <path d="M10.5 5.5v-3h-8v8h3" />
    </>
  ),
  download: <path d="M8 2.5v8M4.5 7L8 10.5 11.5 7M3 13.5h10" />,
  print: (
    <>
      <rect x="4" y="7" width="8" height="6" />
      <path d="M4.5 7V3h7v4M5.5 10h5" />
    </>
  ),
  edit: <path d="M9.5 3.5l3 3L6 13H3v-3zM8 5l3 3" />,
  trash: (
    <>
      <path d="M3 4.5h10M6 4.5v-2h4v2M4.5 4.5l.8 9h5.4l.8-9" />
    </>
  ),
  "arrow-right": <path d="M2.5 8h11M9.5 4l4 4-4 4" />,
  "arrow-left": <path d="M13.5 8h-11M6.5 4l-4 4 4 4" />,
  "arrow-down": <path d="M8 2.5v11M4 9.5l4 4 4-4" />,
  "arrow-up": <path d="M8 13.5v-11M4 6.5l4-4 4 4" />,
  "chevron-down": <path d="M3.5 6l4.5 4.5L12.5 6" />,
  "chevron-up": <path d="M3.5 10l4.5-4.5L12.5 10" />,
  "chevron-right": <path d="M6 3.5L10.5 8 6 12.5" />,
  external: <path d="M6.5 3.5H3.5v9h9V9.5M9 3.5h3.5V7M13 3.5L7.5 9" />,
  info: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 7.5v4M8 5v.01" />
    </>
  ),
  lock: (
    <>
      <rect x="4" y="7.5" width="8" height="6" />
      <path d="M5.5 7.5V5a2.5 2.5 0 0 1 5 0v2.5" />
    </>
  ),
  clock: (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 5v3.5L10.5 10" />
    </>
  ),
  calendar: (
    <>
      <rect x="2.5" y="4" width="11" height="9" />
      <path d="M2.5 7h11M5.5 2.5v3M10.5 2.5v3" />
    </>
  ),
  trace: <path d="M8 13.5v-11M3 7.5L8 2.5l5 5" />,
  menu: <path d="M3 4.5h10M3 8h10M3 11.5h10" />,
  close: <path d="M4 4l8 8M12 4l-8 8" />,
  sun: (
    <>
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.5v1.5M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1.1 1.1M11.5 11.5l1.1 1.1M12.6 3.4l-1.1 1.1M4.5 11.5l-1.1 1.1" />
    </>
  ),
  moon: <path d="M13.2 9.8A6 6 0 0 1 6.2 2.8a6 6 0 1 0 7 7z" />,
  logout: <path d="M9.5 2.5H3.5v11h6M6.5 8h8M11.5 5l3 3-3 3" />,
  star: <path d="M8 2.3l1.7 3.7 4 .5-3 2.8.8 4L8 11.4l-3.5 1.9.8-4-3-2.8 4-.5z" />,
  "station-cut": (
    <>
      <path d="M2.5 13.5h11" />
      <path d="M4 3.5L8 8l4-4.5M8 8v3" />
    </>
  ),
  "station-mill": (
    <>
      <circle cx="8" cy="8" r="3.5" />
      <path d="M8 4.5v-2M8 13.5v-2M4.5 8h-2M13.5 8h-2" />
    </>
  ),
  "station-weld": (
    <>
      <path d="M3 12.5L12.5 3M3 3l9.5 9.5" />
      <path d="M6 8h4" />
    </>
  ),
  "station-clean": (
    <>
      <path d="M4 13.5V8.5l4-6 4 6v5z" />
      <path d="M6 10.5h4" />
    </>
  ),
  "station-crimp": (
    <>
      <path d="M3 4.5h10M3 11.5h10" />
      <path d="M5 4.5v7M8 4.5v7M11 4.5v7" />
    </>
  ),
  "station-assembly": (
    <>
      <rect x="2.5" y="2.5" width="11" height="11" />
      <path d="M8 2.5v11M2.5 8h11" />
    </>
  ),
  "station-hardware": (
    <>
      <circle cx="8" cy="6" r="2" />
      <path d="M8 8v5.5M5.5 13.5h5" />
    </>
  ),
  "station-glaze": (
    <>
      <rect x="3" y="2.5" width="10" height="11" />
      <path d="M5.5 5l4 6M9.5 5l-4 6" />
    </>
  ),
  "station-qc": (
    <>
      <rect x="3" y="3" width="10" height="10" />
      <path d="M5.5 8.5l2 2 3.5-4" />
    </>
  ),
  "station-pack": (
    <>
      <rect x="3" y="5" width="10" height="8" />
      <path d="M3 7.5h10M8 5v8" />
    </>
  ),
};

/** Icono monolínea del sistema — 1,5 px de trazo, extremos cuadrados,
 * uniones a inglete. `aria-hidden` por defecto: el icono acompaña a la
 * etiqueta, no la reemplaza. */
export function Icon({
  name,
  size = 16,
  className = "",
  ...rest
}: {
  name: IconName | string;
  size?: number;
} & SVGProps<SVGSVGElement>): JSX.Element {
  return (
    <svg
      aria-hidden={rest["aria-label"] ? undefined : true}
      className={`ui-icon ${className}`.trim()}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="square"
      strokeLinejoin="miter"
      strokeWidth={1.5}
      viewBox="0 0 16 16"
      width={size}
      {...rest}
    >
      {PATHS[name as IconName] ?? null}
    </svg>
  );
}

/* ---------- OpeningGlyph — gramática §3.6 ---------- */

export type OpeningType =
  | "FIXED"
  | "TURN_LEFT"
  | "TURN_RIGHT"
  | "TILT_TURN_LEFT"
  | "TILT_TURN_RIGHT"
  | "AWNING"
  | "SLIDING"
  | "SLIDING_2L"
  | "SLIDING_3L"
  | "SLIDING_4L"
  | "DOOR"
  | "DOOR_ENTRY"
  | "DOOR_DOUBLE";

/** Preset sliding layouts for the icon vocabulary — same semantics the
 * engine presets declare (track 0 = raíl más exterior). */
const ICON_SLIDING_LAYOUTS: Record<string, { kind: "MOVING" | "FIXED"; track: number }[]> = {
  SLIDING: [
    { kind: "MOVING", track: 0 },
    { kind: "MOVING", track: 1 },
  ],
  SLIDING_2L: [
    { kind: "MOVING", track: 0 },
    { kind: "MOVING", track: 1 },
  ],
  SLIDING_3L: [
    { kind: "MOVING", track: 0 },
    { kind: "MOVING", track: 1 },
    { kind: "MOVING", track: 0 },
  ],
  SLIDING_4L: [
    { kind: "MOVING", track: 0 },
    { kind: "MOVING", track: 1 },
    { kind: "MOVING", track: 0 },
    { kind: "MOVING", track: 1 },
  ],
};

/** Símbolo de apertura — dibuja el MISMO contrato que el canvas y el PDF
 * (`glyphPaths`/`leafPrimitives`), no una aproximación a mano:
 * - batiente = triángulo con base en la bisagra y vértice al 40 %;
 * - `toward` (hacia el observador) = trazo continuo; alejándose = discontinuo;
 * - puerta = triángulos + umbral (el arco de barrido vive en la planta);
 * - corredera = flechas declaradas del layout; fijo = silencio. */
export function OpeningGlyph({
  type,
  toward = true,
  size = 24,
  className = "",
  ...rest
}: {
  type: OpeningType | string;
  toward?: boolean;
  size?: number;
} & SVGProps<SVGSVGElement>): JSX.Element {
  const view = toward ? "interior" : "exterior";
  // viewBox 24×24: marco 3..21, símbolo interior.
  const frame = <rect height="18" strokeWidth={1.5} width="18" x="3" y="3" />;
  const paths: JSX.Element[] = [];
  const sliding = ICON_SLIDING_LAYOUTS[type];
  if (sliding) {
    // La tabla de símbolos declara la dirección por travel — presets
    // engine: [R@0,L@1] / [R@0,R@1,L@0] / [R@0,R@1,L@0,L@1].
    const presets: ("LEFT" | "RIGHT")[][] = [
      ["RIGHT", "LEFT"],
      ["RIGHT", "RIGHT", "LEFT"],
      ["RIGHT", "RIGHT", "LEFT", "LEFT"],
    ];
    const travels = presets[sliding.length - 2] ?? ["RIGHT", "LEFT"];
    const leafW = 18 / sliding.length;
    sliding.forEach((_panel, index) => {
      const prims: GlyphPrimitive[] = [{ k: "arrow", dir: travels[index] ?? null }];
      glyphPaths(prims, 3 + leafW * index, 3, leafW, 18).forEach((path, p) => {
        paths.push(
          <path
            d={path.d}
            key={`${index}-${p}`}
            strokeDasharray={path.dash ?? undefined}
            strokeWidth={1.1}
          />,
        );
      });
    });
  } else {
    const spec = leafSpecsForBay({ opening_type: type === "DOOR" ? "DOOR_ENTRY" : type });
    const leaves = spec?.leaves ?? [];
    const leafW = leaves.length ? 18 / leaves.length : 0;
    leaves.forEach((leaf, index) => {
      const prims = leafPrimitives(leaf, view, { unit: spec?.unit });
      glyphPaths(prims, 3 + leafW * index, 3, leafW, 18).forEach((path, p) => {
        paths.push(
          <path
            d={path.d}
            key={`${index}-${p}`}
            strokeDasharray={path.dash ?? undefined}
            strokeWidth={1.1}
          />,
        );
      });
    });
    if (type === "DOOR_DOUBLE") {
      // Encuentro — la jamba de cierre entre las dos hojas.
      paths.push(<path d="M12 3v18" key="meeting" strokeWidth={1.1} />);
    }
  }
  return (
    <svg
      aria-hidden={rest["aria-label"] ? undefined : true}
      className={`ui-open-glyph ${className}`.trim()}
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="square"
      strokeLinejoin="miter"
      viewBox="0 0 24 24"
      width={size}
      {...rest}
    >
      {frame}
      {paths}
    </svg>
  );
}
