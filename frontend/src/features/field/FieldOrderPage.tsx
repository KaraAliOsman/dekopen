import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  fieldChecklistSave,
  fieldIncidentsReport,
  fieldMeasurementSubmit,
  fieldOrderCard,
  mountingRulesList,
  productionOrderDeliveryConfirm,
  productionOrderDeliveryConfirmation,
} from "../../api/generated/dekopen";
import type {
  FieldOrderCard,
  InstallationCheckItems,
  SiteIncidentKindEnum,
  VanoMeasurementRequestWallType,
} from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { t, tDynamic } from "../../i18n/es-CL";
import { DeniedState, ErrorState, Icon, LoadingState, StatusChip } from "../../ui";
import SignaturePad, { type SignaturePadHandle } from "../production/SignaturePad";
import { ORDER_STATUS_KEY } from "../production/board";

import "./field.css";
import { outboxEnqueue, outboxFlush, outboxList } from "./outbox";
import { PhotoField, type FieldPhoto } from "./PhotoField";

const FIELD_ROLES = ["OWNER", "WORKSHOP_MANAGER", "INSTALLER"];
const CHECK_ITEMS = ["installed", "leveled", "sealed", "adjusted", "clean"] as const;
const INCIDENT_KINDS = ["DAMAGE", "WRONG_MEASURE", "MISSING", "ADJUSTMENT"] as const;
const WALL_TYPES = ["MASONRY", "CONCRETE", "PARTITION", "WOOD"] as const;

type CheckKey = (typeof CHECK_ITEMS)[number];

function newOpKey(): string {
  return crypto.randomUUID();
}

type MutableCard = {
  order: {
    id: string;
    order_code: string;
    status: string;
    quantity: number;
    manifest_units: number[];
    position_id: string | null;
    address: string | null;
  };
  project: {
    id: string;
    code: string;
    name: string;
    client_name: string;
    client_rut: string | null;
    client_phone: string | null;
    delivery_address: string | null;
  };
  position: {
    id: string;
    location_tag: string | null;
    width_mm: string;
    height_mm: string;
    quantity: number;
    system_id: string;
    mounting_rule_id: string | null;
    measurement_state: string;
  } | null;
  delivery: {
    id: string;
    status: string;
    scheduled_date: string;
    time_window: string;
    address: string;
    contact_name: string | null;
    contact_phone: string | null;
    load_checked: boolean;
    units: number[] | null;
    notes: string | null;
  } | null;
  measurement: {
    state: string;
    vano: { width_points_mm?: string[]; height_points_mm?: string[]; wall_type?: string } | null;
    resolution: { fabrication_width_mm?: string; fabrication_height_mm?: string } | null;
  } | null;
  checklists: {
    id: string;
    unit_index: number | null;
    items: InstallationCheckItems;
    notes: string | null;
    updated_at: string | null;
  }[];
  incidents: {
    id: string;
    code: string;
    kind: string;
    status: string;
    unit_index: number | null;
    note: string | null;
  }[];
  confirmation: {
    id: string;
    confirmation_code: string;
    issued_at: string | null;
  } | null;
  warranty: {
    months: number | null;
    until: string | null;
    installed_at: string | null;
  } | null;
};

function asCard(data: FieldOrderCard): MutableCard {
  return data as unknown as MutableCard;
}

/** Una posición, una pantalla (F9): la medición D07, el checklist por
 * unidad, la incidencia con foto y la recepción firmada — todo desde el
 * celular y todo con operation_key para la cola sin conexión. */
export function FieldOrderPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const allowed = org != null && FIELD_ROLES.includes(org.role);
  const { orderId = "" } = useParams();
  const queryClient = useQueryClient();
  const [pending, setPending] = useState(0);
  const [online, setOnline] = useState(navigator.onLine);

  useEffect(() => {
    if (!org) return;
    const refresh = () => setPending(outboxList(org.id).length);
    refresh();
    const flush = async () => {
      const result = await outboxFlush(org.id);
      setOnline(result.online);
      setPending(result.remaining);
      void queryClient.invalidateQueries({ queryKey: ["field-order", orderId] });
    };
    void flush();
    const onOnline = () => void flush();
    const onOffline = () => setOnline(false);
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
    };
  }, [org, orderId, queryClient]);

  const card = useQuery<MutableCard>({
    queryKey: ["field-order", org?.id, orderId],
    enabled: allowed && orderId !== "",
    queryFn: async ({ signal }) => {
      const response = await fieldOrderCard(orderId, {
        signal,
        headers: { "X-Organization-ID": org!.id },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return asCard(response.data);
    },
  });

  const rules = useQuery({
    queryKey: ["mounting-rules", org?.id, card.data?.position?.system_id],
    enabled: allowed && card.data?.position?.system_id != null,
    queryFn: async ({ signal }) => {
      const response = await mountingRulesList(
        { system_id: card.data!.position!.system_id },
        { signal, headers: { "X-Organization-ID": org!.id } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.items;
    },
  });

  if (!allowed) {
    return <DeniedState reason={t("field.denied")} />;
  }
  if (card.isPending) {
    return (
      <div className="field-root" data-density="workshop" data-theme-scope="dark">
        <LoadingState shape="card" />
      </div>
    );
  }
  if (card.isError || !card.data) {
    return (
      <div className="field-root" data-density="workshop" data-theme-scope="dark">
        <ErrorState title={t("field.loadError")} onRetry={() => void card.refetch()} />
      </div>
    );
  }

  const data = card.data;
  const orderStatus = data.order.status;
  const unitList: (number | null)[] =
    data.delivery?.units && data.delivery.units.length > 0
      ? data.delivery.units
      : data.order.manifest_units.length > 0
        ? data.order.manifest_units
        : [null];
  const delivery = data.delivery;

  return (
    <div className="field-root" data-density="workshop" data-theme-scope="dark">
      <header className="field-header">
        <h1>{data.order.order_code}</h1>
        <Link className="field-button field-button--ghost" to="/field/agenda">
          {t("field.backAgenda")}
        </Link>
      </header>
      {pending > 0 || !online ? (
        <div className={`field-outbox${!online ? " field-outbox--offline" : ""}`} role="status">
          <span>
            {!online
              ? t("field.offline")
              : t("field.outboxPending").replace("{count}", String(pending))}
          </span>
        </div>
      ) : null}

      <section className="field-card">
        <h2>
          {data.position?.location_tag ?? data.order.order_code} · {data.project.client_name}
        </h2>
        <div className="field-addr-row">
          <p className="field-visit">
            {delivery?.address ?? data.project.delivery_address ?? data.order.address ?? "—"}
          </p>
          {delivery?.address || data.project.delivery_address || data.order.address ? (
            <a
              className="field-stop__maps"
              href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
                delivery?.address ?? data.project.delivery_address ?? data.order.address ?? "",
              )}`}
              rel="noreferrer"
              target="_blank"
            >
              {t("field.howToGet")}
            </a>
          ) : null}
        </div>
        <div className="field-chip-row">
          <StatusChip
            label={t(ORDER_STATUS_KEY[data.order.status] ?? "production.orderReleased")}
            tone="neutral"
            value={orderStatus}
          />
          {data.position ? (
            <StatusChip
              label={tDynamic("field.measurementState", data.position.measurement_state)}
              tone={data.position.measurement_state === "CONFIRMED" ? "ok" : "info"}
              value={data.position.measurement_state}
            />
          ) : null}
          {data.warranty?.until ? (
            <StatusChip
              label={t("field.warrantyUntil").replace("{date}", data.warranty.until)}
              tone="info"
              value="warranty"
            />
          ) : null}
        </div>
      </section>

      <MeasurementSection
        card={data}
        onQueued={() => setPending(outboxList(org!.id).length)}
        orgId={org!.id}
        orderId={orderId}
        rules={(rules.data ?? []).map((rule) => ({ id: rule.id, label: rule.label }))}
      />

      <ChecklistSection
        card={data}
        onQueued={() => setPending(outboxList(org!.id).length)}
        orgId={org!.id}
        orderId={orderId}
        units={unitList}
      />

      <IncidentSection
        card={data}
        deliveryId={delivery?.id ?? null}
        onQueued={() => setPending(outboxList(org!.id).length)}
        orgId={org!.id}
        orderId={orderId}
        units={unitList}
      />

      <ReceptionSection
        card={data}
        deliveryId={delivery?.id ?? null}
        orgId={org!.id}
        orderId={orderId}
      />
    </div>
  );
}

function MeasurementSection({
  card,
  orderId,
  orgId,
  rules,
  onQueued,
}: {
  card: MutableCard;
  orderId: string;
  orgId: string;
  rules: { id: string; label: string }[];
  onQueued: () => void;
}): JSX.Element | null {
  const queryClient = useQueryClient();
  const vano = card.measurement?.vano;
  const [widths, setWidths] = useState<string[]>(
    vano?.width_points_mm?.length ? [...vano.width_points_mm] : ["", "", ""],
  );
  const [heights, setHeights] = useState<string[]>(
    vano?.height_points_mm?.length ? [...vano.height_points_mm] : ["", "", ""],
  );
  const [wallType, setWallType] = useState<string>(vano?.wall_type ?? "");
  const [ruleId, setRuleId] = useState<string>(card.position?.mounting_rule_id ?? "");
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState<FieldPhoto[]>([]);
  const [queued, setQueued] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  if (!card.position) return null;

  const submit = () => {
    const widthPoints = widths.map((value) => value.trim()).filter(Boolean);
    const heightPoints = heights.map((value) => value.trim()).filter(Boolean);
    const hasVano = widthPoints.length > 0 || heightPoints.length > 0;
    if (!hasVano && !ruleId) {
      setError(t("field.measureEmpty"));
      return;
    }
    if (hasVano && (!ruleId || widthPoints.length === 0 || heightPoints.length === 0)) {
      setError(t("field.measureIncomplete"));
      return;
    }
    const body = {
      position_id: card.position!.id,
      operation_key: newOpKey(),
      vano: hasVano
        ? {
            width_points_mm: widthPoints,
            height_points_mm: heightPoints,
            wall_type: (wallType || null) as
              | (typeof VanoMeasurementRequestWallType)[keyof typeof VanoMeasurementRequestWallType]
              | null,
            notes: notes || undefined,
          }
        : null,
      mounting_rule_id: ruleId || null,
      notes: notes || undefined,
      photos: photos.map((photo) => ({ key: photo.key, sha256: photo.sha256 })),
    };
    setBusy(true);
    setError(null);
    setSaved(null);
    if (!navigator.onLine) {
      outboxEnqueue(orgId, {
        path: `/api/v1/field/orders/${orderId}/measurement/`,
        method: "POST",
        body,
        label: t("field.opMeasurement"),
      });
      setQueued(true);
      setBusy(false);
      onQueued();
      return;
    }
    void fieldMeasurementSubmit(orderId, body, {
      headers: { "X-Organization-ID": orgId },
    })
      .then((response) => {
        if (response.status !== 200 && response.status !== 201) {
          throw new ApiError(response.status, response.data);
        }
        setSaved(response.data.measurement.applied_state);
        void queryClient.invalidateQueries({ queryKey: ["field-order", orderId] });
      })
      .catch(() => {
        outboxEnqueue(orgId, {
          path: `/api/v1/field/orders/${orderId}/measurement/`,
          method: "POST",
          body,
          label: t("field.opMeasurement"),
        });
        setQueued(true);
        onQueued();
      })
      .finally(() => setBusy(false));
  };

  return (
    <section className="field-card">
      <h2>{t("field.measurementTitle")}</h2>
      <div className="field-grid">
        {["w0", "w1", "w2"].map((slot, index) => (
          <label className="field-field" key={slot}>
            <span>{t("field.widthPoint").replace("{n}", String(index + 1))}</span>
            <input
              inputMode="decimal"
              onChange={(event) =>
                setWidths(widths.map((v, i) => (i === index ? event.target.value : v)))
              }
              value={widths[index] ?? ""}
            />
          </label>
        ))}
      </div>
      <div className="field-grid field-section-gap">
        {["h0", "h1", "h2"].map((slot, index) => (
          <label className="field-field" key={slot}>
            <span>{t("field.heightPoint").replace("{n}", String(index + 1))}</span>
            <input
              inputMode="decimal"
              onChange={(event) =>
                setHeights(heights.map((v, i) => (i === index ? event.target.value : v)))
              }
              value={heights[index] ?? ""}
            />
          </label>
        ))}
      </div>
      <div className="field-grid field-section-gap" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label className="field-field">
          <span>{t("field.wallType")}</span>
          <select onChange={(event) => setWallType(event.target.value)} value={wallType}>
            <option value="">{t("field.noData")}</option>
            {WALL_TYPES.map((wall) => (
              <option key={wall} value={wall}>
                {tDynamic("field.wallType", wall)}
              </option>
            ))}
          </select>
        </label>
        <label className="field-field">
          <span>{t("field.mountingRule")}</span>
          <select onChange={(event) => setRuleId(event.target.value)} value={ruleId}>
            <option value="">{t("field.noData")}</option>
            {rules.map((rule) => (
              <option key={rule.id} value={rule.id}>
                {rule.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="field-field field-section-gap">
        <span>{t("field.notes")}</span>
        <textarea onChange={(event) => setNotes(event.target.value)} value={notes} />
      </label>
      <div className="field-section-gap">
        <PhotoField
          label={t("field.photoMeasure")}
          onChange={setPhotos}
          orgId={orgId}
          photos={photos}
        />
      </div>
      {error ? <p className="field-message field-message--error">{error}</p> : null}
      {queued ? <p className="field-message field-message--ok">{t("field.queued")}</p> : null}
      {saved ? (
        <p className="field-message field-message--ok">{tDynamic("field.measureSaved", saved)}</p>
      ) : null}
      <div className="field-actions">
        <button className="field-button" disabled={busy} onClick={submit} type="button">
          {busy ? t("field.saving") : t("field.saveMeasurement")}
        </button>
      </div>
    </section>
  );
}

function ChecklistSection({
  card,
  orderId,
  orgId,
  units,
  onQueued,
}: {
  card: MutableCard;
  orderId: string;
  orgId: string;
  units: (number | null)[];
  onQueued: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [unitIndex, setUnitIndex] = useState<number | null>(units[0] ?? null);
  const current = card.checklists.find((check) => (check.unit_index ?? null) === unitIndex);
  const [items, setItems] = useState<Record<CheckKey, boolean>>({
    installed: false,
    leveled: false,
    sealed: false,
    adjusted: false,
    clean: false,
  });
  const [notes, setNotes] = useState("");
  const [photos, setPhotos] = useState<FieldPhoto[]>([]);
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const [savedUnit, setSavedUnit] = useState<number | null | "">("");

  useEffect(() => {
    setItems({
      installed: Boolean(current?.items?.installed),
      leveled: Boolean(current?.items?.leveled),
      sealed: Boolean(current?.items?.sealed),
      adjusted: Boolean(current?.items?.adjusted),
      clean: Boolean(current?.items?.clean),
    });
    setNotes(current?.notes ?? "");
    setQueued(false);
    setSavedUnit("");
  }, [unitIndex, current?.id, current?.updated_at]);

  const submit = () => {
    const body = {
      unit_index: unitIndex,
      items,
      notes: notes || undefined,
      photos: photos.map((photo) => ({ key: photo.key, sha256: photo.sha256 })),
      operation_key: newOpKey(),
    };
    setBusy(true);
    const queue = () => {
      outboxEnqueue(orgId, {
        path: `/api/v1/field/orders/${orderId}/checklist/`,
        method: "PUT",
        body,
        label: t("field.opChecklist"),
      });
      setQueued(true);
      setSavedUnit("");
      onQueued();
    };
    if (!navigator.onLine) {
      queue();
      setBusy(false);
      return;
    }
    void fieldChecklistSave(orderId, body, {
      headers: { "X-Organization-ID": orgId },
    })
      .then((response) => {
        if (response.status !== 200 && response.status !== 201) {
          throw new ApiError(response.status, response.data);
        }
        setSavedUnit(unitIndex);
        void queryClient.invalidateQueries({ queryKey: ["field-order", orderId] });
      })
      .catch(queue)
      .finally(() => setBusy(false));
  };

  return (
    <section className="field-card">
      <h2>{t("field.checklistTitle")}</h2>
      {units.length > 1 ? (
        <div className="field-chip-row" role="tablist">
          {units.map((unit) => {
            const label = unit === null ? t("field.unitGeneric") : `U${unit}`;
            const check = card.checklists.find((row) => (row.unit_index ?? null) === unit);
            const done = check != null && CHECK_ITEMS.every((key) => check.items[key] === true);
            return (
              <button
                aria-pressed={unitIndex === unit}
                className="field-button field-button--ghost"
                key={unit ?? "generic"}
                onClick={() => setUnitIndex(unit)}
                type="button"
              >
                {done ? <Icon aria-hidden name="check" /> : null}
                {label}
              </button>
            );
          })}
        </div>
      ) : null}
      <div className="field-checklist field-section-gap">
        {CHECK_ITEMS.map((key) => (
          <button
            aria-pressed={items[key]}
            className="field-check"
            key={key}
            onClick={() => setItems({ ...items, [key]: !items[key] })}
            type="button"
          >
            <span className="field-check__mark">
              <Icon aria-hidden name="check" />
            </span>
            {tDynamic("field.check", key)}
            <span className="field-check__state">{items[key] ? t("field.yes") : ""}</span>
          </button>
        ))}
      </div>
      <label className="field-field field-section-gap">
        <span>{t("field.notes")}</span>
        <textarea onChange={(event) => setNotes(event.target.value)} value={notes} />
      </label>
      <div className="field-section-gap">
        <PhotoField
          label={t("field.photoInstall")}
          onChange={setPhotos}
          orgId={orgId}
          photos={photos}
        />
      </div>
      {queued ? <p className="field-message field-message--ok">{t("field.queued")}</p> : null}
      {savedUnit !== "" ? (
        <p className="field-message field-message--ok">{t("field.checkSaved")}</p>
      ) : null}
      <div className="field-actions">
        <button className="field-button" disabled={busy} onClick={submit} type="button">
          {busy ? t("field.saving") : t("field.saveChecklist")}
        </button>
      </div>
    </section>
  );
}

function IncidentSection({
  card,
  orderId,
  orgId,
  units,
  deliveryId,
  onQueued,
}: {
  card: MutableCard;
  orderId: string;
  orgId: string;
  units: (number | null)[];
  deliveryId: string | null;
  onQueued: () => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<SiteIncidentKindEnum>("DAMAGE");
  const [unitIndex, setUnitIndex] = useState<number | null>(units[0] ?? null);
  const [note, setNote] = useState("");
  const [pieceCode, setPieceCode] = useState("");
  const [photos, setPhotos] = useState<FieldPhoto[]>([]);
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  const submit = () => {
    const body = {
      kind,
      operation_key: newOpKey(),
      delivery_id: deliveryId,
      unit_index: unitIndex,
      piece_code: pieceCode || undefined,
      note: note || undefined,
      photos: photos.map((photo) => ({ key: photo.key, sha256: photo.sha256 })),
    };
    setBusy(true);
    const queue = () => {
      outboxEnqueue(orgId, {
        path: `/api/v1/field/orders/${orderId}/incidents/`,
        method: "POST",
        body,
        label: t("field.opIncident"),
      });
      setQueued(true);
      setSaved(false);
      setOpen(false);
      onQueued();
    };
    if (!navigator.onLine) {
      queue();
      setBusy(false);
      return;
    }
    void fieldIncidentsReport(orderId, body, {
      headers: { "X-Organization-ID": orgId },
    })
      .then((response) => {
        if (response.status !== 200 && response.status !== 201) {
          throw new ApiError(response.status, response.data);
        }
        setSaved(true);
        setOpen(false);
        void queryClient.invalidateQueries({ queryKey: ["field-order", orderId] });
      })
      .catch(queue)
      .finally(() => setBusy(false));
  };

  return (
    <section className="field-card">
      <h2>{t("field.incidentsTitle")}</h2>
      {card.incidents.length > 0 ? (
        <ul>
          {card.incidents.map((incident) => {
            const status = incident.status;
            return (
              <li className="field-visit" key={incident.id}>
                <code>{incident.code}</code> · {tDynamic("field.incidentKind", incident.kind)} ·{" "}
                <StatusChip
                  label={tDynamic("field.incidentStatus", status)}
                  tone={status === "RESOLVED" ? "ok" : "danger"}
                  value={status}
                />
              </li>
            );
          })}
        </ul>
      ) : null}
      {saved ? <p className="field-message field-message--ok">{t("field.incidentSaved")}</p> : null}
      {queued ? <p className="field-message field-message--ok">{t("field.queued")}</p> : null}
      {!open ? (
        <div className="field-actions">
          <button
            className="field-button field-button--danger"
            onClick={() => setOpen(true)}
            type="button"
          >
            {t("field.reportIncident")}
          </button>
        </div>
      ) : (
        <>
          <div className="field-chip-row" role="radiogroup">
            {INCIDENT_KINDS.map((option) => (
              <button
                aria-pressed={kind === option}
                className="field-button field-button--ghost"
                key={option}
                onClick={() => setKind(option)}
                type="button"
              >
                {tDynamic("field.incidentKind", option)}
              </button>
            ))}
          </div>
          {units.length > 1 ? (
            <label className="field-field field-section-gap">
              <span>{t("field.unit")}</span>
              <select
                onChange={(event) =>
                  setUnitIndex(event.target.value ? Number(event.target.value) : null)
                }
                value={unitIndex ?? ""}
              >
                <option value="">{t("field.unitGeneric")}</option>
                {units.map((unit) =>
                  unit === null ? null : (
                    <option key={unit} value={unit}>
                      U{unit}
                    </option>
                  ),
                )}
              </select>
            </label>
          ) : null}
          <label className="field-field field-section-gap">
            <span>{t("field.pieceCode")}</span>
            <input onChange={(event) => setPieceCode(event.target.value)} value={pieceCode} />
          </label>
          <label className="field-field field-section-gap">
            <span>{t("field.notes")}</span>
            <textarea onChange={(event) => setNote(event.target.value)} value={note} />
          </label>
          <div className="field-section-gap">
            <PhotoField
              label={t("field.photoIncident")}
              onChange={setPhotos}
              orgId={orgId}
              photos={photos}
            />
          </div>
          <div className="field-actions">
            <button
              className="field-button field-button--danger"
              disabled={busy}
              onClick={submit}
              type="button"
            >
              {busy ? t("field.saving") : t("field.sendIncident")}
            </button>
            <button
              className="field-button field-button--ghost"
              onClick={() => setOpen(false)}
              type="button"
            >
              {t("field.cancel")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function ReceptionSection({
  card,
  orderId,
  orgId,
  deliveryId,
}: {
  card: MutableCard;
  orderId: string;
  orgId: string;
  deliveryId: string | null;
}): JSX.Element {
  const queryClient = useQueryClient();
  const sigRef = useRef<SignaturePadHandle | null>(null);
  const [receiverName, setReceiverName] = useState(card.project.client_name ?? "");
  const [receiverRut, setReceiverRut] = useState(card.project.client_rut ?? "");
  const [observations, setObservations] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actaBusy, setActaBusy] = useState(false);

  const openActa = () => {
    setActaBusy(true);
    setError(null);
    void productionOrderDeliveryConfirmation(orderId, undefined, {
      headers: { "X-Organization-ID": orgId },
    })
      .then((response) => {
        if (response.status !== 200 || !response.data.signed_url) {
          throw new ApiError(response.status, response.data);
        }
        window.open(response.data.signed_url, "_blank", "noopener");
      })
      .catch(() => setError(t("field.actaFailed")))
      .finally(() => setActaBusy(false));
  };

  const canSign = card.order.status === "DISPATCHED" && (card.delivery?.status ?? "") !== "";
  const confirmable =
    canSign &&
    (deliveryId == null ||
      card.delivery?.status === "ON_ROUTE" ||
      card.delivery?.status === "DELIVERED");

  const submit = () => {
    const signature = sigRef.current?.dataURL();
    if (!receiverName.trim() || !signature) {
      setError(t("field.receptionIncomplete"));
      return;
    }
    setBusy(true);
    setError(null);
    void productionOrderDeliveryConfirm(
      orderId,
      {
        receiver_name: receiverName.trim(),
        receiver_rut: receiverRut.trim() || undefined,
        signature_png: signature.split(",")[1] ?? signature,
        observations: observations.trim() || undefined,
      },
      { headers: { "X-Organization-ID": orgId } },
    )
      .then((response) => {
        if (response.status !== 200 && response.status !== 201) {
          throw new ApiError(response.status, response.data);
        }
        setDone(true);
        void queryClient.invalidateQueries({ queryKey: ["field-order", orderId] });
      })
      .catch(() => setError(t("field.receptionFailed")))
      .finally(() => setBusy(false));
  };

  return (
    <section className="field-card">
      <h2>{t("field.receptionTitle")}</h2>
      {card.confirmation ? (
        <>
          <p className="field-message field-message--ok">
            {t("field.actaSealed").replace("{code}", card.confirmation.confirmation_code)}
          </p>
          <div className="field-actions">
            <button
              className="field-button field-button--ghost"
              disabled={actaBusy}
              onClick={openActa}
              type="button"
            >
              {actaBusy ? t("field.saving") : t("field.viewActa")}
            </button>
          </div>
        </>
      ) : done ? (
        <p className="field-message field-message--ok">{t("field.receptionDone")}</p>
      ) : !confirmable ? (
        <p className="field-visit">{t("field.receptionNotYet")}</p>
      ) : (
        <>
          <label className="field-field">
            <span>{t("field.receiverName")}</span>
            <input onChange={(event) => setReceiverName(event.target.value)} value={receiverName} />
          </label>
          <label className="field-field field-section-gap">
            <span>{t("field.receiverRut")}</span>
            <input onChange={(event) => setReceiverRut(event.target.value)} value={receiverRut} />
          </label>
          <div className="field-section-gap">
            <SignaturePad ref={sigRef} />
          </div>
          <label className="field-field field-section-gap">
            <span>{t("field.observations")}</span>
            <textarea
              onChange={(event) => setObservations(event.target.value)}
              value={observations}
            />
          </label>
          {error ? <p className="field-message field-message--error">{error}</p> : null}
          <div className="field-actions">
            <button className="field-button" disabled={busy} onClick={submit} type="button">
              {busy ? t("field.saving") : t("field.signReception")}
            </button>
          </div>
        </>
      )}
    </section>
  );
}
