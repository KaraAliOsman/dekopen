import { useId } from "react";

import { Orb, type OrbState } from "./Orb";
import "./orb.css";

/** Figura completa del asistente — la referencia del dueño: la esfera del
 * Orb sobre una sombra de suelo, con las hojas de ventana translúcidas
 * armándose detrás (la fábrica que el bot viene a ayudar) y la cinta
 * orbital. Se usa en estados vacíos y en la bienvenida del dock.
 *
 * `welcome` activa la animación de una sola pasada «la ventana se arma»:
 * las hojas suben a su lugar, la esfera se asienta y la cinta aparece.
 * `prefers-reduced-motion` la desactiva por completo (orb.css). */
export function BotFigure({
  size = 120,
  state = "idle",
  welcome = false,
}: {
  /** Tamaño de la figura completa (alto). Tamaño canónico de hero: 160. */
  size?: number;
  state?: OrbState;
  welcome?: boolean;
}): JSX.Element {
  const uid = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const paneId = `bot-pane-${uid}`;
  return (
    <svg
      className={`bot-figure${welcome ? " bot-figure--welcome" : ""}`}
      viewBox="0 0 160 170"
      width={size}
      height={size * 1.0625}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={paneId} x1="0" y1="0" x2="0" y2="1">
          <stop className="p0" offset="0" />
          <stop className="p1" offset="1" />
        </linearGradient>
      </defs>
      {/* Las hojas de la ventana detrás de la esfera — tres paños corriendo
          en altura escalonada, como el alzado que el asistente ayuda a
          dibujar. */}
      <g className="bot-figure__panes" stroke="var(--orb-ribbon)">
        <rect x="92" y="10" width="20" height="62" fill={`url(#${paneId})`} />
        <rect x="100" y="28" width="20" height="66" fill={`url(#${paneId})`} />
        <rect x="108" y="48" width="20" height="70" fill={`url(#${paneId})`} />
      </g>
      <ellipse className="bot-figure__shadow" cx="68" cy="146" rx="42" ry="8" />
      <g className="bot-figure__orb" transform="translate(20 36)">
        <Orb state={state} size={96} />
      </g>
    </svg>
  );
}
