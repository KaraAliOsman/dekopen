import { useId } from "react";
import { t } from "../../i18n/es-CL";
import { Orb, type OrbState } from "./Orb";
import "./orb.css";

/** DEKOPEN Bot at figure scale (96–200px) — welcome and empty states. The
 * same sphere/capsule-eyes/orbit-ring identity as the Orb, plus the
 * reference's translucent window panes behind the sphere and a soft ground
 * shadow. Pure SVG: zero runtime weight, no WebGL, prints safely. States
 * come from the same Orb vocabulary — the figure poses the character, it
 * doesn't invent new anatomy. */
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
        <radialGradient id={`${uid}-body`} cx="38%" cy="30%" r="78%" fx="34%" fy="24%">
          <stop offset="0%" stopColor="var(--orb-hi)" />
          <stop offset="34%" stopColor="var(--orb-mid)" />
          <stop offset="72%" stopColor="var(--orb-deep)" />
          <stop offset="100%" stopColor="var(--orb-lo)" />
        </radialGradient>
        <linearGradient id={`${uid}-eye`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--orb-eye-hi)" />
          <stop offset="100%" stopColor="var(--orb-eye)" />
        </linearGradient>
        <radialGradient id={`${uid}-glow`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--orb-eye)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--orb-eye)" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={`${uid}-spec`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--orb-spec)" stopOpacity="0.9" />
          <stop offset="60%" stopColor="var(--orb-spec)" stopOpacity="0.28" />
          <stop offset="100%" stopColor="var(--orb-spec)" stopOpacity="0" />
        </radialGradient>
        <linearGradient id={`${uid}-pane`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="var(--orb-ribbon)" stopOpacity="0.34" />
          <stop offset="100%" stopColor="var(--orb-ribbon)" stopOpacity="0.08" />
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
        {/* Orbit ring, back sweep — wide flat ellipse centred (96,121),
            rx≈94, ry≈24, rotated −7°; the far arc hides behind the sphere. */}
        <g transform="rotate(-7 96 121)">
          <path
            className="bot-figure__ribbon bot-figure__ribbon--back"
            d="M2 121 A94 24 0 0 1 190 121"
          />
        </g>

        <circle cx="96" cy="94" r="66" fill={`url(#${uid}-body)`} className="bot-figure__body" />
        {/* Soft top-left specular + faint cyan bounce where the ring is
            closest — volume, not plastic shine. */}
        <ellipse
          cx="69"
          cy="56"
          rx="29"
          ry="17"
          transform="rotate(-28 69 56)"
          className="bot-figure__spec"
          fill={`url(#${uid}-spec)`}
        />
        <ellipse
          cx="121"
          cy="137"
          rx="25"
          ry="9"
          transform="rotate(-14 121 137)"
          className="bot-figure__bounce"
          fill={`url(#${uid}-glow)`}
        />

        {/* Capsule eyes — the reference's tall cyan slots. */}
        <g className="bot-figure__eyes">
          <ellipse cx="78.7" cy="89.6" rx="18.3" ry="29.2" fill={`url(#${uid}-glow)`} />
          <ellipse cx="121.3" cy="89.6" rx="18.3" ry="29.2" fill={`url(#${uid}-glow)`} />
          <rect x="69" y="67" width="19.2" height="45.8" rx="9.6" fill={`url(#${uid}-eye)`} />
          <rect x="111.7" y="67" width="19.2" height="45.8" rx="9.6" fill={`url(#${uid}-eye)`} />
        </g>

        {/* Orbit ring, front sweep — passes under the belly; tips extend
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
