/** D07 · «Vano y montaje» — sección del inspector.
 *
 * El medidor registra el vano en obra (1–3 puntos por eje, muro,
 * escuadra/desplome), elige el tipo de montaje que el taller aplica y el
 * motor resuelve la medida de fabricación con su desglose y sus avisos.
 * La fijación manual queda registrada con su motivo; el estado de la
 * medida (cliente → rectificada → confirmada) manda sobre la liberación
 * de producción. */
import type { ReactElement } from "react";
import { useMemo } from "react";
import type {
  CodeEnum,
  MeasurementResolveResponse,
  MeasurementResponse,
  MeasurementResponseStateEnum,
  MountingRuleResponse,
  WallTypeEnum,
} from "../../api/generated/models";
import { fmtMm } from "../../format";
import { t } from "../../i18n/es-CL";
import { domainLabel } from "../../i18n/domainLabels";
import { StatusChip } from "../../ui/StatusChip";
import type { VanoDraft } from "./vano";

const WALL_TYPES: WallTypeEnum[] = ["MASONRY", "CONCRETE", "PARTITION", "WOOD"];

interface VanoSectionProps {
  draft: VanoDraft;
  onDraftChange: (next: VanoDraft) => void;
  rules: MountingRuleResponse[] | undefined;
  rulesPending: boolean;
  preview: MeasurementResolveResponse | null;
  previewPending: boolean;
  previewError: boolean;
  saved: MeasurementResponse | null;
  onConfirm: (confirmed: boolean) => void;
  confirmBusy: boolean;
  positionPersisted: boolean;
  disabled: boolean;
}

const MAX_POINTS = 3;

/** Una columna de 1–3 puntos de medida por eje; «+» añade el siguiente. */
function PointInputs({
  legend,
  values,
  onChange,
}: {
  legend: string;
  values: string[];
  onChange: (next: string[]) => void;
}): ReactElement {
  return (
    <div className="vano-points">
      <span className="vano-points__legend">{legend}</span>
      <div className="vano-points__row">
        {values.map((value, index) => (
          <label key={index} className="vano-point">
            <span className="vano-point__tag">
              {t("projects.vanoPointShort")} {index + 1}
            </span>
            <input
              inputMode="decimal"
              value={value}
              onChange={(event) => {
                const next = [...values];
                next[index] = event.target.value;
                onChange(next);
              }}
            />
            {values.length > 1 && (
              <button
                type="button"
                className="vano-point__remove"
                aria-label={`− ${legend} ${index + 1}`}
                onClick={() => onChange(values.filter((_, at) => at !== index))}
              >
                ×
              </button>
            )}
          </label>
        ))}
        {values.length < MAX_POINTS && (
          <button
            type="button"
            className="vano-point__add"
            onClick={() => onChange([...values, ""])}
          >
            +
          </button>
        )}
      </div>
      {values.length > 1 && <p className="vano-note">{t("projects.vanoUsesMin")}</p>}
    </div>
  );
}

export function VanoSection({
  draft,
  onDraftChange,
  rules,
  rulesPending,
  preview,
  previewPending,
  previewError,
  saved,
  onConfirm,
  confirmBusy,
  positionPersisted,
  disabled,
}: VanoSectionProps): ReactElement {
  const state = (saved?.state ?? "CLIENT_DECLARED") as MeasurementResponseStateEnum;
  const patch = (part: Partial<VanoDraft>) => onDraftChange({ ...draft, ...part });

  const breakdown = useMemo(
    () => (preview?.resolution ? preview.resolution.breakdown : []),
    [preview],
  );
  const warnings = preview?.resolution?.warnings ?? [];
  const selectedRule = useMemo(
    () => rules?.find((rule) => rule.id === draft.mountingRuleId),
    [rules, draft.mountingRuleId],
  );

  return (
    <details className="vano-section" open>
      <summary>{t("projects.vanoSection")}</summary>
      <fieldset className="vano-section__body" disabled={disabled}>
        <p className="vano-note">{t("projects.vanoHint")}</p>

        <div className="vano-state">
          <StatusChip enumName="MeasurementResponseStateEnum" value={state} />
          {saved?.confirmed_at && (
            <span className="vano-state__stamp">
              {t("projects.vanoConfirmedAt").replace("{time}", saved.confirmed_at.slice(0, 10))}
            </span>
          )}
          {positionPersisted && (
            <button
              type="button"
              className="ui-btn ui-btn--sm"
              disabled={confirmBusy}
              onClick={() => onConfirm(state !== "CONFIRMED")}
            >
              {state !== "CONFIRMED" ? t("projects.vanoConfirm") : t("projects.vanoUnconfirm")}
            </button>
          )}
        </div>

        <div className="vano-grid">
          <PointInputs
            legend={t("projects.vanoWidthPoints")}
            values={draft.widthPoints}
            onChange={(widthPoints) => patch({ widthPoints })}
          />
          <PointInputs
            legend={t("projects.vanoHeightPoints")}
            values={draft.heightPoints}
            onChange={(heightPoints) => patch({ heightPoints })}
          />
        </div>

        <div className="vano-grid vano-grid--cols">
          <label className="vano-field">
            <span>{t("projects.vanoWallType")}</span>
            <select
              className="assembly-select"
              value={draft.wallType}
              onChange={(event) => patch({ wallType: event.target.value as VanoDraft["wallType"] })}
            >
              <option value="">{t("projects.vanoNoWall")}</option>
              {WALL_TYPES.map((wall) => (
                <option key={wall} value={wall}>
                  {domainLabel("WallTypeEnum", wall).label}
                </option>
              ))}
            </select>
          </label>
          <label className="vano-field">
            <span>{t("projects.vanoSquare")}</span>
            <input
              inputMode="decimal"
              value={draft.squareMm}
              onChange={(event) => patch({ squareMm: event.target.value })}
            />
          </label>
          <label className="vano-field">
            <span>{t("projects.vanoPlumb")}</span>
            <input
              inputMode="decimal"
              value={draft.plumbMm}
              onChange={(event) => patch({ plumbMm: event.target.value })}
            />
          </label>
        </div>

        <label className="vano-field">
          <span>{t("projects.vanoMounting")}</span>
          <select
            className="assembly-select"
            value={draft.mountingRuleId}
            onChange={(event) => patch({ mountingRuleId: event.target.value })}
          >
            <option value="">{t("projects.vanoMountingPick")}</option>
            {rules?.map((rule) => (
              <option key={rule.id} value={rule.id}>
                {domainLabel("CodeEnum", rule.code as CodeEnum).label}
              </option>
            ))}
          </select>
          {rulesPending && <span className="vano-note">{t("projects.loading")}</span>}
          {selectedRule?.review_pending && (
            <span className="vano-note">{t("projects.vanoReviewPending")}</span>
          )}
        </label>

        <label className="vano-field vano-field--wide">
          <span>{t("projects.vanoNotes")}</span>
          <input value={draft.notes} onChange={(event) => patch({ notes: event.target.value })} />
        </label>

        <label className="vano-lock">
          <input
            type="checkbox"
            checked={draft.lockEnabled}
            onChange={(event) => patch({ lockEnabled: event.target.checked })}
          />
          <span>{t("projects.vanoLock")}</span>
        </label>
        {draft.lockEnabled && (
          <div className="vano-grid vano-grid--cols">
            <label className="vano-field">
              <span>{t("assembly.width")} (mm)</span>
              <input
                inputMode="decimal"
                value={draft.lockWidthMm}
                onChange={(event) => patch({ lockWidthMm: event.target.value })}
              />
            </label>
            <label className="vano-field">
              <span>{t("assembly.height")} (mm)</span>
              <input
                inputMode="decimal"
                value={draft.lockHeightMm}
                onChange={(event) => patch({ lockHeightMm: event.target.value })}
              />
            </label>
            <label className="vano-field vano-field--wide">
              <span>{t("projects.vanoLockWhy")}</span>
              <input
                placeholder={t("projects.vanoLockWhyPlaceholder")}
                value={draft.lockReason}
                onChange={(event) => patch({ lockReason: event.target.value })}
              />
            </label>
          </div>
        )}

        {previewPending && <p className="vano-note">{t("projects.loading")}</p>}
        {previewError && (
          <p className="vano-note vano-note--warn" role="alert">
            {t("projects.vanoResolveError")}
          </p>
        )}
        {preview?.resolution && (
          <div className="vano-result">
            <p className="vano-result__headline">
              <StatusChip
                enumName="FabricationSourceEnum"
                value={preview.resolution.fabrication_source}
              />{" "}
              {fmtMm(preview.resolution.fabrication_width_mm)} ×{" "}
              {fmtMm(preview.resolution.fabrication_height_mm)} mm
            </p>
            <p className="vano-subhead">{t("projects.vanoBreakdown")}</p>
            <ul className="vano-breakdown">
              {breakdown.map((item) => (
                <li key={item.side}>
                  <span>{item.label}</span>
                  <span>
                    {Number(item.mm) >= 0 ? "+" : "−"}
                    {fmtMm(Math.abs(Number(item.mm)))} mm
                  </span>
                </li>
              ))}
            </ul>
            {preview.resolution.width_spread_mm !== null &&
              Number(preview.resolution.width_spread_mm) > 0 && (
                <p className="vano-note">
                  {t("projects.vanoSpreadNote").replace(
                    "{mm}",
                    fmtMm(preview.resolution.width_spread_mm),
                  )}
                </p>
              )}
            {warnings.length > 0 && (
              <ul className="vano-warnings">
                {warnings.map((warning) => (
                  <li key={warning.code} className="vano-note vano-note--warn" role="alert">
                    {warning.message ?? warning.code}
                  </li>
                ))}
              </ul>
            )}
            {selectedRule &&
              Array.isArray(selectedRule.authority.fixings) &&
              (selectedRule.authority.fixings as Array<unknown>).length > 0 && (
                <p className="vano-note">
                  {t("projects.vanoFixings")}:{" "}
                  {(
                    selectedRule.authority.fixings as Array<{
                      code?: string;
                      label?: string;
                      qty_per_unit?: string;
                    }>
                  )
                    .map(
                      (fixing) =>
                        (fixing.code ?? fixing.label ?? "") +
                        (fixing.qty_per_unit ? ` ×${fixing.qty_per_unit}` : ""),
                    )
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
            {selectedRule &&
              Array.isArray(selectedRule.authority.frame_extensions) &&
              (selectedRule.authority.frame_extensions as Array<unknown>).length > 0 && (
                <p className="vano-note">
                  {t("projects.vanoExtensions")}:{" "}
                  {(
                    selectedRule.authority.frame_extensions as Array<{
                      side?: string;
                      label?: string;
                      mm?: string;
                    }>
                  )
                    .map(
                      (extension) =>
                        (extension.label ?? extension.side ?? "") +
                        (extension.mm ? ` +${extension.mm} mm` : ""),
                    )
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              )}
          </div>
        )}
        {!preview?.resolution && !previewPending && !saved?.vano && (
          <p className="vano-note">{t("projects.vanoNoRecord")}</p>
        )}
      </fieldset>
    </details>
  );
}
