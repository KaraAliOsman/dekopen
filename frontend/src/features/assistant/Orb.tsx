import { useId } from "react";
import "./orb.css";

/** DEKOPEN's AI identity: an anthracite sphere with twin casement-slot eyes —
 * the paired-window face is the fenestration pun that makes the assistant
 * DEKOPEN's own. Two orthogonal channels carry meaning: the eyes carry life
 * (breathe, blink, gaze, poses) and a thin outer arc carries job status in
 * the same hues as the state pills. No mouth, no glow — the eyes and the
 * ring carry the whole range the product needs. */
export type OrbState =
  | "idle"
  | "input"
  | "queued"
  | "thinking"
  | "working"
  | "waiting"
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
    case "WAITING_FOR_APPROVAL":
      return "waiting";
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

export function Orb({
  state = "idle",
  size = 28,
  title,
}: {
  state?: OrbState;
  size?: number;
  /** Accessible label — omit for decorative use inside a labelled control. */
  title?: string;
}): JSX.Element {
  // Gradient ids must be unique per instance — duplicate ids across mounted
  // orbs would all resolve to the first defs block.
  const uid = useId();
  return (
    <svg
      className={`orb is-${state}${size < 28 ? " orb--s" : ""}`}
      viewBox="0 0 48 48"
      width={size}
      height={size}
      role={title ? "img" : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <defs>
        <radialGradient id={`${uid}-body`} cx="38%" cy="28%" r="80%">
          <stop offset="0%" stopColor="var(--orb-hi)" />
          <stop offset="55%" stopColor="var(--orb-mid)" />
          <stop offset="100%" stopColor="var(--orb-lo)" />
        </radialGradient>
      </defs>

      {/* Semantics channel — the status arc, hidden unless the state needs it. */}
      <circle className="orb__ring" cx="24" cy="24" r="21.5" />

      {/* Life channel — everything that tilts, breathes and blinks. */}
      <g className="orb__tilt">
        <circle className="orb__body" cx="24" cy="24" r="17" fill={`url(#${uid}-body)`} />
        <ellipse
          className="orb__bounce"
          cx="29"
          cy="33"
          rx="6"
          ry="2.6"
          transform="rotate(-18 29 33)"
        />
        <ellipse
          className="orb__spec"
          cx="18"
          cy="15.5"
          rx="5.4"
          ry="3"
          transform="rotate(-26 18 15.5)"
        />

        <g className="orb__eyes orb__eyes--open">
          <rect className="orb__eye" x="15.6" y="20" width="6" height="9.4" rx="3" />
          <rect className="orb__eye" x="26.4" y="20" width="6" height="9.4" rx="3" />
          <circle className="orb__glint" cx="17.8" cy="22.4" r="1" />
          <circle className="orb__glint" cx="28.6" cy="22.4" r="1" />
        </g>
        <g className="orb__eyes orb__eyes--joy">
          <path d="M15.8 26.6 Q18.6 22.2 21.4 26.6" />
          <path d="M26.6 26.6 Q29.4 22.2 32.2 26.6" />
        </g>
        <g className="orb__eyes orb__eyes--worry">
          <rect
            x="15.8"
            y="23.4"
            width="5.8"
            height="3.4"
            rx="1.7"
            transform="rotate(-14 18.7 25.1)"
          />
          <rect
            x="26.4"
            y="23.4"
            width="5.8"
            height="3.4"
            rx="1.7"
            transform="rotate(14 29.3 25.1)"
          />
        </g>
        <g className="orb__eyes orb__eyes--flat">
          <rect x="15.8" y="23.9" width="5.8" height="3" rx="1.5" />
          <rect x="26.4" y="23.9" width="5.8" height="3" rx="1.5" />
        </g>
      </g>
    </svg>
  );
}
