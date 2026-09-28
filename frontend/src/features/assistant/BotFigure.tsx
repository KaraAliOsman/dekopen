import { useId } from "react";
import { t } from "../../i18n/es-CL";
import { Orb, type OrbState } from "./Orb";
import "./orb.css";

/** DEKOPEN Bot at figure scale (96–200px) — welcome and empty states. The
 * same sphere/capsule-eyes/ribbon identity, plus the reference's translucent
 * window panes behind the sphere and a soft ground shadow. Pure SVG: zero
 * runtime weight, no WebGL, prints safely. States come from the same Orb
 * vocabulary — the figure poses the character, it doesn't invent new anatomy. */
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
  const uid = useId();
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
      <defs>
        <radialGradient id={`${uid}-body`} cx="36%" cy="25%" r="85%">
          <stop offset="0%" stopColor="var(--orb-hi)" />
          <stop offset="50%" stopColor="var(--orb-mid)" />
          <stop offset="100%" stopColor="var(--orb-lo)" />
        </radialGradient>
        <linearGradient id={`${uid}-eye`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--orb-eye-hi)" />
          <stop offset="100%" stopColor="var(--orb-eye)" />
        </linearGradient>
        <linearGradient id={`${uid}-pane`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--orb-ribbon)" stopOpacity="0.34" />
          <stop offset="100%" stopColor="var(--orb-ribbon)" stopOpacity="0.08" />
        </linearGradient>
        <linearGradient id={`${uid}-ribbon`} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="var(--orb-ribbon-soft)" />
          <stop offset="55%" stopColor="var(--orb-ribbon)" />
          <stop offset="100%" stopColor="var(--orb-ribbon-hi, #8ff6ff)" />
        </linearGradient>
      </defs>

      {/* Translucent window panes — the reference's glass stack, behind the
          sphere, leaning slightly like the hero board's panels. */}
      <g className="bot-figure__panes" transform="translate(148 20)">
        <path
          d="M6 4 L44 0 L44 96 L6 100 Z"
          fill={`url(#${uid}-pane)`}
          stroke="var(--orb-ribbon)"
          strokeOpacity="0.55"
          strokeWidth="1.4"
        />
        <path
          d="M-14 12 L18 8 L18 92 L-14 96 Z"
          fill={`url(#${uid}-pane)`}
          stroke="var(--orb-ribbon)"
          strokeOpacity="0.4"
          strokeWidth="1.2"
        />
        <path
          d="M-32 22 L-6 18 L-6 88 L-32 92 Z"
          fill={`url(#${uid}-pane)`}
          stroke="var(--orb-ribbon)"
          strokeOpacity="0.28"
          strokeWidth="1"
        />
      </g>

      {/* Ground shadow. */}
      <ellipse className="bot-figure__shadow" cx="96" cy="176" rx="52" ry="7.5" />

      <g className="bot-figure__tilt">
        {/* Ribbon back sweep (ellipse rx≈94, ry≈29, rotated −12° about
            (96,100)): from the left tip through the top to the right tip,
            hidden by the sphere where they overlap. */}
        <path
          className="bot-figure__ribbon bot-figure__ribbon--back"
          d="M4.06 119.55 A94 29 -12 0 0 187.94 80.45"
        />

        <circle cx="96" cy="98" r="62" fill={`url(#${uid}-body)`} className="bot-figure__body" />
        {/* Soft top-left specular + faint cyan bounce where the ribbon is
            closest — volume, not plastic shine. */}
        <ellipse
          cx="74"
          cy="62"
          rx="21"
          ry="12"
          transform="rotate(-24 74 62)"
          className="bot-figure__spec"
        />
        <ellipse
          cx="112"
          cy="136"
          rx="26"
          ry="9"
          transform="rotate(-16 112 136)"
          className="bot-figure__bounce"
        />

        {/* Capsule eyes — the reference's tall cyan slots. */}
        <g className="bot-figure__eyes">
          <rect className="bot-figure__eye-glow" x="60" y="68" width="30" height="52" rx="15" />
          <rect className="bot-figure__eye-glow" x="102" y="68" width="30" height="52" rx="15" />
          <rect x="66" y="74" width="19" height="41" rx="9.5" fill={`url(#${uid}-eye)`} />
          <rect x="108" y="74" width="19" height="41" rx="9.5" fill={`url(#${uid}-eye)`} />
        </g>

        {/* Ribbon front sweep — crosses the belly in front, tips exit the
            silhouette at lower-left. */}
        <path
          className="bot-figure__ribbon bot-figure__ribbon--front"
          d="M187.94 80.45 A94 29 -12 0 1 4.06 119.55"
        />
        <path className="bot-figure__ribbon-run" d="M187.94 80.45 A94 29 -12 0 1 4.06 119.55" />
      </g>
    </svg>
  );
}

/** State text for screen readers stays honest — reuse Orb's mapping by
 * rendering nothing visual here; callers needing a live indicator compose
 * Orb + figure together. */
export { Orb };
