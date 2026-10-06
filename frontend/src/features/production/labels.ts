import { shortTechnicalId } from "../../format";
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

/** Op label that never oversells authority: a feature declared only as a
 * mounting point reads "referencia de montaje", not an executable prep. */
export function opLabel(op: {
  kind?: string | null;
  detail?: Record<string, unknown> | null;
}): string {
  if (op?.detail?.feature === "point_prep") return t("production.opMountingRef");
  return opKindLabel(op?.kind);
}

// Mirrors _STEP_CONSUMED_KINDS in backend/production/service.py — which stock
// kinds a station physically consumes. A consuming step cannot START until the
// order carries a usable cut plan (backend also enforces it).
export const STEP_STOCK_KINDS: Record<string, string[]> = {
  CUT: ["BAR", "SHEET"],
  ASSEMBLE: ["HARDWARE_KIT", "FITTING"],
  HARDWARE: ["HARDWARE_KIT", "FITTING"],
  GLAZE: ["PANEL"],
};

const STOCK_KINDS: ReadonlySet<string> = new Set([
  "BAR",
  "SHEET",
  "KIT",
  "HARDWARE_KIT",
  "FITTING",
  "PANEL",
  "OFFCUT",
  "REMNANT",
]);

export function stockKindLabel(kind: string | null | undefined): string {
  if (kind === null || kind === undefined || kind === "") return "—";
  return STOCK_KINDS.has(kind)
    ? t(`production.stockKindValue.${kind}` as Parameters<typeof t>[0])
    : kind;
}

/** Ledger notes carry machine references (wo-reserve:KIND, wo-consume…) —
 * render them as readable Spanish; the raw value stays in the cell title. */
export function traceNoteLabel(note: string | null | undefined): string {
  if (note === null || note === undefined || note === "") return "—";
  const prefixed = /^wo-(reserve|recheck):(.+)$/.exec(note);
  if (prefixed) {
    const kind = prefixed[2]!;
    const kindLabel = STOCK_KINDS.has(kind)
      ? t(`production.stockKindValue.${kind}` as Parameters<typeof t>[0])
      : kind;
    const action =
      prefixed[1] === "reserve"
        ? t("production.traceNoteWoReserve")
        : t("production.traceNoteWoRecheck");
    return `${action} ${kindLabel}`;
  }
  if (note === "wo-consume") return t("production.traceNoteWoConsume");
  if (note === "wo-replan-release") return t("production.traceNoteWoReplanRelease");
  return note;
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

/** Los perfiles de proceso citan a menudo el CÓDIGO del centro de trabajo
 * sembrado (CUT_SAW, ASSEMBLY_BENCH…) en lugar del código de estación —
 * el lector ve el nombre de la estación canónica en ambos casos. */
const STATION_ALIASES: Record<string, string> = {
  CUT_SAW: "CUT",
  MACHINING_CELL: "MACHINING",
  CRIMPING_MACHINE: "CRIMP",
  CLEANING_STATION: "CLEAN",
  ASSEMBLY_BENCH: "ASSEMBLE",
  SASH_ASSEMBLY_BENCH: "SASH_ASSEMBLE",
  HARDWARE_BENCH: "HARDWARE",
  GLAZING_BENCH: "GLAZE",
  QC_STATION: "QC",
  PACK_STATION: "PACK",
  WELDER: "WELD",
};

export function stationCodeLabel(code: string | null | undefined): string {
  if (code === null || code === undefined || code === "") return "—";
  const resolved = STATION_ALIASES[code] ?? code;
  return STATION_CODES.has(resolved)
    ? t(`production.station.${resolved}` as Parameters<typeof t>[0])
    : code;
}

// Stations that physically work the sealed cut plan — mirrors
// _PLAN_REQUIRED_STATIONS / _OPS_EVIDENCE_STATIONS in
// backend/production/service.py: they can't start on a dead plan and must
// declare every routed member op at COMPLETE.
export const PLAN_REQUIRED_CODES: ReadonlySet<string> = new Set([
  "MACHINING",
  "PROFILE_CUT",
  "REINFORCEMENT_CUT",
]);

// Member-local vocabulary — mirrors the machining pack's operator language
// (backend/production/pack.py): the printed sheet and the screen name the
// same datum identically, so a stick reconciles paper↔web without a map.
const OP_REFERENCES: ReadonlyMap<string, string> = new Map([
  ["member_start", "Ext. A"],
  ["member_end", "Ext. B"],
  ["bar_left_edge", "borde barra"],
  ["sheet_top_left", "esquina lámina"],
]);

export function opReferenceLabel(reference: string | null | undefined): string {
  if (reference === null || reference === undefined || reference === "") return "—";
  return OP_REFERENCES.get(reference) ?? reference;
}

const OP_FACES: ReadonlyMap<string, string> = new Map([
  ["OUTSIDE_FACE", "cara exterior"],
  ["INSIDE_FACE", "cara interior"],
  ["TOP_EDGE", "canto superior"],
  ["BOTTOM_EDGE", "canto inferior"],
  ["START_EDGE", "canto Ext. A"],
  ["END_EDGE", "canto Ext. B"],
]);

export function opFaceLabel(face: string | null | undefined): string {
  if (face === null || face === undefined || face === "") return "—";
  return OP_FACES.get(face) ?? face;
}

const OP_BASES: ReadonlyMap<string, string> = new Map([
  ["cut_plan.head_trim", "Plan de corte"],
  ["cut_plan.placement", "Plan de corte"],
  ["cut_plan.tail_trim", "Plan de corte"],
  ["member_end_overlap", "Solape de extremo"],
]);

export function opBasisLabel(basis: string | null | undefined): string {
  if (basis === null || basis === undefined || basis === "") return "—";
  const mapped = OP_BASES.get(basis);
  if (mapped) return mapped;
  if (basis.startsWith("handle_requirement_policy:")) {
    return `Política herraje ${basis.split(":", 2)[1] ?? ""}`;
  }
  if (basis.startsWith("handle_policy:")) {
    return `Herraje ${shortTechnicalId(basis.split(":", 2)[1] ?? "")}`;
  }
  return basis;
}

const OP_BOUNDARIES: ReadonlyMap<string, string> = new Map([
  ["HEAD_TRIM", "corte inicial"],
  ["TAIL_TRIM", "corte final"],
]);

export function opBoundaryLabel(boundary: string | null | undefined): string {
  if (boundary === null || boundary === undefined || boundary === "") return "—";
  return OP_BOUNDARIES.get(boundary) ?? boundary;
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
