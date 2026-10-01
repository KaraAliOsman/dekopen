import { t } from "../../i18n/es-CL";
import "./orb.css";

/** DEKOPEN Bot — flat 2D identity inspired by modern assistant marks (Grok):
 * a solid graphite sphere, two cyan capsule eyes, and one thin cyan orbit
 * line tilted through the silhouette — drawn as a flat ellipse whose back
 * half hides behind the sphere and whose front half sweeps under it. No
 * gradients, no gloss, no specular, no body, no mouth — geometry and one
 * accent color carry the whole character, so it reads crisp at any size.
 *
 * Two orthogonal channels carry meaning: the eyes carry life (breathe, blink,
 * gaze, poses) and a thin circular arc carries job status in the state-pill
 * hues; the orbit line is identity, tinted on consequential states. */
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
      {/* Semantics channel — the status arc, hidden unless the state needs it. */}
      <circle className="orb__ring" cx="24" cy="24" r="22.5" />

      {/* Life channel — everything that tilts, breathes and blinks. */}
      <g className="orb__tilt">
        {/* Orbit line, back sweep — a wide flat ellipse tilted through the
            sphere; the far arc hides behind the body. */}
        <g transform="rotate(-8 24 29)">
          <path className="orb__ribbon orb__ribbon--back" d="M1.5 29 A22.5 5.8 0 0 1 46.5 29" />
        </g>

        {/* Sphere — one flat fill; a slightly darker flat bottom crescent
            gives a hint of depth without any gradient. */}
        <circle className="orb__body" cx="24" cy="22.5" r="15.8" fill="var(--orb-mid)" />
        <path
          className="orb__shade"
          d="M8.9 28.5 A15.8 15.8 0 0 0 39.1 28.5 A18.5 13 0 0 1 8.9 28.5 Z"
        />

        <g className="orb__eyes orb__eyes--open">
          <rect x="16.6" y="16" width="4.6" height="11" rx="2.3" fill="var(--orb-eye)" />
          <rect x="26.8" y="16" width="4.6" height="11" rx="2.3" fill="var(--orb-eye)" />
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

        {/* Orbit line, front sweep — passes under the belly, tips extending
            past the silhouette on both sides. Never a mouth. */}
        <g transform="rotate(-8 24 29)">
          <path className="orb__ribbon orb__ribbon--front" d="M46.5 29 A22.5 5.8 0 0 1 1.5 29" />
          {/* Working state: a bright segment runs the front line. */}
          <path className="orb__ribbon-run" d="M46.5 29 A22.5 5.8 0 0 1 1.5 29" />
        </g>
      </g>
    </svg>
  );
}
