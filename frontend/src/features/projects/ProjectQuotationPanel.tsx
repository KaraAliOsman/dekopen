import { fmtMm } from "../../format";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError } from "../../api/apiMutator";
import {
  documentaryArtifactAccess,
  documentaryFreezeRevisionA,
  documentaryListArtifacts,
  documentaryPrepareInputs,
  documentarySaveInputs,
  productionRelease,
  projectQuoteApproveInternal,
  projectQuoteLinkCreate,
  projectQuoteLinkRevoke,
  projectQuoteLinksList,
  projectsStartSuccessor,
  projectsResetPricing,
} from "../../api/generated/dekopen";
import type {
  AccessoryLine,
  AccessorySchedule,
  ApprovalRecord,
  CoverageEnum,
  PolishingEdges,
  DocumentaryPolicyOption,
  DocumentaryPreparationPosition,
  DocumentaryPreparationResponse,
  DocumentaryStructuralInput,
  HandleIntent,
  HandleRequirement,
  ObligationKindEnum,
  OrderTypeEnum,
  ProjectResponse,
  WorkshopAnnotation,
  WorkshopGlassTarget,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { formatDateTime, formatRevision } from "../../format";
import {
  addDecimal,
  compareDecimal,
  formatDecimal,
  midpointDecimal,
  parseDecimal,
  subtractDecimal,
} from "./decimal";
import { runJob } from "../jobs/runJob";
import { useConfirm, usePrompt } from "../../ui";

function requirementsFor(position: DocumentaryPreparationPosition): HandleRequirement[] {
  const group = position.handle_requirements.find(
    (entry) => entry.policy_id === position.handle_requirement_policy_id,
  );
  return group?.requirements ?? [];
}

function intentFor(
  position: DocumentaryPreparationPosition,
  requirement: HandleRequirement,
): HandleIntent | undefined {
  return position.handle_intents.find(
    (intent) =>
      intent.bay_id === requirement.bay_id &&
      (intent.leaf_id ?? null) === requirement.leaf_id &&
      intent.handle_domain_slot === requirement.handle_domain_slot,
  );
}

function intentKey(requirement: HandleRequirement): string {
  return `${requirement.bay_id}|${requirement.leaf_id ?? ""}|${requirement.handle_domain_slot}`;
}

const REFERENCE_KEYS = {
  OUTER_TOP: "quotation.refOuterTop",
  OUTER_BOTTOM: "quotation.refOuterBottom",
  LEAF_TOP: "quotation.refLeafTop",
  LEAF_BOTTOM: "quotation.refLeafBottom",
} as const;

const EDGE_KEYS = {
  top: "quotation.edgeTop",
  right: "quotation.edgeRight",
  bottom: "quotation.edgeBottom",
  left: "quotation.edgeLeft",
} as const;

const OBLIGATION_KINDS = [
  "SEALING",
  "FASTENING",
  "DRAINAGE",
  "INSTALLATION_ACCESSORY",
  "OTHER_DECLARED",
] as const;

const OBLIGATION_KIND_KEYS: Record<(typeof OBLIGATION_KINDS)[number], TranslationKey> = {
  SEALING: "quotation.kindSealing",
  FASTENING: "quotation.kindFastening",
  DRAINAGE: "quotation.kindDrainage",
  INSTALLATION_ACCESSORY: "quotation.kindInstallation",
  OTHER_DECLARED: "quotation.kindOther",
};

const ORDER_TYPES = [
  "SUPPLIER_PROFILE_PO",
  "SUPPLIER_GLASS_PO",
  "SUPPLIER_HARDWARE_PO",
  "SUPPLIER_PANEL_PO",
] as const;

const ORDER_TYPE_KEYS: Record<(typeof ORDER_TYPES)[number], TranslationKey> = {
  SUPPLIER_PROFILE_PO: "quotation.orderProfile",
  SUPPLIER_GLASS_PO: "quotation.orderGlass",
  SUPPLIER_HARDWARE_PO: "quotation.orderHardware",
  SUPPLIER_PANEL_PO: "quotation.orderPanel",
};

const EMPTY_EDGES: PolishingEdges = { top: false, right: false, bottom: false, left: false };

const approvalStatusKeys: Record<ApprovalRecord["status"], TranslationKey> = {
  PENDING: "quotation.linkPending",
  APPROVED: "quotation.linkApproved",
  DECLINED: "quotation.linkDeclined",
  REVOKED: "quotation.linkRevoked",
};

/** One inspector rule that blocked the freeze, from the 422's
 * `error.inspector_failures` extra (review WB2). */
interface InspectorFailure {
  rule: string;
  severity: string;
  title: string;
  diagnosis: string;
  recommendation: string;
  module_id: string | null;
  bay_id: string | null;
  leaf_id: string | null;
}

function readInspectorFailures(payload: unknown): InspectorFailure[] {
  if (typeof payload !== "object" || payload === null) return [];
  const error = (payload as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return [];
  const failures = (error as { inspector_failures?: unknown }).inspector_failures;
  if (!Array.isArray(failures)) return [];
  return failures.filter(
    (item): item is InspectorFailure =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as InspectorFailure).rule === "string" &&
      typeof (item as InspectorFailure).title === "string",
  );
}

/** The server's human detail ("Vano 3 · Dormitorio: no hay precio…") beats
 * the generic toast copy whenever the API supplies one. Plain DRF 400s have
 * no contract envelope — dig out the first field error with its field name
 * so a rejected Emitir names what to fix instead of the generic toast. */
function apiDetail(payload: unknown): string | null {
  if (typeof payload !== "object" || payload === null) return null;
  const error = (payload as { error?: unknown }).error;
  const detail =
    typeof error === "object" && error !== null ? (error as { detail?: unknown }).detail : null;
  if (typeof detail === "string" && detail.trim()) return detail;

  const fieldError = (node: unknown, path: string): string | null => {
    if (typeof node === "string" && node.trim()) return path ? `${path}: ${node}` : node;
    if (Array.isArray(node)) {
      for (const item of node) {
        const hit = fieldError(item, path);
        if (hit) return hit;
      }
      return null;
    }
    if (typeof node === "object" && node !== null) {
      for (const [key, value] of Object.entries(node)) {
        const hit = fieldError(value, path ? `${path}.${key}` : key);
        if (hit) return hit;
      }
    }
    return null;
  };
  return fieldError(payload, "");
}

function GlassPolishingRow({
  target,
  record,
  disabled,
  onEdges,
}: {
  target: WorkshopGlassTarget;
  record: { edges: PolishingEdges } | undefined;
  disabled: boolean;
  onEdges(edges: PolishingEdges): void;
}): JSX.Element {
  const polished = record ? Object.values(record.edges).some(Boolean) : false;
  const [expanded, setExpanded] = useState(polished);
  const showEdges = expanded || polished;
  const value = showEdges ? "EDGES" : record ? "NONE" : "";
  return (
    <div className="workshop-target">
      <strong>{target.label}</strong>
      <div className="workshop-row">
        <label className="workshop-field">
          <span>{t("quotation.polishedEdges")}</span>
          <select
            disabled={disabled}
            value={value}
            onChange={(event) => {
              const next = event.target.value;
              if (next === "NONE") {
                setExpanded(false);
                onEdges(EMPTY_EDGES);
              } else if (next === "EDGES") {
                setExpanded(true);
              }
            }}
          >
            <option value="">{t("quotation.chooseCoverage")}</option>
            <option value="NONE">{t("quotation.polishNone")}</option>
            <option value="EDGES">{t("quotation.polishEdges")}</option>
          </select>
        </label>
        {!record && <span className="handle-pending">{t("quotation.handlePending")}</span>}
        {showEdges &&
          (["top", "right", "bottom", "left"] as const).map((edge) => (
            <label className="workshop-check" key={edge}>
              <input
                type="checkbox"
                disabled={disabled}
                checked={record?.edges[edge] ?? false}
                onChange={(event) =>
                  onEdges({
                    ...(record?.edges ?? EMPTY_EDGES),
                    [edge]: event.target.checked,
                  })
                }
              />
              {t(EDGE_KEYS[edge])}
            </label>
          ))}
      </div>
    </div>
  );
}

function nextObligationId(items: AccessoryLine[]): string {
  const used = new Set(items.map((item) => item.obligation_id));
  let index = items.length + 1;
  while (used.has(`acc-${index}`)) index += 1;
  return `acc-${index}`;
}

function parseMmList(text: string): string[] | null {
  const parts = text
    .split(/[,;]+/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length === 0) return [];
  if (!parts.every((part) => /^\d+(?:\.\d{1,4})?$/.test(part))) return null;
  return parts;
}

function CsvMmField({
  id,
  label,
  values,
  disabled,
  onCommit,
}: {
  id: string;
  label: string;
  values: string[] | null | undefined;
  disabled: boolean;
  onCommit(value: string[] | null): void;
}): JSX.Element {
  const canonical = (values ?? []).map(fmtMm).join(", ");
  const [draft, setDraft] = useState(canonical);
  useEffect(() => setDraft(canonical), [canonical]);
  return (
    <label className="workshop-field">
      <span>{label}</span>
      <input
        id={id}
        value={draft}
        disabled={disabled}
        inputMode="decimal"
        placeholder="300, 600"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => {
          const parsed = parseMmList(draft);
          if (parsed === null) {
            setDraft(canonical);
          } else if (parsed.join(",") !== (values ?? []).map(fmtMm).join(",")) {
            onCommit(parsed.length > 0 ? parsed : null);
          }
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") event.currentTarget.blur();
          if (event.key === "Escape") setDraft(canonical);
        }}
      />
      <span className="workshop-unit">mm</span>
    </label>
  );
}

/** Stored decimals arrive as "300.0000" — the workshop inputs are edited by
 * people, so display strings normalize to business precision once at load
 * (fmtMm trims trailing zeros; the field stays editable). */
function normalizePreparationMm(
  position: DocumentaryPreparationPosition,
): DocumentaryPreparationPosition {
  const annotations = position.workshop_annotations.map((annotation) => ({
    ...annotation,
    bottom_drain_holes_mm: annotation.bottom_drain_holes_mm?.map(fmtMm) ?? null,
    closing_points_perimeter_mm: annotation.closing_points_perimeter_mm?.map(fmtMm) ?? null,
    continuous_width_mm:
      annotation.continuous_width_mm == null ? null : fmtMm(annotation.continuous_width_mm),
  }));
  const structural = position.structural_inputs.map((input) => ({
    ...input,
    required_ix_cm4: input.required_ix_cm4 == null ? null : fmtMm(input.required_ix_cm4),
  }));
  const intents = position.handle_intents.map((intent) => ({
    ...intent,
    requested_height_mm: intent.requested_height_mm === "" ? "" : fmtMm(intent.requested_height_mm),
  }));
  return {
    ...position,
    workshop_annotations: annotations,
    structural_inputs: structural,
    handle_intents: intents,
  };
}

/** Valid input range for the entered height under its vertical reference.
 * The policy bounds describe the final handle coordinate measured from the
 * leaf's top edge; the engine converts each reference into that coordinate
 * before comparing, so the input's own range depends on the reference.
 * All math stays in exact decimals — binary floats would reject boundary
 * entries the engine accepts. */
function heightBounds(
  position: DocumentaryPreparationPosition,
  requirement: HandleRequirement,
  reference: HandleIntent["vertical_reference"],
): [string, string] | null {
  const rect = requirement.leaf_rects.find(
    (entry) => entry.placement_policy_id === position.manufacturing_placement_policy_id,
  );
  const min = parseDecimal(requirement.mounting_min_from_leaf_top_mm);
  const max = parseDecimal(requirement.mounting_max_from_leaf_top_mm);
  const leafTop = rect ? parseDecimal(rect.leaf_top_from_outer_top_mm) : null;
  const leafHeight = rect ? parseDecimal(rect.leaf_height_mm) : null;
  const outerHeight = parseDecimal(requirement.outer_height_mm);
  if (!min || !max || !leafTop || !leafHeight || !outerHeight) return null;
  switch (reference) {
    case "LEAF_TOP":
      return [formatDecimal(min), formatDecimal(max)];
    case "LEAF_BOTTOM":
      return [
        formatDecimal(subtractDecimal(leafHeight, max)),
        formatDecimal(subtractDecimal(leafHeight, min)),
      ];
    case "OUTER_TOP":
      return [formatDecimal(addDecimal(leafTop, min)), formatDecimal(addDecimal(leafTop, max))];
    case "OUTER_BOTTOM":
      return [
        formatDecimal(subtractDecimal(subtractDecimal(outerHeight, leafTop), max)),
        formatDecimal(subtractDecimal(subtractDecimal(outerHeight, leafTop), min)),
      ];
  }
}

/** Dropping or switching the handle policy must not leave intents whose
 * (bay, leaf, slot) no longer exists — freeze rejects extra intents — and a
 * retained intent's reference must still be permitted by the new rule. */
function reconciledHandlePolicy(
  position: DocumentaryPreparationPosition,
  policyId: string,
  previouslySeeded: ReadonlySet<string>,
): { update: Partial<DocumentaryPreparationPosition>; seededKeys: string[] } {
  const requirements = position.handle_requirements.find(
    (entry) => entry.policy_id === policyId,
  )?.requirements;
  if (!requirements) return { update: { handle_requirement_policy_id: policyId }, seededKeys: [] };
  const byKey = new Map(requirements.map((requirement) => [intentKey(requirement), requirement]));
  const intents = position.handle_intents.flatMap((intent) => {
    const requirement = byKey.get(
      `${intent.bay_id}|${intent.leaf_id ?? ""}|${intent.handle_domain_slot}`,
    );
    if (!requirement) return [];
    if (requirement.permitted_vertical_references.includes(intent.vertical_reference))
      return [intent];
    const [fallback] = requirement.permitted_vertical_references;
    return fallback ? [{ ...intent, vertical_reference: fallback }] : [];
  });
  // Carried auto-seeds must not keep the old policy's midpoint: recompute each
  // to the new bounds (or drop when none resolves — the same contract
  // reseedHandleIntents keeps on a placement change). A stale generated
  // default must never ship as if it were chosen.
  const wasSeeded = (intent: {
    bay_id: string;
    leaf_id?: string | null;
    handle_domain_slot: string;
  }) =>
    [...previouslySeeded].some((key) =>
      key.startsWith(`${intent.bay_id}|${intent.leaf_id ?? ""}|${intent.handle_domain_slot}|`),
    );
  const reseated = intents.flatMap((intent) => {
    if (!wasSeeded(intent)) return [intent];
    const requirement = byKey.get(
      `${intent.bay_id}|${intent.leaf_id ?? ""}|${intent.handle_domain_slot}`,
    );
    if (!requirement) return [];
    const bounds = heightBounds(position, requirement, intent.vertical_reference);
    const boundMin = bounds ? parseDecimal(bounds[0]) : null;
    const boundMax = bounds ? parseDecimal(bounds[1]) : null;
    if (boundMin === null || boundMax === null) return [];
    return [
      {
        ...intent,
        requested_height_mm: formatDecimal(midpointDecimal(boundMin, boundMax)),
      },
    ];
  });
  // Requirements only present under the new policy get their seeded intent
  // here too — same displayed-value contract as the initial load.
  const merged = {
    ...position,
    handle_requirement_policy_id: policyId,
    handle_intents: reseated,
  };
  const seeded = seedHandleIntents(merged);
  const carried = reseated.filter(wasSeeded).map(seedKeyForIntent);
  return {
    update: {
      handle_requirement_policy_id: policyId,
      handle_intents: seeded.position.handle_intents,
    },
    seededKeys: [...new Set([...carried, ...seeded.seededKeys])],
  };
}

/** Identity of an intent the app auto-seeded — tracked per position so a
 * placement/policy change recomputes seeded heights while manual entries
 * stay exactly what the estimator typed. */
function seedKeyForIntent(intent: {
  bay_id: string;
  leaf_id?: string | null;
  handle_domain_slot: string;
  vertical_reference: string;
}): string {
  return `${intent.bay_id}|${intent.leaf_id ?? ""}|${intent.handle_domain_slot}|${intent.vertical_reference}`;
}

/** A requirement with no stored intent must not pretend the displayed
 * midpoint is saved: seed it so the visible height IS what Guardar/Emitir
 * persists — the estimator's click stays the confirmation. Requirements
 * whose bounds cannot be resolved keep NO intent at all (a blank height
 * fails the save serializer and would block even quote-only emission);
 * their pending chip still shows until the estimator types a value. */
function seedHandleIntents(position: DocumentaryPreparationPosition): {
  position: DocumentaryPreparationPosition;
  seededKeys: string[];
} {
  const requirements = requirementsFor(position);
  if (requirements.length === 0) return { position, seededKeys: [] };
  const intents = [...position.handle_intents];
  const seededKeys: string[] = [];
  for (const requirement of requirements) {
    if (intentFor(position, requirement)) continue;
    const reference = requirement.permitted_vertical_references[0];
    if (!reference) continue;
    const bounds = heightBounds(position, requirement, reference);
    const boundMin = bounds ? parseDecimal(bounds[0]) : null;
    const boundMax = bounds ? parseDecimal(bounds[1]) : null;
    if (boundMin === null || boundMax === null) continue;
    const intent = {
      bay_id: requirement.bay_id,
      leaf_id: requirement.leaf_id,
      handle_domain_slot: requirement.handle_domain_slot,
      requested_height_mm: formatDecimal(midpointDecimal(boundMin, boundMax)),
      vertical_reference: reference,
    };
    intents.push(intent);
    seededKeys.push(seedKeyForIntent(intent));
  }
  return {
    position: seededKeys.length ? { ...position, handle_intents: intents } : position,
    seededKeys,
  };
}

/** After a placement-policy change the leaf bounds move: auto-seeded
 * midpoints are recomputed (or dropped when no bound resolves — a stale
 * default must not pretend to be saved), while manually entered heights
 * stay exactly what the estimator typed. */
function reseedHandleIntents(
  position: DocumentaryPreparationPosition,
  previouslySeeded: ReadonlySet<string>,
): {
  position: DocumentaryPreparationPosition;
  seededKeys: string[];
} {
  const requirements = requirementsFor(position);
  const byKey = new Map(requirements.map((requirement) => [intentKey(requirement), requirement]));
  const intents = position.handle_intents.flatMap((intent) => {
    if (!previouslySeeded.has(seedKeyForIntent(intent))) return [intent];
    const requirement = byKey.get(
      `${intent.bay_id}|${intent.leaf_id ?? ""}|${intent.handle_domain_slot}`,
    );
    if (
      !requirement ||
      !requirement.permitted_vertical_references.includes(intent.vertical_reference)
    )
      return [];
    const bounds = heightBounds(position, requirement, intent.vertical_reference);
    const boundMin = bounds ? parseDecimal(bounds[0]) : null;
    const boundMax = bounds ? parseDecimal(bounds[1]) : null;
    if (boundMin === null || boundMax === null) return [];
    return [
      {
        ...intent,
        requested_height_mm: formatDecimal(midpointDecimal(boundMin, boundMax)),
      },
    ];
  });
  const seeded = seedHandleIntents({ ...position, handle_intents: intents });
  // The full surviving seeded set: recomputed intents keep their membership
  // (same key), dropped ones leave, fresh seeds join.
  const surviving = new Set(
    seeded.position.handle_intents
      .filter((intent) => previouslySeeded.has(seedKeyForIntent(intent)))
      .map(seedKeyForIntent),
  );
  return {
    position: seeded.position,
    seededKeys: [...surviving, ...seeded.seededKeys],
  };
}

function selectedPolicy(
  options: DocumentaryPolicyOption[],
  value: string | null,
  onChange: (value: string) => void,
  label: string,
  disabled: boolean,
  id: string,
): JSX.Element {
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        required
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{t("quotation.choosePolicy")}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label} · v{option.version}
          </option>
        ))}
      </select>
    </div>
  );
}

function annotationKey(bayId: string, leafId: string | null | undefined): string {
  return `${bayId}|${leafId ?? ""}`;
}

/** Advisory defaults ride a separate channel so the backend never fabricates
 * stored authority. The emit form prefills them as editable values — only what
 * the estimator saves becomes data. Stored rows win per-field. */
function mergePreparationSuggestions(
  position: DocumentaryPreparationResponse["positions"][number],
): DocumentaryPreparationResponse["positions"][number] {
  const pending = new Map(
    (position.workshop_suggestions ?? []).map((suggestion) => [
      annotationKey(suggestion.bay_id, suggestion.leaf_id),
      suggestion,
    ]),
  );
  const annotations = position.workshop_annotations.map((row) => {
    const key = annotationKey(row.bay_id, row.leaf_id);
    const suggestion = pending.get(key);
    if (!suggestion) return row;
    pending.delete(key);
    return {
      ...row,
      bottom_drain_holes_mm: row.bottom_drain_holes_mm ?? suggestion.bottom_drain_holes_mm,
      closing_points_perimeter_mm:
        row.closing_points_perimeter_mm ?? suggestion.closing_points_perimeter_mm,
      continuous_width_mm: row.continuous_width_mm ?? suggestion.continuous_width_mm,
      finish_class: row.finish_class ?? suggestion.finish_class,
      has_coupler: row.has_coupler ?? suggestion.has_coupler,
    };
  });
  const storedPolishing = new Set(
    position.glass_polishing.map((row) => annotationKey(row.bay_id, row.leaf_id)),
  );
  return {
    ...position,
    workshop_annotations: [...annotations, ...pending.values()],
    glass_polishing: [
      ...position.glass_polishing,
      ...(position.polishing_suggestions ?? []).filter(
        (suggestion) => !storedPolishing.has(annotationKey(suggestion.bay_id, suggestion.leaf_id)),
      ),
    ],
  };
}

export function ProjectQuotationPanel({
  project,
  orgId,
  canWrite,
  canRelease = false,
  onChanged,
  onDirtyChange,
}: {
  project: ProjectResponse;
  orgId: string;
  canWrite: boolean;
  /** OWNER/WORKSHOP_MANAGER — releasing a sealed version creates workshop
   * orders, a warehouse-side authority estimators don't hold. */
  canRelease?: boolean;
  onChanged(): Promise<unknown>;
  onDirtyChange?(dirty: boolean): void;
}): JSX.Element {
  const confirm = useConfirm();
  const prompt = usePrompt();
  const queryClient = useQueryClient();
  const [preparation, setPreparation] = useState<DocumentaryPreparationResponse | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [sharedUrl, setSharedUrl] = useState("");
  // Inspector rules that blocked the last freeze attempt — the 422's
  // inspector_failures payload so the estimator sees WHAT failed (WB2).
  const [inspectorFailures, setInspectorFailures] = useState<InspectorFailure[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const generation = useRef(0);
  // Which handle intents the app seeded (vs typed by the estimator) —
  // placement/policy changes recompute only the seeded ones.
  const seededIntentKeys = useRef(new Map<string, Set<string>>());
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  // Emitted document index: opening an existing artifact is one access call,
  // not a generation job — the emit path only runs when the slot is empty.
  const artifactIndex = useQuery({
    queryKey: ["documents", "artifacts", orgId, project.id],
    queryFn: async () => {
      const response = await documentaryListArtifacts(project.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.artifacts;
    },
  });
  // The customer-link ledger — same key the workspace header polls, so one
  // cache feeds both the timeline and the per-link revoke controls here.
  const approvals = useQuery({
    queryKey: ["projects", "quote-approvals", orgId, project.id],
    queryFn: async () => {
      const response = await projectQuoteLinksList(project.id);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
  });
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);

  async function loadPreparation(): Promise<void> {
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await documentaryPrepareInputs(project.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current === current) {
        setPreparation({
          ...response.data,
          positions: response.data.positions.map((position) => {
            const seeded = seedHandleIntents(mergePreparationSuggestions(position));
            seededIntentKeys.current.set(String(position.position_id), new Set(seeded.seededKeys));
            return normalizePreparationMm(seeded.position);
          }),
        });
      }
    } catch {
      if (generation.current === current) setMessage(t("quotation.loadError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  function updatePosition(index: number, update: Partial<DocumentaryPreparationPosition>): void {
    if (!preparation) return;
    setDirty(true);
    setPreparation({
      ...preparation,
      positions: preparation.positions.map((position, positionIndex) =>
        positionIndex === index ? { ...position, ...update } : position,
      ),
    });
  }

  function updateIntent(
    index: number,
    requirement: HandleRequirement,
    patch: Partial<HandleIntent>,
  ): void {
    if (!preparation) return;
    const position = preparation.positions[index];
    if (!position) return;
    const intents = [...position.handle_intents];
    const existing = intentFor(position, requirement);
    if (existing) {
      intents[intents.indexOf(existing)] = { ...existing, ...patch };
    } else {
      const reference = patch.vertical_reference ?? requirement.permitted_vertical_references[0];
      if (!reference) return;
      intents.push({
        bay_id: requirement.bay_id,
        leaf_id: requirement.leaf_id,
        handle_domain_slot: requirement.handle_domain_slot,
        requested_height_mm: patch.requested_height_mm ?? "",
        vertical_reference: reference,
      });
    }
    // A manual edit detaches the slot from reseed: the next placement/policy
    // change must keep the estimator's value, not recompute over it.
    const keys = seededIntentKeys.current.get(String(position.position_id));
    if (existing) {
      keys?.delete(seedKeyForIntent(existing));
    }
    updatePosition(index, { handle_intents: intents });
  }

  function updateAnnotation(
    index: number,
    bayId: string,
    leafId: string | null,
    patch: Partial<WorkshopAnnotation>,
  ): void {
    if (!preparation) return;
    const position = preparation.positions[index];
    if (!position) return;
    const annotations = [...position.workshop_annotations];
    const existing = annotations.find(
      (item) => item.bay_id === bayId && (item.leaf_id ?? null) === leafId,
    );
    if (existing) {
      annotations[annotations.indexOf(existing)] = { ...existing, ...patch };
    } else {
      annotations.push({
        bay_id: bayId,
        leaf_id: leafId,
        finish_class: "WHITE",
        ...patch,
      });
    }
    updatePosition(index, { workshop_annotations: annotations });
  }

  function updateStructural(
    index: number,
    targetId: string,
    patch: Partial<DocumentaryStructuralInput>,
  ): void {
    if (!preparation) return;
    const position = preparation.positions[index];
    if (!position) return;
    const inputs = [...position.structural_inputs];
    const existing = inputs.find((item) => item.target_id === targetId);
    if (existing) {
      inputs[inputs.indexOf(existing)] = { ...existing, ...patch };
    } else {
      inputs.push({ target_id: targetId, ...patch });
    }
    updatePosition(index, { structural_inputs: inputs });
  }

  function setPolishingEdges(
    index: number,
    bayId: string,
    leafId: string | null,
    edges: PolishingEdges,
  ): void {
    if (!preparation) return;
    const position = preparation.positions[index];
    if (!position) return;
    const polishing = [...position.glass_polishing];
    const existing = polishing.find(
      (item) => item.bay_id === bayId && (item.leaf_id ?? null) === leafId,
    );
    if (existing) {
      polishing[polishing.indexOf(existing)] = { ...existing, edges };
    } else {
      polishing.push({ bay_id: bayId, leaf_id: leafId, edges });
    }
    updatePosition(index, { glass_polishing: polishing });
  }

  function updateAccessories(index: number, patch: Partial<AccessorySchedule>): void {
    if (!preparation) return;
    const position = preparation.positions[index];
    if (!position) return;
    const schedule = position.accessory_schedule ?? {
      coverage: "NONE_REQUIRED" as CoverageEnum,
      items: [] as AccessoryLine[],
    };
    updatePosition(index, { accessory_schedule: { ...schedule, ...patch } });
  }

  function updateAccessoryItem(
    index: number,
    itemIndex: number,
    patch: Partial<AccessoryLine> | null,
  ): void {
    const position = preparation?.positions[index];
    if (!position?.accessory_schedule) return;
    const items = [...position.accessory_schedule.items];
    if (patch === null) {
      items.splice(itemIndex, 1);
    } else {
      items[itemIndex] = { ...items[itemIndex]!, ...patch };
    }
    updateAccessories(index, { items });
  }

  async function emit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!preparation || !confirmed) return;
    // A silent early-return reads as a dead button (review PM-C3): name the
    // first missing gate instead of swallowing the click.
    if (!project.current_pricing_operation_id) {
      setMessage(t("quotation.emitNeedsPricing"));
      return;
    }
    if (!preparation.quotation_valid_until) {
      setMessage(t("quotation.emitNeedsValidUntil"));
      return;
    }
    if (preparation.positions.some((position) => !position.location_tag.trim())) {
      setMessage(t("quotation.emitNeedsLocation"));
      return;
    }
    if (
      preparation.positions.some(
        (position) =>
          !position.manufacturing_placement_policy_id ||
          !position.handle_requirement_policy_id ||
          !position.reinforcement_cut_policy_id,
      )
    ) {
      setMessage(t("quotation.emitNeedsPolicies"));
      return;
    }
    // A generated midpoint is a suggestion, not a choice: it can only seal
    // after the estimator accepts it (one click per position) or edits it.
    if (
      preparation.positions.some(
        (position) => (seededIntentKeys.current.get(String(position.position_id))?.size ?? 0) > 0,
      )
    ) {
      setMessage(t("quotation.seedsUnconfirmed"));
      return;
    }
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    try {
      const saved = await documentarySaveInputs(
        project.id,
        {
          payment_terms: preparation.payment_terms,
          quotation_valid_until: preparation.quotation_valid_until,
          positions: preparation.positions.map((position) => ({
            position_id: position.position_id,
            calculation_hash: position.calculation_hash,
            location_tag: position.location_tag,
            manufacturing_placement_policy_id: position.manufacturing_placement_policy_id!,
            handle_requirement_policy_id: position.handle_requirement_policy_id!,
            reinforcement_cut_policy_id: position.reinforcement_cut_policy_id!,
            workshop_annotations: position.workshop_annotations,
            structural_inputs: position.structural_inputs,
            glass_polishing: position.glass_polishing,
            handle_intents: position.handle_intents,
            accessory_schedule: position.accessory_schedule,
            legacy_handle_migration_confirmed: position.legacy_handle_migration_confirmed,
          })),
        },
        requestOptions,
      );
      if (saved.status !== 200) throw new ApiError(saved.status, saved.data);
      const frozen = await documentaryFreezeRevisionA(
        project.id,
        { pricing_operation_id: project.current_pricing_operation_id, confirmed: true },
        requestOptions,
      );
      if (frozen.status !== 200 && frozen.status !== 201)
        throw new ApiError(frozen.status, frozen.data);
      if (generation.current !== current) return;
      setPreparation(null);
      setConfirmed(false);
      setDirty(false);
      setInspectorFailures([]);
      // A new sealed revision rebases the commercial deal — the header
      // stepper's "Saldo" must recompute against THIS revision, not the
      // previously emitted one (review WM5).
      void queryClient.invalidateQueries({
        queryKey: ["projects", "payments-summary", orgId, project.id],
      });
      setMessage(
        `${t("quotation.emitted")} ${formatRevision(frozen.data.revision_code)}${
          frozen.data.production_allowed ? "" : ` · ${t("quotation.quoteOnlyNotice")}`
        }`,
      );
      await onChanged();
    } catch (error) {
      if (generation.current !== current) return;
      setInspectorFailures(error instanceof ApiError ? readInspectorFailures(error.payload) : []);
      setMessage(
        error instanceof ApiError
          ? (apiDetail(error.payload) ??
              t(error.status === 409 ? "quotation.conflict" : "quotation.error"))
          : t("quotation.error"),
      );
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function startSuccessor(): Promise<void> {
    if (!(await confirm({ title: t("quotation.successorConfirm") }))) return;
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectsStartSuccessor(
        project.id,
        { confirmed: true, expected_current_revision: project.current_revision },
        requestOptions,
      );
      if (response.status !== 200 && response.status !== 201) {
        throw new ApiError(response.status, response.data);
      }
      if (generation.current !== current) return;
      setMessage(t("quotation.successorReady"));
      await onChanged();
    } catch {
      if (generation.current === current) setMessage(t("quotation.successorError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function resetPricing(): Promise<void> {
    const reason = await prompt({ title: t("quotation.resetReason"), input: { required: true } });
    if (!reason?.trim() || !project.current_pricing_operation_id) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectsResetPricing(
        project.id,
        {
          expected_operation_id: project.current_pricing_operation_id,
          reason,
          confirmed: true,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setPreparation(null);
      setDirty(false);
      await onChanged();
    } catch {
      setMessage(t("quotation.conflict"));
    } finally {
      setBusy(false);
    }
  }

  /** Liberar a producción — one WORKSHOP_OT per sealed position. The
   * endpoint is idempotent: re-pressing returns the existing orders, so the
   * action can never duplicate work on the floor. */
  async function release(versionId: string): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const response = await productionRelease(versionId, requestOptions);
      if (response.status !== 200 && response.status !== 201) {
        throw new ApiError(response.status, response.data);
      }
      setMessage(
        `${t("quotation.released")} ${String(response.data.released)} ${t("production.orders")}`,
      );
      await onChanged();
    } catch {
      setMessage(t("quotation.releaseError"));
    } finally {
      setBusy(false);
    }
  }

  async function openEvidence(versionId: string, revisionCode: string): Promise<void> {
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    try {
      // An emitted artifact opens straight through access — no generation
      // job, no worker round-trip, nothing for the user to wait on.
      let artifactId = artifactIndex.data?.find(
        (item) =>
          item.project_version_id === versionId &&
          item.document_type === "DOC-01" &&
          item.format === "PDF",
      )?.id;
      if (!artifactId) {
        setMessage(t("quotation.documentGenerating"));
        const job = await runJob(
          {
            type: "document.artifact.generate",
            payload: {
              document_type: "DOC-01",
              format: "PDF",
              project_version_id: versionId,
              order_id: null,
            },
            idempotency_key: `doc01:${versionId}`,
          },
          requestOptions,
        );
        artifactId = (job.result as { artifact: { id: string } }).artifact.id;
        queryClient.invalidateQueries({
          queryKey: ["documents", "artifacts", orgId, project.id],
        });
      }
      const access = await documentaryArtifactAccess(artifactId, requestOptions);
      if (access.status !== 200) {
        throw new ApiError(access.status, access.data);
      }
      if (generation.current === current) {
        const response = await fetch(access.data.signed_url);
        if (!response.ok) throw new ApiError(response.status, {});
        const blob = await response.blob();
        const objectUrl = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = objectUrl;
        anchor.download = `COT-${project.code}-${revisionCode}.pdf`;
        anchor.click();
        URL.revokeObjectURL(objectUrl);
      }
    } catch {
      if (generation.current === current) setMessage(t("quotation.documentError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  const canEmit =
    canWrite &&
    project.status === "DRAFT" &&
    project.pricing_current &&
    project.current_pricing_operation_id !== null;
  // APPROVED stays revisable — the client portal can flip a quote to
  // APPROVED and still request changes; the sealed revision is immutable
  // and the successor just needs a fresh approval (review WM7).
  const canRevise = canWrite && (project.status === "QUOTED" || project.status === "APPROVED");
  const canShare =
    canWrite &&
    (project.status === "QUOTED" || project.status === "APPROVED") &&
    (project.versions?.length ?? 0) > 0;

  async function shareQuote(): Promise<void> {
    const pendingLink = (approvals.data ?? []).find((link) => link.status === "PENDING");
    if (pendingLink) {
      const ok = await confirm({
        title: t("quotation.shareReplacesLink"),
        confirmLabel: t("quotation.share"),
      });
      if (!ok) return;
    }
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    setSharedUrl("");
    try {
      const response = await projectQuoteLinkCreate(project.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      // The header's commercial timeline derives "sent" from the approvals
      // list — refetch so the freshly created link shows immediately.
      void queryClient.invalidateQueries({
        queryKey: ["projects", "quote-approvals", orgId, project.id],
      });
      const url = `${window.location.origin}${response.data.path}`;
      setSharedUrl(url);
      try {
        await navigator.clipboard.writeText(url);
        setMessage(t("quotation.shareCopied"));
      } catch {
        setMessage(t("quotation.shareReady"));
      }
    } catch {
      if (generation.current === current) setMessage(t("quotation.error"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function copySharedUrl(): Promise<void> {
    try {
      await navigator.clipboard.writeText(sharedUrl);
      setMessage(t("quotation.shareCopied"));
    } catch {
      setMessage(sharedUrl);
    }
  }

  async function approveInternally(): Promise<void> {
    const ok = await confirm({
      title: t("quotation.markApprovedConfirm"),
      confirmLabel: t("quotation.markApproved"),
    });
    if (!ok) return;
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectQuoteApproveInternal(project.id, {}, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      void queryClient.invalidateQueries({
        queryKey: ["projects", "quote-approvals", orgId, project.id],
      });
      await onChanged();
      setMessage(t("quotation.markApprovedDone"));
    } catch {
      if (generation.current === current) setMessage(t("quotation.error"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function revokeLink(approvalId: string): Promise<void> {
    const ok = await confirm({
      title: t("quotation.linkRevokeConfirm"),
      confirmLabel: t("quotation.linkRevoke"),
      danger: true,
    });
    if (!ok) return;
    const current = ++generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectQuoteLinkRevoke(project.id, approvalId, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await queryClient.invalidateQueries({
        queryKey: ["projects", "quote-approvals", orgId, project.id],
      });
      setMessage(t("quotation.linkRevokedDone"));
    } catch {
      if (generation.current === current) setMessage(t("quotation.error"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  // Consolidated "what's missing" for emission — the same conditions the
  // submit gate enforces, shown live instead of one native validation bubble
  // at a time. Each item focuses its field.
  const emitMissing: { key: string; label: string; targetId?: string }[] = [];
  if (preparation) {
    if (!project.current_pricing_operation_id) {
      emitMissing.push({ key: "pricing", label: t("quotation.missingPricing") });
    }
    if (!preparation.payment_terms.trim()) {
      emitMissing.push({
        key: "terms",
        label: t("quotation.paymentTerms"),
        targetId: "quotation-payment-terms",
      });
    }
    if (!preparation.quotation_valid_until) {
      emitMissing.push({
        key: "valid",
        label: t("quotation.validUntil"),
        targetId: "quotation-valid-until",
      });
    }
    preparation.positions.forEach((position, index) => {
      const tag = `${t("quotation.position")} ${index + 1}`;
      if (!position.location_tag.trim()) {
        emitMissing.push({
          key: `loc-${position.position_id}`,
          label: `${tag} — ${t("projects.location")}`,
          targetId: `position-location-${position.position_id}`,
        });
      }
      if (!position.manufacturing_placement_policy_id) {
        emitMissing.push({
          key: `pl-${position.position_id}`,
          label: `${tag} — ${t("quotation.placementPolicy")}`,
          targetId: `placement-policy-${position.position_id}`,
        });
      }
      if (!position.handle_requirement_policy_id) {
        emitMissing.push({
          key: `hp-${position.position_id}`,
          label: `${tag} — ${t("quotation.handlePolicy")}`,
          targetId: `handle-policy-${position.position_id}`,
        });
      }
      if (!position.reinforcement_cut_policy_id) {
        emitMissing.push({
          key: `rf-${position.position_id}`,
          label: `${tag} — ${t("quotation.reinforcementPolicy")}`,
          targetId: `reinforcement-policy-${position.position_id}`,
        });
      }
      const pendingSeeds = seededIntentKeys.current.get(String(position.position_id));
      if (pendingSeeds && pendingSeeds.size > 0) {
        const domKey = [...pendingSeeds][0]!.split("|").slice(0, 3).join("|");
        emitMissing.push({
          key: `seed-${position.position_id}`,
          label: `${tag} — ${t("quotation.missingSeedConfirm")}`,
          targetId: `handle-height-${position.position_id}-${domKey}`,
        });
      }
    });
    if (!confirmed) {
      emitMissing.push({
        key: "confirm",
        label: t("quotation.confirm"),
        targetId: "quotation-confirm",
      });
    }
  }

  return (
    <section className="quotation-panel" aria-busy={busy}>
      <header>
        <div>
          <h2>{t("quotation.title")}</h2>
          <p>
            {t("quotation.current")}: <strong>{formatRevision(project.current_revision)}</strong>
          </p>
        </div>
        {canEmit && !preparation && (
          <button disabled={busy} onClick={() => void loadPreparation()}>
            {t("quotation.prepare")}
          </button>
        )}
        {canEmit && (
          <button disabled={busy} onClick={() => void resetPricing()}>
            {t("quotation.resetPricing")}
          </button>
        )}
        {canRevise && (
          <button disabled={busy} onClick={() => void startSuccessor()}>
            {t("quotation.editQuoted")}
          </button>
        )}
        {canShare && (
          <button disabled={busy} onClick={() => void shareQuote()}>
            {t("quotation.share")}
          </button>
        )}
        {canWrite && project.status === "QUOTED" && (
          <button disabled={busy} onClick={() => void approveInternally()}>
            {t("quotation.markApproved")}
          </button>
        )}
      </header>
      {message && <p role="status">{message}</p>}
      {sharedUrl && (
        <div className="quotation-share">
          <a
            className="link-button"
            href={`https://wa.me/?text=${encodeURIComponent(
              t("quotation.shareBody").replace("{name}", project.name).replace("{url}", sharedUrl),
            )}`}
            rel="noreferrer"
            target="_blank"
          >
            {t("quotation.shareWhatsApp")}
          </a>
          <a
            className="link-button"
            href={`mailto:${project.client_email ?? ""}?subject=${encodeURIComponent(
              t("quotation.shareSubject").replace("{code}", project.code),
            )}&body=${encodeURIComponent(
              t("quotation.shareBody").replace("{name}", project.name).replace("{url}", sharedUrl),
            )}`}
          >
            {t("quotation.shareEmail")}
          </a>
          <button className="link-button" onClick={() => void copySharedUrl()} type="button">
            {t("quotation.shareCopy")}
          </button>
        </div>
      )}
      {inspectorFailures.length > 0 && (
        <ul className="quotation-inspector-failures" role="alert">
          {inspectorFailures.map((failure, index) => (
            <li key={`${failure.rule}-${failure.bay_id ?? ""}-${index}`}>
              <strong>{failure.rule}</strong> · {failure.title}
              {failure.bay_id ? (
                <>
                  {" · "}
                  {t("quotation.inspectorAffected")} {failure.bay_id}
                  {failure.leaf_id ? `/${failure.leaf_id}` : ""}
                </>
              ) : null}
              {failure.recommendation ? <p>{failure.recommendation}</p> : null}
            </li>
          ))}
        </ul>
      )}
      {canWrite && project.status === "DRAFT" && !project.pricing_current && (
        <p>{t("quotation.priceFirst")}</p>
      )}
      {preparation && (
        <form className="quotation-form" onSubmit={(event) => void emit(event)}>
          <label htmlFor="quotation-payment-terms">{t("quotation.paymentTerms")}</label>
          <textarea
            id="quotation-payment-terms"
            required
            maxLength={2000}
            disabled={busy}
            value={preparation.payment_terms}
            onChange={(event) => {
              setDirty(true);
              setPreparation({ ...preparation, payment_terms: event.target.value });
            }}
          />
          <label htmlFor="quotation-valid-until">{t("quotation.validUntil")}</label>
          <input
            id="quotation-valid-until"
            required
            type="date"
            disabled={busy}
            value={preparation.quotation_valid_until ?? ""}
            onChange={(event) => {
              setDirty(true);
              setPreparation({ ...preparation, quotation_valid_until: event.target.value });
            }}
          />
          {preparation.positions.map((position, index) => (
            <fieldset key={position.position_id} disabled={busy}>
              <legend>
                {t("quotation.position")} {index + 1} · {position.system_name}
                {!position.production_ready && (
                  <span className="handle-pending">{t("quotation.quoteOnlyChip")}</span>
                )}
              </legend>
              <label htmlFor={`position-location-${position.position_id}`}>
                {t("projects.location")}
              </label>
              <input
                id={`position-location-${position.position_id}`}
                required
                maxLength={100}
                value={position.location_tag}
                onChange={(event) => updatePosition(index, { location_tag: event.target.value })}
              />
              {selectedPolicy(
                position.placement_options,
                position.manufacturing_placement_policy_id,
                (value) => {
                  // Bounds move under the new placement: auto-seeded
                  // midpoints recompute, manual heights stay as typed.
                  const reseeded = reseedHandleIntents(
                    {
                      ...position,
                      manufacturing_placement_policy_id: value,
                    },
                    seededIntentKeys.current.get(String(position.position_id)) ?? new Set(),
                  );
                  seededIntentKeys.current.set(
                    String(position.position_id),
                    new Set(reseeded.seededKeys),
                  );
                  updatePosition(index, reseeded.position);
                },
                t("quotation.placementPolicy"),
                busy,
                `placement-policy-${position.position_id}`,
              )}
              {selectedPolicy(
                position.handle_options,
                position.handle_requirement_policy_id,
                (value) => {
                  const reconciled = reconciledHandlePolicy(
                    position,
                    value,
                    seededIntentKeys.current.get(String(position.position_id)) ?? new Set(),
                  );
                  seededIntentKeys.current.set(
                    String(position.position_id),
                    new Set(reconciled.seededKeys),
                  );
                  updatePosition(index, reconciled.update);
                },
                t("quotation.handlePolicy"),
                busy,
                `handle-policy-${position.position_id}`,
              )}
              {selectedPolicy(
                position.reinforcement_options,
                position.reinforcement_cut_policy_id,
                (value) => updatePosition(index, { reinforcement_cut_policy_id: value }),
                t("quotation.reinforcementPolicy"),
                busy,
                `reinforcement-policy-${position.position_id}`,
              )}
              {requirementsFor(position).length > 0 && (
                <div className="handle-inputs">
                  <h4>{t("quotation.handleInputs")}</h4>
                  {(seededIntentKeys.current.get(String(position.position_id))?.size ?? 0) > 0 && (
                    <div className="handle-suggested-bar">
                      <span>{t("quotation.seedsNotice")}</span>
                      <button
                        type="button"
                        className="handle-suggested-confirm"
                        disabled={busy}
                        onClick={() => {
                          // Adopt every generated midpoint on this position as
                          // the estimator's choice — they stop being suggested
                          // values and can seal.
                          seededIntentKeys.current.get(String(position.position_id))?.clear();
                          updatePosition(index, {});
                        }}
                      >
                        {t("quotation.confirmSuggested")}
                      </button>
                    </div>
                  )}
                  {requirementsFor(position).map((requirement) => {
                    const intent = intentFor(position, requirement);
                    const reference =
                      intent?.vertical_reference ?? requirement.permitted_vertical_references[0];
                    const bounds = reference
                      ? heightBounds(position, requirement, reference)
                      : null;
                    const height =
                      intent?.requested_height_mm !== undefined && intent.requested_height_mm !== ""
                        ? parseDecimal(intent.requested_height_mm)
                        : null;
                    const boundMin = bounds?.[0] ? parseDecimal(bounds[0]) : null;
                    const boundMax = bounds?.[1] ? parseDecimal(bounds[1]) : null;
                    const outOfBounds =
                      bounds !== null &&
                      height !== null &&
                      boundMin !== null &&
                      boundMax !== null &&
                      (compareDecimal(height, boundMin) < 0 ||
                        compareDecimal(height, boundMax) > 0);
                    // The policy's permitted span midpoint is the sane
                    // default — visible, editable, still the estimator's
                    // call; true authority stays the sealed intent.
                    const defaultHeight =
                      boundMin !== null && boundMax !== null
                        ? formatDecimal(midpointDecimal(boundMin, boundMax))
                        : "";
                    return (
                      <div className="handle-row" key={intentKey(requirement)}>
                        <div className="handle-leaf">
                          <strong>{requirement.leaf_label}</strong>
                          <span>
                            {requirement.requires_handedness
                              ? t("quotation.handednessRequired")
                              : requirement.host_member_side === "LEFT"
                                ? t("quotation.sideLeft")
                                : t("quotation.sideRight")}
                            {requirement.handle_domain_slot !== "PRIMARY" &&
                              ` · ${requirement.handle_domain_slot}`}
                          </span>
                        </div>
                        <div className="handle-field">
                          <label
                            htmlFor={`handle-height-${position.position_id}-${intentKey(requirement)}`}
                          >
                            {t("quotation.handleHeight")}
                          </label>
                          <input
                            id={`handle-height-${position.position_id}-${intentKey(requirement)}`}
                            type="text"
                            inputMode="decimal"
                            disabled={busy}
                            aria-invalid={outOfBounds || undefined}
                            placeholder={bounds ? `${bounds[0]}–${bounds[1]}` : undefined}
                            value={intent?.requested_height_mm ?? defaultHeight}
                            onChange={(event) =>
                              updateIntent(index, requirement, {
                                requested_height_mm: event.target.value,
                              })
                            }
                          />
                          {bounds && (
                            <span className="handle-bounds">
                              {t("quotation.handleBounds")} {bounds[0]}–{bounds[1]} mm
                            </span>
                          )}
                        </div>
                        <div className="handle-field">
                          <label
                            htmlFor={`handle-ref-${position.position_id}-${intentKey(requirement)}`}
                          >
                            {t("quotation.handleReference")}
                          </label>
                          <select
                            id={`handle-ref-${position.position_id}-${intentKey(requirement)}`}
                            disabled={
                              busy || requirement.permitted_vertical_references.length === 1
                            }
                            value={
                              intent?.vertical_reference ??
                              requirement.permitted_vertical_references[0]
                            }
                            onChange={(event) =>
                              updateIntent(index, requirement, {
                                requested_height_mm: intent?.requested_height_mm ?? "",
                                vertical_reference: event.target
                                  .value as HandleIntent["vertical_reference"],
                              })
                            }
                          >
                            {requirement.permitted_vertical_references.map((reference) => (
                              <option key={reference} value={reference}>
                                {t(REFERENCE_KEYS[reference])}
                              </option>
                            ))}
                          </select>
                        </div>
                        {!intent?.requested_height_mm && (
                          <span className="handle-pending">{t("quotation.handlePending")}</span>
                        )}
                        {intent?.requested_height_mm &&
                          (seededIntentKeys.current
                            .get(String(position.position_id))
                            ?.has(seedKeyForIntent(intent)) ??
                            false) && (
                            <span className="handle-suggested">
                              {t("quotation.handleSuggested")}
                            </span>
                          )}
                        {outOfBounds && (
                          <span className="handle-pending" role="alert">
                            {t("quotation.handleOutOfBounds")}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
              {position.workshop_targets && (
                <details
                  className="workshop-inputs"
                  /* Inspector failures name the exact bay/leaf that needs
                     workshop data — auto-open the editor that fixes it
                     (hostile H1: the <details> hid the required fields). */
                  open={inspectorFailures.some(
                    (failure) =>
                      (failure.bay_id != null &&
                        position.workshop_targets.bays.some(
                          (bay) => bay.bay_id === failure.bay_id,
                        )) ||
                      (failure.leaf_id != null &&
                        position.workshop_targets.leaves.some(
                          (leaf) => leaf.leaf_id === failure.leaf_id,
                        )),
                  )}
                >
                  <summary>{t("quotation.workshopData")}</summary>
                  {position.workshop_targets.bays.map((bay) => {
                    const annotation = position.workshop_annotations.find(
                      (item) => item.bay_id === bay.bay_id && (item.leaf_id ?? null) === null,
                    );
                    return (
                      <div className="workshop-target" key={bay.bay_id}>
                        <strong>{bay.label}</strong>
                        <div className="workshop-row">
                          <CsvMmField
                            id={`drains-${position.position_id}-${bay.bay_id}`}
                            label={t("quotation.drains")}
                            values={annotation?.bottom_drain_holes_mm}
                            disabled={busy}
                            onCommit={(value) =>
                              updateAnnotation(index, bay.bay_id, null, {
                                bottom_drain_holes_mm: value,
                              })
                            }
                          />
                          <label className="workshop-field">
                            <span>{t("quotation.continuousWidth")}</span>
                            <input
                              type="text"
                              inputMode="decimal"
                              disabled={busy}
                              value={annotation?.continuous_width_mm ?? ""}
                              onChange={(event) =>
                                updateAnnotation(index, bay.bay_id, null, {
                                  continuous_width_mm: event.target.value || null,
                                })
                              }
                            />
                            <span className="workshop-unit">mm</span>
                          </label>
                          <label className="workshop-field">
                            <span>{t("quotation.expansionCoupler")}</span>
                            <select
                              disabled={busy}
                              value={
                                annotation?.has_coupler === true
                                  ? "YES"
                                  : annotation?.has_coupler === false
                                    ? "NO"
                                    : ""
                              }
                              onChange={(event) => {
                                const value = event.target.value;
                                if (value !== "YES" && value !== "NO") return;
                                updateAnnotation(index, bay.bay_id, null, {
                                  has_coupler: value === "YES",
                                });
                              }}
                            >
                              <option value="">{t("quotation.chooseCoverage")}</option>
                              <option value="NO">{t("quotation.answerNo")}</option>
                              <option value="YES">{t("quotation.answerYes")}</option>
                            </select>
                          </label>
                          {annotation?.has_coupler == null && (
                            <span className="handle-pending">{t("quotation.handlePending")}</span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                  {position.workshop_targets.leaves.length > 0 && (
                    <div className="workshop-group">
                      <h5>{t("quotation.closingPoints")}</h5>
                      {position.workshop_targets.leaves.map((leaf) => {
                        const annotation = position.workshop_annotations.find(
                          (item) =>
                            item.bay_id === leaf.bay_id && (item.leaf_id ?? null) === leaf.leaf_id,
                        );
                        return (
                          <CsvMmField
                            key={`${leaf.bay_id}|${leaf.leaf_id ?? ""}`}
                            id={`closing-${position.position_id}-${leaf.bay_id}-${leaf.leaf_id ?? ""}`}
                            label={leaf.leaf_label}
                            values={annotation?.closing_points_perimeter_mm}
                            disabled={busy}
                            onCommit={(value) =>
                              updateAnnotation(index, leaf.bay_id, leaf.leaf_id ?? null, {
                                closing_points_perimeter_mm: value,
                              })
                            }
                          />
                        );
                      })}
                    </div>
                  )}
                  {position.workshop_targets.spans.length > 0 && (
                    <div className="workshop-group">
                      <h5>{t("quotation.structuralInputs")}</h5>
                      {position.workshop_targets.spans.map((span) => {
                        const structural = position.structural_inputs.find(
                          (item) => item.target_id === span.target_id,
                        );
                        return (
                          <div className="workshop-target" key={span.target_id}>
                            <strong>
                              {span.label} · {fmtMm(span.span_mm)} mm
                            </strong>
                            <div className="workshop-row">
                              <label className="workshop-field">
                                <span>{t("quotation.requiredIx")}</span>
                                <input
                                  type="text"
                                  inputMode="decimal"
                                  disabled={busy}
                                  value={structural?.required_ix_cm4 ?? ""}
                                  onChange={(event) =>
                                    updateStructural(index, span.target_id, {
                                      required_ix_cm4: event.target.value || null,
                                    })
                                  }
                                />
                                <span className="workshop-unit">cm⁴</span>
                              </label>
                              <label className="workshop-field workshop-field--wide">
                                <span>{t("quotation.structuralBasis")}</span>
                                <input
                                  type="text"
                                  maxLength={1000}
                                  disabled={busy}
                                  value={structural?.structural_basis ?? ""}
                                  placeholder={t("quotation.structuralBasisHint")}
                                  onChange={(event) =>
                                    updateStructural(index, span.target_id, {
                                      structural_basis: event.target.value || null,
                                    })
                                  }
                                />
                              </label>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                  {position.workshop_targets.glass.length > 0 && (
                    <div className="workshop-group">
                      <h5>{t("quotation.glassPolishing")}</h5>
                      {position.workshop_targets.glass.map((target) => (
                        <GlassPolishingRow
                          key={`${target.bay_id}|${target.leaf_id ?? ""}`}
                          target={target}
                          record={position.glass_polishing.find(
                            (item) =>
                              item.bay_id === target.bay_id &&
                              (item.leaf_id ?? null) === target.leaf_id,
                          )}
                          disabled={busy}
                          onEdges={(edges) =>
                            setPolishingEdges(index, target.bay_id, target.leaf_id ?? null, edges)
                          }
                        />
                      ))}
                    </div>
                  )}
                  <div className="workshop-group">
                    <h5>{t("quotation.accessories")}</h5>
                    <label className="workshop-field">
                      <span>{t("quotation.coverage")}</span>
                      <select
                        disabled={busy}
                        value={position.accessory_schedule?.coverage ?? ""}
                        onChange={(event) => {
                          const coverage = event.target.value as CoverageEnum | "";
                          if (!coverage) return;
                          updateAccessories(index, {
                            coverage,
                            items:
                              coverage === "DECLARED"
                                ? (position.accessory_schedule?.items ?? [])
                                : [],
                          });
                        }}
                      >
                        <option value="">{t("quotation.chooseCoverage")}</option>
                        <option value="NONE_REQUIRED">{t("quotation.coverageNone")}</option>
                        <option value="DECLARED">{t("quotation.coverageDeclared")}</option>
                      </select>
                    </label>
                    {position.accessory_schedule?.coverage === "DECLARED" && (
                      <div className="workshop-accessories">
                        {position.accessory_schedule.items.map((item, itemIndex) => (
                          <div className="workshop-accessory" key={itemIndex}>
                            <input
                              type="text"
                              disabled={busy}
                              maxLength={200}
                              placeholder={t("quotation.obligationId")}
                              value={item.obligation_id}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  obligation_id: event.target.value,
                                })
                              }
                            />
                            <select
                              disabled={busy}
                              value={item.obligation_kind}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  obligation_kind: event.target.value as ObligationKindEnum,
                                })
                              }
                            >
                              {OBLIGATION_KINDS.map((kind) => (
                                <option key={kind} value={kind}>
                                  {t(OBLIGATION_KIND_KEYS[kind])}
                                </option>
                              ))}
                            </select>
                            <input
                              type="text"
                              disabled={busy}
                              maxLength={200}
                              placeholder={t("quotation.technicalSku")}
                              value={item.technical_sku}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  technical_sku: event.target.value,
                                })
                              }
                            />
                            <input
                              type="text"
                              disabled={busy}
                              maxLength={200}
                              placeholder={t("quotation.purchasingSku")}
                              value={item.purchasing_sku}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  purchasing_sku: event.target.value,
                                })
                              }
                            />
                            <input
                              type="text"
                              disabled={busy}
                              maxLength={300}
                              placeholder={t("quotation.manufacturer")}
                              value={item.manufacturer_name}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  manufacturer_name: event.target.value,
                                })
                              }
                            />
                            <select
                              disabled={busy}
                              value={item.order_type}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  order_type: event.target.value as OrderTypeEnum,
                                })
                              }
                            >
                              {ORDER_TYPES.map((order) => (
                                <option key={order} value={order}>
                                  {t(ORDER_TYPE_KEYS[order])}
                                </option>
                              ))}
                            </select>
                            <input
                              type="number"
                              disabled={busy}
                              min="1"
                              step="1"
                              placeholder={t("quotation.quantityPerUnit")}
                              value={item.quantity_per_position_unit}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  quantity_per_position_unit: Math.max(
                                    1,
                                    Number(event.target.value) || 1,
                                  ),
                                })
                              }
                            />
                            <input
                              type="text"
                              disabled={busy}
                              maxLength={1000}
                              placeholder={t("quotation.description")}
                              value={item.description}
                              onChange={(event) =>
                                updateAccessoryItem(index, itemIndex, {
                                  description: event.target.value,
                                })
                              }
                            />
                            <button
                              type="button"
                              className="ghost-button is-danger"
                              disabled={busy}
                              aria-label={t("quotation.removeAccessory")}
                              onClick={() => updateAccessoryItem(index, itemIndex, null)}
                            >
                              ×
                            </button>
                          </div>
                        ))}
                        <button
                          type="button"
                          className="ghost-button"
                          disabled={busy}
                          onClick={() =>
                            updateAccessories(index, {
                              items: [
                                ...position.accessory_schedule!.items,
                                {
                                  obligation_id: nextObligationId(
                                    position.accessory_schedule!.items,
                                  ),
                                  obligation_kind: "INSTALLATION_ACCESSORY",
                                  technical_sku: "",
                                  purchasing_sku: "",
                                  manufacturer_name: "",
                                  order_type: "SUPPLIER_HARDWARE_PO",
                                  unit: "EA",
                                  quantity_per_position_unit: 1,
                                  description: "",
                                },
                              ],
                            })
                          }
                        >
                          {t("quotation.addAccessory")}
                        </button>
                      </div>
                    )}
                  </div>
                </details>
              )}
            </fieldset>
          ))}
          {emitMissing.length > 0 && (
            <div className="emit-checklist" aria-live="polite">
              <strong>{t("quotation.missingTitle")}</strong>
              <ul>
                {emitMissing.map((item) => (
                  <li key={item.key}>
                    {item.targetId ? (
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => document.getElementById(item.targetId!)?.focus()}
                      >
                        {item.label}
                      </button>
                    ) : (
                      item.label
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {preparation.positions.length > 0 &&
            (preparation.positions.every((position) => position.production_ready) ? (
              <p className="emit-outcome">{t("quotation.emitOutcomeReady")}</p>
            ) : (
              <p className="emit-outcome emit-outcome--warn" role="note">
                {t("quotation.emitOutcomeQuoteOnly")}{" "}
                {preparation.positions
                  .map((position, index) => ({ position, index }))
                  .filter(({ position }) => !position.production_ready)
                  .map(({ index }) => `${t("quotation.position")} ${index + 1}`)
                  .join(" · ")}
              </p>
            ))}
          <label className="quotation-confirm">
            <input
              id="quotation-confirm"
              required
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(event) => {
                setDirty(true);
                setConfirmed(event.target.checked);
              }}
            />
            {t("quotation.confirm")}
          </label>
          <div className="projects-actions">
            <button disabled={busy || !confirmed}>{t("quotation.emit")}</button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                if (!dirty) {
                  setPreparation(null);
                  setConfirmed(false);
                  return;
                }
                void confirm({ title: t("projects.discard") }).then((ok) => {
                  if (ok) {
                    setPreparation(null);
                    setConfirmed(false);
                    setDirty(false);
                  }
                });
              }}
            >
              {t("projects.cancel")}
            </button>
          </div>
        </form>
      )}
      {(approvals.data?.length ?? 0) > 0 && (
        <div className="quotation-links">
          <h3>{t("quotation.linksTitle")}</h3>
          <ul>
            {approvals.data?.map((link) => {
              const live = link.status === "PENDING" && Date.parse(link.expires_at) > Date.now();
              return (
                <li
                  className="quotation-link"
                  data-status={link.status.toLowerCase()}
                  key={link.id}
                >
                  <span className="status-chip" data-status={link.status.toLowerCase()}>
                    {t(approvalStatusKeys[link.status] ?? "quotation.linkPending")}
                  </span>
                  <strong>{formatRevision(link.revision_code)}</strong>
                  <time dateTime={link.created_at}>{formatDateTime(link.created_at)}</time>
                  {link.status === "PENDING" && (
                    <span className="quotation-link__meta">
                      {live
                        ? `${t("quotation.linkExpires")} ${formatDateTime(link.expires_at)}`
                        : t("quotation.linkExpired")}
                    </span>
                  )}
                  {(link.view_count ?? 0) > 0 && (
                    <span className="quotation-link__meta">
                      {t("quotation.linkViews").replace("{count}", String(link.view_count))}
                      {link.last_viewed_at ? ` · ${formatDateTime(link.last_viewed_at)}` : ""}
                    </span>
                  )}
                  {(link.status === "APPROVED" || link.status === "DECLINED") && (
                    <span className="quotation-link__meta">
                      {link.decided_by ?? ""}
                      {link.decided_at ? ` · ${formatDateTime(link.decided_at)}` : ""}
                      {link.decided_note ? ` · “${link.decided_note}”` : ""}
                    </span>
                  )}
                  {link.status === "REVOKED" && link.revoked_at && (
                    <span className="quotation-link__meta">
                      {t("quotation.linkRevokedAt")} {formatDateTime(link.revoked_at)}
                    </span>
                  )}
                  {live && canWrite && (
                    <button type="button" disabled={busy} onClick={() => void revokeLink(link.id)}>
                      {t("quotation.linkRevoke")}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
      {(project.versions?.length ?? 0) > 0 && (
        <div className="quotation-history">
          <h3>{t("quotation.history")}</h3>
          <ul>
            {project.versions?.map((version) => (
              <li key={version.id}>
                <strong>{formatRevision(version.revision_code)}</strong>
                <time dateTime={version.emitted_at}>{formatDateTime(version.emitted_at)}</time>
                <span>
                  {t(
                    version.documentary_complete
                      ? "quotation.completeEvidence"
                      : "quotation.designEvidence",
                  )}
                </span>
                <span>
                  {t(
                    version.production_allowed
                      ? "quotation.productionReady"
                      : "quotation.quoteOnlyChip",
                  )}
                </span>
                {artifactIndex.data?.some(
                  (item) =>
                    item.project_version_id === version.id && item.document_type === "DOC-01",
                ) && <span>{t("quotation.documentEmitted")}</span>}
                <button
                  disabled={busy}
                  onClick={() => void openEvidence(version.id, version.revision_code)}
                >
                  {t("quotation.openEvidence")}
                </button>
                {canRelease ? (
                  version.production_allowed ? (
                    <button
                      type="button"
                      className="primary-action"
                      disabled={busy}
                      onClick={() => void release(version.id)}
                    >
                      {t("quotation.release")}
                    </button>
                  ) : (
                    <span className="handle-pending">{t("quotation.releaseBlocked")}</span>
                  )
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
