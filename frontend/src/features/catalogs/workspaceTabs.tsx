/** P16 — pestañas de la página de sistema: vidrios, herrajes, reglas de
 * compatibilidad, cobertura de costos e historial. Cada tabla muestra la
 * procedencia del dato con la misma regla que gobierna emisión y
 * liberación: quién lo declaró, quién lo revisó, si está verificado. */
import type { ReactNode } from "react";

import type {
  CostCoverageRow,
  GlassTab,
  HardwareTab,
  HistoryTab,
  KitResponse,
  RulesTab,
  TypologyLimitRow,
} from "../../api/generated/models";
import { t, tOptional } from "../../i18n/es-CL";
import { domainLabel } from "../../i18n/domainLabels";
import { EntityCode, Length } from "../../ui/format";
import { StatusChip } from "../../ui/StatusChip";

type Label = Parameters<typeof t>[0];
const ct = (key: string) => t(`catalog.${key}` as Label);
const wst = (key: string) => t(`catalog.ws.${key}` as Label);

/** Same precedence as the workspace badge: a technical review is the only
 * thing that makes a row "Verificado"; provenance alone is not. */
export function ProvenanceBadge({
  row,
}: {
  row: {
    data_provenance?: string;
    review_pending?: boolean;
    technical_reviewed_at?: string | null;
  };
}): JSX.Element {
  if (row.technical_reviewed_at)
    return <StatusChip label={wst("verified")} tone="ok" value={null} />;
  if (row.data_provenance === "LEGACY_UNVERIFIED")
    return <StatusChip label={ct("provenanceLegacy")} tone="warn" value={null} />;
  if (row.review_pending)
    return <StatusChip label={ct("reviewPending")} tone="warn" value={null} />;
  return <StatusChip label={provenanceLabel(row.data_provenance)} tone="neutral" value={null} />;
}

export function provenanceLabel(value: string | null | undefined): string {
  if (!value) return "—";
  if (value === "LEGACY_UNVERIFIED") return t("catalog.provenanceLegacy");
  const key = `catalog.provenance.${value}` as Label;
  return [
    "catalog.provenance.SEED_SYNTHETIC",
    "catalog.provenance.MANUAL",
    "catalog.provenance.IMPORT",
  ].includes(key)
    ? t(key)
    : value;
}

function originLabel(orgId: string | null): string {
  return orgId === null ? ct("global") : ct("own");
}

function optLabel(value: string | null | undefined): string {
  if (!value) return "—";
  const key = `catalog.option.${value}` as Label;
  try {
    const label = t(key);
    return label === key ? value : label;
  } catch {
    return value;
  }
}

function unitLabel(value: string | null | undefined): string {
  if (!value) return "—";
  return tOptional(`purchasing.unitValue.${value}.other` as Label) ?? value;
}

/** Nombre de campo y valor de evidencia en español — las fichas y la tabla
 * de fuentes nunca vuelcan claves técnicas (`role`, `GLAZING_BEAD`) en crudo. */
export function catalogFieldLabel(name: string): string {
  return tOptional(`catalog.field.${name}` as Label) ?? name;
}

export function catalogFieldValue(name: string, value: string | null | undefined): string {
  if (!value) return "—";
  if (name === "role")
    return (
      tOptional(`catalog.option.${value}` as Label) ??
      domainLabel("CatalogItemRoleEnum", value).label
    );
  if (name === "finish_class")
    return (
      tOptional(`projects.color.${value}` as Label) ??
      tOptional(`catalog.option.finishClass.${value}` as Label) ??
      value
    );
  return value;
}

function DataTable({
  head,
  rows,
  empty,
}: {
  head: string[];
  rows: ReactNode;
  empty: string;
}): JSX.Element {
  const hasRows = rows !== null && rows !== false;
  if (!hasRows) return <p className="ws-empty">{empty}</p>;
  return (
    <div className="catalog-table-scroll">
      <table className="ws-table">
        <thead>
          <tr>
            {head.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  );
}

function SubSection({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="ws-subsection">
      <header className="ws-subsection-head">
        <h4>
          {title} <span className="ws-count">{count}</span>
        </h4>
      </header>
      {children}
    </section>
  );
}

/* ---------- Vidrios ---------- */

export function GlassPanel({ glass }: { glass: GlassTab }): JSX.Element {
  return (
    <>
      <SubSection title={wst("glassProducts")} count={glass.products.length}>
        <DataTable
          head={[
            wst("glassName"),
            wst("glassNotation"),
            wst("glassComposition"),
            ct("field.glass_thickness_mm"),
            wst("glassSafety"),
            wst("supplier"),
            wst("provenance"),
          ]}
          empty={wst("noGlassProducts")}
          rows={
            glass.products.length
              ? glass.products.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{row.commercial_name}</th>
                    <td>
                      <EntityCode value={row.notation} />
                    </td>
                    <td>
                      <code className="ws-mono">
                        {Array.isArray(row.composition?.panes)
                          ? (row.composition?.panes as unknown[]).join(" · ")
                          : "—"}
                      </code>
                    </td>
                    <td>
                      <Length value={row.total_thickness_mm} />
                    </td>
                    <td>{row.safety_class ?? "—"}</td>
                    <td>{row.supplier_name ?? "—"}</td>
                    <td>
                      <ProvenanceBadge row={row} />{" "}
                      <small className="ws-origin">{originLabel(row.org_id)}</small>
                    </td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("glassFormats")} count={glass.purchase_mappings.length}>
        <DataTable
          head={[
            wst("glassTechSku"),
            wst("commercialSku"),
            wst("manufacturer"),
            wst("unit"),
            ct("field.version"),
            wst("provenance"),
          ]}
          empty={wst("noGlassFormats")}
          rows={
            glass.purchase_mappings.length
              ? glass.purchase_mappings.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">
                      <EntityCode value={row.technical_sku} />
                    </th>
                    <td>
                      <EntityCode value={row.purchasing_sku} />
                    </td>
                    <td>{row.manufacturer_name}</td>
                    <td>{unitLabel(row.purchase_unit)}</td>
                    <td>v{row.version}</td>
                    <td>
                      {provenanceLabel(row.provenance?.data_provenance as string | undefined)}{" "}
                      <small className="ws-origin">{originLabel(row.org_id)}</small>
                    </td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("glassSurcharges")} count={glass.surcharges.length}>
        <DataTable
          head={[wst("product"), wst("kind"), wst("unit"), wst("unitCost"), wst("provenance")]}
          empty={wst("noGlassSurcharges")}
          rows={
            glass.surcharges.length
              ? glass.surcharges.map((row) => {
                  const product = glass.products.find((item) => item.id === row.product_id);
                  return (
                    <tr key={row.id} id={`ws-row-${row.id}`}>
                      <th scope="row">{product?.commercial_name ?? row.product_id}</th>
                      <td>{wst(`glassSurcharge.${row.kind}`)}</td>
                      <td>{unitLabel(row.unit)}</td>
                      <td>
                        {row.unit_cost} {row.currency}
                      </td>
                      <td>
                        <ProvenanceBadge row={row} />
                      </td>
                    </tr>
                  );
                })
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("glassSafetyRules")} count={glass.safety_rules.length}>
        <DataTable
          head={[
            wst("rule"),
            wst("requiredSafety"),
            wst("severity"),
            wst("applies"),
            wst("source"),
          ]}
          empty={wst("noGlassSafetyRules")}
          rows={
            glass.safety_rules.length
              ? glass.safety_rules.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">
                      {row.code} — {row.title}
                    </th>
                    <td>{optLabel(row.required_safety)}</td>
                    <td>
                      <StatusChip
                        label={optLabel(row.severity)}
                        tone={row.severity === "ERROR" ? "danger" : "warn"}
                        value={null}
                      />
                    </td>
                    <td>
                      {(row.applies_openings ?? []).length
                        ? (row.applies_openings as string[]).map(optLabel).join(", ")
                        : wst("allOpenings")}
                    </td>
                    <td>{row.source_ref ?? "—"}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("glassLimits")} count={glass.type_limits.length}>
        <DataTable
          head={[
            wst("rule"),
            wst("laminaKind"),
            wst("thicknessRange"),
            wst("sideRange"),
            wst("areaRange"),
            wst("severity"),
          ]}
          empty={wst("noGlassLimits")}
          rows={
            glass.type_limits.length
              ? glass.type_limits.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{row.code}</th>
                    <td>{optLabel(row.lamina_kind)}</td>
                    <td>
                      {row.thickness_min_mm ?? "—"}–{row.thickness_max_mm ?? "—"} mm
                    </td>
                    <td>
                      {row.min_side_mm ?? "—"}–{row.max_side_mm ?? "—"} mm
                    </td>
                    <td>
                      {row.min_area_m2 ?? "—"}–{row.max_area_m2 ?? "—"} m²
                    </td>
                    <td>
                      <StatusChip
                        label={optLabel(row.severity)}
                        tone={row.severity === "ERROR" ? "danger" : "warn"}
                        value={null}
                      />
                    </td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
    </>
  );
}

/* ---------- Herrajes ---------- */

function rangeFor(limit: TypologyLimitRow | undefined): string | null {
  if (!limit) return null;
  const width =
    limit.min_leaf_width_mm || limit.max_leaf_width_mm
      ? `${limit.min_leaf_width_mm ?? "—"}–${limit.max_leaf_width_mm ?? "—"}`
      : null;
  const height =
    limit.min_leaf_height_mm || limit.max_leaf_height_mm
      ? `${limit.min_leaf_height_mm ?? "—"}–${limit.max_leaf_height_mm ?? "—"}`
      : null;
  const parts = [
    width && `${wst("leafWidth")} ${width} mm`,
    height && `${wst("leafHeight")} ${height} mm`,
    limit.max_leaf_weight_kg && `${limit.max_leaf_weight_kg} kg`,
  ].filter(Boolean);
  return parts.length ? parts.join(" · ") : null;
}

export function HardwarePanel({
  hardware,
  kits,
  limits,
}: {
  hardware: HardwareTab;
  kits: KitResponse[];
  limits: TypologyLimitRow[];
}): JSX.Element {
  const openings = [...new Set(kits.map((kit) => kit.opening_type))].sort();
  return (
    <>
      <SubSection title={wst("kitGroups")} count={kits.length}>
        {!openings.length ? (
          <p className="ws-empty">{wst("noKits")}</p>
        ) : (
          openings.map((opening) => {
            const group = kits.filter((kit) => kit.opening_type === opening);
            const range = rangeFor(limits.find((limit) => limit.opening_type === opening));
            return (
              <div key={opening} className="ws-kit-group">
                <header>
                  <h5>{ct(`option.${opening}`)}</h5>
                  {range && <small>{range}</small>}
                </header>
                <ul className="ws-kit-list">
                  {group.map((kit) => (
                    <li key={kit.id} id={`ws-row-${kit.id}`}>
                      <strong>{kit.name}</strong> <EntityCode value={kit.sku} />{" "}
                      <ProvenanceBadge row={kit} />
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        )}
      </SubSection>
      <SubSection title={wst("handleModels")} count={hardware.handle_models.length}>
        <DataTable
          head={[ct("field.sku"), wst("name"), wst("kind"), wst("opening"), wst("priceDelta")]}
          empty={wst("noHandleModels")}
          rows={
            hardware.handle_models.length
              ? hardware.handle_models.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">
                      <EntityCode value={row.sku} />
                    </th>
                    <td>{row.name}</td>
                    <td>{optLabel(row.kind)}</td>
                    <td>{optLabel(row.opening_type)}</td>
                    <td>{row.price_delta_clp ?? "—"}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("hardwareOptions")} count={hardware.options.length}>
        <DataTable
          head={[ct("field.sku"), wst("name"), wst("kind"), wst("opening"), wst("priceDelta")]}
          empty={wst("noHardwareOptions")}
          rows={
            hardware.options.length
              ? hardware.options.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">
                      <EntityCode value={row.sku} />
                    </th>
                    <td>{row.name}</td>
                    <td>{optLabel(row.kind)}</td>
                    <td>{optLabel(row.opening_type)}</td>
                    <td>{row.price_delta_clp ?? "—"}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("kitPurchase")} count={hardware.purchase_mappings.length}>
        <DataTable
          head={[
            wst("kit"),
            wst("commercialSku"),
            wst("manufacturer"),
            wst("unit"),
            wst("provenance"),
          ]}
          empty={wst("noKitPurchase")}
          rows={
            hardware.purchase_mappings.length
              ? hardware.purchase_mappings.map((row) => {
                  const kit = kits.find((item) => item.id === row.hardware_kit_id);
                  return (
                    <tr key={row.id} id={`ws-row-${row.id}`}>
                      <th scope="row">{kit?.name ?? row.hardware_kit_id}</th>
                      <td>
                        <EntityCode value={row.purchasing_sku} />
                      </td>
                      <td>{row.manufacturer_name}</td>
                      <td>{row.purchase_unit}</td>
                      <td>
                        {provenanceLabel(row.provenance?.data_provenance as string | undefined)}
                      </td>
                    </tr>
                  );
                })
              : null
          }
        />
      </SubSection>
    </>
  );
}

/* ---------- Reglas de compatibilidad ---------- */

export function RulesPanel({ rules }: { rules: RulesTab }): JSX.Element {
  return (
    <>
      <SubSection title={wst("cutRules")} count={rules.cut_rules.length}>
        <DataTable
          head={[
            wst("role"),
            ct("field.cut_angle_deg"),
            wst("weldedEnds"),
            ct("field.interlock_deduction_mm"),
            wst("rounding"),
          ]}
          empty={wst("noCutRules")}
          rows={
            rules.cut_rules.length
              ? rules.cut_rules.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{ct(`option.${row.role}`)}</th>
                    <td>{row.cut_angle_deg}°</td>
                    <td>{row.welded_ends ?? "—"}</td>
                    <td>
                      <Length value={row.interlock_deduction_mm} />
                    </td>
                    <td>
                      <Length value={row.rounding_mm} />
                    </td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("reinforcementRules")} count={rules.reinforcement_rules.length}>
        <DataTable
          head={[
            wst("role"),
            wst("finishClass"),
            wst("minLength"),
            wst("mandatory"),
            ct("field.cut_deduction_mm"),
            wst("screws"),
          ]}
          empty={wst("noReinforcementRules")}
          rows={
            rules.reinforcement_rules.length
              ? rules.reinforcement_rules.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{ct(`option.${row.role}`)}</th>
                    <td>{optLabel(row.finish_class)}</td>
                    <td>
                      <Length value={row.min_length_mm} />
                    </td>
                    <td>{row.mandatory ? wst("mandatoryYes") : "—"}</td>
                    <td>
                      <Length value={row.cut_deduction_mm} />
                    </td>
                    <td>{row.screws_per_m ?? "—"}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("typologyLimits")} count={rules.typology_limits.length}>
        <DataTable
          head={[
            wst("opening"),
            wst("leafWidth"),
            wst("leafHeight"),
            wst("maxWeight"),
            wst("aspect"),
          ]}
          empty={wst("noTypologyLimits")}
          rows={
            rules.typology_limits.length
              ? rules.typology_limits.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{optLabel(row.opening_type)}</th>
                    <td>
                      {row.min_leaf_width_mm ?? "—"}–{row.max_leaf_width_mm ?? "—"} mm
                    </td>
                    <td>
                      {row.min_leaf_height_mm ?? "—"}–{row.max_leaf_height_mm ?? "—"} mm
                    </td>
                    <td>{row.max_leaf_weight_kg ? `${row.max_leaf_weight_kg} kg` : "—"}</td>
                    <td>{row.max_aspect_ratio ?? "—"}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("openingCapabilities")} count={rules.opening_capabilities.length}>
        <DataTable
          head={[
            wst("movement"),
            wst("directions"),
            wst("leafRoles"),
            wst("unitKinds"),
            wst("fixedInSash"),
          ]}
          empty={wst("noOpeningCapabilities")}
          rows={
            rules.opening_capabilities.length
              ? rules.opening_capabilities.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{optLabel(row.movement)}</th>
                    <td>{(row.directions as string[]).map(optLabel).join(", ") || "—"}</td>
                    <td>{(row.leaf_roles as string[]).map(optLabel).join(", ") || "—"}</td>
                    <td>{(row.unit_kinds as string[]).map(optLabel).join(", ") || "—"}</td>
                    <td>{row.fixed_in_sash ? "●" : "—"}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("mountingRules")} count={rules.mounting_rules.length}>
        <DataTable
          head={[wst("rule"), ct("field.version"), wst("authority")]}
          empty={wst("noMountingRules")}
          rows={
            rules.mounting_rules.length
              ? rules.mounting_rules.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">
                      <EntityCode value={row.code} /> — {row.label}
                    </th>
                    <td>v{row.version}</td>
                    <td>{originLabel(row.org_id)}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("inspectorConfigs")} count={rules.inspector_configs.length}>
        <DataTable
          head={[wst("rule"), wst("params"), ct("state")]}
          empty={wst("noInspectorConfigs")}
          rows={
            rules.inspector_configs.length
              ? rules.inspector_configs.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">
                      <EntityCode value={row.rule_id} />
                    </th>
                    <td>
                      <code className="ws-mono">{JSON.stringify(row.params)}</code>
                    </td>
                    <td>{ct(row.is_active ? "active" : "inactive")}</td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
    </>
  );
}

/* ---------- Costos (cobertura P07) ---------- */

export function CostsPanel({ costs }: { costs: CostCoverageRow[] }): JSX.Element {
  return (
    <SubSection title={wst("costCoverage")} count={costs.length}>
      <p className="ws-hint">{wst("costCoverageHint")}</p>
      <DataTable
        head={[
          ct("field.sku"),
          wst("name"),
          wst("kind"),
          wst("unit"),
          wst("coverage"),
          wst("resolve"),
        ]}
        empty={wst("noCostItems")}
        rows={
          costs.length
            ? costs.map((row) => (
                <tr key={row.sku} id={`ws-row-${row.sku}`}>
                  <th scope="row">
                    <EntityCode value={row.sku} />
                  </th>
                  <td>{row.name}</td>
                  <td>{optLabel(row.kind)}</td>
                  <td>{row.required_unit}</td>
                  <td>
                    {row.active_cost_items > 0 ? (
                      <StatusChip
                        label={`${row.active_cost_items} ${wst("costItems")}`}
                        tone="ok"
                        value={null}
                      />
                    ) : (
                      <StatusChip label={wst("uncovered")} tone="warn" value={null} />
                    )}
                  </td>
                  <td>
                    {row.active_cost_items === 0 && (
                      <a className="link-button" href="/pricing/cost-lists">
                        {wst("openCostLists")}
                      </a>
                    )}
                  </td>
                </tr>
              ))
            : null
        }
      />
    </SubSection>
  );
}

/* ---------- Historial ---------- */

const WS_IMPORT_STATUS: Record<string, Label> = {
  UPLOADED: "catalog.ws.importStatus.UPLOADED",
  EXTRACTING: "catalog.ws.importStatus.EXTRACTING",
  REVIEW_READY: "catalog.ws.importStatus.REVIEW_READY",
  CONFIRMED: "catalog.ws.importStatus.CONFIRMED",
  FAILED: "catalog.ws.importStatus.FAILED",
};

function statusTone(status: string): "ok" | "warn" | "danger" | "neutral" {
  if (status === "CONFIRMED") return "ok";
  if (status === "FAILED") return "danger";
  if (status === "REVIEW_READY" || status === "EXTRACTING") return "warn";
  return "neutral";
}

export function HistoryPanel({ history }: { history: HistoryTab }): JSX.Element {
  return (
    <>
      <SubSection title={wst("importHistory")} count={history.imports.length}>
        <DataTable
          head={[wst("file"), wst("kind"), ct("state"), wst("uploadedBy"), wst("reviewedBy")]}
          empty={wst("noImports")}
          rows={
            history.imports.length
              ? history.imports.map((row) => (
                  <tr key={row.id} id={`ws-row-${row.id}`}>
                    <th scope="row">{row.file_name}</th>
                    <td>{row.kind === "IMAGE" ? wst("kindImage") : row.kind}</td>
                    <td>
                      <StatusChip
                        label={t(WS_IMPORT_STATUS[row.status] ?? "catalog.ws.importStatus.FAILED")}
                        tone={statusTone(row.status)}
                        value={null}
                      />
                      {row.error_code && (
                        <small className="ws-evidence-applies">
                          {" "}
                          <EntityCode value={row.error_code} />
                        </small>
                      )}
                    </td>
                    <td>
                      {row.created_by_label ?? row.created_by}
                      <br />
                      <small>{row.created_at.slice(0, 10)}</small>
                    </td>
                    <td>
                      {row.reviewed_by_label ? (
                        <>
                          {row.reviewed_by_label}
                          {row.reviewed_at && (
                            <>
                              <br />
                              <small>{row.reviewed_at.slice(0, 10)}</small>
                            </>
                          )}
                        </>
                      ) : (
                        wst("notReviewed")
                      )}
                    </td>
                  </tr>
                ))
              : null
          }
        />
      </SubSection>
      <SubSection title={wst("importEvents")} count={history.events.length}>
        <DataTable
          head={[wst("file"), wst("event"), wst("actor"), wst("when"), wst("detail")]}
          empty={wst("noImportEvents")}
          rows={
            history.events.length
              ? history.events.map((row) => {
                  const detail = (row.detail ?? {}) as Record<string, unknown>;
                  const file = history.imports.find((item) => item.id === row.import_id);
                  return (
                    <tr key={row.id} id={`ws-row-${row.id}`}>
                      <th scope="row">{file?.file_name ?? row.import_id}</th>
                      <td>
                        <StatusChip
                          label={wst(`importEvent.${row.event}`)}
                          tone={row.event === "CONFIRMED" ? "ok" : "neutral"}
                          value={null}
                        />
                      </td>
                      <td>{row.actor_label ?? wst("systemActor")}</td>
                      <td>{row.created_at.slice(0, 16).replace("T", " ")}</td>
                      <td>
                        <small className="ws-mono">
                          {detail.candidates_count !== undefined
                            ? `${detail.candidates_count} ${wst("candidates")}`
                            : detail.confirmed_count !== undefined
                              ? `${detail.confirmed_count} ${wst("confirmed")}`
                              : String(detail.error_code ?? "—")}
                        </small>
                      </td>
                    </tr>
                  );
                })
              : null
          }
        />
      </SubSection>
    </>
  );
}
