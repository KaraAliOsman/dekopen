/** Firma DEKOPEN — los componentes que hacen que se reconozca el producto
 * en una captura: la carga que dibuja una cota, la hoja con inglete, el
 * botón que responde «¿de dónde sale?» y la marca de demo. */
import { type ReactNode, useRef, useState } from "react";

import { t } from "../i18n/es-CL";
import { Popover } from "./Overlays";
import { TechDetails } from "./TechDetails";

/* ---------- DimLoader ---------- */

/** Carga con gramática de cota: una línea acotada que crece de 0 → 100 %
 * mientras el sistema «mide». Prohibido el spinner genérico en superficies
 * que muestran dimensiones; el arco se dibuja, no gira.
 * `indeterminate` dibuja la línea base con el tramo móvil; `value` 0–1
 * dibuja progreso real. */
export function DimLoader({
  value,
  label,
  className = "",
}: {
  /** 0..1 — omitido = indeterminado. */
  value?: number;
  label?: string;
  className?: string;
}): JSX.Element {
  const pct = value === undefined ? null : Math.min(1, Math.max(0, value));
  return (
    <span
      aria-label={label ?? t("ui.loadingDims")}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={pct === null ? undefined : Math.round(pct * 100)}
      className={`dim-loader${pct === null ? " is-indeterminate" : ""} ${className}`.trim()}
      role="progressbar"
    >
      <svg aria-hidden className="dim-loader__svg" viewBox="0 0 120 24">
        {/* línea de cota con sus testigos */}
        <line className="dim-loader__witness" x1="8" x2="8" y1="4" y2="20" />
        <line className="dim-loader__witness" x1="112" x2="112" y1="4" y2="20" />
        <line className="dim-loader__baseline" x1="8" x2="112" y1="12" y2="12" />
        {pct === null ? (
          <line className="dim-loader__sweep" x1="8" x2="112" y1="12" y2="12" />
        ) : (
          <line className="dim-loader__fill" x1="8" x2={8 + 104 * pct} y1="12" y2="12" />
        )}
        {/* flechas de cota */}
        <path className="dim-loader__arrow" d="M8 12l5-3v6z" />
        <path className="dim-loader__arrow" d="M112 12l-5-3v6z" />
      </svg>
      <span className="dim-loader__text">{label ?? t("ui.loadingDims")}</span>
    </span>
  );
}

/* ---------- SheetSurface ---------- */

/** La hoja — paper + borde + sombra de lámina; `miter` aplica la esquina
 * recortada a 45° que es la firma de DEKOPEN (solo superficies tipo hoja:
 * documento, vista previa, lienzo, marca). */
export function SheetSurface({
  miter = false,
  title,
  children,
  className = "",
}: {
  miter?: boolean;
  title?: ReactNode;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <article className={`ui-sheet${miter ? " sheet-miter" : ""} ${className}`.trim()}>
      {title ? <header className="ui-sheet__head">{title}</header> : null}
      <div className="ui-sheet__body">{children}</div>
    </article>
  );
}

/* ---------- TraceButton ---------- */

export type Trace = {
  /** La fórmula visible — «ancho × alto × precio_m²». */
  formula?: string;
  /** Entradas que alimentaron el cálculo. */
  inputs?: { label: string; value: string }[];
  /** Fuente autoritativa — tabla de precio, revisión del documento, regla. */
  authority?: string;
  /** Versión del motor que produjo el número. */
  engineVersion?: string;
};

/** «¿De dónde sale?» — cada número derivable responde: fórmula, entradas,
 * autoridad, versión del motor. Recibe la traza del backend; NUNCA la
 * computa — si no hay traza, el número no debiera mostrar una cifra
 * calculada en absoluto. */
export function TraceButton({ trace }: { trace: Trace | null | undefined }): JSX.Element | null {
  const anchorRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  if (!trace) return null;
  return (
    <>
      <button
        aria-expanded={open}
        className="ui-trace"
        onClick={() => setOpen((v) => !v)}
        ref={anchorRef}
        type="button"
      >
        {t("ui.traceQuestion")}
      </button>
      {open ? (
        <Popover anchorRef={anchorRef} onClose={() => setOpen(false)}>
          <dl className="ui-trace__grid">
            {trace.formula ? (
              <>
                <dt>{t("ui.traceFormula")}</dt>
                <dd className="fmt-num">{trace.formula}</dd>
              </>
            ) : null}
            {trace.inputs?.length ? (
              <>
                <dt>{t("ui.traceInputs")}</dt>
                <dd>
                  {trace.inputs.map((input) => (
                    <div className="ui-trace__input" key={input.label}>
                      <span>{input.label}</span>
                      <span className="fmt-num">{input.value}</span>
                    </div>
                  ))}
                </dd>
              </>
            ) : null}
            {trace.authority ? (
              <>
                <dt>{t("ui.traceAuthority")}</dt>
                <dd>{trace.authority}</dd>
              </>
            ) : null}
            {trace.engineVersion ? (
              <>
                <dt>{t("ui.traceEngine")}</dt>
                <dd className="fmt-num">{trace.engineVersion}</dd>
              </>
            ) : null}
          </dl>
          <TechDetails diagnostic={JSON.stringify(trace, null, 2)} />
        </Popover>
      ) : null}
    </>
  );
}

/* ---------- DemoBadge ---------- */

/** Marca de datos demo — discreta pero inequívoca: el contenido no es
 * producción del cliente. */
export function DemoBadge({ title }: { title?: string }): JSX.Element {
  return (
    <span className="ui-demo-badge" title={title}>
      {t("ui.demoBadge")}
    </span>
  );
}
