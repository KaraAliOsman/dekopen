import { useCallback, useEffect, useState } from "react";

import {
  productionCncMachineCreate,
  productionCncMachineUpdate,
  productionCncToolCreate,
  productionCncToolUpdate,
  productionCncWorkspace,
} from "../../api/generated/dekopen";
import { ApiError } from "../../api/apiMutator";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { fmtMm, formatDateTime } from "../../format";
import { t, tOptional } from "../../i18n/es-CL";
import { ORDER_STATUS_KEY } from "./board";

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
  machine_type: string;
  axes_count: number | null;
  travel_x_mm: string | null;
  travel_y_mm: string | null;
  travel_z_mm: string | null;
  emitter_implemented?: boolean;
};

type CncAuditEvent = {
  id: string;
  entity: string;
  entity_id: string;
  entity_code: string;
  action: string;
  actor_id: string | null;
  changed?: Record<string, { from: unknown; to: unknown }>;
  created_at: string;
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
  audit?: CncAuditEvent[];
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

const MACHINE_TYPES = ["MACHINING_CENTER", "ROUTER", "SAW_DRILL_LINE", "COPY_ROUTER", "OTHER"];

const MACHINE_TYPE_LABELS: Record<string, string> = {
  MACHINING_CENTER: "production.cncMachineTypeCenter",
  ROUTER: "production.cncMachineTypeRouter",
  SAW_DRILL_LINE: "production.cncMachineTypeSawDrill",
  COPY_ROUTER: "production.cncMachineTypeCopy",
  OTHER: "production.cncMachineTypeOther",
};

function machineTypeLabel(machineType: string): string {
  return tOptional(MACHINE_TYPE_LABELS[machineType] ?? "") ?? t("production.cncMachineTypeOther");
}

const AUDIT_ACTIONS: Record<string, string> = {
  created: "production.cncAuditCreated",
  updated: "production.cncAuditUpdated",
  deactivated: "production.cncAuditDeactivated",
  reactivated: "production.cncAuditReactivated",
};

const AUDIT_FIELDS: Record<string, string> = {
  code: "código",
  name: "nombre",
  kind: "tipo",
  active: "activa",
  diameter_mm: "⌀ mm",
  working_length_mm: "largo útil",
  max_depth_mm: "profundidad",
  compatible_kinds: "operaciones",
  manufacturer: "fabricante",
  model: "modelo",
  controller_family: "control",
  coordinate_systems: "coordenadas",
  supported_kinds: "operaciones",
  supported_faces: "caras",
  max_member_length_mm: "largo máx",
  safe_margin_mm: "margen",
  clamp_zones: "mordazas",
  tool_ids: "magazine",
  postprocessor_id: "emisor",
  postprocessor_version: "versión emisor",
  units: "unidades",
  encoding: "codificación",
  machine_type: "tipo",
  axes_count: "ejes",
  travel_x_mm: "carrera X",
  travel_y_mm: "carrera Y",
  travel_z_mm: "carrera Z",
};

function auditText(event: CncAuditEvent): string {
  const action = tOptional(AUDIT_ACTIONS[event.action] ?? "") ?? event.action;
  const entity =
    event.entity === "machine" ? t("production.cncAuditMachine") : t("production.cncAuditTool");
  const fields = Object.entries(event.changed ?? {})
    .map(([key]) => AUDIT_FIELDS[key] ?? key)
    .join(", ");
  return fields
    ? `${entity} ${event.entity_code} — ${action} (${fields})`
    : `${entity} ${event.entity_code} — ${action}`;
}

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

/** Tool-machine kinds (SAW_BLADE, DRILL_BIT, …) are a different enum than
 * operation kinds — separate label map so neither leaks raw. */
const TOOL_KIND_LABELS: Record<string, string> = {
  SAW_BLADE: "production.cncToolKindSaw",
  DRILL_BIT: "production.cncToolKindDrill",
  END_MILL: "production.cncToolKindEndMill",
  ROUTER_BIT: "production.cncToolKindRouter",
  PUNCH: "production.cncToolKindPunch",
  MARKING: "production.cncToolKindMarking",
  CUSTOM: "production.cncToolKindCustom",
};

function kindLabel(kind: string): string {
  return tOptional(KIND_LABELS[kind] ?? "") ?? kind;
}

function toolKindLabel(kind: string): string {
  return tOptional(TOOL_KIND_LABELS[kind] ?? "") ?? kind;
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
    const body = {
      code: String(toolForm.code ?? ""),
      name: String(toolForm.name ?? ""),
      kind: String(toolForm.kind ?? "DRILL_BIT"),
      diameter_mm: String(toolForm.diameter_mm || "") || null,
      working_length_mm: String(toolForm.working_length_mm || "") || null,
      max_depth_mm: String(toolForm.max_depth_mm || "") || null,
      compatible_kinds: (toolForm.compatible_kinds as string[] | undefined)?.length
        ? (toolForm.compatible_kinds as string[])
        : null,
    };
    try {
      if (toolForm.id) {
        await productionCncToolUpdate(String(toolForm.id), body);
      } else {
        await productionCncToolCreate(body);
      }
      setToolForm(null);
      await load();
    } catch (err) {
      setError(extractError(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleToolActive(tool: CncTool) {
    setBusy(true);
    try {
      await productionCncToolUpdate(tool.id, { active: !tool.active });
      await load();
    } catch (err) {
      setError(extractError(err));
    } finally {
      setBusy(false);
    }
  }

  async function toggleMachineActive(machine: CncMachine) {
    setBusy(true);
    try {
      await productionCncMachineUpdate(machine.id, { active: !machine.active });
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
    const body = {
      code: String(machineForm.code ?? ""),
      name: String(machineForm.name ?? ""),
      manufacturer: String(machineForm.manufacturer ?? ""),
      model: String(machineForm.model ?? ""),
      max_member_length_mm: String(machineForm.max_member_length_mm || "") || null,
      safe_margin_mm: String(machineForm.safe_margin_mm || "") || null,
      machine_type: String(machineForm.machine_type || "MACHINING_CENTER"),
      axes_count: String(machineForm.axes_count || "") || null,
      travel_x_mm: String(machineForm.travel_x_mm || "") || null,
      travel_y_mm: String(machineForm.travel_y_mm || "") || null,
      travel_z_mm: String(machineForm.travel_z_mm || "") || null,
      postprocessor_id: String(machineForm.postprocessor_id || "neutral-ops-v1"),
      supported_kinds: (machineForm.supported_kinds as string[] | undefined)?.length
        ? (machineForm.supported_kinds as string[])
        : null,
      supported_faces: (machineForm.supported_faces as string[] | undefined)?.length
        ? (machineForm.supported_faces as string[])
        : null,
      tool_ids: (machineForm.tool_ids as string[] | undefined) ?? [],
    };
    try {
      if (machineForm.id) {
        await productionCncMachineUpdate(String(machineForm.id), body);
      } else {
        await productionCncMachineCreate(body);
      }
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
                          machine_type: "MACHINING_CENTER",
                          axes_count: "3",
                          travel_x_mm: "",
                          travel_y_mm: "",
                          travel_z_mm: "",
                          postprocessor_id: "neutral-ops-v1",
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
                        <th>{t("production.cncMachineType")}</th>
                        <th>{t("production.cncMachineAxes")}</th>
                        <th>{t("production.cncMachineEnvelope")}</th>
                        <th>{t("production.cncMachineKinds")}</th>
                        <th>{t("production.cncMachineFaces")}</th>
                        <th>{t("production.cncMachineMagazine")}</th>
                        <th>{t("production.cncMachineEmitter")}</th>
                        {canWrite ? <th /> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {data.machines.map((machine) => (
                        <tr key={machine.id} className={machine.active ? "" : "cnc-row-inactive"}>
                          <td>
                            <strong>{machine.code}</strong>
                            {!machine.active ? (
                              <div className="cnc-member-meta">{t("production.cncInactive")}</div>
                            ) : null}
                            <div className="cnc-member-meta">
                              {[
                                machine.name,
                                machine.manufacturer || machine.model
                                  ? `${machine.manufacturer} ${machine.model}`.trim()
                                  : "",
                              ]
                                .filter(Boolean)
                                .join(" · ")}
                            </div>
                          </td>
                          <td>{machineTypeLabel(machine.machine_type)}</td>
                          <td>{machine.axes_count ?? "—"}</td>
                          <td>
                            {machine.max_member_length_mm
                              ? `≤ ${fmtMm(machine.max_member_length_mm)} mm`
                              : "—"}
                            {machine.travel_x_mm || machine.travel_y_mm || machine.travel_z_mm
                              ? ` · ${[
                                  machine.travel_x_mm,
                                  machine.travel_y_mm,
                                  machine.travel_z_mm,
                                ]
                                  .filter(Boolean)
                                  .map((v) => fmtMm(v))
                                  .join("×")} mm`
                              : ""}
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
                          <td>
                            {machine.postprocessor_id}
                            {machine.emitter_implemented === false ? (
                              <div className="cnc-emitter-missing">
                                {t("production.cncGapCauseEmitter")}
                              </div>
                            ) : null}
                          </td>
                          {canWrite ? (
                            <td className="cnc-actions">
                              <button
                                type="button"
                                className="cnc-add"
                                onClick={() =>
                                  setMachineForm({
                                    id: machine.id,
                                    code: machine.code,
                                    name: machine.name,
                                    manufacturer: machine.manufacturer,
                                    model: machine.model,
                                    max_member_length_mm: machine.max_member_length_mm ?? "",
                                    safe_margin_mm: machine.safe_margin_mm ?? "",
                                    machine_type: machine.machine_type ?? "MACHINING_CENTER",
                                    axes_count:
                                      machine.axes_count != null ? String(machine.axes_count) : "",
                                    travel_x_mm: machine.travel_x_mm ?? "",
                                    travel_y_mm: machine.travel_y_mm ?? "",
                                    travel_z_mm: machine.travel_z_mm ?? "",
                                    postprocessor_id: machine.postprocessor_id ?? "neutral-ops-v1",
                                    supported_kinds: machine.supported_kinds ?? [],
                                    supported_faces: machine.supported_faces ?? [],
                                    tool_ids: machine.tool_ids,
                                  })
                                }
                              >
                                {t("ui.edit")}
                              </button>
                              <button
                                type="button"
                                className="cnc-add"
                                disabled={busy}
                                onClick={() => void toggleMachineActive(machine)}
                              >
                                {machine.active
                                  ? t("production.cncDeactivate")
                                  : t("production.cncActivate")}
                              </button>
                            </td>
                          ) : null}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {machineForm ? (
                  <form
                    noValidate
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
                    <div className="cnc-form-row">
                      <label>
                        {t("production.cncMachineType")}
                        <select
                          value={String(machineForm.machine_type ?? "MACHINING_CENTER")}
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              machine_type: e.target.value,
                            })
                          }
                        >
                          {MACHINE_TYPES.map((machineType) => (
                            <option key={machineType} value={machineType}>
                              {machineTypeLabel(machineType)}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        {t("production.cncMachineAxes")}
                        <input
                          value={String(machineForm.axes_count ?? "")}
                          inputMode="numeric"
                          placeholder="3"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              axes_count: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineEmitter")}
                        <input
                          value={String(machineForm.postprocessor_id ?? "")}
                          placeholder="neutral-ops-v1"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              postprocessor_id: e.target.value,
                            })
                          }
                        />
                      </label>
                    </div>
                    <div className="cnc-form-row">
                      <label>
                        {t("production.cncMachineTravelX")}
                        <input
                          value={String(machineForm.travel_x_mm ?? "")}
                          inputMode="decimal"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              travel_x_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineTravelY")}
                        <input
                          value={String(machineForm.travel_y_mm ?? "")}
                          inputMode="decimal"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              travel_y_mm: e.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        {t("production.cncMachineTravelZ")}
                        <input
                          value={String(machineForm.travel_z_mm ?? "")}
                          inputMode="decimal"
                          onChange={(e) =>
                            setMachineForm({
                              ...machineForm,
                              travel_z_mm: e.target.value,
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
                <p className="cnc-hint">{t("production.cncToolCodeHint")}</p>
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
                        {canWrite ? <th /> : null}
                      </tr>
                    </thead>
                    <tbody>
                      {data.tools.map((tool) => (
                        <tr key={tool.id} className={tool.active ? "" : "cnc-row-inactive"}>
                          <td>
                            <strong>{tool.code}</strong>
                            {!tool.active ? (
                              <div className="cnc-member-meta">{t("production.cncInactive")}</div>
                            ) : null}
                          </td>
                          <td>{tool.name}</td>
                          <td>{toolKindLabel(tool.kind)}</td>
                          <td>{tool.diameter_mm ?? "—"}</td>
                          <td>{tool.max_depth_mm ?? "—"}</td>
                          <td>
                            {tool.compatible_kinds
                              ? tool.compatible_kinds.map(kindLabel).join(", ")
                              : t("production.cncAllKinds")}
                          </td>
                          {canWrite ? (
                            <td className="cnc-actions">
                              <button
                                type="button"
                                className="cnc-add"
                                onClick={() =>
                                  setToolForm({
                                    id: tool.id,
                                    code: tool.code,
                                    name: tool.name,
                                    kind: tool.kind,
                                    diameter_mm: tool.diameter_mm ?? "",
                                    working_length_mm: tool.working_length_mm ?? "",
                                    max_depth_mm: tool.max_depth_mm ?? "",
                                    compatible_kinds: tool.compatible_kinds ?? [],
                                  })
                                }
                              >
                                {t("ui.edit")}
                              </button>
                              <button
                                type="button"
                                className="cnc-add"
                                disabled={busy}
                                onClick={() => void toggleToolActive(tool)}
                              >
                                {tool.active
                                  ? t("production.cncDeactivate")
                                  : t("production.cncActivate")}
                              </button>
                            </td>
                          ) : null}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {toolForm ? (
                  <form
                    noValidate
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
                              {toolKindLabel(kind)}
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
                      {data.orders.map((order) => {
                        const orderStatus = order.status;
                        return (
                          <tr key={order.order_id}>
                            <td>
                              <strong>{order.order_code}</strong>
                            </td>
                            <td>
                              {ORDER_STATUS_KEY[orderStatus]
                                ? t(ORDER_STATUS_KEY[orderStatus])
                                : "—"}
                            </td>
                            <td>
                              {order.programs_total === 0
                                ? "—"
                                : `${order.programs_current}/${order.programs_total}`}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
              {data.audit?.length ? (
                <div>
                  <h3>{t("production.cncAudit")}</h3>
                  <ul className="cnc-audit">
                    {data.audit.map((event) => (
                      <li key={event.id}>
                        <span className="cnc-audit-date">{formatDateTime(event.created_at)}</span>
                        {auditText(event)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </div>
      ) : null}
    </section>
  );
}
