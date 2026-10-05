/** Estructura — los contenedores con reglas de la constitución:
 * Paneles planos, Inspector de 300–320 px con "Avanzado" plegado,
 * KeyValue de especificación, Stepper de fases, Stat que solo existe
 * con una decisión asociada. */
import { useId, type ReactNode } from "react";

import { t } from "../i18n/es-CL";

/* ---------- Panel / Section ---------- */

/** Superficie de panel — E1 (borde de 1 px, sin sombra). La tarjeta es
 * paper solo cuando contiene una hoja o un formulario completo. */
export function Panel({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return (
    <section className={`ui-panel ${className}`.trim()}>
      {title || actions ? (
        <header className="ui-panel__head">
          {title ? <h2 className="ui-panel__title">{title}</h2> : null}
          {actions ? <div className="ui-panel__actions">{actions}</div> : null}
        </header>
      ) : null}
      <div className="ui-panel__body">{children}</div>
    </section>
  );
}

/** Sección con título dentro de un panel/formulario — divide un formulario
 * largo por secciones con títulos, nunca en un muro. */
export function Section({
  title,
  children,
}: {
  title: ReactNode;
  children: ReactNode;
}): JSX.Element {
  return (
    <fieldset className="ui-section">
      <legend className="ui-section__title">{title}</legend>
      {children}
    </fieldset>
  );
}

/* ---------- KeyValue ---------- */

/** Par especificación — etiqueta técnica a la izquierda, valor a la
 * derecha. La unidad y el formato vienen de ui/format.tsx. */
export function KeyValue({
  label,
  children,
  hint,
}: {
  label: ReactNode;
  children: ReactNode;
  hint?: string;
}): JSX.Element {
  return (
    <div className="ui-kv" title={hint}>
      <dt className="ui-kv__key">{label}</dt>
      <dd className="ui-kv__value">{children}</dd>
    </div>
  );
}

/** Lista de especificación — agrupa KeyValue. */
export function SpecList({ children }: { children: ReactNode }): JSX.Element {
  return <dl className="ui-spec">{children}</dl>;
}

/* ---------- Stepper ---------- */

export type StepItem = {
  key: string;
  label: ReactNode;
  state: "done" | "current" | "pending" | "blocked";
};

/** Fases del flujo — el paso actual es el único marcado; los bloqueados
 * explican por qué no se puede avanzar. */
export function Stepper({
  steps,
  onStep,
}: {
  steps: StepItem[];
  onStep?: (key: string) => void;
}): JSX.Element {
  return (
    <ol className="ui-stepper">
      {steps.map((step, index) => (
        <li
          aria-current={step.state === "current" ? "step" : undefined}
          className={`ui-stepper__item is-${step.state}`}
          key={step.key}
        >
          <button
            className="ui-stepper__step"
            disabled={!onStep || step.state === "blocked"}
            onClick={() => onStep?.(step.key)}
            type="button"
          >
            <span aria-hidden className="ui-stepper__index">
              {index + 1}
            </span>
            <span className="ui-stepper__label">{step.label}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}

/* ---------- Stat ---------- */

/** Stat — una cifra que existe SOLO porque alguien la decidió mostrar:
 * `decision` es el nombre del documento/nota que justifica la métrica.
 * Sin decisión el componente no renderiza (dev-warn incluida) — los KPI
 * decorativos están prohibidos. */
export function Stat({
  label,
  value,
  detail,
  decision,
}: {
  label: ReactNode;
  value: ReactNode;
  /** Contexto breve — «sobre 12 proyectos», «período actual». */
  detail?: ReactNode;
  /** Referencia a la decisión que autoriza la métrica (doc/decisiones). */
  decision?: string;
}): JSX.Element | null {
  if (!decision) {
    if (import.meta.env.DEV) {
      console.warn("[Stat] render rechazado — falta `decision` que justifique la métrica.");
    }
    return null;
  }
  return (
    <figure className="ui-stat" data-decision={decision}>
      <figcaption className="ui-stat__label">{label}</figcaption>
      <div className="ui-stat__value">{value}</div>
      {detail ? <div className="ui-stat__detail">{detail}</div> : null}
    </figure>
  );
}

/* ---------- Inspector ---------- */

/** Riel de inspección 300–320 px — contenido según selección, lo más usado
 * primero, «Avanzado» plegado al final. */
export function Inspector({
  title,
  children,
  footer,
  collapsed,
  onCollapse,
}: {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  collapsed?: boolean;
  onCollapse?: (collapsed: boolean) => void;
}): JSX.Element {
  const bodyId = useId();
  return (
    <aside className={`ui-inspector${collapsed ? " is-collapsed" : ""}`}>
      <header className="ui-inspector__head">
        <h2 className="ui-inspector__title">{title}</h2>
        {onCollapse ? (
          <button
            aria-controls={bodyId}
            aria-expanded={!collapsed}
            className="ui-inspector__toggle"
            onClick={() => onCollapse(!collapsed)}
            type="button"
          >
            {collapsed ? "‹" : "›"}
          </button>
        ) : null}
      </header>
      {collapsed ? null : (
        <>
          <div className="ui-inspector__body" id={bodyId}>
            {children}
          </div>
          {footer ? <footer className="ui-inspector__foot">{footer}</footer> : null}
        </>
      )}
    </aside>
  );
}

/** Grupo plegable dentro del inspector — «Avanzado» es el caso típico:
 * comienza cerrado y muestra su etiqueta técnica aunque el contenido
 * quede oculto. */
export function InspectorGroup({
  title,
  defaultOpen = true,
  children,
}: {
  title: ReactNode;
  defaultOpen?: boolean;
  children: ReactNode;
}): JSX.Element {
  return (
    <details className="ui-inspector-group" open={defaultOpen}>
      <summary className="ui-inspector-group__title">{title}</summary>
      <div className="ui-inspector-group__body">{children}</div>
    </details>
  );
}

/** Atajo semántico para el grupo «Avanzado» del inspector. */
export function AdvancedGroup({ children }: { children: ReactNode }): JSX.Element {
  return (
    <InspectorGroup defaultOpen={false} title={t("ui.advanced")}>
      {children}
    </InspectorGroup>
  );
}
