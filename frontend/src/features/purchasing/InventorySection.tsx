import { useCallback, useEffect, useState, type FormEvent } from "react";

import { ApiError } from "../../api/apiMutator";
import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import { formatDateTime } from "../../format";
import { useConfirm } from "../../ui";

type RequestFn = <T>(path: string, method?: string, body?: unknown) => Promise<T>;

type Remnant = {
  id: string;
  kind: "BAR" | "SHEET";
  stock_authority_id: string | null;
  article_sku?: string | null;
  sheet_workshop_sku: string | null;
  material: string | null;
  color: string | null;
  length_mm: string | null;
  width_mm: string | null;
  height_mm: string | null;
  status: "AVAILABLE" | "RESERVED" | "CONSUMED" | "SCRAPPED";
  origin: "RECEIPT" | "PRODUCTION" | "MANUAL";
  origin_order_id: string | null;
  reserved_order_id: string | null;
  reserved_order_code: string | null;
  origin_order_code: string | null;
  rack_location: string | null;
  notes: string | null;
  created_at: string;
};

type Movement = {
  id: string;
  item_id: string;
  movement_type: string;
  quantity: string;
  order_id: string | null;
  lot_code: string | null;
  rack_location: string | null;
  note: string | null;
  actor_label: string | null;
  created_at: string;
};

type StockIdentity = {
  item_id: string;
  sku: string;
  name: string;
  racks?: string | null;
};

function remnantAge(createdAt: string): string {
  const days = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / 86_400_000));
  if (days === 0) return t("inventory.ageNew");
  return `${days} ${t(days === 1 ? "inventory.ageDay" : "inventory.ageDays")}`;
}

type BarAuthority = {
  id: string;
  commercial_sku: string;
  physical_stock_identity: string | null;
  stock_color: string | null;
  source: "PROFILE" | "REINFORCEMENT";
};

const REMNANT_STATUS: ReadonlySet<string> = new Set([
  "AVAILABLE",
  "RESERVED",
  "CONSUMED",
  "SCRAPPED",
]);
const REMNANT_KIND: ReadonlySet<string> = new Set(["BAR", "SHEET"]);
const REMNANT_ORIGIN: ReadonlySet<string> = new Set(["RECEIPT", "PRODUCTION", "MANUAL"]);
const MOVEMENT_TYPE: ReadonlySet<string> = new Set([
  "RECEIPT",
  "CONSUMPTION",
  "RESERVATION",
  "RELEASE",
  "ADJUSTMENT",
  "RETURN",
  "SCRAP",
]);

function remnantStatusLabel(status: string): string {
  return REMNANT_STATUS.has(status)
    ? t(`inventory.remnantStatus.${status}` as Parameters<typeof t>[0])
    : status;
}

function remnantKindLabel(kind: string): string {
  return REMNANT_KIND.has(kind)
    ? t(`inventory.remnantKind.${kind}` as Parameters<typeof t>[0])
    : kind;
}

function remnantOriginLabel(origin: string): string {
  return REMNANT_ORIGIN.has(origin)
    ? t(`inventory.remnantOrigin.${origin}` as Parameters<typeof t>[0])
    : origin;
}

function movementLabel(type: string): string {
  return MOVEMENT_TYPE.has(type)
    ? t(`inventory.movement.${type}` as Parameters<typeof t>[0])
    : type;
}

function remnantDims(r: Remnant): string {
  if (r.kind === "BAR") {
    return r.length_mm ? `${fmtMm(r.length_mm)} mm` : "—";
  }
  if (r.width_mm && r.height_mm) return `${fmtMm(r.width_mm)} × ${fmtMm(r.height_mm)} mm`;
  return "—";
}

/** Stock + offcut pool + movement ledger — the inventory half of the
 * purchasing workspace. Reads stay open to estimator roles; writes are
 * workshop-manager only (the API enforces the same split). */
export function InventorySection({
  request,
  canWrite,
  stockItems,
}: {
  request: RequestFn;
  canWrite: boolean;
  stockItems: StockIdentity[];
}): JSX.Element {
  const confirm = useConfirm();
  const [remnants, setRemnants] = useState<Remnant[]>([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [statusFilter, setStatusFilter] = useState("AVAILABLE");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [adjustItem, setAdjustItem] = useState<string | null>(null);
  const [adjustForm, setAdjustForm] = useState({
    movement_type: "ADJUSTMENT",
    quantity: "",
    lot_code: "",
    rack_location: "",
    note: "",
  });
  const [form, setForm] = useState({
    kind: "SHEET" as "BAR" | "SHEET",
    stock_authority_id: "",
    sheet_workshop_sku: "",
    length_mm: "",
    width_mm: "",
    height_mm: "",
    rack_location: "",
    material: "",
    color: "",
    notes: "",
  });
  const [authorities, setAuthorities] = useState<BarAuthority[]>([]);
  const [label, setLabel] = useState<{
    remnant_id: string;
    identity: string;
    qr_svg: string;
    dims: string;
    rack: string;
  } | null>(null);

  const load = useCallback(() => {
    void request<{ remnants?: Remnant[] }>("inventory/remnants/")
      .then((data) => setRemnants(data.remnants ?? []))
      .catch(() => setRemnants([]));
    void request<{ movements?: Movement[] }>("inventory/movements/")
      .then((data) => setMovements(data.movements ?? []))
      .catch(() => setMovements([]));
    void request<{ authorities?: BarAuthority[] }>("inventory/bar-authorities/")
      .then((data) => setAuthorities(data.authorities ?? []))
      .catch(() => setAuthorities([]));
  }, [request]);

  useEffect(load, [load]);

  async function run(task: Promise<unknown>, fallback: string): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      await task;
      load();
    } catch (error) {
      const detail =
        error instanceof ApiError && typeof error.payload === "object" && error.payload !== null
          ? (error.payload as { error?: { detail?: unknown } }).error?.detail
          : undefined;
      setMessage(
        typeof detail === "string" && detail ? detail : t(fallback as Parameters<typeof t>[0]),
      );
    } finally {
      setBusy(false);
    }
  }

  const itemNames = new Map(stockItems.map((s) => [s.item_id, `${s.sku} · ${s.name}`]));
  const authorityNames = new Map(
    authorities.map((a) => [
      a.id,
      `${a.commercial_sku}${a.stock_color ? ` · ${a.stock_color}` : ""}`,
    ]),
  );
  const visible = remnants.filter((r) => r.status === statusFilter);
  const counts = new Map<string, number>();
  for (const r of remnants) counts.set(r.status, (counts.get(r.status) ?? 0) + 1);

  function createRemnant(event: FormEvent): void {
    event.preventDefault();
    const authority = authorities.find((a) => a.id === form.stock_authority_id);
    void run(
      request("inventory/remnants/", "POST", {
        kind: form.kind,
        stock_authority_id: form.kind === "BAR" ? form.stock_authority_id : null,
        physical_stock_identity:
          form.kind === "BAR" ? (authority?.physical_stock_identity ?? null) : null,
        sheet_workshop_sku: form.kind === "SHEET" ? form.sheet_workshop_sku.trim() : null,
        length_mm: form.kind === "BAR" ? form.length_mm : null,
        width_mm: form.kind === "SHEET" ? form.width_mm : null,
        height_mm: form.kind === "SHEET" ? form.height_mm : null,
        rack_location: form.rack_location.trim() || null,
        material: form.material.trim() || null,
        color: form.kind === "SHEET" ? form.color.trim() || null : null,
        notes: form.notes.trim() || null,
      }),
      "inventory.remnantCreateError",
    ).then(() => setShowCreate(false));
  }

  function recordMovement(event: FormEvent): void {
    event.preventDefault();
    if (!adjustItem) return;
    void run(
      request("inventory/movements/", "POST", {
        item_id: adjustItem,
        movement_type: adjustForm.movement_type,
        quantity: adjustForm.quantity,
        lot_code: adjustForm.lot_code.trim() || null,
        rack_location: adjustForm.rack_location.trim() || null,
        note: adjustForm.note.trim(),
      }),
      "inventory.movementError",
    ).then(() => setAdjustItem(null));
  }

  const adjustTarget = stockItems.find((s) => s.item_id === adjustItem);

  function showLabel(remnant: Remnant): void {
    void request<{
      remnant: Remnant;
      identity: string;
      qr_svg: string;
    }>(`inventory/remnants/${remnant.id}/label/`)
      .then((data) =>
        setLabel({
          remnant_id: remnant.id.slice(0, 8).toUpperCase(),
          identity: data.identity,
          qr_svg: data.qr_svg,
          dims: remnantDims(remnant),
          rack: remnant.rack_location ?? "—",
        }),
      )
      .catch(() => setLabel(null));
  }

  return (
    <section className="purchasing-stock" aria-label={t("inventory.title")}>
      {canWrite && stockItems.length > 0 ? (
        <details className="inventory-adjust">
          <summary>{t("inventory.adjustTitle")}</summary>
          <ul className="inventory-adjust-items">
            {stockItems.map((item) => (
              <li key={item.item_id}>
                <span>
                  {item.sku} · {item.name}
                </span>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setAdjustItem(item.item_id)}
                >
                  {t("inventory.adjust")}
                </button>
              </li>
            ))}
          </ul>
          {adjustTarget ? (
            <form className="inventory-remnant-form" onSubmit={recordMovement}>
              <p className="purchasing-hint">
                {adjustTarget.sku} · {adjustTarget.name}
              </p>
              <label>
                {t("inventory.movementType")}
                <select
                  value={adjustForm.movement_type}
                  onChange={(e) => setAdjustForm((f) => ({ ...f, movement_type: e.target.value }))}
                >
                  <option value="ADJUSTMENT">{t("inventory.movement.ADJUSTMENT")}</option>
                  <option value="RETURN">{t("inventory.movement.RETURN")}</option>
                  <option value="SCRAP">{t("inventory.movement.SCRAP")}</option>
                </select>
              </label>
              <label>
                {t("inventory.movementQty")}
                <input
                  required
                  type="number"
                  min="0.01"
                  step="any"
                  value={adjustForm.quantity}
                  onChange={(e) => setAdjustForm((f) => ({ ...f, quantity: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.lotCode")}
                <input
                  value={adjustForm.lot_code}
                  onChange={(e) => setAdjustForm((f) => ({ ...f, lot_code: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.movementRack")}
                <input
                  value={adjustForm.rack_location}
                  onChange={(e) => setAdjustForm((f) => ({ ...f, rack_location: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.movementNote")}
                <input
                  required
                  value={adjustForm.note}
                  onChange={(e) => setAdjustForm((f) => ({ ...f, note: e.target.value }))}
                />
              </label>
              <button type="submit" disabled={busy}>
                {t("inventory.movementSubmit")}
              </button>
            </form>
          ) : null}
        </details>
      ) : null}
      <h2>{t("inventory.remnants")}</h2>
      <p className="purchasing-hint">{t("inventory.remnantsHint")}</p>
      <div className="inventory-remnant-filter" role="group" aria-label={t("inventory.filter")}>
        {[...REMNANT_STATUS].map((status) => (
          <button
            key={status}
            type="button"
            className="portal-view-toggle"
            data-active={statusFilter === status}
            onClick={() => setStatusFilter(status)}
          >
            {remnantStatusLabel(status)} ({counts.get(status) ?? 0})
          </button>
        ))}
        {canWrite ? (
          <button
            type="button"
            className="secondary"
            onClick={() => setShowCreate((value) => !value)}
          >
            {t("inventory.remnantCreate")}
          </button>
        ) : null}
      </div>
      {showCreate ? (
        <form className="inventory-remnant-form" onSubmit={createRemnant}>
          <label>
            {t("inventory.remnantKind")}
            <select
              value={form.kind}
              onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as "BAR" | "SHEET" }))}
            >
              <option value="SHEET">{t("inventory.remnantKind.SHEET")}</option>
              <option value="BAR">{t("inventory.remnantKind.BAR")}</option>
            </select>
          </label>
          {form.kind === "BAR" ? (
            <>
              <label>
                {t("inventory.stockAuthority")}
                <select
                  required
                  value={form.stock_authority_id}
                  onChange={(e) => setForm((f) => ({ ...f, stock_authority_id: e.target.value }))}
                >
                  <option value="" disabled>
                    {t("inventory.stockAuthorityPick")}
                  </option>
                  {authorities.map((authority) => (
                    <option key={authority.id} value={authority.id}>
                      {authority.commercial_sku}
                      {authority.stock_color ? ` · ${authority.stock_color}` : ""}
                      {authority.source === "REINFORCEMENT"
                        ? ` · ${t("inventory.authorityReinforcement")}`
                        : ""}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {t("inventory.lengthMm")}
                <input
                  required
                  type="number"
                  min="1"
                  value={form.length_mm}
                  onChange={(e) => setForm((f) => ({ ...f, length_mm: e.target.value }))}
                />
              </label>
            </>
          ) : (
            <>
              <label>
                {t("inventory.sheetSku")}
                <input
                  required
                  value={form.sheet_workshop_sku}
                  onChange={(e) => setForm((f) => ({ ...f, sheet_workshop_sku: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.widthMm")}
                <input
                  required
                  type="number"
                  min="1"
                  value={form.width_mm}
                  onChange={(e) => setForm((f) => ({ ...f, width_mm: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.heightMm")}
                <input
                  required
                  type="number"
                  min="1"
                  value={form.height_mm}
                  onChange={(e) => setForm((f) => ({ ...f, height_mm: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.material")}
                <input
                  value={form.material}
                  onChange={(e) => setForm((f) => ({ ...f, material: e.target.value }))}
                />
              </label>
              <label>
                {t("inventory.color")}
                <input
                  value={form.color}
                  onChange={(e) => setForm((f) => ({ ...f, color: e.target.value }))}
                />
              </label>
            </>
          )}
          <label>
            {t("inventory.rack")}
            <input
              value={form.rack_location}
              onChange={(e) => setForm((f) => ({ ...f, rack_location: e.target.value }))}
            />
          </label>
          <button type="submit" disabled={busy}>
            {t("inventory.remnantCreate")}
          </button>
        </form>
      ) : null}
      {visible.length > 0 ? (
        <table className="inventory-remnants">
          <thead>
            <tr>
              <th>{t("inventory.remnantCode")}</th>
              <th>{t("inventory.remnantKind")}</th>
              <th>{t("inventory.identity")}</th>
              <th>{t("inventory.dims")}</th>
              <th>{t("inventory.rack")}</th>
              <th>{t("inventory.origin")}</th>
              <th>{t("inventory.reservedFor")}</th>
              <th>{t("inventory.registered")}</th>
              <th>{t("inventory.actions")}</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => (
              <tr key={r.id}>
                <td className="inventory-remnant-code">
                  {`RET-${r.id.slice(0, 8).toUpperCase()}`}
                </td>
                <td>{remnantKindLabel(r.kind)}</td>
                <td>
                  {r.kind === "SHEET"
                    ? (r.sheet_workshop_sku ?? "—")
                    : (r.article_sku ??
                      authorityNames.get(r.stock_authority_id ?? "") ??
                      ([r.material, r.color].filter(Boolean).join(" · ") || "—"))}
                  {r.notes ? <span className="purchasing-hint"> — {r.notes}</span> : null}
                </td>
                <td>{remnantDims(r)}</td>
                <td>{r.rack_location ?? "—"}</td>
                <td>
                  {remnantOriginLabel(r.origin)}
                  {r.origin_order_code ? ` · ${r.origin_order_code}` : ""}
                </td>
                <td>
                  {r.status === "RESERVED"
                    ? (r.reserved_order_code ?? r.reserved_order_id?.slice(0, 8) ?? "—")
                    : "—"}
                </td>
                <td>
                  {remnantAge(r.created_at)}
                  <span className="purchasing-hint"> · {formatDateTime(r.created_at)}</span>
                </td>
                <td>
                  <button type="button" className="secondary" onClick={() => showLabel(r)}>
                    {t("inventory.label")}
                  </button>
                  {canWrite && r.status === "RESERVED" ? (
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void run(
                          request(`inventory/remnants/${r.id}/release/`, "POST", {}),
                          "inventory.remnantReleaseError",
                        )
                      }
                    >
                      {t("inventory.release")}
                    </button>
                  ) : null}
                  {canWrite && r.status === "AVAILABLE" ? (
                    <button
                      type="button"
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void confirm({
                          title: t("inventory.scrapConfirmTitle"),
                          body: t("inventory.scrapConfirmBody"),
                          confirmLabel: t("inventory.scrap"),
                          danger: true,
                        }).then((ok) => {
                          if (!ok) return;
                          void run(
                            request(`inventory/remnants/${r.id}/scrap/`, "POST", {}),
                            "inventory.remnantScrapError",
                          );
                        })
                      }
                    >
                      {t("inventory.scrap")}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="purchasing-hint">{t("inventory.noRemnants")}</p>
      )}
      {label ? (
        <div className="inventory-label" role="figure" aria-label={t("inventory.label")}>
          <div className="qr" dangerouslySetInnerHTML={{ __html: label.qr_svg }} />
          <div>
            <p className="inventory-label-id">RET-{label.remnant_id}</p>
            <p className="inventory-label-name">{label.identity}</p>
            <p className="inventory-label-dims">{label.dims}</p>
            <p className="inventory-label-rack">
              {t("inventory.rack")}: {label.rack}
            </p>
            <button type="button" className="secondary" onClick={() => window.print()}>
              {t("inventory.labelPrint")}
            </button>
          </div>
        </div>
      ) : null}
      {movements.length > 0 ? (
        <details className="inventory-movements">
          <summary>{t("inventory.movements")}</summary>
          <table>
            <thead>
              <tr>
                <th>{t("inventory.movementWhen")}</th>
                <th>{t("inventory.movementType")}</th>
                <th>{t("inventory.movementItem")}</th>
                <th>{t("inventory.movementQty")}</th>
                <th>{t("inventory.movementRack")}</th>
                <th>{t("inventory.movementWho")}</th>
                <th>{t("inventory.movementNote")}</th>
              </tr>
            </thead>
            <tbody>
              {movements.map((m) => (
                <tr key={m.id}>
                  <td>{formatDateTime(m.created_at)}</td>
                  <td>{movementLabel(m.movement_type)}</td>
                  <td>{itemNames.get(m.item_id) ?? m.item_id.slice(0, 8)}</td>
                  <td>{m.quantity}</td>
                  <td>{m.rack_location ?? "—"}</td>
                  <td>{m.actor_label ?? "—"}</td>
                  <td>{m.note ?? m.lot_code ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ) : null}
      {message ? <p className="purchasing-message">{message}</p> : null}
    </section>
  );
}
