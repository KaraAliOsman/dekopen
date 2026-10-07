/* P18 — Desempeño térmico y normativa chilena (OGUC 4.1.10).
 *
 * El panel del proyecto muestra, por posición, el Uw que el motor computó
 * (con su traza: qué Uf/Ug/Ψg entran y con qué autoridad), la clase de
 * permeabilidad al aire resuelta del informe de ensayo y el veredicto de
 * cumplimiento para la zona térmica elegida. Ningún semáforo vive sin
 * causa: cada veredicto lleva el listado de códigos que lo explican, y un
 * valor DEMO nunca produce «Cumple». El §8 («techo») propone la
 * alternativa conforme más barata para cada posición que falla.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  positionThermalAlternatives,
  positionsUpdate,
  projectsThermal,
  projectsUpdate,
} from "../../api/generated/dekopen";
import type {
  OrientationCompliance,
  PatchedProjectUpdateRequest,
  PositionResponse,
  PositionUpdateRequest,
  ProjectResponse,
  ProjectThermal,
  ResolvedClasses,
  ThermalAlternativesResponse,
  ThermalCause,
  ThermalPosition,
  UwComputation,
} from "../../api/generated/models";
import { ApiError } from "../../api/apiMutator";
import { t, tOptional } from "../../i18n/es-CL";
import type { TranslationKey } from "../../i18n/es-CL";
import { formatAreaM2, formatDims, formatMoney, formatPercent, formatUvalue } from "../../format";
import { StatusChip } from "../../ui/StatusChip";
import { TraceButton } from "../../ui/Signature";
import type { Trace } from "../../ui/Signature";

const ZONES = ["A", "B", "C", "D", "E", "F", "G", "H", "I"] as const;
const USES = ["RESIDENTIAL", "EQUIPMENT"] as const;
const ORIENTATIONS = ["N", "OP", "S", "OGT"] as const;
const POSITION_ORIENTATIONS = ["N", "OP", "S", "OGT", "ROOF"] as const;

function verdictTone(verdict: string | null | undefined): "ok" | "danger" | "warn" | "neutral" {
  if (verdict === "COMPLIES") return "ok";
  if (verdict === "FAILS") return "danger";
  if (verdict === "INSUFFICIENT_DATA") return "warn";
  return "neutral";
}

export function verdictLabel(verdict: string | null | undefined): string {
  if (!verdict) return t("projects.thermal.verdict.NO_DATA");
  const key = `projects.thermal.verdict.${verdict}`;
  return tOptional(key) ?? verdict;
}

function authorityLabel(authority: string | null | undefined): string {
  if (!authority) return t("projects.thermal.authority.NONE");
  return tOptional(`projects.thermal.authority.${authority}`) ?? authority;
}

function causeLabel(cause: ThermalCause): string {
  const text = tOptional(`projects.thermal.cause.${cause.code}`) ?? cause.code;
  return cause.detail ? `${text} · ${cause.detail}` : text;
}

/** La traza del Uw — qué entradas lo alimentaron y con qué autoridad. El
 * panel nunca recalcula: todo viene del motor vía API. */
function uwTrace(uw: UwComputation | null | undefined): Trace | null {
  if (!uw) return null;
  const inputs: { label: string; value: string }[] = [
    { label: t("projects.thermal.traceAg"), value: `${formatAreaM2(uw.ag_m2)} m²` },
    { label: t("projects.thermal.traceAf"), value: `${formatAreaM2(uw.af_m2)} m²` },
    { label: t("projects.thermal.traceLg"), value: `${formatAreaM2(uw.lg_m)} m` },
  ];
  for (const pane of uw.panes ?? []) {
    inputs.push({
      label: `${t("projects.thermal.tracePane")} ${pane.article_sku}`,
      value: [
        `Ug ${formatUvalue(pane.ug_w_m2k)}`,
        `${formatAreaM2(pane.area_m2)} m²`,
        pane.spacer_code ? `Ψg ${formatUvalue(pane.psi_w_m_k)} (${pane.spacer_code})` : null,
      ]
        .filter(Boolean)
        .join(" · "),
    });
  }
  for (const zone of uw.frame ?? []) {
    inputs.push({
      label: `${t("projects.thermal.traceFrame")} ${zone.member_group}`,
      value: [`Uf ${formatUvalue(zone.uf_w_m2k)}`, `${formatAreaM2(zone.area_m2)} m²`]
        .filter(Boolean)
        .join(" · "),
    });
  }
  for (const missing of uw.missing ?? []) {
    const text = tOptional(`projects.thermal.missing.${missing.code}`) ?? missing.code;
    inputs.push({
      label: t("projects.thermal.traceMissing"),
      value: missing.detail ? `${text} · ${missing.detail}` : text,
    });
  }
  const authority = [
    authorityLabel(uw.authority),
    ...(uw.missing ?? []).map(() => t("projects.thermal.traceMissingNote")),
  ].join(" ");
  return {
    formula: t("projects.thermal.formula"),
    inputs,
    authority,
    engineVersion: "dekopen-engine",
  };
}

function classesText(classes: ResolvedClasses | null | undefined): string {
  if (!classes) return "—";
  const parts = [
    classes.air_class != null ? `A${classes.air_class}` : null,
    classes.water_class ?? null,
    classes.wind_class ?? null,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : "—";
}

/* ------------------------------------------------------------------ */
/* Ajustes del proyecto — zona térmica, uso y áreas de fachada.         */
/* ------------------------------------------------------------------ */

function ThermalSettings({
  project,
  orgId,
  editable,
  thermal,
  onChanged,
  onError,
}: {
  project: ProjectResponse;
  orgId: string;
  editable: boolean;
  thermal: ProjectThermal | null;
  onChanged(): Promise<unknown>;
  onError(message: string): void;
}): JSX.Element {
  const [zone, setZone] = useState<string>(project.thermal_zone ?? "");
  const [use, setUse] = useState<string>(project.thermal_use ?? "RESIDENTIAL");
  const [walls, setWalls] = useState<Record<string, string>>(() => {
    const stored = project.thermal_wall_areas ?? {};
    return {
      N: String(stored.N ?? ""),
      OP: String(stored.OP ?? ""),
      S: String(stored.S ?? ""),
      OGT: String(stored.OGT ?? ""),
    };
  });
  const [saving, setSaving] = useState(false);

  async function save(): Promise<void> {
    setSaving(true);
    const wallAreas: Record<string, string> = {};
    for (const orientation of ORIENTATIONS) {
      const raw = (walls[orientation] ?? "").trim().replace(",", ".");
      if (raw !== "") {
        const num = Number(raw);
        if (!Number.isFinite(num) || num <= 0) {
          setSaving(false);
          onError(t("projects.thermal.wallInvalid"));
          return;
        }
        wallAreas[orientation] = raw;
      }
    }
    const body: PatchedProjectUpdateRequest = {
      thermal_zone: (zone || null) as PatchedProjectUpdateRequest["thermal_zone"],
      thermal_use: use as PatchedProjectUpdateRequest["thermal_use"],
      thermal_wall_areas: Object.keys(wallAreas).length ? wallAreas : null,
      expected_updated_at: project.updated_at,
    };
    try {
      const response = await projectsUpdate(project.id, body, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      onError("");
      await onChanged();
    } catch (caught) {
      onError(
        caught instanceof ApiError && caught.status === 409
          ? t("projects.conflict")
          : t("projects.saveError"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="thermal-settings" aria-label={t("projects.thermal.settings")}>
      <div className="thermal-settings__grid">
        <label>
          {t("projects.thermal.zone")}
          <select
            disabled={!editable || saving}
            onChange={(event) => setZone(event.target.value)}
            value={zone}
          >
            <option value="">{t("projects.thermal.zoneNone")}</option>
            {ZONES.map((item) => (
              <option key={item} value={item}>
                {t("projects.thermal.zoneValue")} {item}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("projects.thermal.use")}
          <select
            disabled={!editable || saving}
            onChange={(event) => setUse(event.target.value)}
            value={use}
          >
            {USES.map((item) => (
              <option key={item} value={item}>
                {t(`projects.thermal.useValue.${item}` as TranslationKey)}
              </option>
            ))}
          </select>
        </label>
        {ORIENTATIONS.map((orientation) => (
          <label key={orientation}>
            {t(`projects.thermal.wall.${orientation}` as TranslationKey)}
            <input
              disabled={!editable || saving}
              inputMode="decimal"
              onChange={(event) =>
                setWalls((current) => ({ ...current, [orientation]: event.target.value }))
              }
              placeholder={t("projects.thermal.wallPlaceholder")}
              value={walls[orientation] ?? ""}
            />
          </label>
        ))}
      </div>
      {editable && (
        <div className="form-actions">
          <button
            className="ui-button ui-button--small"
            disabled={saving}
            onClick={() => void save()}
            type="button"
          >
            {t("projects.thermal.save")}
          </button>
        </div>
      )}
      {!thermal?.thermal_zone && (
        <p className="ui-empty-inline">{t("projects.thermal.noZoneHint")}</p>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Orientaciones — % de vanos sobre paramentos expuestos (Tabla 3).     */
/* ------------------------------------------------------------------ */

function OrientationTable({ rows }: { rows: OrientationCompliance[] }): JSX.Element | null {
  if (!rows.length) return null;
  return (
    <section aria-label={t("projects.thermal.orientationTitle")}>
      <h4 className="thermal-heading">{t("projects.thermal.orientationTitle")}</h4>
      <div className="projects-table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">{t("projects.thermal.colOrientation")}</th>
              <th scope="col">{t("projects.thermal.colWindowArea")}</th>
              <th scope="col">{t("projects.thermal.colWallArea")}</th>
              <th scope="col">{t("projects.thermal.colPctActual")}</th>
              <th scope="col">{t("projects.thermal.colPctAllowed")}</th>
              <th scope="col">{t("projects.thermal.colVerdict")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.orientation}>
                <th scope="row">
                  {t(`projects.thermal.orientation.${row.orientation}` as TranslationKey)}
                </th>
                <td>{formatAreaM2(row.window_area_m2)} m²</td>
                <td>
                  {row.wall_area_m2 != null
                    ? `${formatAreaM2(row.wall_area_m2)} m²`
                    : t("projects.thermal.noData")}
                </td>
                <td>
                  {row.actual_pct != null
                    ? formatPercent(row.actual_pct, "points")
                    : t("projects.thermal.noData")}
                </td>
                <td>{row.allowed_pct != null ? `${row.allowed_pct} %` : "—"}</td>
                <td>
                  <StatusChip
                    label={verdictLabel(row.verdict)}
                    tone={verdictTone(row.verdict)}
                    value={null}
                  />
                  {row.causes.length > 0 && (
                    <small className="thermal-causes">
                      {row.causes.map(causeLabel).join(" · ")}
                    </small>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* §8 — alternativas conformes para una posición que no cumple.         */
/* ------------------------------------------------------------------ */

function PositionAlternatives({
  positionId,
  orgId,
  currency,
}: {
  positionId: string;
  orgId: string;
  currency: string;
}): JSX.Element {
  const query = useQuery({
    queryKey: ["thermal-alternatives", orgId, positionId],
    queryFn: async () => {
      const response = await positionThermalAlternatives(positionId, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    retry: false,
  });
  const data: ThermalAlternativesResponse | undefined = query.data;
  if (query.isLoading) return <p className="ui-empty-inline">{t("projects.loading")}</p>;
  if (query.isError)
    return <p className="ui-empty-inline">{t("projects.thermal.alternativesError")}</p>;
  if (!data?.alternatives.length)
    return <p className="ui-empty-inline">{t("projects.thermal.noAlternatives")}</p>;
  return (
    <table className="thermal-alternatives">
      <thead>
        <tr>
          <th scope="col">{t("projects.thermal.altKind")}</th>
          <th scope="col">{t("projects.thermal.altLabel")}</th>
          <th scope="col">{t("projects.thermal.altUw")}</th>
          <th scope="col">{t("projects.thermal.altDelta")}</th>
        </tr>
      </thead>
      <tbody>
        {data.alternatives.map((alt, index) => (
          <tr key={`${alt.kind}-${index}`}>
            <td>{t(`projects.thermal.kind.${alt.kind}` as TranslationKey)}</td>
            <td>{alt.label}</td>
            <td>
              {alt.uw_w_m2k != null ? (
                <>
                  {formatUvalue(alt.uw_w_m2k)} <small className="thermal-causes">W/m²·K</small>
                </>
              ) : (
                t("projects.thermal.noData")
              )}
            </td>
            <td>
              {alt.price_delta_net != null
                ? formatMoney(alt.price_delta_net, currency)
                : t("projects.thermal.noData")}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/* ------------------------------------------------------------------ */
/* Fila de posición — Uw + traza, clases, veredicto, §8.                */
/* ------------------------------------------------------------------ */

export function PositionThermalLine({
  position,
  thermal,
  orgId,
  currency,
  editable,
  onChanged,
  onError,
}: {
  position: PositionResponse | null;
  thermal: ThermalPosition;
  orgId: string;
  currency: string;
  editable: boolean;
  onChanged(): Promise<unknown>;
  onError(message: string): void;
}): JSX.Element {
  const [altOpen, setAltOpen] = useState(false);
  const [savingOrientation, setSavingOrientation] = useState(false);
  const uw = thermal.thermal.uw;
  const classes = thermal.thermal.classes;
  const verdict = thermal.thermal.verdict;

  async function changeOrientation(value: string): Promise<void> {
    if (!position) return;
    setSavingOrientation(true);
    const body: PositionUpdateRequest = {
      location_tag: position.location_tag ?? "",
      quantity: position.quantity,
      design: position.design as PositionUpdateRequest["design"],
      thermal_orientation: (value || null) as PositionUpdateRequest["thermal_orientation"],
      expected_updated_at: position.updated_at,
    };
    try {
      const response = await positionsUpdate(position.id, body, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      onError("");
      await onChanged();
    } catch (caught) {
      onError(
        caught instanceof ApiError && caught.status === 409
          ? t("projects.conflict")
          : t("projects.saveError"),
      );
    } finally {
      setSavingOrientation(false);
    }
  }

  return (
    <tr id={`thermal-row-${thermal.id}`}>
      <th scope="row">
        {thermal.position_index}. {thermal.location_tag || t("projects.issue.noLocation")}
      </th>
      <td>
        <select
          aria-label={t("projects.thermal.positionOrientation")}
          disabled={!editable || savingOrientation}
          onChange={(event) => void changeOrientation(event.target.value)}
          value={thermal.thermal_orientation ?? ""}
        >
          <option value="">{t("projects.thermal.orientationNone")}</option>
          {POSITION_ORIENTATIONS.map((item) => (
            <option key={item} value={item}>
              {t(`projects.thermal.orientation.${item}` as TranslationKey)}
            </option>
          ))}
        </select>
      </td>
      <td>{formatDims(thermal.width_mm, thermal.height_mm)}</td>
      <td>{formatAreaM2(thermal.surface_m2)} m²</td>
      <td>
        <span className="thermal-uw">
          <strong>
            {uw?.uw_w_m2k != null
              ? `${formatUvalue(uw.uw_w_m2k)} W/m²·K`
              : t("projects.thermal.noData")}
          </strong>
          <TraceButton trace={uwTrace(uw)} />
        </span>
      </td>
      <td>
        <span className="thermal-classes">{classesText(classes)}</span>
        {classes?.report_ref ? (
          <small className="thermal-causes">
            {classes.report_ref}
            {classes.laboratory ? ` · ${classes.laboratory}` : ""}
          </small>
        ) : null}
      </td>
      <td>
        <StatusChip label={verdictLabel(verdict)} tone={verdictTone(verdict)} value={null} />
        {thermal.thermal.causes.length > 0 && (
          <small className="thermal-causes">
            {thermal.thermal.causes.map(causeLabel).join(" · ")}
          </small>
        )}
      </td>
      <td>
        {verdict === "FAILS" && (
          <button
            aria-expanded={altOpen}
            className="ui-button ui-button--small"
            onClick={() => setAltOpen((open) => !open)}
            type="button"
          >
            {t("projects.thermal.improve")}
          </button>
        )}
        {altOpen && (
          <PositionAlternatives currency={currency} orgId={orgId} positionId={thermal.id} />
        )}
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/* Mini-ficha — Uw + clase + orientación en la tarjeta de posición.     */
/* ------------------------------------------------------------------ */

export function PositionThermalFiche({
  position,
  thermal,
  orgId,
  editable,
  onChanged,
  onError,
}: {
  position: PositionResponse;
  thermal: ThermalPosition | undefined;
  orgId: string;
  editable: boolean;
  onChanged(): Promise<unknown>;
  onError(message: string): void;
}): JSX.Element {
  const [saving, setSaving] = useState(false);
  const uw = thermal?.thermal.uw;
  const classes = thermal?.thermal.classes;

  async function changeOrientation(value: string): Promise<void> {
    setSaving(true);
    const body: PositionUpdateRequest = {
      location_tag: position.location_tag ?? "",
      quantity: position.quantity,
      design: position.design as PositionUpdateRequest["design"],
      thermal_orientation: (value || null) as PositionUpdateRequest["thermal_orientation"],
      expected_updated_at: position.updated_at,
    };
    try {
      const response = await positionsUpdate(position.id, body, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      onError("");
      await onChanged();
    } catch (caught) {
      onError(
        caught instanceof ApiError && caught.status === 409
          ? t("projects.conflict")
          : t("projects.saveError"),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="position-thermal">
      <div>
        <dt>{t("projects.thermal.positionOrientation")}</dt>
        <dd>
          {editable ? (
            <select
              aria-label={t("projects.thermal.positionOrientation")}
              disabled={saving}
              onChange={(event) => void changeOrientation(event.target.value)}
              value={position.thermal_orientation ?? ""}
            >
              <option value="">{t("projects.thermal.orientationNone")}</option>
              {POSITION_ORIENTATIONS.map((item) => (
                <option key={item} value={item}>
                  {t(`projects.thermal.orientation.${item}` as TranslationKey)}
                </option>
              ))}
            </select>
          ) : (
            ((position.thermal_orientation &&
              t(
                `projects.thermal.orientation.${position.thermal_orientation}` as TranslationKey,
              )) ??
            "—")
          )}
        </dd>
      </div>
      <div>
        <dt>{t("projects.thermal.colUw")}</dt>
        <dd>
          {uw?.uw_w_m2k != null ? (
            <>
              {formatUvalue(uw.uw_w_m2k)} W/m²·K <TraceButton trace={uwTrace(uw)} />
            </>
          ) : (
            t("projects.thermal.noData")
          )}
        </dd>
      </div>
      <div>
        <dt>{t("projects.thermal.colClasses")}</dt>
        <dd>
          {classesText(classes)}
          {classes?.report_ref ? (
            <small className="thermal-causes">{classes.report_ref}</small>
          ) : null}
        </dd>
      </div>
      <div>
        <dt>{t("projects.thermal.colVerdict")}</dt>
        <dd>
          <StatusChip
            label={verdictLabel(thermal?.thermal.verdict)}
            tone={verdictTone(thermal?.thermal.verdict)}
            value={null}
          />
        </dd>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Panel — veredicto del proyecto + orientaciones + posiciones.         */
/* ------------------------------------------------------------------ */

export function ProjectThermalPanel({
  project,
  orgId,
  editable,
  onChanged,
  onError,
}: {
  project: ProjectResponse;
  orgId: string;
  editable: boolean;
  onChanged(): Promise<unknown>;
  onError(message: string): void;
}): JSX.Element {
  const query = useQuery({
    queryKey: ["project-thermal", orgId, project.id, project.updated_at],
    queryFn: async () => {
      const response = await projectsThermal(project.id, {
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    retry: false,
  });
  const thermal = query.data ?? null;
  const positionById = useMemo(() => {
    const map = new Map<string, PositionResponse>();
    for (const position of project.positions ?? []) map.set(position.id, position);
    return map;
  }, [project.positions]);

  if (query.isLoading) return <p role="status">{t("projects.loading")}</p>;
  if (query.isError) {
    return <p className="ui-empty-inline">{t("projects.thermal.loadError")}</p>;
  }
  return (
    <div className="project-thermal">
      <header className="project-thermal__head">
        <div>
          <h3>{t("projects.thermal.title")}</h3>
          <p className="project-thermal__note">{t("projects.thermal.subtitle")}</p>
        </div>
        {thermal && (
          <StatusChip
            label={verdictLabel(thermal.verdict)}
            tone={verdictTone(thermal.verdict)}
            value={null}
          />
        )}
      </header>
      <ThermalSettings
        editable={editable}
        onChanged={onChanged}
        onError={onError}
        orgId={orgId}
        project={project}
        thermal={thermal}
      />
      {thermal && (
        <>
          <OrientationTable rows={thermal.orientations} />
          <section aria-label={t("projects.thermal.positionsTitle")}>
            <h4 className="thermal-heading">{t("projects.thermal.positionsTitle")}</h4>
            <div className="projects-table-scroll">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{t("projects.thermal.colPosition")}</th>
                    <th scope="col">{t("projects.thermal.positionOrientation")}</th>
                    <th scope="col">{t("projects.dims")}</th>
                    <th scope="col">{t("projects.thermal.colSurface")}</th>
                    <th scope="col">{t("projects.thermal.colUw")}</th>
                    <th scope="col">{t("projects.thermal.colClasses")}</th>
                    <th scope="col">{t("projects.thermal.colVerdict")}</th>
                    <th scope="col">{t("projects.thermal.colImprove")}</th>
                  </tr>
                </thead>
                <tbody>
                  {thermal.positions.map((row) => (
                    <PositionThermalLine
                      currency={project.currency}
                      editable={editable}
                      key={row.id}
                      onChanged={onChanged}
                      onError={onError}
                      orgId={orgId}
                      position={positionById.get(row.id) ?? null}
                      thermal={row}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
