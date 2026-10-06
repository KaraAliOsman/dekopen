import { useCallback, useEffect, useState } from "react";

import {
  productionCncProgramCompare,
  productionOrderCncProgramGenerate,
  productionOrderCncReadiness,
} from "../../api/generated/dekopen";
import { ApiError, apiFetchBlob } from "../../api/apiMutator";
import { actionErrorDetail } from "../errors";
import { fmtMm, shortTechnicalId } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";
import {
  cutRoleLabel,
  opBasisLabel,
  opFaceLabel,
  opKindLabel,
  opLabel,
  opReferenceLabel,
} from "./labels";

type CncOp = {
  operation_id: string;
  kind: string;
  u_mm: string | null;
  x_mm: string | null;
  y_mm: string | null;
  face: string | null;
  reference: string | null;
  depth_mm: string | null;
  angle_left_deg: string | null;
  angle_right_deg: string | null;
  tool_id: string | null;
  basis: string;
  detail?: Record<string, string>;
};

type CncVerdict = {
  operation_id: string;
  level: "PASS" | "WARN" | "BLOCK";
  code: string;
  detail: Record<string, string>;
};

type CncMachineVerdict = {
  machine_id: string;
  machine_code: string;
  machine_name: string;
  verdict: "PASS" | "WARN" | "BLOCK";
  blockers: CncVerdict[];
  warnings: CncVerdict[];
};

type CncMember = {
  member_id: string;
  member_label: string;
  workshop_sku?: string | null;
  role?: string | null;
  material?: string | null;
  axis?: string | null;
  angle_left_deg?: string | null;
  angle_right_deg?: string | null;
  leaf_slot?: string | null;
  repetition_index?: number | null;
  bay_id?: string | null;
  leaf_id?: string | null;
  position_index?: number | null;
  length_mm: string;
  operation_count: number;
  kinds: string[];
  machines: CncMachineVerdict[];
  operations: CncOp[];
};

type CncProgram = {
  id: string;
  program_no: string;
  member_id: string;
  member_label: string;
  operation_count: number;
  verdict: string;
  fingerprint: string;
  status: string;
  machine_code: string | null;
  plan_seed?: string | null;
  plan_fingerprint?: string | null;
  superseded_by?: { id: string; program_no: string } | null;
  created_at: string;
};

type CncGapCheck = {
  machine_id: string;
  machine_code: string;
  can_run: boolean;
  cause: string;
};

type CncGap = {
  gap_id: string;
  kind: string;
  op_kind: string | null;
  cause: string;
  source: string;
  declared_value?: string;
  bay_id?: string | null;
  leaf_id?: string | null;
  member_id?: string | null;
  kit_sku?: string | null;
  machines?: CncGapCheck[];
};

type CncIssue = {
  code: string;
  detail?: string;
} & Record<string, unknown>;

type CncReadinessData = {
  order_id: string;
  order_code: string;
  plan?: { fingerprint?: string; plan_seed?: string; position_id?: string };
  members: CncMember[];
  declared_gaps?: CncGap[];
  issues?: CncIssue[];
  required_tool_ids?: string[];
  machines: {
    id: string;
    code: string;
    name: string;
    emitter_implemented?: boolean;
  }[];
  programs: CncProgram[];
};

type ProgramDiff = {
  base: { program_no: string };
  other: { program_no: string };
  added: { operation_id: string; kind?: string }[];
  removed: { operation_id: string; kind?: string }[];
  changed: { operation_id: string; fields: Record<string, { from: unknown; to: unknown }> }[];
  counts: { added: number; removed: number; changed: number; unchanged: number };
};

/** gap.kind/op_kind can carry declaration kinds outside the op enum
 * (OTHER) — never print the raw token. */
function gapKindLabel(gap: CncGap): string {
  const kind = gap.op_kind ?? gap.kind;
  if (!kind || kind === "OTHER") return t("production.cncGapOther");
  const label = opKindLabel(kind);
  return label === kind ? t("production.cncGapOther") : label;
}

const MATERIAL_LABELS: Record<string, string> = {
  PVC: "PVC",
  ALUMINIUM: "aluminio",
};

const AXIS_LABELS: Record<string, string> = {
  HORIZONTAL: "horizontal",
  VERTICAL: "vertical",
};
const GAP_CAUSES: Record<string, string> = {
  no_rule: "production.cncGapCauseNoRule",
  no_coordinates: "production.cncGapCauseNoCoords",
  no_tool: "production.cncGapCauseNoTool",
  unsupported_kind: "production.cncGapCauseUnsupported",
  emitter_not_implemented: "production.cncGapCauseEmitter",
  unassessable: "production.cncGapCauseUnassessable",
};

function gapCauseLabel(cause: string): string {
  return tOptional(GAP_CAUSES[cause] ?? "") ?? t("production.cncGapCauseGeneric");
}

const GAP_SOURCES: Record<string, string> = {
  "workshop_annotations.bottom_drain_holes_mm": "production.cncGapSourceDrains",
  "workshop_annotations.closing_points_perimeter_mm": "production.cncGapSourceClosing",
  "workshop_annotations.has_coupler": "production.cncGapSourceCoupler",
  handle_intents: "production.cncGapSourceHandles",
  hardware_machining: "production.cncGapSourceHardware",
};

function gapSourceLabel(source: string): string {
  return tOptional(GAP_SOURCES[source] ?? "") ?? t("production.cncGapSourceGeneric");
}

const DETAIL_KEYS: Record<string, string> = {
  host_label: "pieza",
  member: "pieza",
  member_label: "pieza",
  tool_id: "herramienta",
  required_kind: "operación",
  depth_mm: "profundidad",
  max_depth_mm: "prof. máx",
  member_length_mm: "largo pieza",
  max_member_length_mm: "largo máx",
  clamp_zone: "mordaza",
  margin_mm: "margen",
  coordinate_system: "coordenadas",
  face: "cara",
  kind: "operación",
  u_mm: "u",
  postprocessor_id: "emisor",
};

/** Verdict detail values rendered in words, not `k=v` — a reader knows what
 * "broca DR-8 no cubre 12 mm" means, not what the code field is called. */
function blockerText(blocker: CncVerdict): string {
  const key = `production.cncBlock_${blocker.code}`;
  const label = tOptional(key) ?? t("production.cncBlockGeneric");
  const values = Object.entries(blocker.detail)
    .filter(([k]) => k !== "host" && blocker.detail[k] !== "")
    .map(([k, v]) => `${DETAIL_KEYS[k] ?? k} ${v}`)
    .join(" · ");
  return values ? `${label} — ${values}` : label;
}

function issueText(issue: CncIssue): string {
  const key = `production.cncIssue_${issue.code}`;
  const label = tOptional(key) ?? t("production.cncIssueGeneric");
  const context = Object.entries(issue)
    .filter(([k]) => !["code", "detail"].includes(k))
    .map(([k, v]) => `${DETAIL_KEYS[k] ?? k} ${v}`)
    .join(" · ");
  const detail = typeof issue.detail === "string" ? issue.detail : "";
  return [label, context, detail].filter(Boolean).join(" — ");
}

export function CncPanel({ orderId, canWrite }: { orderId: string; canWrite: boolean }) {
  const [data, setData] = useState<CncReadinessData | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selectedOp, setSelectedOp] = useState<string | null>(null);
  const [diff, setDiff] = useState<Record<string, ProgramDiff | "loading">>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await productionOrderCncReadiness(orderId);
      setData(response.data as CncReadinessData);
      setError(null);
      setForbidden(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setForbidden(true);
        setError(null);
      } else {
        setError(t("production.cncLoadError"));
      }
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  async function generate(machineId: string, memberId: string) {
    setBusy(true);
    try {
      await productionOrderCncProgramGenerate(orderId, {
        machine_id: machineId,
        member_id: memberId,
      });
      await load();
    } catch (err) {
      // ApiError carries the contract payload on .payload — reading
      // .detail/.error off the error object itself always misses it.
      setError(actionErrorDetail(err, t("production.cncProgramError")));
    } finally {
      setBusy(false);
    }
  }

  async function downloadProgram(program: CncProgram, filename: string) {
    try {
      const { blob, filename: downloadName } = await apiFetchBlob(
        `/api/v1/production/cnc/programs/${program.id}/file/${filename}`,
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = downloadName ?? `${program.program_no}-${filename}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t("production.cncProgramError"));
    }
  }

  async function comparePrograms(program: CncProgram, otherId: string) {
    setDiff((current) => ({ ...current, [program.id]: "loading" }));
    try {
      const response = await productionCncProgramCompare(program.id, otherId);
      setDiff((current) => ({
        ...current,
        [program.id]: response.data as unknown as ProgramDiff,
      }));
    } catch {
      setDiff((current) => {
        const next = { ...current };
        delete next[program.id];
        return next;
      });
      setError(t("production.cncProgramError"));
    }
  }

  return (
    <div className="cnc-panel">
      <button
        type="button"
        className="cnc-panel-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {t("production.cncTitle")}
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
      </button>
      {open ? (
        <div className="cnc-panel-body">
          {error ? (
            <p className="cnc-error" role="alert">
              {error}
            </p>
          ) : null}
          {loading && !data ? (
            <p className="cnc-empty">{t("production.cncLoading")}</p>
          ) : forbidden ? (
            <p className="cnc-empty" role="alert">
              {t("production.cncNoPermission")}
            </p>
          ) : !data ? (
            error ? null : (
              <p className="cnc-empty">{t("production.cncLoading")}</p>
            )
          ) : (
            <>
              {data.plan?.fingerprint || data.plan?.plan_seed ? (
                <p className="cnc-plan-line">
                  {t("production.cncPlan")}: {shortTechnicalId(data.plan.fingerprint ?? "")}
                  {data.plan.plan_seed
                    ? ` · ${t("production.cncPlanSeed")} ${data.plan.plan_seed}`
                    : ""}
                </p>
              ) : null}
              {data.issues?.length ? (
                <ul className="cnc-issues" role="alert">
                  {data.issues.map((issue, index) => (
                    <li key={index}>{issueText(issue)}</li>
                  ))}
                </ul>
              ) : null}
              {data.machines.length === 0 ? (
                <p className="cnc-empty" role="alert">
                  {t("production.cncNoMachines")}
                </p>
              ) : null}
              {data.machines.some((m) => m.emitter_implemented === false) ? (
                <ul className="cnc-issues" role="alert">
                  {data.machines
                    .filter((m) => m.emitter_implemented === false)
                    .map((m) => (
                      <li key={m.id}>
                        {m.code} — {t("production.cncGapCauseEmitter")}
                      </li>
                    ))}
                </ul>
              ) : null}
              {data.required_tool_ids?.length ? (
                <p className="cnc-required-tools">
                  {t("production.cncRequiredTools")}: {data.required_tool_ids.join(", ")}
                </p>
              ) : null}
              {data.members.length === 0 ? (
                <p className="cnc-empty">{t("production.cncNoOps")}</p>
              ) : (
                <table className="cnc-table">
                  <thead>
                    <tr>
                      <th>{t("production.cncMember")}</th>
                      <th>{t("production.cncOps")}</th>
                      {data.machines.map((machine) => (
                        <th key={machine.id}>{machine.code}</th>
                      ))}
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.members.map((member) => (
                      <CncMemberRow
                        key={member.member_id}
                        member={member}
                        machines={data.machines}
                        canWrite={canWrite}
                        busy={busy}
                        expanded={expanded === member.member_id}
                        onToggle={() =>
                          setExpanded((value) =>
                            value === member.member_id ? null : member.member_id,
                          )
                        }
                        selectedOp={selectedOp}
                        onSelectOp={(id) => setSelectedOp(id)}
                        onGenerate={(machineId) => void generate(machineId, member.member_id)}
                      />
                    ))}
                  </tbody>
                </table>
              )}
              {data.declared_gaps?.length ? <DeclaredGaps gaps={data.declared_gaps} /> : null}
              {data.programs.length ? (
                <div className="cnc-programs">
                  <h4>{t("production.cncPrograms")}</h4>
                  <ul>
                    {data.programs.map((program) => (
                      <CncProgramRow
                        key={program.id}
                        program={program}
                        programs={data.programs}
                        diff={diff}
                        onDownload={(filename) => void downloadProgram(program, filename)}
                        onCompare={(otherId) => void comparePrograms(program, otherId)}
                      />
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

function CncMemberRow({
  member,
  machines,
  canWrite,
  busy,
  expanded,
  onToggle,
  selectedOp,
  onSelectOp,
  onGenerate,
}: {
  member: CncMember;
  machines: { id: string; code: string }[];
  canWrite: boolean;
  busy: boolean;
  expanded: boolean;
  onToggle: () => void;
  selectedOp: string | null;
  onSelectOp: (id: string | null) => void;
  onGenerate: (machineId: string) => void;
}) {
  const byMachine = new Map(member.machines.map((verdict) => [verdict.machine_id, verdict]));
  return (
    <>
      <tr className="cnc-member">
        <td>
          <button type="button" className="cnc-member-label" onClick={onToggle}>
            {member.member_label}
            <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
          </button>
          {member.workshop_sku || member.role ? (
            <div className="cnc-member-meta">
              {[member.workshop_sku, member.role ? cutRoleLabel(member.role) : null]
                .filter(Boolean)
                .join(" · ")}
            </div>
          ) : null}
        </td>
        <td>
          {member.operation_count} · {member.kinds.map(opKindLabel).join(", ")}
          {member.length_mm ? ` · ${fmtMm(member.length_mm)}` : ""}
        </td>
        {machines.map((machine) => {
          const verdict = byMachine.get(machine.id);
          if (!verdict) {
            return <td key={machine.id}>—</td>;
          }
          return (
            <td key={machine.id}>
              <button
                type="button"
                className={`cnc-verdict cnc-verdict-${verdict.verdict.toLowerCase()} cnc-verdict-btn`}
                onClick={onToggle}
              >
                {tOptional(`production.cncVerdict${verdict.verdict}`) ?? verdict.verdict}
                {verdict.blockers.length ? ` (${verdict.blockers.length})` : ""}
                {!verdict.blockers.length && verdict.warnings.length
                  ? ` (${verdict.warnings.length})`
                  : ""}
              </button>
            </td>
          );
        })}
        <td>
          {canWrite
            ? machines.map((machine) => {
                const verdict = byMachine.get(machine.id);
                if (!verdict || verdict.verdict === "BLOCK") return null;
                return (
                  <button
                    key={machine.id}
                    type="button"
                    className="cnc-generate"
                    disabled={busy}
                    onClick={() => onGenerate(machine.id)}
                  >
                    {t("production.cncGenerate")} {machine.code}
                  </button>
                );
              })
            : null}
        </td>
      </tr>
      {expanded ? (
        <tr className="cnc-member-ops">
          <td colSpan={2 + machines.length + 1}>
            <MemberCard
              member={member}
              machines={machines}
              byMachine={byMachine}
              selectedOp={selectedOp}
              onSelectOp={onSelectOp}
            />
          </td>
        </tr>
      ) : null}
    </>
  );
}

/** Tarjeta de miembro: identidad física (SKU, rol, largo), vista por caras
 * con las operaciones dibujadas desde el datum declarado, la tabla de
 * operaciones con coordenadas y fuente de regla, y el veredicto por máquina
 * con las razones en palabras — nunca dentro de un tooltip. */
function MemberCard({
  member,
  machines,
  byMachine,
  selectedOp,
  onSelectOp,
}: {
  member: CncMember;
  machines: { id: string; code: string }[];
  byMachine: Map<string, CncMachineVerdict>;
  selectedOp: string | null;
  onSelectOp: (id: string | null) => void;
}) {
  return (
    <div className="cnc-member-card">
      <div className="cnc-member-card-head">
        <strong>{member.member_label}</strong>
        <span>
          {[
            member.workshop_sku,
            member.role ? cutRoleLabel(member.role) : null,
            member.material ? (MATERIAL_LABELS[member.material] ?? member.material) : null,
            member.axis ? (AXIS_LABELS[member.axis] ?? member.axis) : null,
            member.leaf_slot,
          ]
            .filter(Boolean)
            .join(" · ")}
          {member.length_mm ? ` · ${fmtMm(member.length_mm)}` : ""}
          {member.angle_left_deg ? ` · ${member.angle_left_deg}°` : ""}
          {member.angle_right_deg ? `/${member.angle_right_deg}°` : ""}
        </span>
      </div>
      <MemberOpsDiagram member={member} selectedOp={selectedOp} onSelectOp={onSelectOp} />
      <table className="cnc-ops">
        <thead>
          <tr>
            <th>#</th>
            <th>{t("production.cncOpKind")}</th>
            <th>{t("production.cncFace")}</th>
            <th>u (mm)</th>
            <th>X (mm)</th>
            <th>Y (mm)</th>
            <th>{t("production.cncReference")}</th>
            <th>{t("production.cncDepth")}</th>
            <th>{t("production.cncTool")}</th>
            <th>{t("production.cncBasis")}</th>
          </tr>
        </thead>
        <tbody>
          {member.operations.map((op, index) => (
            <tr
              key={op.operation_id}
              className={selectedOp === op.operation_id ? "cnc-op-row is-selected" : "cnc-op-row"}
              onClick={() => onSelectOp(selectedOp === op.operation_id ? null : op.operation_id)}
            >
              <td>{index + 1}</td>
              <td>{opLabel(op)}</td>
              <td>{opFaceLabel(op.face)}</td>
              <td>{fmtMm(op.u_mm)}</td>
              <td>{fmtMm(op.x_mm)}</td>
              <td>{fmtMm(op.y_mm)}</td>
              <td>{opReferenceLabel(op.reference)}</td>
              <td>{fmtMm(op.depth_mm)}</td>
              <td>{op.tool_id ?? "—"}</td>
              <td>{opBasisLabel(op.basis)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="cnc-verdicts">
        <h5>{t("production.cncVerdicts")}</h5>
        <ul>
          {machines.map((machine) => {
            const verdict = byMachine.get(machine.id);
            if (!verdict) return null;
            const reasons = [...verdict.blockers, ...verdict.warnings];
            return (
              <li key={machine.id} className="cnc-verdict-line">
                <span className={`cnc-verdict cnc-verdict-${verdict.verdict.toLowerCase()}`}>
                  {tOptional(`production.cncVerdict${verdict.verdict}`) ?? verdict.verdict}
                </span>
                <span className="cnc-verdict-machine">{machine.code}</span>
                {reasons.length ? (
                  <ul className="cnc-reasons">
                    {reasons.map((reason, index) => (
                      <li key={index}>{blockerText(reason)}</li>
                    ))}
                  </ul>
                ) : (
                  <span className="cnc-verdict-ok">{t("production.cncVerdictOk")}</span>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

/** Declared-but-not-emitted operations for the order: what the sealed data
 * asked for that no emitter produced, the source it was declared in, the
 * cause, and per machine whether it could run it if it existed. */
function DeclaredGaps({ gaps }: { gaps: CncGap[] }) {
  return (
    <div className="cnc-gaps">
      <h4>{t("production.cncDeclaredGaps")}</h4>
      <table className="cnc-table">
        <thead>
          <tr>
            <th>{t("production.cncOpKind")}</th>
            <th>{t("production.cncGapSource")}</th>
            <th>{t("production.cncGapCause")}</th>
            <th>{t("production.cncGapMachines")}</th>
          </tr>
        </thead>
        <tbody>
          {gaps.map((gap) => (
            <tr key={gap.gap_id}>
              <td>
                {gapKindLabel(gap)}
                {gap.kit_sku ? ` · ${gap.kit_sku}` : ""}
                {gap.declared_value ? ` · ${gap.declared_value}` : ""}
                {gap.leaf_id || gap.bay_id
                  ? ` · ${[gap.bay_id, gap.leaf_id].filter(Boolean).join("/")}`
                  : ""}
              </td>
              <td>{gapSourceLabel(gap.source)}</td>
              <td>{gapCauseLabel(gap.cause)}</td>
              <td>
                <ul className="cnc-gap-machines">
                  {(gap.machines ?? []).map((check) => (
                    <li key={check.machine_id}>
                      {check.machine_code}:{" "}
                      {check.can_run ? t("production.cncGapCanRun") : gapCauseLabel(check.cause)}
                    </li>
                  ))}
                </ul>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CncProgramRow({
  program,
  programs,
  diff,
  onDownload,
  onCompare,
}: {
  program: CncProgram;
  programs: CncProgram[];
  diff: Record<string, ProgramDiff | "loading">;
  onDownload: (filename: string) => void;
  onCompare: (otherId: string) => void;
}) {
  const superseded = program.status === "SUPERSEDED";
  // Versions of the same member on the same machine — the only comparison
  // that makes physical sense.
  const siblings = programs.filter(
    (other) =>
      other.id !== program.id &&
      other.member_id === program.member_id &&
      other.machine_code === program.machine_code,
  );
  const result = diff[program.id];
  return (
    <li className={superseded ? "cnc-program cnc-program-stale" : "cnc-program"}>
      <span className="cnc-program-no">{program.program_no}</span>
      <span className="cnc-program-meta">
        {program.member_label} · {program.machine_code} · {program.operation_count}{" "}
        {t("production.cncOpsUnit")}
      </span>
      <span className={`cnc-verdict cnc-verdict-${program.verdict.toLowerCase()}`}>
        {tOptional(`production.cncVerdict${program.verdict}`) ?? program.verdict}
      </span>
      {program.plan_seed ? (
        <span className="cnc-program-seed">
          {t("production.cncPlanSeed")} {program.plan_seed}
        </span>
      ) : null}
      {superseded ? (
        <span className="cnc-stale">
          {program.superseded_by
            ? `${t("production.cncSupersededBy")} ${program.superseded_by.program_no}`
            : t("production.cncSuperseded")}
        </span>
      ) : (
        <span className="cnc-program-actions">
          {["operations.json", "operations.csv", "manifest.json"].map((filename) => (
            <button
              key={filename}
              type="button"
              className="cnc-program-file"
              onClick={() => onDownload(filename)}
            >
              {filename}
            </button>
          ))}
          {siblings.length ? (
            <button
              type="button"
              className="cnc-program-file"
              disabled={result === "loading"}
              onClick={() => {
                const other = siblings[siblings.length - 1];
                if (other) onCompare(other.id);
              }}
            >
              {t("production.cncCompare")}
            </button>
          ) : null}
        </span>
      )}
      {result && result !== "loading" ? <ProgramDiffView diff={result} /> : null}
    </li>
  );
}

/** Diff between two program versions — what physically changed in the file
 * before the new one goes to the cell. */
function ProgramDiffView({ diff }: { diff: ProgramDiff }) {
  return (
    <div className="cnc-diff">
      <p className="cnc-diff-counts">
        {t("production.cncDiffAdded")}: {diff.counts.added} · {t("production.cncDiffRemoved")}:{" "}
        {diff.counts.removed} · {t("production.cncDiffChanged")}: {diff.counts.changed} ·{" "}
        {t("production.cncDiffUnchanged")}: {diff.counts.unchanged}
      </p>
      {diff.changed.length ? (
        <table className="cnc-table">
          <thead>
            <tr>
              <th>{t("production.cncDiffOp")}</th>
              <th>{t("production.cncDiffField")}</th>
              <th>{t("production.cncDiffFrom")}</th>
              <th>{t("production.cncDiffTo")}</th>
            </tr>
          </thead>
          <tbody>
            {diff.changed.flatMap((change) =>
              Object.entries(change.fields).map(([field, values]) => (
                <tr key={`${change.operation_id}-${field}`}>
                  <td>{shortTechnicalId(change.operation_id)}</td>
                  <td>{DETAIL_KEYS[field] ?? field}</td>
                  <td>{String(values.from ?? "—")}</td>
                  <td>{String(values.to ?? "—")}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      ) : null}
      {diff.added.length || diff.removed.length ? (
        <p className="cnc-diff-ops">
          {[
            diff.added.length
              ? `${t("production.cncDiffAdded")}: ${diff.added
                  .map((op) => opKindLabel(String(op.kind ?? "")))
                  .join(", ")}`
              : "",
            diff.removed.length
              ? `${t("production.cncDiffRemoved")}: ${diff.removed
                  .map((op) => opKindLabel(String(op.kind ?? "")))
                  .join(", ")}`
              : "",
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      ) : null}
    </div>
  );
}

/** Face view of a member: four lanes (canto superior, exterior, interior,
 * canto inferior) with every op drawn at its declared u from the member
 * datum; edge work anchors at the member ends. Ops without a declared face
 * land on a "cara no declarada" lane — never guessed. */
const FACE_LANES = ["TOP_EDGE", "OUTSIDE_FACE", "INSIDE_FACE", "BOTTOM_EDGE"];

function MemberOpsDiagram({
  member,
  selectedOp,
  onSelectOp,
}: {
  member: CncMember;
  selectedOp: string | null;
  onSelectOp: (id: string | null) => void;
}) {
  const lengthMm = Math.max(parseFloat(member.length_mm || "0") || 0, 1);
  const W = 680;
  const pad = 26;
  const laneH = 22;
  const top = 22;
  const ux = (uMm: number) => pad + (uMm / lengthMm) * (W - pad * 2);

  function opU(op: CncOp): number | null {
    if (op.u_mm != null) {
      const u = parseFloat(op.u_mm);
      return op.reference === "member_end" ? ux(lengthMm - u) : ux(u);
    }
    if (op.face === "START_EDGE" || op.reference === "bar_left_edge") return pad;
    if (op.face === "END_EDGE") return W - pad;
    return null;
  }

  function opLane(op: CncOp): number {
    // Edge-cap ops draw on the (single) end lane, faceless ops on the last.
    if (op.face === "START_EDGE" || op.face === "END_EDGE") {
      return FACE_LANES.length;
    }
    const index = FACE_LANES.indexOf(op.face ?? "");
    return index === -1 ? FACE_LANES.length + 1 : index;
  }

  const lanes = [
    ...FACE_LANES.map((face) => ({ key: face, label: opFaceLabel(face) })),
    { key: "EDGES", label: t("production.cncLaneEdges") },
    { key: "NO_FACE", label: t("production.cncLaneNoFace") },
  ];
  const H = top + lanes.length * laneH + 16;
  const unplaced = member.operations.filter((op) => opU(op) === null);

  return (
    <div className="cnc-diagram">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={member.member_label}>
        <text x={pad} y={12} className="cnc-diagram-datum">
          {t("production.cncDiagramStart")}
        </text>
        <text x={W - pad} y={12} textAnchor="end" className="cnc-diagram-datum">
          {t("production.cncDiagramEnd")} · {fmtMm(member.length_mm)}
        </text>
        <line x1={pad} y1={16} x2={pad} y2={H - 10} className="cnc-diagram-datum-line" />
        <line x1={W - pad} y1={16} x2={W - pad} y2={H - 10} className="cnc-diagram-datum-line" />
        {lanes.map((lane, index) => {
          const y = top + index * laneH;
          return (
            <g key={lane.key}>
              <rect
                x={pad}
                y={y}
                width={W - pad * 2}
                height={laneH - 4}
                rx={2}
                className="cnc-diagram-bar"
              />
              <text x={4} y={y + laneH / 2 + 3} className="cnc-diagram-datum">
                {lane.label}
              </text>
            </g>
          );
        })}
        {member.operations.map((op, index) => {
          const x = opU(op);
          if (x === null) return null;
          const lane = opLane(op);
          const cy = top + lane * laneH + laneH / 2 - 2;
          const selected = op.operation_id === selectedOp;
          return (
            <g
              key={op.operation_id}
              className={selected ? "cnc-diagram-op is-selected" : "cnc-diagram-op"}
              onClick={() => onSelectOp(selected ? null : op.operation_id)}
              role="button"
              aria-label={`${index + 1} ${opLabel(op)}`}
            >
              <title>
                {`${index + 1} · ${opLabel(op)} · u=${op.u_mm ?? "—"} · ${opFaceLabel(op.face)}`}
              </title>
              <OpMark kind={op.kind} x={x} cy={cy} />
              <text x={x} y={cy - 8} textAnchor="middle" className="cnc-diagram-seq">
                {index + 1}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="cnc-diagram-legend">
        <span>{member.member_label}</span>
        {unplaced.length > 0 ? (
          <span className="cnc-diagram-missing">
            {t("production.cncDiagramMissing")}: {unplaced.map((op) => opLabel(op)).join(", ")}
          </span>
        ) : null}
      </p>
    </div>
  );
}

function OpMark({ kind, x, cy }: { kind: string; x: number; cy: number }) {
  switch (kind) {
    case "DRILL":
    case "DRAINAGE":
    case "VENTILATION":
      return (
        <circle cx={x} cy={cy} r={4.5} className={`cnc-mark cnc-mark-${kind.toLowerCase()}`} />
      );
    case "SLOT":
    case "ROUTING":
      return (
        <rect
          x={x - 9}
          y={cy - 3.5}
          width={18}
          height={7}
          rx={3.5}
          className={`cnc-mark cnc-mark-${kind.toLowerCase()}`}
        />
      );
    case "HANDLE_PREP":
    case "LOCK_PREP":
    case "HINGE_PREP":
    case "CYLINDER_PREP":
    case "HARDWARE_PREP":
      return (
        <g className="cnc-mark cnc-mark-hardware">
          <circle cx={x} cy={cy} r={5} />
          <line x1={x - 7} y1={cy} x2={x + 7} y2={cy} />
          <line x1={x} y1={cy - 7} x2={x} y2={cy + 7} />
        </g>
      );
    case "END_MACHINING":
    case "SAW_CUT":
    case "SAW_REFERENCE":
      return <rect x={x - 3} y={cy - 8} width={6} height={16} className="cnc-mark cnc-mark-edge" />;
    case "MILLING":
      return (
        <rect x={x - 6} y={cy - 5} width={12} height={10} className="cnc-mark cnc-mark-milling" />
      );
    default:
      return (
        <rect
          x={x - 4}
          y={cy - 4}
          width={8}
          height={8}
          transform={`rotate(45 ${x} ${cy})`}
          className="cnc-mark cnc-mark-custom"
        />
      );
  }
}
