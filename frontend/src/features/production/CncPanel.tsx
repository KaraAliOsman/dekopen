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

type CncReadinessData = {
  order_id: string;
  order_code: string;
  members: CncMember[];
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

export function CncPanel({ orderId, canWrite }: { orderId: string; canWrite: boolean }) {
  const [data, setData] = useState<CncReadinessData | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

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
  onGenerate,
}: {
  member: CncMember;
  machines: { id: string; code: string }[];
  canWrite: boolean;
  busy: boolean;
  expanded: boolean;
  onToggle: () => void;
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
                  <tr key={op.operation_id}>
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
