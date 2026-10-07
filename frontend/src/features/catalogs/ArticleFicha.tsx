/** P16 — ficha de artículo: la tarjeta técnica completa de un perfil.
 * Geometría real con escala/origen/orientación, validaciones de sección
 * (un fallo impide VERIFICADO en el backend), insignia de procedencia que
 * despliega documento origen + revisor + fecha, identidades de compra y
 * refuerzos vinculados. */
import { useEffect, useState } from "react";

import type { ArticleFicha } from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { domainLabel } from "../../i18n/domainLabels";
import { fmtMm } from "../../format";
import { EntityCode, Length } from "../../ui/format";
import { Dialog } from "../../ui/Dialog";
import { StatusChip } from "../../ui/StatusChip";
import { DimLoader } from "../../ui/Signature";
import { SectionPreviewSvg } from "../canvas/SectionPreviewSvg";
import type { catalogApi } from "./catalogModel";
import {
  ProvenanceBadge,
  catalogFieldLabel,
  catalogFieldValue,
  provenanceLabel,
} from "./workspaceTabs";

type Label = Parameters<typeof t>[0];
const ct = (key: string) => t(`catalog.${key}` as Label);
const wst = (key: string) => t(`catalog.ws.${key}` as Label);
const ft = (key: string) => t(`catalog.ficha.${key}` as Label);

export function ArticleFichaDialog({
  api,
  articleId,
  onClose,
}: {
  api: ReturnType<typeof catalogApi>;
  articleId: string;
  onClose: () => void;
}): JSX.Element {
  const [ficha, setFicha] = useState<ArticleFicha | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    const controller = new AbortController();
    void api
      .articleFicha(articleId, controller.signal)
      .then((result) => {
        if (alive) setFicha(result);
      })
      .catch(() => {
        if (alive && !controller.signal.aborted) setError(true);
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [api, articleId]);

  const article = ficha?.article;
  return (
    <Dialog
      title={article ? `${article.sku} · ${article.name}` : ft("title")}
      onClose={onClose}
      width="l"
    >
      {!ficha && !error && <DimLoader label={ct("loading")} />}
      {error && <p role="alert">{ct("errorNetwork")}</p>}
      {ficha && article && (
        <div className="ficha">
          <section className="ficha-geometry">
            <div className="ficha-section-preview">
              <SectionPreviewSvg
                section={article.section}
                faceWidthMm={Number(article.face_width_mm) || 60}
                depthMm={article.section?.depth_mm ? Number(article.section.depth_mm) : undefined}
                material={article.material}
              />
            </div>
            <dl className="ficha-meta">
              <div>
                <dt>{ft("scale")}</dt>
                <dd>{ft("scaleMm")}</dd>
              </div>
              <div>
                <dt>{ct("field.orientation")}</dt>
                <dd>
                  {article.section?.orientation
                    ? ct(`sectionOrientation.${article.section.orientation}`)
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>{ct("field.local_origin")}</dt>
                <dd>
                  {article.section?.local_origin
                    ? domainLabel("LocalOriginEnum", article.section.local_origin).label
                    : "—"}
                </dd>
              </div>
              <div>
                <dt>{ct("field.drawing_ref")}</dt>
                <dd>{article.section?.drawing_ref ?? "—"}</dd>
              </div>
            </dl>
            <ul className="ficha-checks" aria-label={ft("checks")}>
              {ficha.section_checks.map((check) => (
                <li key={check.code} className={check.ok ? "is-ok" : "is-fail"}>
                  <StatusChip
                    label={ft(`check.${check.code}`)}
                    tone={check.ok ? "ok" : "danger"}
                    value={null}
                  />
                  {!check.ok && (
                    <small>
                      {check.value != null && `${ft("value")} ${check.value}`}
                      {check.limit != null && ` · ${ft("limit")} ${check.limit}`}
                    </small>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section className="ficha-facts">
            <h4>{ft("facts")}</h4>
            <dl className="ws-identity-facts">
              <div>
                <dt>{wst("role")}</dt>
                <dd>{ct(`option.${article.role}`)}</dd>
              </div>
              <div>
                <dt>{wst("face")}</dt>
                <dd>
                  <Length value={article.face_width_mm} />
                </dd>
              </div>
              <div>
                <dt>{wst("weight")}</dt>
                <dd>
                  {article.weight_kg_m ? `${fmtMm(article.weight_kg_m)} kg/m` : wst("unknown")}
                </dd>
              </div>
              <div>
                <dt>{ct("field.welding_loss_mm")}</dt>
                <dd>
                  <Length value={article.welding_loss_mm} />
                </dd>
              </div>
              <div>
                <dt>{wst("commercialLength")}</dt>
                <dd>
                  <Length value={article.commercial_length_mm} />
                </dd>
              </div>
              <div>
                <dt>{wst("provenance")}</dt>
                <dd>
                  <ProvenanceBadge row={article} />
                </dd>
              </div>
            </dl>
          </section>

          <section className="ficha-provenance">
            <h4>{ft("provenanceTitle")}</h4>
            <ul className="ficha-stamps">
              <li>
                <strong>{provenanceLabel(article.data_provenance)}</strong>
                {article.data_provenance === "SEED_SYNTHETIC" && <small> · {ft("seedNote")}</small>}
              </li>
              {article.technical_reviewed_at ? (
                <li>
                  {ft("reviewedBy")} {article.reviewed_by_label ?? article.technical_reviewed_by} ·{" "}
                  {String(article.technical_reviewed_at).slice(0, 10)}
                </li>
              ) : (
                <li className="is-warn">{ft("notReviewed")}</li>
              )}
              {article.section_revised_at && (
                <li>
                  {ft("sectionRevisedBy")}{" "}
                  {article.section_revised_by_label ?? article.section_revised_by} ·{" "}
                  {String(article.section_revised_at).slice(0, 10)} · v{article.section_revision}
                </li>
              )}
            </ul>
            {ficha.evidence.length > 0 && (
              <div className="catalog-table-scroll">
                <table className="ws-table">
                  <thead>
                    <tr>
                      <th scope="col">{wst("evidenceField")}</th>
                      <th scope="col">{wst("evidenceValue")}</th>
                      <th scope="col">{wst("evidenceSource")}</th>
                      <th scope="col">{wst("evidenceStateCol")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ficha.evidence.map((row) => (
                      <tr key={String(row.id)}>
                        <td>{catalogFieldLabel(String(row.field_name))}</td>
                        <td>
                          {catalogFieldValue(
                            String(row.field_name),
                            row.value_text == null ? null : String(row.value_text),
                          )}
                          {row.unit ? ` ${row.unit}` : ""}
                          <br />
                          <small>
                            {`${wst("evidenceDeclaredBy")} ${String(row.declared_by_label ?? row.declared_by)}`}
                          </small>
                        </td>
                        <td>
                          {row.source_url ? (
                            <a href={String(row.source_url)} target="_blank" rel="noreferrer">
                              {String(row.source_document)}
                            </a>
                          ) : (
                            String(row.source_document)
                          )}
                          {row.source_page ? ` · ${wst("evidencePage")} ${row.source_page}` : ""}
                        </td>
                        <td>
                          <StatusChip
                            label={wst(`evidenceState.${row.review_state}`)}
                            tone={
                              row.review_state === "REVIEWED"
                                ? "ok"
                                : row.review_state === "REJECTED"
                                  ? "danger"
                                  : "neutral"
                            }
                            value={null}
                          />
                          {row.reviewed_by_label && (
                            <>
                              <br />
                              <small>
                                {String(row.reviewed_by_label)} ·{" "}
                                {String(row.reviewed_at).slice(0, 10)}
                              </small>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {ficha.evidence.length === 0 && <p className="ui-empty-inline">{ft("noEvidence")}</p>}
          </section>

          {ficha.purchase_mappings.length > 0 && (
            <section className="ficha-purchase">
              <h4>{ft("purchase")}</h4>
              <ul className="ficha-lines">
                {ficha.purchase_mappings.map((row) => (
                  <li key={row.id}>
                    <EntityCode value={row.commercial_sku} /> · {row.manufacturer_name}
                    {row.supplier_name ? ` · ${row.supplier_name}` : ""} · {row.purchase_unit}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {ficha.reinforcements.length > 0 && (
            <section className="ficha-reinforcements">
              <h4>{wst("reinforcements")}</h4>
              <ul className="ficha-lines">
                {ficha.reinforcements.map((row) => (
                  <li key={row.id}>
                    <EntityCode value={row.sku} /> · {row.name}
                    {row.thickness_mm ? ` · ${row.thickness_mm} mm` : ""}
                    {row.is_default ? ` · ${wst("default")}` : ""}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Dialog>
  );
}
