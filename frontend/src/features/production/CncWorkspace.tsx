import { useCallback, useEffect, useState } from "react";

import {
  productionCncMachineCreate,
  productionCncToolCreate,
  productionCncWorkspace,
} from "../../api/generated/dekopen";
import { ApiError } from "../../api/apiMutator";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { fmtMm } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";

type CncTool = {
  id: string;
  code: string;
  name: string;
  kind: string;
  diameter_mm: string | null;
  working_length_mm: string | null;
  max_depth_mm: string | null;
  compatible_kinds: string[] | null;
  active: boolean;
};

type CncMachine = {
  id: string;
  code: string;
  name: string;
  manufacturer: string;
  model: string;
  supported_kinds: string[] | null;
  supported_faces: string[] | null;
  max_member_length_mm: string | null;
  safe_margin_mm: string | null;
  clamp_zones: { start_mm: string; end_mm: string; label: string }[];
  tool_ids: string[];
  postprocessor_id: string;
  active: boolean;
};

type WorkspaceData = {
  machines: CncMachine[];
  tools: CncTool[];
  orders: {
    order_id: string;
    order_code: string;
    status: string;
    programs_total: number;
    programs_current: number;
  }[];
};

const TOOL_KINDS = [
  "SAW_BLADE",
  "DRILL_BIT",
  "END_MILL",
  "ROUTER_BIT",
  "PUNCH",
  "MARKING",
  "CUSTOM",
];

const OP_KINDS = [
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
];

const FACES = ["OUTSIDE_FACE", "INSIDE_FACE", "TOP_EDGE", "BOTTOM_EDGE", "START_EDGE", "END_EDGE"];

const KIND_LABELS: Record<string, string> = {
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

function kindLabel(kind: string): string {
  return tOptional(KIND_LABELS[kind] ?? "") ?? kind;
}

function faceLabel(face: string): string {
  return tOptional(FACE_LABELS[face] ?? "") ?? face;
}

export function CncWorkspace() {
  const auth = useAuthSession();
  const role = auth.me?.active_organization?.role ?? "";
  const canWrite = role === "OWNER" || role === "WORKSHOP_MANAGER";
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [toolForm, setToolForm] = useState<Record<string, string | string[]> | null>(null);
  const [machineForm, setMachineForm] = useState<Record<string, string | string[]> | null>(null);

  const load = useCallback(async () => {
    try {
      const response = await productionCncWorkspace();
      setData(response.data as WorkspaceData);
      setError(null);
    } catch {
      setError(t("production.cncLoadError"));
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void load();
  }, [open, load]);

  function extractError(err: unknown): string {
    if (err instanceof ApiError) {
      const detail = (err.payload as { error?: { detail?: string } } | null)?.error?.detail;
      if (typeof detail === "string" && detail) return detail;
    }
    return t("production.cncSaveError");
  }

  async function saveTool() {
    if (!toolForm) return;
    setBusy(true);
    try {
      await productionCncToolCreate({
        code: String(toolForm.code ?? ""),
        name: String(toolForm.name ?? ""),
        kind: String(toolForm.kind ?? "DRILL_BIT"),
        diameter_mm: String(toolForm.diameter_mm || "") || null,
        working_length_mm: String(toolForm.working_length_mm || "") || null,
        max_depth_mm: String(toolForm.max_depth_mm || "") || null,
        compatible_kinds: (toolForm.compatible_kinds as string[] | undefined)?.length
          ? (toolForm.compatible_kinds as string[])
          : null,
      });
      setToolForm(null);
      await load();
    } catch (err) {
      setError(extractError(err));
    } finally {
      setBusy(false);
    }
  }

  async function saveMachine() {
    if (!machineForm) return;
    setBusy(true);
    try {
      await productionCncMachineCreate({
        code: String(machineForm.code ?? ""),
        name: String(machineForm.name ?? ""),
        manufacturer: String(machineForm.manufacturer ?? ""),
        model: String(machineForm.model ?? ""),
        max_member_length_mm: String(machineForm.max_member_length_mm || "") || null,
        safe_margin_mm: String(machineForm.safe_margin_mm || "") || null,
        supported_kinds: (machineForm.supported_kinds as string[] | undefined)?.length
          ? (machineForm.supported_kinds as string[])
          : null,
        supported_faces: (machineForm.supported_faces as string[] | undefined)?.length
          ? (machineForm.supported_faces as string[])
          : null,
        tool_ids: (machineForm.tool_ids as string[] | undefined) ?? [],
      });
      setMachineForm(null);
      await load();
    } catch (err) {
      setError(extractError(err));
    } finally {
      setBusy(false);
    }
  }

  function toggleListValue(
    form: Record<string, string | string[]>,
    key: string,
    value: string,
    setter: (next: Record<string, string | string[]>) => void,
  ) {
    const current = (form[key] as string[] | undefined) ?? [];
    setter({
      ...form,
      [key]: current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value],
    });
  }

  return (
    <section className="cnc-workspace">
      <button
        type="button"
        className="cnc-panel-toggle"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {t("production.cncWorkspaceTitle")}
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
          ) : (
            <div className="cnc-workspace-grid">
              <div>
                <div className="cnc-section-head">
                  <h3>{t("production.cncMachines")}</h3>
                  {canWrite && !machineForm ? (
                    <button
                      type="button"
                      className="cnc-add"
                      onClick={() =>
                        setMachineForm({
                          code: "",
                          name: "",
                          manufacturer: "",
                          model: "",
                          max_member_length_mm: "",
                          safe_margin_mm: "",
                          supported_kinds: [],
                          supported_faces: [],
                          tool_ids: [],
                        })
                      }
                    >
                      {t("production.cncMachineAdd")}
                    </button>
                  ) : null}
                </div>
                {data.machines.length === 0 ? (
                  <p className="cnc-empty">{t("production.cncMachinesEmpty")}</p>
                ) : (
                  <table className="cnc-table">
                    <thead>
                      <tr>
                        <th>{t("production.cncMachineCode")}</th>
                        <th>{t("production.cncMachineName")}</th>
                        <th>{t("production.cncMachineEnvelope")}</th>
                        <th>{t("production.cncMachineKinds")}</th>
                        <th>{t("production.cncMachineFaces")}</th>
                        <th>{t("production.cncMachineMagazine")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.machines.map((machine) => (
                        <tr key={machine.id}>
                          <td>
                            <strong>{machine.code}</strong>
                            {machine.manufacturer
                              ? ` · ${machine.manufacturer} ${machine.model}`
                              : ""}
                          </td>
                          <td>{machine.name}</td>
                          <td>
                            {machine.max_member_length_mm
                              ? `≤ ${fmtMm(machine.max_member_length_mm)} mm`
                              : "—"}
                          </td>
                          <td>
                            {machine.supported_kinds
                              ? machine.supported_kinds.map(kindLabel).join(", ")
                              : t("production.cncAllKinds")}
                          </td>
                          <td>
                            {machine.supported_faces
                              ? machine.supported_faces.map(faceLabel).join(", ")
                              : t("production.cncAllFaces")}
                          </td>
                          <td>{machine.tool_ids.length}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {machineForm ? (
                  <form
                    className="cnc-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void saveMachine();
                    }}
                  >
                    <div className="cnc-form-row">
                      <label>
                        {t("production.cncMachineCode")}
                        <input
                          value={String(machineForm.code ?? "")}
                          required
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              code: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineName")}
                        <input
                          value={String(machineForm.name ?? "")}
                          required
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              name: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineManufacturer")}
                        <input
                          value={String(machineForm.manufacturer ?? "")}
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              manufacturer: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineModel")}
                        <input
                          value={String(machineForm.model ?? "")}
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              model: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="cnc-form-row">
                      <label>
                        {t("production.cncMachineMaxLength")}
                        <input
                          value={String(machineForm.max_member_length_mm ?? "")}
                          inputMode="decimal"
                          placeholder="3500"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              max_member_length_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineMargin")}
                        <input
                          value={String(machineForm.safe_margin_mm ?? "")}
                          inputMode="decimal"
                          placeholder="25"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              safe_margin_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <fieldset className="cnc-form-group">
                      <legend>{t("production.cncMachineKinds")}</legend>
                      <div className="cnc-checks">
                        {OP_KINDS.map((kind) => (
                          <label key={kind}>
                            <input
                              type="checkbox"
                              checked={(
                                (machineForm.supported_kinds as string[] | undefined) ?? []
                              ).includes(kind)}
                              onChange={() =>
                                toggleListValue(
                                  machineForm,
                                  "supported_kinds",
                                  kind,
                                  setMachineForm,
                                )
                              }
                            />
                            {kindLabel(kind)}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <fieldset className="cnc-form-group">
                      <legend>{t("production.cncMachineFaces")}</legend>
                      <div className="cnc-checks">
                        {FACES.map((face) => (
                          <label key={face}>
                            <input
                              type="checkbox"
                              checked={(
                                (machineForm.supported_faces as string[] | undefined) ?? []
                              ).includes(face)}
                              onChange={() =>
                                toggleListValue(
                                  machineForm,
                                  "supported_faces",
                                  face,
                                  setMachineForm,
                                )
                              }
                            />
                            {faceLabel(face)}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <fieldset className="cnc-form-group">
                      <legend>{t("production.cncMachineMagazine")}</legend>
                      <div className="cnc-checks">
                        {data.tools.map((tool) => (
                          <label key={tool.id}>
                            <input
                              type="checkbox"
                              checked={(
                                (machineForm.tool_ids as string[] | undefined) ?? []
                              ).includes(tool.id)}
                              onChange={() =>
                                toggleListValue(machineForm, "tool_ids", tool.id, setMachineForm)
                              }
                            />
                            {tool.code} — {tool.name}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <div className="cnc-form-actions">
                      <button type="submit" disabled={busy}>
                        {t("production.cncSave")}
                      </button>
                      <button type="button" onClick={() => setMachineForm(null)} disabled={busy}>
                        {t("ui.cancel")}
                      </button>
                    </div>
                  </form>
                ) : null}
              </div>
              <div>
                <div className="cnc-section-head">
                  <h3>{t("production.cncTools")}</h3>
                  {canWrite && !toolForm ? (
                    <button
                      type="button"
                      className="cnc-add"
                      onClick={() =>
                        setToolForm({
                          code: "",
                          name: "",
                          kind: "DRILL_BIT",
                          diameter_mm: "",
                          working_length_mm: "",
                          max_depth_mm: "",
                          compatible_kinds: [],
                        })
                      }
                    >
                      {t("production.cncToolAdd")}
                    </button>
                  ) : null}
                </div>
                {data.tools.length === 0 ? (
                  <p className="cnc-empty">{t("production.cncToolsEmpty")}</p>
                ) : (
                  <table className="cnc-table">
                    <thead>
                      <tr>
                        <th>{t("production.cncToolCode")}</th>
                        <th>{t("production.cncToolName")}</th>
                        <th>{t("production.cncToolKind")}</th>
                        <th>⌀ mm</th>
                        <th>{t("production.cncToolDepth")}</th>
                        <th>{t("production.cncToolKinds")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.tools.map((tool) => (
                        <tr key={tool.id}>
                          <td>
                            <strong>{tool.code}</strong>
                          </td>
                          <td>{tool.name}</td>
                          <td>{tool.kind}</td>
                          <td>{tool.diameter_mm ?? "—"}</td>
                          <td>{tool.max_depth_mm ?? "—"}</td>
                          <td>
                            {tool.compatible_kinds
                              ? tool.compatible_kinds.map(kindLabel).join(", ")
                              : t("production.cncAllKinds")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {toolForm ? (
                  <form
                    className="cnc-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void saveTool();
                    }}
                  >
                    <div className="cnc-form-row">
                      <label>
                        {t("production.cncToolCode")}
                        <input
                          value={toolForm.code ?? ""}
                          required
                          onChange={(e) => setToolForm({ ...toolForm, code: e.target.value })}
                        />
                      </label>
                      <label>
                        {t("production.cncToolName")}
                        <input
                          value={toolForm.name ?? ""}
                          required
                          onChange={(e) => setToolForm({ ...toolForm, name: e.target.value })}
                        />
                      </label>
                      <label>
                        {t("production.cncToolKind")}
                        <select
                          value={toolForm.kind ?? "DRILL_BIT"}
                          onChange={(e) => setToolForm({ ...toolForm, kind: e.target.value })}
                        >
                          {TOOL_KINDS.map((kind) => (
                            <option key={kind} value={kind}>
                              {kind}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="cnc-form-row">
                      <label>
                        ⌀ mm
                        <input
                          value={toolForm.diameter_mm ?? ""}
                          inputMode="decimal"
                          onChange={(e) =>
                            setToolForm({
                              ...toolForm,
                              diameter_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncToolLength")}
                        <input
                          value={toolForm.working_length_mm ?? ""}
                          inputMode="decimal"
                          onChange={(e) =>
                            setToolForm({
                              ...toolForm,
                              working_length_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncToolDepth")}
                        <input
                          value={toolForm.max_depth_mm ?? ""}
                          inputMode="decimal"
                          onChange={(e) =>
                            setToolForm({
                              ...toolForm,
                              max_depth_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <fieldset className="cnc-form-group">
                      <legend>{t("production.cncToolKinds")}</legend>
                      <div className="cnc-checks">
                        {OP_KINDS.map((kind) => (
                          <label key={kind}>
                            <input
                              type="checkbox"
                              checked={(
                                (toolForm.compatible_kinds as unknown | undefined as
                                  string[] | undefined) ?? []
                              ).includes(kind)}
                              onChange={() => {
                                const current =
                                  (toolForm.compatible_kinds as unknown as string[] | undefined) ??
                                  [];
                                setToolForm({
                                  ...toolForm,
                                  compatible_kinds: current.includes(kind)
                                    ? current.filter((k) => k !== kind)
                                    : [...current, kind],
                                });
                              }}
                            />
                            {kindLabel(kind)}
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <div className="cnc-form-actions">
                      <button type="submit" disabled={busy}>
                        {t("production.cncSave")}
                      </button>
                      <button type="button" onClick={() => setToolForm(null)} disabled={busy}>
                        {t("ui.cancel")}
                      </button>
                    </div>
                  </form>
                ) : null}
              </div>
              <div>
                <h3>{t("production.cncOrders")}</h3>
                {data.orders.length === 0 ? (
                  <p className="cnc-empty">{t("production.cncOrdersEmpty")}</p>
                ) : (
                  <table className="cnc-table">
                    <thead>
                      <tr>
                        <th>{t("production.cncOrderCode")}</th>
                        <th>{t("production.cncOrderStatus")}</th>
                        <th>{t("production.cncOrderPrograms")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.orders.map((order) => (
                        <tr key={order.order_id}>
                          <td>
                            <strong>{order.order_code}</strong>
                          </td>
                          <td>{tOptional(`production.order${order.status}`) ?? order.status}</td>
                          <td>
                            {order.programs_total === 0
                              ? "—"
                              : `${order.programs_current}/${order.programs_total}`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
