/** P24 — Analítica que sirve para decidir.
 *
 * Cuatro secciones (ventas, margen, producción, terreno) leen las funciones
 * ``private.analytics_*`` vía /api/v1/analytics/overview/. Reglas de la casa:
 * métrica sin dato → «Sin dato» con su causa, jamás 0; cada cifra enlaza
 * «¿Cómo se calcula?» a su definición versionada (docs/analytics/metricas.md);
 * la tabla de detalle exporta a CSV el mismo contrato que la pantalla.
 * Montos sólo si el rol está en analytics_financial_roles de la org. */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError, apiFetchBlob } from "../../api/apiMutator";
import {
  analyticsMarginBreakdown,
  analyticsOverview,
  getAnalyticsExportUrl,
} from "../../api/generated/dekopen";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { formatDate, formatMoney, formatQty } from "../../format";
import { t, tOptional, type TranslationKey } from "../../i18n/es-CL";
import {
  DataTable,
  DeniedState,
  Dialog,
  EmptyState,
  ErrorState,
  LoadingState,
  Money,
  PageHeader,
  Panel,
  Percent,
  SegmentedControl,
  Stat,
  UnknownValue,
} from "../../ui";

import "./analytics.css";

const READER_ROLES = ["OWNER", "WORKSHOP_MANAGER"];

const PERIODS = ["7d", "30d", "90d", "12m", "custom"] as const;
type PeriodKey = (typeof PERIODS)[number];

const SANTIAGO_FMT = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/Santiago",
});

/** AAAA-MM-DD de «hoy − n días» en America/Santiago — el mismo reloj que
 * usa la SQL de analítica. */
function clDay(offsetDays: number): string {
  const day = new Date(Date.now() - offsetDays * 86_400_000);
  return SANTIAGO_FMT.format(day);
}

type JsonObject = Record<string, unknown>;

type MetricCell = { value: number | null; n: number | null; cause: string | null };

function metricOf(raw: unknown): MetricCell {
  if (raw === null || raw === undefined) return { value: null, n: null, cause: null };
  if (typeof raw === "number") return { value: raw, n: null, cause: null };
  const obj = raw as JsonObject;
  const rawValue = obj.value;
  const value =
    typeof rawValue === "number" ? rawValue : rawValue == null ? null : Number(rawValue);
  return {
    value: Number.isFinite(value) ? (value as number) : null,
    n: typeof obj.n === "number" ? obj.n : null,
    cause: typeof obj.cause === "string" ? obj.cause : null,
  };
}

function sectionOf(raw: unknown): JsonObject {
  return raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as JsonObject) : {};
}

function metricsOf(section: JsonObject): JsonObject {
  return sectionOf(section.metrics);
}

function rowsOf(section: JsonObject, key: string): JsonObject[] {
  const rows = section[key];
  return Array.isArray(rows) ? (rows as JsonObject[]) : [];
}

/** Label traducido o el código crudo — nunca una celda vacía. */
function labelOf(prefix: string, code: unknown): string {
  return tOptional(`${prefix}.${String(code)}`) ?? String(code ?? "");
}

/* ---------- «¿Cómo se calcula?» ---------- */

function DefinitionDialog({
  metricKey,
  definitions,
  onClose,
}: {
  metricKey: string | null;
  definitions: JsonObject;
  onClose: () => void;
}): JSX.Element | null {
  if (metricKey === null) return null;
  const def = sectionOf(definitions[metricKey]);
  return (
    <Dialog title={String(def.title ?? metricKey)} onClose={onClose}>
      <dl className="analytics-def">
        <dt>{t("analytics.def.formula")}</dt>
        <dd>{String(def.formula ?? "")}</dd>
        <dt>{t("analytics.def.source")}</dt>
        <dd>
          <code>{String(def.source ?? "")}</code>
        </dd>
        <dt>{t("analytics.def.period")}</dt>
        <dd>{String(def.period ?? "")}</dd>
      </dl>
    </Dialog>
  );
}

function HowButton({
  metricKey,
  onHow,
}: {
  metricKey: string;
  onHow: (key: string) => void;
}): JSX.Element {
  return (
    <button
      className="analytics-how"
      data-metric={metricKey}
      onClick={() => onHow(metricKey)}
      type="button"
    >
      {t("analytics.how")}
    </button>
  );
}

/* ---------- Tarjeta de métrica ---------- */

type MetricKind = "count" | "money" | "pct" | "pp" | "days" | "mm" | "mm2" | "hours";

function MetricValue({ metric, kind }: { metric: MetricCell; kind: MetricKind }): JSX.Element {
  if (metric.value === null) {
    return <UnknownValue cause={metric.cause ?? undefined} />;
  }
  switch (kind) {
    case "money":
      return <Money value={metric.value} />;
    case "pct":
      return <Percent kind="points" value={metric.value} />;
    case "pp":
      // Desviación en puntos porcentuales, con signo — no es un porcentaje.
      return (
        <>
          {metric.value > 0 ? "+" : ""}
          {formatQty(metric.value)} pp
        </>
      );
    case "days":
      return (
        <>
          {formatQty(metric.value)} {t("analytics.days")}
        </>
      );
    case "mm":
      return <>{formatQty(metric.value)} mm</>;
    case "mm2":
      return <>{formatQty(metric.value)} mm²</>;
    case "hours":
      return <>{formatQty(metric.value)} h</>;
    default:
      return <>{formatQty(metric.value)}</>;
  }
}

function MetricStat({
  label,
  metric,
  kind = "count",
  metricKey,
  onHow,
}: {
  label: string;
  metric: MetricCell;
  kind?: MetricKind;
  metricKey: string;
  onHow: (key: string) => void;
}): JSX.Element {
  return (
    <div className="analytics-card">
      <Stat
        decision={`docs/analytics/metricas.md#${metricKey}`}
        detail={metric.n !== null ? `${t("analytics.detailN")} ${metric.n}` : undefined}
        label={label}
        value={<MetricValue kind={kind} metric={metric} />}
      />
      <HowButton metricKey={metricKey} onHow={onHow} />
    </div>
  );
}

/* ---------- Barras sobrias (tokens P01, sin librería) ---------- */

function BarList({
  rows,
  labelKey,
  valueKey,
  maxValue,
  format = (v: number) => formatQty(v),
}: {
  rows: JsonObject[];
  labelKey: string;
  valueKey: string;
  maxValue?: number;
  format?: (value: number) => string;
}): JSX.Element {
  const max = maxValue ?? Math.max(0, ...rows.map((r) => Number(r[valueKey]) || 0));
  return (
    <ul className="analytics-bars">
      {rows.map((row, i) => {
        const value = Number(row[valueKey]);
        const hasValue = Number.isFinite(value) && row[valueKey] !== null;
        const width = hasValue && max > 0 ? (value / max) * 100 : 0;
        return (
          <li className="analytics-bars__row" key={`${String(row[labelKey])}-${i}`}>
            <span className="analytics-bars__label">{String(row[labelKey] ?? "")}</span>
            <span className="analytics-bars__track">
              <span className="analytics-bars__fill" style={{ width: `${width}%` }} />
            </span>
            <span className="analytics-bars__value">
              {hasValue ? format(value) : <UnknownValue />}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/* ---------- Detalle F6 + exportación CSV ---------- */

const DETAIL_SOURCES = [
  { key: "quotes", section: "sales", rows: "rows" },
  { key: "obras", section: "margins", rows: "obras" },
  { key: "ots", section: "production", rows: "ot_waste" },
  { key: "steps", section: "production", rows: "station_times" },
  { key: "remakes", section: "production", rows: "remakes" },
  { key: "deliveries", section: "field", rows: "deliveries" },
  { key: "incidents", section: "field", rows: "incidents" },
  { key: "warranties", section: "field", rows: "warranties" },
] as const;
type DetailKey = (typeof DETAIL_SOURCES)[number]["key"];

/** Render sobrio de celda por convención de nombre — nunca 0 por nulo. */
function DetailCell({ column, value }: { column: string; value: unknown }): JSX.Element {
  if (value === null || value === undefined || value === "") {
    return <UnknownValue />;
  }
  if (typeof value === "boolean") {
    return <>{value ? t("analytics.yes") : t("analytics.no")}</>;
  }
  if (typeof value === "number") {
    if (column.endsWith("_count") || column === "ots_total" || column === "ots_done")
      return <>{formatQty(value)}</>;
    if (column.endsWith("_mm2")) return <>{formatQty(value)} mm²</>;
    if (column.endsWith("_mm") || column === "mm_amount") return <>{formatQty(value)} mm</>;
    if (column.endsWith("_hours") || column === "hours") return <>{formatQty(value)} h</>;
    if (column.endsWith("_days")) return <>{formatQty(value)} d</>;
    if (column.endsWith("_pp"))
      return (
        <>
          {value > 0 ? "+" : ""}
          {formatQty(value)} pp
        </>
      );
    if (column.endsWith("_pct")) return <Percent kind="points" value={value} />;
    if (/(^|_)(net|cost|price|total|amount)$|discount/.test(column)) return <Money value={value} />;
    return <>{formatQty(value)}</>;
  }
  if (typeof value === "string") {
    if (/^[A-Z][A-Z0-9_]{2,}$/.test(value)) {
      const label = tOptional(`analytics.value.${value}`);
      if (label !== undefined) return <>{label}</>;
    }
    if (/_at$|_date$|_until$/.test(column)) return <>{formatDate(value)}</>;
  }
  if (Array.isArray(value)) {
    return <>{value.length === 0 ? "—" : value.map(String).join(", ")}</>;
  }
  if (typeof value === "object" && value !== null) {
    const obj = value as JsonObject;
    if (typeof obj.note === "string" && obj.note !== "") return <>{obj.note}</>;
    if (typeof obj.qc_item === "string" && obj.qc_item !== "") return <>{obj.qc_item}</>;
    return <>{JSON.stringify(value)}</>;
  }
  return <>{String(value)}</>;
}

function DetailTable({ rows }: { rows: JsonObject[] }): JSX.Element {
  const columns = useMemo(() => {
    const keys: string[] = [];
    for (const row of rows.slice(0, 20)) {
      for (const key of Object.keys(row)) {
        // Los uuid técnicos (id, project_id, version_id…) van al CSV,
        // no a la tabla — el detalle humano usa códigos y nombres.
        if (key === "id" || key.endsWith("_id")) continue;
        if (!keys.includes(key) && keys.length < 9) keys.push(key);
      }
    }
    return keys;
  }, [rows]);
  return (
    <DataTable
      ariaLabel={t("analytics.section.detail")}
      columns={columns.map((key) => ({
        key,
        label: tOptional(`analytics.col.${key}`) ?? key,
        numeric: rows.length > 0 && typeof rows[0]?.[key] === "number",
        render: (row: JsonObject) => <DetailCell column={key} value={row[key]} />,
      }))}
      rows={rows}
      rowKey={(row) =>
        String(row.id ?? row.order_id ?? row.project_id ?? row.version_id ?? JSON.stringify(row))
      }
    />
  );
}

/* ---------- Desglose de margen por obra (§8 — causa + origen) ---------- */

const CAUSE_KEYS = ["material", "remake", "horas", "descarte", "descuento"];

function MarginBreakdownDialog({
  orgId,
  projectId,
  onClose,
  onHow,
}: {
  orgId: string;
  projectId: string | null;
  onClose: () => void;
  onHow: (key: string) => void;
}): JSX.Element | null {
  const query = useQuery<JsonObject>({
    enabled: projectId !== null,
    queryFn: async ({ signal }) => {
      const response = await analyticsMarginBreakdown(
        { project_id: projectId! },
        { signal, headers: { "X-Organization-ID": orgId } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data as JsonObject;
    },
    queryKey: ["analytics-margin-breakdown", orgId, projectId],
  });
  if (projectId === null) return null;
  const data = query.data;
  const project = sectionOf(data?.project);
  const causes = (data?.causes as JsonObject[] | undefined) ?? [];
  const real = sectionOf(data?.real);
  const quoted = sectionOf(data?.quoted);
  const ots = (data?.ots as JsonObject[] | undefined) ?? [];
  const quotedNet = typeof quoted.net === "number" ? quoted.net : null;
  const realTotal = typeof real.total === "number" ? real.total : null;
  return (
    <Dialog
      title={`${String(project.code ?? "")} · ${String(project.name ?? "")}`}
      onClose={onClose}
      width="l"
    >
      {query.isPending ? (
        <LoadingState shape="table" />
      ) : query.isError || data == null ? (
        <ErrorState title={t("analytics.breakdownError")} onRetry={() => void query.refetch()} />
      ) : (
        <div className="analytics-breakdown">
          <div className="analytics-breakdown__grid">
            <Stat
              decision="docs/analytics/metricas.md#real_margin_pct"
              label={t("analytics.quotedMargin")}
              value={
                <Percent
                  kind="points"
                  value={typeof quoted.margin_pct === "number" ? quoted.margin_pct : null}
                />
              }
            />
            <Stat
              decision="docs/analytics/metricas.md#real_margin_pct"
              label={t("analytics.realMargin")}
              value={
                <Percent
                  kind="points"
                  value={
                    quotedNet !== null && realTotal !== null && quotedNet > 0
                      ? (100 * (quotedNet - realTotal)) / quotedNet
                      : null
                  }
                />
              }
            />
            <Stat
              decision="docs/analytics/metricas.md#real_margin_pct"
              label={t("analytics.realCost")}
              value={<Money value={realTotal} />}
            />
          </div>
          <h4 className="analytics-breakdown__title">{t("analytics.causes")}</h4>
          <ul className="analytics-causes">
            {causes.map((cause) => {
              const key = String(cause.key);
              return (
                <li key={key}>
                  <Link to={`/projects/${projectId}`}>
                    {CAUSE_KEYS.includes(key) ? t(`analytics.cause.${key}` as TranslationKey) : key}
                  </Link>
                  <span className="analytics-causes__amount">
                    {cause.amount === null || cause.amount === undefined ? (
                      <UnknownValue />
                    ) : (
                      <Money value={Number(cause.amount)} />
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
          {Array.isArray(real.missing) && real.missing.length > 0 ? (
            <p className="analytics-missing">{real.missing.map(String).join(" · ")}</p>
          ) : null}
          {ots.length > 0 ? (
            <>
              <h4 className="analytics-breakdown__title">{t("analytics.originOts")}</h4>
              <ul className="analytics-ots">
                {ots.map((ot) => (
                  <li key={String(ot.id)}>
                    <Link to="/production">{String(ot.code)}</Link>
                    <span className="analytics-ots__status">
                      {ot.is_remake === true ? t("analytics.isRemake") : String(ot.status)}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}
          <p className="analytics-breakdown__how">
            <HowButton metricKey="real_margin_pct" onHow={onHow} />
          </p>
        </div>
      )}
    </Dialog>
  );
}

/* ---------- Página ---------- */

const PERIOD_DAYS: Record<Exclude<PeriodKey, "custom">, number> = {
  "7d": 7,
  "30d": 30,
  "90d": 90,
  "12m": 365,
};

export function AnalyticsPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  const allowed = org != null && READER_ROLES.includes(org.role);
  const [params, setParams] = useSearchParams();

  const periodParam = params.get("period") ?? "30d";
  const period: PeriodKey = (PERIODS as readonly string[]).includes(periodParam)
    ? (periodParam as PeriodKey)
    : "30d";
  const desde =
    params.get("desde") ?? clDay(period === "custom" ? PERIOD_DAYS["30d"] : PERIOD_DAYS[period]);
  const hasta = params.get("hasta") ?? clDay(0);

  const [howKey, setHowKey] = useState<string | null>(null);
  const [obraId, setObraId] = useState<string | null>(null);
  const [detailKey, setDetailKey] = useState<DetailKey>("quotes");
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState(false);

  const query = useQuery<JsonObject>({
    enabled: allowed,
    queryFn: async ({ signal }) => {
      const response = await analyticsOverview(
        { desde, hasta },
        { signal, headers: { "X-Organization-ID": org!.id } },
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data as unknown as JsonObject;
    },
    queryKey: ["analytics-overview", org?.id, desde, hasta],
  });

  if (!allowed || org == null) {
    return <DeniedState reason={t("analytics.denied")} />;
  }

  const sales = sectionOf(query.data?.sales);
  const margins = sectionOf(query.data?.margins);
  const production = sectionOf(query.data?.production);
  const field = sectionOf(query.data?.field);
  const financial = sales.financial !== false;
  const definitions = sectionOf(query.data?.definitions);

  const salesM = metricsOf(sales);
  const marginsM = metricsOf(margins);
  const productionM = metricsOf(production);
  const fieldM = metricsOf(field);

  const detailSource = DETAIL_SOURCES.find((d) => d.key === detailKey)!;
  const detailSection =
    detailSource.section === "sales"
      ? sales
      : detailSource.section === "margins"
        ? margins
        : detailSource.section === "production"
          ? production
          : field;
  const detailRows = rowsOf(detailSection, detailSource.rows);

  function setPeriod(next: PeriodKey): void {
    const nextParams = new URLSearchParams(params);
    nextParams.set("period", next);
    if (next === "custom") {
      nextParams.set("desde", desde);
      nextParams.set("hasta", hasta);
    } else {
      nextParams.delete("desde");
      nextParams.delete("hasta");
    }
    setParams(nextParams);
  }

  function setCustomDate(which: "desde" | "hasta", value: string): void {
    if (!value) return;
    const nextParams = new URLSearchParams(params);
    nextParams.set("period", "custom");
    nextParams.set(which, value);
    setParams(nextParams);
  }

  async function downloadCsv(): Promise<void> {
    setExportBusy(true);
    setExportError(false);
    try {
      const { blob, filename } = await apiFetchBlob(
        getAnalyticsExportUrl({ metric: detailKey, desde, hasta }),
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename ?? `dekopen-analitica-${detailKey}.csv`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      setExportError(true);
    } finally {
      setExportBusy(false);
    }
  }

  const punctuality = sectionOf(productionM.ot_punctuality);

  return (
    <section aria-labelledby="page-title" className="analytics">
      <PageHeader
        context={t("analytics.subtitle")}
        headingId="page-title"
        title={t("analytics.title")}
      />

      <div className="analytics-toolbar">
        <SegmentedControl
          name="analytics-period"
          onValueChange={setPeriod}
          options={PERIODS.map((p) => ({
            value: p,
            label: t(`analytics.period.${p}` as TranslationKey),
          }))}
          value={period}
        />
        {period === "custom" ? (
          <span className="analytics-custom">
            <input
              aria-label={t("analytics.from")}
              onChange={(event) => setCustomDate("desde", event.target.value)}
              type="date"
              value={desde}
            />
            <input
              aria-label={t("analytics.to")}
              onChange={(event) => setCustomDate("hasta", event.target.value)}
              type="date"
              value={hasta}
            />
          </span>
        ) : null}
        <span className="analytics-range">
          {desde} → {hasta}
        </span>
      </div>

      {!financial ? (
        <p className="analytics-financial-note" role="note">
          {t("analytics.noFinancial")}
        </p>
      ) : null}

      {query.isPending ? (
        <LoadingState shape="table" />
      ) : query.isError || query.data == null ? (
        <ErrorState title={t("analytics.loadError")} onRetry={() => void query.refetch()} />
      ) : (
        <>
          <Panel title={t("analytics.section.sales")}>
            <div className="analytics-grid">
              {salesM.emitted !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.emitted")}
                  metric={metricOf(salesM.emitted)}
                  metricKey="conversion_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {salesM.approved !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.approved")}
                  metric={metricOf(salesM.approved)}
                  metricKey="conversion_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {salesM.declined !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.declined")}
                  metric={metricOf(salesM.declined)}
                  metricKey="conversion_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {salesM.changes_requested !== undefined &&
              metricOf(salesM.changes_requested).value !== 0 ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.changes")}
                  metric={metricOf(salesM.changes_requested)}
                  metricKey="conversion_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {salesM.conversion_pct !== undefined ? (
                <MetricStat
                  kind="pct"
                  label={t("analytics.conversion")}
                  metric={metricOf(salesM.conversion_pct)}
                  metricKey="conversion_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {salesM.avg_decision_days !== undefined ? (
                <MetricStat
                  kind="days"
                  label={t("analytics.avgDecision")}
                  metric={metricOf(salesM.avg_decision_days)}
                  metricKey="avg_decision_days"
                  onHow={setHowKey}
                />
              ) : null}
              {salesM.pipeline_net !== undefined ? (
                <MetricStat
                  kind="money"
                  label={t("analytics.pipeline")}
                  metric={metricOf(salesM.pipeline_net)}
                  metricKey="pipeline_net"
                  onHow={setHowKey}
                />
              ) : null}
            </div>
            {rowsOf(sales, "pipeline_by_phase").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.pipelineByPhase")}</h3>
                <BarList
                  format={(v) => formatMoney(v, "CLP")}
                  labelKey="phase"
                  rows={rowsOf(sales, "pipeline_by_phase").map((r) => ({
                    ...r,
                    phase: labelOf("analytics.phase", r.phase),
                  }))}
                  valueKey="net"
                />
              </div>
            ) : null}
            {rowsOf(sales, "by_estimator").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.byEstimator")}</h3>
                <BarList
                  format={(v) => `${formatQty(v)} %`}
                  labelKey="estimator"
                  maxValue={100}
                  rows={rowsOf(sales, "by_estimator")}
                  valueKey="conversion_pct"
                />
              </div>
            ) : null}
            {rowsOf(sales, "by_typology").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.byTypology")}</h3>
                <BarList
                  format={(v) => `${formatQty(v)} %`}
                  labelKey="typology"
                  maxValue={100}
                  rows={rowsOf(sales, "by_typology")}
                  valueKey="conversion_pct"
                />
              </div>
            ) : null}
            {rowsOf(sales, "rejection_reasons").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.rejectionReasons")}</h3>
                <ul className="analytics-list">
                  {rowsOf(sales, "rejection_reasons").map((r, i) => (
                    <li key={i}>
                      <span>{String(r.note ?? t("analytics.noReason"))}</span>
                      <span>{formatQty(Number(r.count) || 0)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Panel>

          <Panel title={t("analytics.section.margins")}>
            <div className="analytics-grid">
              {marginsM.quoted_avg_margin_pct !== undefined ? (
                <MetricStat
                  kind="pct"
                  label={t("analytics.quotedAvgMargin")}
                  metric={metricOf(marginsM.quoted_avg_margin_pct)}
                  metricKey="real_margin_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {marginsM.real_avg_margin_pct !== undefined ? (
                <MetricStat
                  kind="pct"
                  label={t("analytics.realAvgMargin")}
                  metric={metricOf(marginsM.real_avg_margin_pct)}
                  metricKey="real_margin_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {marginsM.deviation_pp !== undefined ? (
                <MetricStat
                  kind="pp"
                  label={t("analytics.deviation")}
                  metric={metricOf(marginsM.deviation_pp)}
                  metricKey="deviation_pp"
                  onHow={setHowKey}
                />
              ) : null}
              {marginsM.obras !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.obras")}
                  metric={metricOf(marginsM.obras)}
                  metricKey="real_margin_pct"
                  onHow={setHowKey}
                />
              ) : null}
            </div>
            {rowsOf(margins, "obras").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.obrasDetail")}</h3>
                <DataTable
                  ariaLabel={t("analytics.obrasDetail")}
                  columns={[
                    {
                      key: "code",
                      label: t("analytics.col.code"),
                      render: (row: JsonObject) => <>{String(row.code)}</>,
                    },
                    {
                      key: "project_name",
                      label: t("analytics.col.project_name"),
                      render: (row: JsonObject) => <>{String(row.project_name ?? "")}</>,
                    },
                    {
                      key: "state",
                      label: t("analytics.col.state"),
                      render: (row: JsonObject) => <>{labelOf("analytics.obraState", row.state)}</>,
                    },
                    {
                      key: "quoted_margin_pct",
                      label: t("analytics.col.quoted_margin_pct"),
                      numeric: true,
                      render: (row: JsonObject) => (
                        <DetailCell column="quoted_margin_pct" value={row.quoted_margin_pct} />
                      ),
                    },
                    {
                      key: "real_margin_pct",
                      label: t("analytics.col.real_margin_pct"),
                      numeric: true,
                      render: (row: JsonObject) => (
                        <DetailCell column="real_margin_pct" value={row.real_margin_pct} />
                      ),
                    },
                    {
                      key: "deviation_pp",
                      label: t("analytics.col.deviation_pp"),
                      numeric: true,
                      render: (row: JsonObject) => (
                        <DetailCell column="deviation_pp" value={row.deviation_pp} />
                      ),
                    },
                    {
                      key: "actions",
                      label: "",
                      render: (row: JsonObject) => (
                        <button
                          className="analytics-how"
                          onClick={() => setObraId(String(row.project_id))}
                          type="button"
                        >
                          {t("analytics.viewBreakdown")}
                        </button>
                      ),
                    },
                  ]}
                  rows={rowsOf(margins, "obras")}
                  rowKey={(row) => String(row.project_id)}
                />
                <p className="analytics-hint">{t("analytics.obrasHint")}</p>
              </div>
            ) : null}
          </Panel>

          <Panel title={t("analytics.section.production")}>
            <div className="analytics-grid">
              {productionM.merma_plan_mm !== undefined ? (
                <MetricStat
                  kind="mm"
                  label={t("analytics.mermaPlan")}
                  metric={metricOf(productionM.merma_plan_mm)}
                  metricKey="merma_real_mm"
                  onHow={setHowKey}
                />
              ) : null}
              {productionM.merma_real_mm !== undefined ? (
                <MetricStat
                  kind="mm"
                  label={t("analytics.mermaReal")}
                  metric={metricOf(productionM.merma_real_mm)}
                  metricKey="merma_real_mm"
                  onHow={setHowKey}
                />
              ) : null}
              {productionM.merma_placas_mm2 !== undefined ? (
                <MetricStat
                  kind="mm2"
                  label={t("analytics.mermaPlacas")}
                  metric={metricOf(productionM.merma_placas_mm2)}
                  metricKey="merma_placas_mm2"
                  onHow={setHowKey}
                />
              ) : null}
              {productionM.aprovechamiento_pct !== undefined ? (
                <MetricStat
                  kind="pct"
                  label={t("analytics.aprovechamiento")}
                  metric={metricOf(productionM.aprovechamiento_pct)}
                  metricKey="aprovechamiento_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {productionM.ots_total !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.otsTotal")}
                  metric={metricOf(productionM.ots_total)}
                  metricKey="ot_punctuality"
                  onHow={setHowKey}
                />
              ) : null}
              {productionM.ots_remakes !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.remakes")}
                  metric={metricOf(productionM.ots_remakes)}
                  metricKey="remakes"
                  onHow={setHowKey}
                />
              ) : null}
            </div>
            {rowsOf(production, "station_times").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.stationTimes")}</h3>
                <BarList
                  format={(v) => `${formatQty(v)} h`}
                  labelKey="label"
                  rows={rowsOf(production, "station_times")}
                  valueKey="avg_hours"
                />
              </div>
            ) : null}
            {punctuality.a_tiempo !== undefined ||
            punctuality.atrasadas !== undefined ||
            punctuality.sin_plazo !== undefined ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.punctuality")}</h3>
                <ul className="analytics-list">
                  <li>
                    <span>{t("analytics.punctuality.onTime")}</span>
                    <span>{formatQty(Number(punctuality.a_tiempo) || 0)}</span>
                  </li>
                  <li>
                    <span>{t("analytics.punctuality.late")}</span>
                    <span>{formatQty(Number(punctuality.atrasadas) || 0)}</span>
                  </li>
                  <li>
                    <span>{t("analytics.punctuality.noDeadline")}</span>
                    <span>{formatQty(Number(punctuality.sin_plazo) || 0)}</span>
                  </li>
                </ul>
              </div>
            ) : null}
          </Panel>

          <Panel title={t("analytics.section.field")}>
            <div className="analytics-grid">
              {fieldM.deliveries_on_time_pct !== undefined ? (
                <MetricStat
                  kind="pct"
                  label={t("analytics.deliveriesOnTime")}
                  metric={metricOf(fieldM.deliveries_on_time_pct)}
                  metricKey="deliveries_on_time_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {fieldM.installations !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.installations")}
                  metric={metricOf(fieldM.installations)}
                  metricKey="deliveries_on_time_pct"
                  onHow={setHowKey}
                />
              ) : null}
              {fieldM.incidents_open !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.incidentsOpen")}
                  metric={metricOf(fieldM.incidents_open)}
                  metricKey="incidents_open"
                  onHow={setHowKey}
                />
              ) : null}
              {fieldM.warranties_open !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.warrantiesOpen")}
                  metric={metricOf(fieldM.warranties_open)}
                  metricKey="warranties"
                  onHow={setHowKey}
                />
              ) : null}
              {fieldM.warranties_expiring !== undefined ? (
                <MetricStat
                  kind="count"
                  label={t("analytics.warrantiesExpiring")}
                  metric={metricOf(fieldM.warranties_expiring)}
                  metricKey="warranties"
                  onHow={setHowKey}
                />
              ) : null}
            </div>
            {rowsOf(field, "incidents_by_kind").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.incidentsByKind")}</h3>
                <BarList
                  labelKey="kind"
                  rows={rowsOf(field, "incidents_by_kind").map((r) => ({
                    ...r,
                    kind: labelOf("analytics.incidentKind", r.kind),
                  }))}
                  valueKey="count"
                />
              </div>
            ) : null}
            {rowsOf(field, "incidents_by_typology").length > 0 ? (
              <div className="analytics-sub">
                <h3 className="analytics-sub__title">{t("analytics.incidentsByTypology")}</h3>
                <BarList
                  labelKey="typology"
                  rows={rowsOf(field, "incidents_by_typology")}
                  valueKey="count"
                />
              </div>
            ) : null}
          </Panel>

          <Panel
            actions={
              <button
                className="analytics-export"
                disabled={exportBusy || detailRows.length === 0}
                onClick={() => void downloadCsv()}
                type="button"
              >
                {exportBusy ? t("analytics.exporting") : t("analytics.exportCsv")}
              </button>
            }
            title={t("analytics.section.detail")}
          >
            <div className="analytics-toolbar analytics-toolbar--detail">
              <SegmentedControl
                name="analytics-detail"
                onValueChange={(key) => setDetailKey(key as DetailKey)}
                options={DETAIL_SOURCES.map((d) => ({
                  value: d.key,
                  label: t(`analytics.detail.${d.key}` as TranslationKey),
                }))}
                value={detailKey}
              />
            </div>
            {exportError ? <p className="form-error">{t("analytics.exportError")}</p> : null}
            {detailRows.length === 0 ? (
              <EmptyState title={t("analytics.detailEmpty")} />
            ) : (
              <DetailTable rows={detailRows} />
            )}
          </Panel>
        </>
      )}

      <DefinitionDialog
        definitions={definitions}
        metricKey={howKey}
        onClose={() => setHowKey(null)}
      />
      <MarginBreakdownDialog
        orgId={org.id}
        onClose={() => setObraId(null)}
        onHow={setHowKey}
        projectId={obraId}
      />
    </section>
  );
}
