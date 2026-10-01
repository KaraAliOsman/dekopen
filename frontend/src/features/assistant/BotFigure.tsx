import { t } from "../../i18n/es-CL";
import { Orb, type OrbState } from "./Orb";
import "./orb.css";

/** DEKOPEN Bot at figure scale (96–200px) — welcome and empty states. The
 * same flat-2D identity as the Orb: solid graphite sphere with a darker
 * bottom crescent, twin cyan capsule eyes, one thin orbit line through the
 * silhouette, and the reference's flat translucent window panes behind it.
 * Pure SVG: zero runtime weight, no WebGL, prints safely. States come from
 * the same Orb vocabulary — the figure poses the character, it doesn't
 * invent new anatomy. */
export function BotFigure({
  state = "idle",
  size = 120,
  title,
}: {
  state?: OrbState;
  /** 96–200 — below 96 the panes stop reading; use Orb instead. */
  size?: number;
  title?: string;
}): JSX.Element {
  const label = title ?? t("assistant.figureLabel");
  return (
    <svg
      className={`bot-figure is-${state}`}
      viewBox="0 0 200 200"
      width={size}
      height={size}
      role="img"
      aria-label={label}
    >
      {/* Flat translucent window panes — the reference's glass stack, behind
          the sphere, leaning slightly like the hero board's panels. */}
      <g className="bot-figure__panes" transform="translate(148 20)">
        <path
          d="M6 4 L44 0 L44 96 L6 100 Z"
          fill="var(--orb-ribbon-soft)"
          fillOpacity="0.16"
          stroke="var(--orb-ribbon)"
          strokeOpacity="0.55"
          strokeWidth="1.4"
        />
        <path
          d="M-14 12 L18 8 L18 92 L-14 96 Z"
          fill="var(--orb-ribbon-soft)"
          fillOpacity="0.1"
          stroke="var(--orb-ribbon)"
          strokeOpacity="0.4"
          strokeWidth="1.2"
        />
        <path
          d="M-32 22 L-6 18 L-6 88 L-32 92 Z"
          fill="var(--orb-ribbon-soft)"
          fillOpacity="0.06"
          stroke="var(--orb-ribbon)"
          strokeOpacity="0.28"
          strokeWidth="1"
        />
      </g>

      {/* Ground shadow — a flat ellipse, no blur. */}
      <ellipse className="bot-figure__shadow" cx="96" cy="176" rx="52" ry="7.5" />

      <g className="bot-figure__tilt">
        {/* Orbit line, back sweep — wide flat ellipse centred (96,121),
            rx≈94, ry≈24, rotated −7°; the far arc hides behind the sphere. */}
        <g transform="rotate(-7 96 121)">
          <path
            className="bot-figure__ribbon bot-figure__ribbon--back"
            d="M2 121 A94 24 0 0 1 190 121"
          />
        </g>

        {/* Sphere — flat fill + flat darker crescent under the belly. */}
        <circle cx="96" cy="94" r="66" fill="var(--orb-mid)" className="bot-figure__body" />
        <path
          className="bot-figure__shade"
          d="M36.8 118 A66 66 0 0 0 155.2 118 A76 52 0 0 1 36.8 118 Z"
        />

        {/* Capsule eyes — flat cyan, no glow halo. */}
        <g className="bot-figure__eyes">
          <rect x="69" y="67" width="19.2" height="45.8" rx="9.6" fill="var(--orb-eye)" />
          <rect x="111.7" y="67" width="19.2" height="45.8" rx="9.6" fill="var(--orb-eye)" />
        </g>

        {/* Orbit line, front sweep — passes under the belly; tips extend
            past the silhouette both sides. */}
        <g transform="rotate(-7 96 121)">
          <path
            className="bot-figure__ribbon bot-figure__ribbon--front"
            d="M190 121 A94 24 0 0 1 2 121"
          />
          <path className="bot-figure__ribbon-run" d="M190 121 A94 24 0 0 1 2 121" />
        </g>
      </g>
    </svg>
  );
}

/** State text for screen readers stays honest — reuse Orb's mapping by
 * rendering nothing visual here; callers needing a live indicator compose
 * Orb + figure together. */
export { Orb };
