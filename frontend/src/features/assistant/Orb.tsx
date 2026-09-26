import "./orb.css";

/** DEKOPEN's AI identity: a small graphite orb with luminous eyes. It is the
 * assistant's presence everywhere — launcher, dock header, workspace, job
 * states — so the AI reads as a teammate, not a chat widget. The state maps
 * to the durable job lifecycle: idle / thinking (planning) / working
 * (running) / waiting (needs the user) / ok (succeeded) / error. */
export type OrbState = "idle" | "thinking" | "working" | "waiting" | "ok" | "error";

export function Orb({
  state = "idle",
  size = 40,
  title,
}: {
  state?: OrbState;
  size?: number;
  /** Accessible label — omit for decorative use inside a labelled control. */
  title?: string;
}): JSX.Element {
  return (
    <svg
      className="orb"
      data-state={state}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
    >
      <defs>
        {/* Graphite body — light falls from top-left, so the sphere reads
            volumetric instead of flat. */}
        <radialGradient id="orb-body" cx="38%" cy="30%" r="78%">
          <stop offset="0%" stopColor="#4d5a57" />
          <stop offset="38%" stopColor="#2c3634" />
          <stop offset="72%" stopColor="#151b1a" />
          <stop offset="100%" stopColor="#0b0f0e" />
        </radialGradient>
        <linearGradient id="orb-sheen" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.34" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <radialGradient id="orb-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--orb-eye)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--orb-eye)" stopOpacity="0" />
        </radialGradient>
      </defs>

      <circle className="orb-halo" cx="32" cy="33" r="29.5" fill="url(#orb-glow)" />
      <circle className="orb-body" cx="32" cy="33" r="24" fill="url(#orb-body)" />
      {/* Rim light on the lower edge keeps the orb from sinking into dark
          surfaces entirely. */}
      <path
        className="orb-rim"
        d="M 14.8 45.5 A 24 24 0 0 0 49.2 45.5"
        fill="none"
        stroke="#5a6a67"
        strokeOpacity="0.5"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
      <ellipse className="orb-sheen" cx="26" cy="22" rx="10.5" ry="6.5" fill="url(#orb-sheen)" />

      <g className="orb-eyes">
        <g className="orb-eye orb-eye--l">
          <circle className="orb-eye-glow" cx="25" cy="33" r="5.5" />
          <ellipse className="orb-eye-dot" cx="25" cy="33" rx="2.6" ry="3.6" />
          <circle className="orb-eye-spark" cx="24" cy="31.6" r="0.9" />
        </g>
        <g className="orb-eye orb-eye--r">
          <circle className="orb-eye-glow" cx="39" cy="33" r="5.5" />
          <ellipse className="orb-eye-dot" cx="39" cy="33" rx="2.6" ry="3.6" />
          <circle className="orb-eye-spark" cx="38" cy="31.6" r="0.9" />
        </g>
      </g>

      {/* State ring — waiting (attention) and error carry a colored arc so the
          state reads at a glance even at 20px. */}
      <circle className="orb-state-ring" cx="32" cy="33" r="24" />
    </svg>
  );
}
