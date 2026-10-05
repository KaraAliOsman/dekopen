import { useState } from "react";
import type { ExtraArticleOption, ExtraLine, ExtraSuggestion } from "../../api/generated/models";
import { formatMoney } from "../../format";
import { t, tDynamic, tOptional } from "../../i18n/es-CL";
import type { ExtraSelectionJson } from "../canvas/productEditing";

/** D06 — «Extras de la posición»: declared accessories for the vano.
 *
 * The panel only edits selection records (sku + parameters); the engine
 * re-measures every declaration into sublines and cuts — a UI control
 * never fabricates a quantity or a price.
 */

const SIDED_KINDS = new Set(["FRAME_EXTENSION", "COVER_TRIM"]);
const COUNTED_KINDS = new Set(["MOSQUITO_SCREEN", "VENTILATOR"]);
const SIDE_KEYS = ["top", "right", "bottom", "left"] as const;

function defaultSelection(article: ExtraArticleOption): ExtraSelectionJson {
  if (SIDED_KINDS.has(article.kind)) return { sku: article.sku, sides: [...SIDE_KEYS] };
  return { sku: article.sku };
}

interface PositionExtrasPanelProps {
  /** Catalog extras this system qualifies for (design options payload). */
  articles: ExtraArticleOption[];
  extras: ExtraSelectionJson[];
  suggestions: ExtraSuggestion[];
  /** Engine-derived sublines from the latest evaluation (`bom.extra_lines`). */
  lines: ExtraLine[];
  disabled: boolean;
  onChange: (next: ExtraSelectionJson[]) => void;
}

export function PositionExtrasPanel({
  articles,
  extras,
  suggestions,
  lines,
  disabled,
  onChange,
}: PositionExtrasPanelProps): JSX.Element | null {
  const [pick, setPick] = useState("");
  const selected = new Set(extras.map((extra) => extra.sku));
  const bySku = new Map(articles.map((article) => [article.sku, article]));
  const available = articles.filter((article) => !selected.has(article.sku));
  const pending = suggestions.filter(
    (suggestion) => !selected.has(suggestion.sku) && bySku.has(suggestion.sku),
  );

  const update = (sku: string, patch: Partial<ExtraSelectionJson>) =>
    onChange(extras.map((extra) => (extra.sku === sku ? { ...extra, ...patch } : extra)));

  const add = (sku: string) => {
    const article = bySku.get(sku);
    if (!article) return;
    onChange([...extras, defaultSelection(article)]);
    setPick("");
  };

  const toggleSide = (extra: ExtraSelectionJson, side: string) => {
    const sides = new Set(extra.sides ?? []);
    if (sides.has(side)) sides.delete(side);
    else sides.add(side);
    update(extra.sku, { sides: [...sides] });
  };

  return (
    <section className="assembly-inspector position-extras" aria-label={t("projects.extras")}>
      <header className="assembly-inspector__header">
        <h4>{t("projects.extras")}</h4>
      </header>
      {pending.length > 0 && (
        <ul className="position-extras__suggestions">
          {pending.map((suggestion) => (
            <li key={suggestion.sku}>
              <div className="position-extras__suggestion">
                <strong>{suggestion.name}</strong>
                <span className="position-extras__reason">{suggestion.reason}</span>
              </div>
              <button
                type="button"
                className="ui-button ui-button--ghost"
                disabled={disabled}
                onClick={() => add(suggestion.sku)}
              >
                {t("projects.extrasAdd")}
              </button>
            </li>
          ))}
        </ul>
      )}
      {extras.length === 0 ? (
        <p className="assembly-hint">{t("projects.extrasEmpty")}</p>
      ) : (
        <ul className="position-extras__list">
          {extras.map((extra) => {
            const article = bySku.get(extra.sku);
            const kindLabel =
              tOptional(`catalog.extraKind.${article?.kind ?? ""}`) ?? article?.kind ?? "";
            return (
              <li key={extra.sku} className="position-extras__item">
                <div className="position-extras__item-head">
                  <span>
                    {article?.name ?? extra.sku}
                    {kindLabel ? <em> · {kindLabel}</em> : null}
                  </span>
                  <button
                    type="button"
                    className="ui-button ui-button--ghost"
                    disabled={disabled}
                    onClick={() => onChange(extras.filter((item) => item.sku !== extra.sku))}
                  >
                    {t("projects.extrasRemove")}
                  </button>
                </div>
                {article?.kind === "SILL" && (
                  <div className="position-extras__fields">
                    <label>
                      <span>{t("projects.extrasVueloLeft")}</span>
                      <input
                        inputMode="decimal"
                        disabled={disabled}
                        placeholder={article.vuelo_default_mm ?? "0"}
                        value={extra.vuelo_left_mm ?? ""}
                        onChange={(event) =>
                          update(extra.sku, {
                            vuelo_left_mm: event.target.value || undefined,
                          })
                        }
                      />
                    </label>
                    <label>
                      <span>{t("projects.extrasVueloRight")}</span>
                      <input
                        inputMode="decimal"
                        disabled={disabled}
                        placeholder={article.vuelo_default_mm ?? "0"}
                        value={extra.vuelo_right_mm ?? ""}
                        onChange={(event) =>
                          update(extra.sku, {
                            vuelo_right_mm: event.target.value || undefined,
                          })
                        }
                      />
                    </label>
                  </div>
                )}
                {article && SIDED_KINDS.has(article.kind) && (
                  <div
                    className="position-extras__fields position-extras__sides"
                    role="group"
                    aria-label={t("projects.extrasSides")}
                  >
                    {SIDE_KEYS.map((side) => (
                      <label key={side} className="position-extras__side">
                        <input
                          type="checkbox"
                          disabled={disabled}
                          checked={(extra.sides ?? []).includes(side)}
                          onChange={() => toggleSide(extra, side)}
                        />
                        <span>{tDynamic("projects.extrasSide", side)}</span>
                      </label>
                    ))}
                  </div>
                )}
                {article && COUNTED_KINDS.has(article.kind) && (
                  <div className="position-extras__fields">
                    <label>
                      <span>{t("projects.extrasQty")}</span>
                      <input
                        inputMode="numeric"
                        disabled={disabled}
                        placeholder={t("projects.extrasQtyAuto")}
                        value={extra.qty?.toString() ?? ""}
                        onChange={(event) => {
                          const value = Number(event.target.value);
                          update(extra.sku, {
                            qty:
                              event.target.value === "" || !Number.isFinite(value) || value < 1
                                ? undefined
                                : Math.floor(value),
                          });
                        }}
                      />
                    </label>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {available.length > 0 && (
        <div className="position-extras__add">
          <select
            className="assembly-select"
            aria-label={t("projects.extrasAdd")}
            disabled={disabled}
            value={pick}
            onChange={(event) => {
              if (event.target.value) add(event.target.value);
              else setPick("");
            }}
          >
            <option value="">{t("projects.extrasAdd")}</option>
            {available.map((article) => (
              <option key={article.sku} value={article.sku}>
                {article.name}
                {tOptional(`catalog.extraKind.${article.kind}`)
                  ? ` · ${tOptional(`catalog.extraKind.${article.kind}`)}`
                  : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      {lines.length > 0 && (
        <dl className="inspector-summary__list position-extras__lines">
          {lines.map((line) => (
            <div key={line.sku} className="inspector-summary__row">
              <dt>
                {line.name}
                {line.detail ? <em> — {line.detail}</em> : null}
              </dt>
              <dd>
                {line.unit_price === null || line.total_price === null
                  ? `${line.quantity} ${line.unit} · ${t("ui.noData")}`
                  : `${line.quantity} ${line.unit} × ${formatMoney(
                      line.unit_price,
                      line.unit_price_currency,
                    )} = ${formatMoney(line.total_price, line.unit_price_currency)}`}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
