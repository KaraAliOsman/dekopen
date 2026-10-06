import { useId } from "react";

import { t } from "../../i18n/es-CL";
import "./orb.css";

/** Estados del Orb — la spec (idle, queued, thinking, working, waiting,
 * success, error, canceled) más dos extensiones de producto:
 * `input` (está escuchando una meta que el usuario escribe) y `approval`
 * (espera confirmación humana — anillo naranja de «requiere persona» §F7). */
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

/** Job ai_jobs.state → estado del Orb. Cualquier estado desconocido cae a
 * «idle» seguro — el indicador nunca inventa actividad. */
export function orbStateFor(state: string | null | undefined): OrbState {
  switch (state) {
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

/** El Orb — figura de la spec `docs/cola/adjuntos/bot/dekopen-orb.*` más la
 * cinta orbital inclinada de la referencia del dueño: esfera de antracita
 * (material de miembro), ojos cápsula teal que comunican el estado (abiertos,
 * entrecerrados, parpadeo, mirada lateral) y un anillo exterior que lleva el
 * color semántico solo cuando el estado lo necesita. Todo el arte vive en un
 * SVG inline tematizado por CSS — cada instancia recibe ids de gradiente
 * únicos vía useId, así varios Orbs en pantalla no colisionan. */
export function Orb({
  state = "idle",
  size = 28,
  title,
}: {
  state?: OrbState;
  /** Tamaños canónicos de la spec: 16, 20, 28, 64 (y 160 vía BotFigure). */
  size?: number;
  title?: string;
}): JSX.Element {
  const uid = useId();
  const gradientId = `orb-body-${uid.replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const label = title ? `${title} — ${t(STATE_TEXT[state] ?? STATE_TEXT.idle)}` : undefined;
  return (
    <svg
      className={`orb is-${state}${size < 28 ? " orb--s" : ""}`}
      viewBox="0 0 48 48"
      width={size}
      height={size}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <defs>
        <radialGradient id={gradientId} cx="38%" cy="28%" r="80%">
          <stop className="s0" offset="0" />
          <stop className="s1" offset="55%" />
          <stop className="s2" offset="100%" />
        </radialGradient>
      </defs>
      {/* Anillo semántico — el canal de estado (acento/advertencia/ok/peligro/
          naranja-persona). Oculto cuando no hay nada que reportar. */}
      <circle className="orb__ring" cx="24" cy="24" r="21.5" />
      <g className="orb__tilt">
        {/* Cinta orbital: mitad trasera tras la esfera, mitad delantera sobre
            ella — la elipse inclinada de la referencia del dueño. */}
        <ellipse
          className="orb__ribbon orb__ribbon--back"
          cx="24"
          cy="26"
          rx="20"
          ry="5.8"
          transform="rotate(-12 24 26)"
        />
        <g className="orb__sphere">
          <circle className="orb__body" cx="24" cy="24" r="17" fill={`url(#${gradientId})`} />
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
          {/* Los ojos llevan la vida: pose, parpadeo, mirada. */}
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
        <path
          className="orb__ribbon orb__ribbon--front"
          d="M40.91 25.71 A20 5.8 -12 0 1 9.45 32.79"
        />
      </g>
    </svg>
  );
}
