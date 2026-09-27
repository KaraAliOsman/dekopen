import { useCallback, useEffect, useState } from "react";

import {
  productionOrderCncProgramGenerate,
  productionOrderCncReadiness,
} from "../../api/generated/dekopen";
import { apiFetchBlob } from "../../api/apiMutator";
import { fmtMm } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";

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
  created_at: string;
};

type CncIssue = {
  code: string;
  detail?: string;
} & Record<string, unknown>;

type CncReadinessData = {
  order_id: string;
  order_code: string;
  members: CncMember[];
  issues?: CncIssue[];
  machines: { id: string; code: string; name: string }[];
  programs: CncProgram[];
};

const OP_LABELS: Record<string, string> = {
  SAW_CUT: "production.cncKindSaw",
  DRILL: "production.cncKindDrill",
  SLOT: "production.cncKindSlot",
  DRAINAGE: "production.cncKindDrainage",
  VENTILATION: "production.cncKindVentilation",
  HANDLE_PREP: "production.cncKindHandle",
  LOCK_PREP: "production.cncKindLock",
  HINGE_PREP: "production.cncKindHinge",
  CORNER_CONNECTOR: "production.cncKindCorner",
  T_CONNECTOR: "production.cncKindTee",
  MILLING: "production.cncKindMilling",
  END_MACHINING: "production.cncKindEnd",
  ROUTING: "production.cncKindRouting",
  GASKET_MARK: "production.cncKindGasket",
  CUSTOM: "production.cncKindCustom",
};

const FACE_LABELS: Record<string, string> = {
  OUTSIDE_FACE: "production.cncFaceOutside",
  INSIDE_FACE: "production.cncFaceInside",
  TOP_EDGE: "production.cncFaceTop",
  BOTTOM_EDGE: "production.cncFaceBottom",
  START_EDGE: "production.cncFaceStart",
  END_EDGE: "production.cncFaceEnd",
};

function opKindLabel(kind: string): string {
  return tOptional(OP_LABELS[kind] ?? "") ?? kind;
}

function faceLabel(face: string | null): string {
  if (!face) return "—";
  return tOptional(FACE_LABELS[face] ?? "") ?? face;
}

function blockerText(blocker: CncVerdict): string {
  const key = `production.cncBlock_${blocker.code}`;
  const label = tOptional(key) ?? blocker.code;
  const values = Object.entries(blocker.detail)
    .filter(([k]) => k !== "host")
    .map(([k, v]) => `${k}=${v}`)
    .join(" · ");
  return values ? `${label}: ${values}` : label;
}

function issueText(issue: CncIssue): string {
  const key = `production.cncIssue_${issue.code}`;
  const label = tOptional(key) ?? issue.code;
  const context = Object.entries(issue)
    .filter(([k]) => !["code", "detail"].includes(k))
    .map(([k, v]) => `${k}=${v}`)
    .join(" · ");
  const detail = typeof issue.detail === "string" ? issue.detail : "";
  return [label, context, detail].filter(Boolean).join(" — ");
}

export function CncPanel({ orderId, canWrite }: { orderId: string; canWrite: boolean }) {
  const [data, setData] = useState<CncReadinessData | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [selectedOp, setSelectedOp] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await productionOrderCncReadiness(orderId);
      setData(response.data as CncReadinessData);
      setError(null);
    } catch {
      setError(t("production.cncLoadError"));
      setData(null);
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
      const apiErr = err as { detail?: string; error?: string };
      setError(apiErr.detail || apiErr.error || t("production.cncProgramError"));
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
          {!data ? (
            <p className="cnc-empty">{t("production.cncLoading")}</p>
          ) : data.members.length === 0 ? (
            <p className="cnc-empty">{t("production.cncNoOps")}</p>
          ) : (
            <>
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
              {data.programs.length ? (
                <div className="cnc-programs">
                  <h4>{t("production.cncPrograms")}</h4>
                  <ul>
                    {data.programs.map((program) => (
                      <li
                        key={program.id}
                        className={
                          program.status === "SUPERSEDED"
                            ? "cnc-program cnc-program-stale"
                            : "cnc-program"
                        }
                      >
                        <span className="cnc-program-no">{program.program_no}</span>
                        <span className="cnc-program-meta">
                          {program.member_label} · {program.machine_code} ·{" "}
                          {program.operation_count} {t("production.cncOpsUnit")}
                        </span>
                        <span
                          className={`cnc-verdict cnc-verdict-${program.verdict.toLowerCase()}`}
                        >
                          {tOptional(`production.cncVerdict${program.verdict}`) ?? program.verdict}
                        </span>
                        {program.status === "SUPERSEDED" ? (
                          <span className="cnc-stale">{t("production.cncSuperseded")}</span>
                        ) : (
                          <span className="cnc-program-actions">
                            {["operations.json", "operations.csv"].map((filename) => (
                              <button
                                key={filename}
                                type="button"
                                className="cnc-program-file"
                                onClick={() => void downloadProgram(program, filename)}
                              >
                                {filename}
                              </button>
                            ))}
                          </span>
                        )}
                      </li>
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
              <span
                className={`cnc-verdict cnc-verdict-${verdict.verdict.toLowerCase()}`}
                title={
                  verdict.blockers.length
                    ? verdict.blockers.map(blockerText).join("\n")
                    : verdict.warnings.length
                      ? verdict.warnings.map(blockerText).join("\n")
                      : undefined
                }
              >
                {tOptional(`production.cncVerdict${verdict.verdict}`) ?? verdict.verdict}
              </span>
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
            <MemberOpsDiagram member={member} selectedOp={selectedOp} onSelectOp={onSelectOp} />
            <table className="cnc-ops">
              <thead>
                <tr>
                  <th>#</th>
                  <th>{t("production.cncOpKind")}</th>
                  <th>u (mm)</th>
                  <th>{t("production.cncFace")}</th>
                  <th>{t("production.cncReference")}</th>
                  <th>{t("production.cncDepth")}</th>
                  <th>{t("production.cncTool")}</th>
                </tr>
              </thead>
              <tbody>
                {member.operations.map((op, index) => (
                  <tr
                    key={op.operation_id}
                    className={
                      selectedOp === op.operation_id ? "cnc-op-row is-selected" : "cnc-op-row"
                    }
                    onClick={() =>
                      onSelectOp(selectedOp === op.operation_id ? null : op.operation_id)
                    }
                  >
                    <td>{index + 1}</td>
                    <td>{opKindLabel(op.kind)}</td>
                    <td>{op.u_mm ?? "—"}</td>
                    <td>{faceLabel(op.face)}</td>
                    <td>{op.reference ?? "—"}</td>
                    <td>{op.depth_mm ?? "—"}</td>
                    <td>{op.tool_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      ) : null}
    </>
  );
}

/**
 * Machine-neutral member bar: every machining op placed on the member's own
 * axis (u from the member START datum; member_end ops anchored at the end).
 * Clicking a mark highlights the matching row — this is the human check the
 * operator does before a program is generated.
 */
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
  const W = 640;
  const H = 86;
  const pad = 26;
  const barY = 42;
  const barH = 14;
  const ux = (uMm: number) => pad + (uMm / lengthMm) * (W - pad * 2);

  function opX(op: CncOp): number | null {
    if (op.u_mm != null) {
      const u = parseFloat(op.u_mm);
      return op.reference === "member_end" ? ux(lengthMm - u) : ux(u);
    }
    if (op.reference === "bar_left_edge") return pad + 3;
    if (op.face === "START_EDGE") return pad;
    if (op.face === "END_EDGE") return W - pad;
    return null;
  }

  const unplaced = member.operations.filter((op) => opX(op) === null);

  return (
    <div className="cnc-diagram">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={member.member_label}>
        <text x={pad} y={14} className="cnc-diagram-datum">
          {t("production.cncDiagramStart")}
        </text>
        <text x={W - pad} y={14} textAnchor="end" className="cnc-diagram-datum">
          {t("production.cncDiagramEnd")} · {fmtMm(member.length_mm)}
        </text>
        <line x1={pad} y1={22} x2={pad} y2={barY - 4} className="cnc-diagram-datum-line" />
        <line x1={W - pad} y1={22} x2={W - pad} y2={barY - 4} className="cnc-diagram-datum-line" />
        <rect
          x={pad}
          y={barY}
          width={W - pad * 2}
          height={barH}
          rx={2}
          className="cnc-diagram-bar"
        />
        {member.operations.map((op, index) => {
          const x = opX(op);
          if (x === null) return null;
          const selected = op.operation_id === selectedOp;
          const cy = barY + barH / 2;
          return (
            <g
              key={op.operation_id}
              className={selected ? "cnc-diagram-op is-selected" : "cnc-diagram-op"}
              onClick={() => onSelectOp(selected ? null : op.operation_id)}
              role="button"
              aria-label={`${index + 1} ${opKindLabel(op.kind)}`}
            >
              <title>
                {`${index + 1} · ${opKindLabel(op.kind)} · u=${op.u_mm ?? "—"} · ${faceLabel(op.face)}`}
              </title>
              <OpMark kind={op.kind} x={x} cy={cy} />
              <text x={x} y={barY - 6} textAnchor="middle" className="cnc-diagram-seq">
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
            {t("production.cncDiagramMissing")}:{" "}
            {unplaced.map((op) => opKindLabel(op.kind)).join(", ")}
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
