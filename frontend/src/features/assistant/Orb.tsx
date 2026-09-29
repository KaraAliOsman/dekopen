import { useId } from "react";
import { t } from "../../i18n/es-CL";
import "./orb.css";

/** DEKOPEN Bot — the identity from `referencias/dekopen-bot-original.png` (user-
 * provided reference; this SVG is original geometry matching it, not a copied
 * mark): a graphite-near-black sphere with soft volume, two tall cyan capsule
 * eyes, and a thin cyan orbital ring tilted around it — drawn as a wide flat
 * ellipse whose back half disappears behind the sphere and whose front half
 * sweeps beneath it, so the wrap is physically coherent and never reads as a
 * mouth. No body, no mouth, no helmet.
 *
 * Two orthogonal channels carry meaning: the eyes carry life (breathe, blink,
 * gaze, poses) and a thin circular arc carries job status in the state-pill
 * hues; the orbit ring is identity, tinted subtly on consequential states. */
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
      </defs>

      {/* Semantics channel — the status arc, hidden unless the state needs it. */}
      <circle className="orb__ring" cx="24" cy="24" r="22.5" />

      {/* Life channel — everything that tilts, breathes and blinks. */}
      <g className="orb__tilt">
        {/* Orbit ring, back sweep — a wide flat ellipse centred below the
            eyes; its far arc hides behind the sphere like the reference. */}
        <g transform="rotate(-8 24 29)">
          <path className="orb__ribbon orb__ribbon--back" d="M1.5 29 A22.5 5.8 0 0 1 46.5 29" />
        </g>

        <circle className="orb__body" cx="24" cy="22.5" r="15.8" fill={`url(#${uid}-body)`} />
        {/* Soft top-left specular — graphite sheen, not a stuck-on pill. */}
        <ellipse
          className="orb__spec"
          cx="17.5"
          cy="13.5"
          rx="7"
          ry="4"
          transform="rotate(-28 17.5 13.5)"
          fill={`url(#${uid}-spec)`}
        />
        {/* Cyan bounce where the orbit comes closest under the belly. */}
        <ellipse
          className="orb__bounce"
          cx="30"
          cy="33"
          rx="6"
          ry="2.2"
          transform="rotate(-14 30 33)"
          fill={`url(#${uid}-glow)`}
        />

        <g className="orb__eyes orb__eyes--open">
          <ellipse cx="18.9" cy="21.5" rx="4.4" ry="7" fill={`url(#${uid}-glow)`} />
          <ellipse cx="29.1" cy="21.5" rx="4.4" ry="7" fill={`url(#${uid}-glow)`} />
          <rect x="16.6" y="16" width="4.6" height="11" rx="2.3" fill={`url(#${uid}-eye)`} />
          <rect x="26.8" y="16" width="4.6" height="11" rx="2.3" fill={`url(#${uid}-eye)`} />
        </g>
        <g className="orb__eyes orb__eyes--joy">
          <path d="M16.2 24.4 Q18.9 20.4 21.6 24.4" />
          <path d="M26.4 24.4 Q29.1 20.4 31.8 24.4" />
        </g>
        <g className="orb__eyes orb__eyes--worry">
          <rect
            x="16.2"
            y="20.6"
            width="5"
            height="4.2"
            rx="2.1"
            transform="rotate(-10 18.7 22.7)"
          />
          <rect
            x="26.8"
            y="20.6"
            width="5"
            height="4.2"
            rx="2.1"
            transform="rotate(10 29.3 22.7)"
          />
        </g>
        <g className="orb__eyes orb__eyes--flat">
          <rect x="16.4" y="21.2" width="5" height="3.4" rx="1.7" />
          <rect x="26.6" y="21.2" width="5" height="3.4" rx="1.7" />
        </g>

        {/* Orbit ring, front sweep — passes under the belly, tips extending
            past the silhouette on both sides. Never a mouth. */}
        <g transform="rotate(-8 24 29)">
          <path className="orb__ribbon orb__ribbon--front" d="M46.5 29 A22.5 5.8 0 0 1 1.5 29" />
          {/* Working state: a bright segment runs the front ring. */}
          <path className="orb__ribbon-run" d="M46.5 29 A22.5 5.8 0 0 1 1.5 29" />
        </g>
      </g>
    </svg>
  );
}
