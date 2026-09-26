import { t } from "../../i18n/es-CL";

export function cutRoleLabel(role: string | null | undefined): string {
  if (role === null || role === undefined || role === "") return "—";
  const known: ReadonlySet<string> = new Set([
    "FRAME",
    "SASH",
    "MULLION_V",
    "MULLION_H",
    "INVERSOR",
    "GLAZING_BEAD",
    "COUPLER",
    "ADDITIONAL",
    "THRESHOLD",
    "CHANNEL",
    "REINFORCEMENT",
  ]);
  return known.has(role) ? t(`production.role.${role}` as Parameters<typeof t>[0]) : role;
}

const OP_KINDS: ReadonlySet<string> = new Set([
  "SAW_CUT",
  "DRILL",
  "SLOT",
  "DRAINAGE",
  "VENTILATION",
  "HANDLE_PREP",
  "LOCK_PREP",
  "HINGE_PREP",
  "CORNER_CONNECTOR",
  "T_CONNECTOR",
  "MILLING",
  "END_MACHINING",
  "ROUTING",
  "GASKET_MARK",
  "CUSTOM",
]);

export function opKindLabel(kind: string | null | undefined): string {
  if (kind === null || kind === undefined || kind === "") return "—";
  return OP_KINDS.has(kind) ? t(`production.opKind.${kind}` as Parameters<typeof t>[0]) : kind;
}

const STOCK_KINDS: ReadonlySet<string> = new Set([
  "BAR",
  "SHEET",
  "KIT",
  "FITTING",
  "OFFCUT",
  "REMNANT",
]);

export function stockKindLabel(kind: string | null | undefined): string {
  if (kind === null || kind === undefined || kind === "") return "—";
  return STOCK_KINDS.has(kind)
    ? t(`production.stockKindValue.${kind}` as Parameters<typeof t>[0])
    : kind;
}

const CENTER_KINDS: ReadonlySet<string> = new Set([
  "CUT",
  "PROFILE_CUT",
  "REINFORCEMENT_CUT",
  "MACHINING",
  "WELDING",
  "CRIMP",
  "CRIMPING",
  "CLEANING",
  "ASSEMBLY",
  "SASH_ASSEMBLY",
  "HARDWARE",
  "GLAZING",
  "QC",
  "PACK",
]);

export function centerKindLabel(kind: string | null | undefined): string {
  if (kind === null || kind === undefined || kind === "") return "—";
  return CENTER_KINDS.has(kind)
    ? t(`production.centerKind.${kind}` as Parameters<typeof t>[0])
    : kind;
}

const STATION_CODES: ReadonlySet<string> = new Set([
  "CUT",
  "PROFILE_CUT",
  "REINFORCEMENT_CUT",
  "MACHINING",
  "WELD",
  "CLEAN",
  "CRIMP",
  "SASH_ASSEMBLE",
  "ASSEMBLE",
  "HARDWARE",
  "GLAZE",
  "QC",
  "PACK",
  "INSTALL",
  "DISPATCH",
]);

export function stationCodeLabel(code: string | null | undefined): string {
  if (code === null || code === undefined || code === "") return "—";
  return STATION_CODES.has(code)
    ? t(`production.station.${code}` as Parameters<typeof t>[0])
    : code;
}

const REMNANT_STATUSES: ReadonlySet<string> = new Set([
  "AVAILABLE",
  "RESERVED",
  "CONSUMED",
  "SCRAPPED",
]);

export function remnantStatusLabel(status: string | null | undefined): string {
  if (status === null || status === undefined || status === "") return "—";
  return REMNANT_STATUSES.has(status)
    ? t(`production.remnantStatus.${status}` as Parameters<typeof t>[0])
    : status;
}
