/** StatusChip — el estado como etiqueta + tono + icono, siempre. El color
 * nunca comunica solo: la etiqueta está en español vía domainLabels y el
 * tono añade icono de forma. */
import { domainLabel } from "../i18n/domainLabels";
import { Icon, type IconName } from "./icons";

const TONE_TO_BADGE: Record<string, string> = {
  ok: "success",
  warn: "warning",
  danger: "danger",
  info: "info",
  person: "blocked",
  neutral: "neutral",
  unknown: "unknown",
};

/** Chip de estado ligado al enum — `enumName` es el nombre del export
 * orval («ProjectResponseStatusEnum») y `value` el token del API. Si el
 * valor no está etiquetado cae en tono desconocido y el test de
 * exhaustividad lo atrapa antes de producción. */
export function StatusChip({
  enumName,
  value,
  /** Etiqueta ya resuelta — para valores compuestos que no vienen de un
   * enum orval directo. */
  label,
  tone,
}: {
  enumName?: string;
  value: string | null | undefined;
  label?: string;
  tone?: string;
}): JSX.Element {
  const resolved =
    enumName && value
      ? domainLabel(enumName, value)
      : { label: label ?? value ?? "—", tone: (tone ?? "neutral") as "neutral" };
  const badge = TONE_TO_BADGE[resolved.tone] ?? "neutral";
  const iconName = "icon" in resolved ? (resolved.icon as IconName | undefined) : undefined;
  return (
    <span className={`ui-badge ui-chip ui-badge--${badge}`}>
      {iconName ? (
        <Icon aria-hidden className="ui-chip__icon" name={iconName} />
      ) : (
        <span aria-hidden className="ui-badge__dot" />
      )}
      {resolved.label}
    </span>
  );
}
