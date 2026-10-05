/** Formateadores de dominio §3.3 — componentes + funciones de cadena.
 *
 * Reglas inviolables:
 * - Un nulo jamás se pinta como número: cae en <UnknownValue>.
 * - Las medidas agrupan con espacio fino (U+2009) y llevan la unidad en
 *   minúscula al 85 % del tamaño, en g-500.
 * - El dinero sigue la convención del documento (es-CL, CLP entero).
 * - Las cifras de medida van en Plex Mono — los números son datos, no texto.
 */
import { type ReactNode, useState } from "react";

import {
  formatAreaM2,
  formatDate,
  formatDateTime,
  formatDims,
  formatLengthMm,
  formatMoney,
  formatPercent,
  formatQty,
  formatRelativeTime,
  formatUvalue,
  formatWeightKg,
} from "../format";
import { t } from "../i18n/es-CL";
import { UnknownValue } from "./States";

type NullableValue = string | number | null | undefined;

type FormatProps = {
  value: NullableValue;
  /** Causa del valor faltante — se muestra bajo «Sin dato». */
  missingCause?: ReactNode;
  /** Acción para completar el dato — texto del enlace. */
  missingAction?: ReactNode;
  onMissingAction?: () => void;
};

function Unit({ children }: { children: ReactNode }): JSX.Element {
  return <span className="fmt-unit">{children}</span>;
}

function Num({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}): JSX.Element {
  return <span className={`fmt-num ${className}`.trim()}>{children}</span>;
}

/** Dinero — "$1.435.471" CLP, "US$1.435,47", "UF 12,3456". */
export function Money({
  value,
  currency = "CLP",
  missingCause,
  missingAction,
  onMissingAction,
}: FormatProps & { currency?: string }): JSX.Element {
  if (value === null || value === undefined || value === "") {
    return <UnknownValue cause={missingCause} action={missingAction} onAction={onMissingAction} />;
  }
  return <Num>{formatMoney(value, currency)}</Num>;
}

/** Par ancho×alto — "2 400 × 1 800 mm". */
export function Dims({
  width,
  height,
  missingCause,
  missingAction,
  onMissingAction,
}: {
  width: NullableValue;
  height: NullableValue;
} & Omit<FormatProps, "value">): JSX.Element {
  const text = formatDims(width, height);
  if (text === "—") {
    return <UnknownValue cause={missingCause} action={missingAction} onAction={onMissingAction} />;
  }
  return (
    <Num>
      {text} <Unit>mm</Unit>
    </Num>
  );
}

/** Longitud en milímetros — "2 400 mm". */
export function Length(props: FormatProps): JSX.Element {
  const text = formatLengthMm(props.value);
  if (text === "—") {
    return (
      <UnknownValue
        cause={props.missingCause}
        action={props.missingAction}
        onAction={props.onMissingAction}
      />
    );
  }
  return (
    <Num>
      {text} <Unit>mm</Unit>
    </Num>
  );
}

/** Área — "4,32 m²". */
export function Area(props: FormatProps): JSX.Element {
  const text = formatAreaM2(props.value);
  if (text === "—") {
    return (
      <UnknownValue
        cause={props.missingCause}
        action={props.missingAction}
        onAction={props.onMissingAction}
      />
    );
  }
  return (
    <Num>
      {text} <Unit>m²</Unit>
    </Num>
  );
}

/** Peso — "12,3 kg". */
export function Weight(props: FormatProps): JSX.Element {
  const text = formatWeightKg(props.value);
  if (text === "—") {
    return (
      <UnknownValue
        cause={props.missingCause}
        action={props.missingAction}
        onAction={props.onMissingAction}
      />
    );
  }
  return (
    <Num>
      {text} <Unit>kg</Unit>
    </Num>
  );
}

/** Transmitancia — "1,40 W/m²·K". */
export function Uvalue(props: FormatProps): JSX.Element {
  const text = formatUvalue(props.value);
  if (text === "—") {
    return (
      <UnknownValue
        cause={props.missingCause}
        action={props.missingAction}
        onAction={props.onMissingAction}
      />
    );
  }
  return (
    <Num>
      {text} <Unit>W/m²·K</Unit>
    </Num>
  );
}

/** Cantidad entera — "12", "1 240". */
export function Qty(props: FormatProps & { unit?: ReactNode }): JSX.Element {
  const text = formatQty(props.value);
  if (text === "—") {
    return (
      <UnknownValue
        cause={props.missingCause}
        action={props.missingAction}
        onAction={props.onMissingAction}
      />
    );
  }
  return (
    <Num>
      {text}
      {props.unit ? (
        <>
          {" "}
          <Unit>{props.unit}</Unit>
        </>
      ) : null}
    </Num>
  );
}

/** Porcentaje — "93,5 %". `kind`: "fraction" (0–1 del motor) | "points". */
export function Percent(props: FormatProps & { kind?: "fraction" | "points" }): JSX.Element {
  const text = formatPercent(props.value, props.kind);
  if (text === "—") {
    return (
      <UnknownValue
        cause={props.missingCause}
        action={props.missingAction}
        onAction={props.onMissingAction}
      />
    );
  }
  return <Num>{text}</Num>;
}

/** Código de entidad — Plex Mono, clic para copiar con plan B de portapapeles. */
export function EntityCode({
  value,
  missingCause,
  missingAction,
  onMissingAction,
}: FormatProps): JSX.Element {
  const [copied, setCopied] = useState(false);
  if (value === null || value === undefined || value === "") {
    return <UnknownValue cause={missingCause} action={missingAction} onAction={onMissingAction} />;
  }
  const code = String(value);
  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(code);
    } catch {
      // Navegadores sin API de portapapeles: área de texto oculta.
      const helper = document.createElement("textarea");
      helper.value = code;
      helper.style.position = "fixed";
      helper.style.opacity = "0";
      document.body.appendChild(helper);
      helper.select();
      document.execCommand("copy");
      helper.remove();
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  return (
    <button type="button" className="fmt-code" onClick={copy} title={t("ui.copyCode")}>
      <Num>{code}</Num>
      <span className="fmt-code-hint">{copied ? t("ui.copied") : t("ui.copyCode")}</span>
    </button>
  );
}

/** Marca de tiempo — relativa ("hace 5 min") con la absoluta en el tooltip,
 * siempre en America/Santiago. */
export function Timestamp({
  value,
  missingCause,
  missingAction,
  onMissingAction,
}: FormatProps): JSX.Element {
  if (value === null || value === undefined || value === "") {
    return <UnknownValue cause={missingCause} action={missingAction} onAction={onMissingAction} />;
  }
  const stamp = new Date(value);
  if (Number.isNaN(stamp.getTime())) {
    return <Num>{value}</Num>;
  }
  return (
    <time dateTime={stamp.toISOString()} title={formatDateTime(value)}>
      {formatRelativeTime(value)}
    </time>
  );
}

/** Fecha sola — "05-10-2026" America/Santiago. */
export function DateOnly({
  value,
  missingCause,
  missingAction,
  onMissingAction,
}: FormatProps): JSX.Element {
  const text = formatDate(value);
  if (value === null || value === undefined || value === "") {
    return <UnknownValue cause={missingCause} action={missingAction} onAction={onMissingAction} />;
  }
  return <Num>{text}</Num>;
}
