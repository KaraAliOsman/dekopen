import { useId } from "react";
import { t } from "../../i18n/es-CL";
import "./orb.css";

/** DEKOPEN Bot — the identity from `referencias/dekopen-bot-original.png` (user-
 * provided reference; this SVG is original geometry matching it, not a copied
 * mark): a graphite-near-black sphere with soft volume, two tall cyan capsule
 * eyes, and a thin cyan orbital ribbon that passes in front of the sphere's
 * belly and behind its upper right — drawn as two half-arcs so the wrap is
 * physically coherent. No body, no mouth, no helmet.
 *
 * Two orthogonal channels carry meaning: the eyes carry life (breathe, blink,
 * gaze, poses) and a thin circular arc carries job status in the state-pill
 * hues; the ribbon is identity, tinted subtly on consequential states. */
export type OrbState =
  | "idle"
  | "input"
  | "queued"
  | "thinking"
  | "working"
  | "waiting"
  | "approval"
  | "success"
  | "error"
  | "canceled";

/** Durable job lifecycle → orb state. Unknown future states degrade to idle —
 * never pass the API state through unmapped. */
export function orbStateFor(jobState?: string): OrbState {
  switch (jobState) {
    case "QUEUED":
      return "queued";
    case "PLANNING":
      return "thinking";
    case "RUNNING":
      return "working";
    case "WAITING_FOR_USER":
      return "waiting";
    case "WAITING_FOR_APPROVAL":
      return "approval";
    case "SUCCEEDED":
      return "success";
    case "FAILED":
    case "FAILED_RETRYABLE":
      return "error";
    case "CANCELED":
      return "canceled";
    default:
      return "idle";
  }
}

/** OrbState → i18n key — explicit state text for accessibility, per mandate. */
const STATE_TEXT: Record<OrbState, Parameters<typeof t>[0]> = {
  idle: "assistant.state.idle",
  input: "assistant.state.input",
  queued: "assistant.state.queued",
  thinking: "assistant.state.thinking",
  working: "assistant.state.working",
  waiting: "assistant.state.waiting",
  approval: "assistant.state.approval",
  success: "assistant.state.success",
  error: "assistant.state.error",
  canceled: "assistant.state.canceled",
};

export function Orb({
  state = "idle",
  size = 28,
  title,
}: {
  state?: OrbState;
  size?: number;
  /** Accessible label — omit for decorative use inside a labelled control.
   * When present, the current state is announced with it. */
  title?: string;
}): JSX.Element {
  // Gradient ids must be unique per instance — duplicate ids across mounted
  // orbs would all resolve to the first defs block.
  const uid = useId();
  const label = title ? `${title} — ${t(STATE_TEXT[state] ?? STATE_TEXT.idle)}` : undefined;
  return (
    <svg
      className={`orb is-${state}${size < 28 ? " orb--s" : ""}`}
      viewBox="0 0 48 48"
      width={size}
      height={size}
      role={label ? "img" : undefined}
      aria-hidden={label ? undefined : true}
      aria-label={label}
    >
      <defs>
        <radialGradient id={`${uid}-body`} cx="36%" cy="26%" r="82%">
          <stop offset="0%" stopColor="var(--orb-hi)" />
          <stop offset="52%" stopColor="var(--orb-mid)" />
          <stop offset="100%" stopColor="var(--orb-lo)" />
        </radialGradient>
        <linearGradient id={`${uid}-eye`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--orb-eye-hi)" />
          <stop offset="100%" stopColor="var(--orb-eye)" />
        </linearGradient>
      </defs>

      {/* Semantics channel — the status arc, hidden unless the state needs it. */}
      <circle className="orb__ring" cx="24" cy="24" r="21.5" />

      {/* Life channel — everything that tilts, breathes and blinks. */}
      <g className="orb__tilt">
        {/* Ribbon back sweep — drawn before the sphere so its upper-right
            run disappears behind the body like the reference's orbit. */}
        <path
          className="orb__ribbon orb__ribbon--back"
          d="M2.07 30.47 A22.6 6.9 -14 0 0 45.93 19.53"
        />

        <circle className="orb__body" cx="24" cy="23.5" r="15.5" fill={`url(#${uid}-body)`} />
        <ellipse
          className="orb__bounce"
          cx="28.5"
          cy="33.6"
          rx="6.4"
          ry="2.4"
          transform="rotate(-16 28.5 33.6)"
        />
        <ellipse
          className="orb__spec"
          cx="18.4"
          cy="15"
          rx="5.2"
          ry="2.9"
          transform="rotate(-24 18.4 15)"
        />

        <g className="orb__eyes orb__eyes--open">
          <rect className="orb__eye-glow" x="14.9" y="16.4" width="8.2" height="14.4" rx="4.1" />
          <rect className="orb__eye-glow" x="25.1" y="16.4" width="8.2" height="14.4" rx="4.1" />
          <rect
            className="orb__eye"
            x="16.4"
            y="17.9"
            width="5.2"
            height="11.4"
            rx="2.6"
            fill={`url(#${uid}-eye)`}
          />
          <rect
            className="orb__eye"
            x="26.6"
            y="17.9"
            width="5.2"
            height="11.4"
            rx="2.6"
            fill={`url(#${uid}-eye)`}
          />
          <circle className="orb__glint" cx="18.2" cy="20" r="0.9" />
          <circle className="orb__glint" cx="28.4" cy="20" r="0.9" />
        </g>
        <g className="orb__eyes orb__eyes--joy">
          <path d="M15.9 25.6 Q19 21.4 22.1 25.6" />
          <path d="M26.1 25.6 Q29.2 21.4 32.3 25.6" />
        </g>
        <g className="orb__eyes orb__eyes--worry">
          <rect
            x="15.9"
            y="22.2"
            width="6.2"
            height="4.6"
            rx="2.3"
            transform="rotate(-9 19 24.5)"
          />
          <rect x="26" y="22.2" width="6.2" height="4.6" rx="2.3" transform="rotate(9 29.1 24.5)" />
        </g>
        <g className="orb__eyes orb__eyes--flat">
          <rect x="15.9" y="22.6" width="6.2" height="3.6" rx="1.8" />
          <rect x="26" y="22.6" width="6.2" height="3.6" rx="1.8" />
        </g>

        {/* Ribbon front sweep — over the belly, tips extend past the
            silhouette at lower-left. */}
        <path
          className="orb__ribbon orb__ribbon--front"
          d="M45.93 19.53 A22.6 6.9 -14 0 1 2.07 30.47"
        />
        {/* Working state: a bright segment runs the front ribbon. */}
        <path className="orb__ribbon-run" d="M45.93 19.53 A22.6 6.9 -14 0 1 2.07 30.47" />
      </g>
    </svg>
  );
}
