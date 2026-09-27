import { FormEvent, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import { portalQuoteDecide, portalQuoteRetrieve } from "../../api/generated/dekopen";
import type { PortalPosition, PortalQuote } from "../../api/generated/models";
import type { PositionDesign } from "../../api/generated/models";
import { t, TranslationKey } from "../../i18n/es-CL";
import { formatRevision } from "../../format";
import { PositionThumb, THUMB_MEMBERS } from "../projects/PositionThumb";
import { reSkinMembers, type MemberGeometry } from "../canvas/members";
import "./portal.css";
import { formatDate, formatMoney } from "../money";

const money = formatMoney;

/** Sealed finish text → the closest renderable member surface — a Nogal foil
 * quote must not draw a white PVC window beside "Terminación: Nogal". */
const FINISH_SURFACES: [RegExp, string][] = [
  [/madera|nogal|roble|caoba|wengue|cedro|sapeli|rovere|nuss|wood|foil|foliad/i, "PVC_FOIL"],
  [/antracit|grafito|negro|dark|black|bronce|bronze/i, "ALUMINIUM_ANTHRACITE"],
  [/aluminio|aluminum|anodiz|natural/i, "ALUMINIUM"],
];

function positionMembers(position: PortalPosition): MemberGeometry {
  const text =
    `${position.color_interior ?? ""} ${position.color_exterior ?? ""} ${position.finish ?? ""}`
      .normalize("NFD")
      .replace(/\p{Diacritic}/gu, "");
  for (const [pattern, material] of FINISH_SURFACES) {
    if (pattern.test(text)) return reSkinMembers(THUMB_MEMBERS, material);
  }
  return THUMB_MEMBERS;
}

/** The contract error body carries a precise public detail for portal codes
 * (revoked / expired / superseded) — prefer it over a generic fallback. */
function errorDetail(payload: unknown): string | null {
  const detail = (payload as { error?: { detail?: unknown } } | null)?.error?.detail;
  return typeof detail === "string" && detail !== "" ? detail : null;
}

function positionDesign(position: PortalPosition): PositionDesign {
  return {
    system_id: "",
    nominal_width_mm: position.width_mm,
    nominal_height_mm: position.height_mm,
    // The sealed interior color drives the preview's finish semantics —
    // exterior face coloring is conveyed separately in the facts line.
    color: position.color_interior || "WHITE",
    parametric_tree: position.parametric_tree,
  };
}

const typologyKeys: Record<string, TranslationKey> = {
  FIXED: "typology.fixed",
  TURN: "typology.turn",
  TILT_TURN: "typology.tiltTurn",
  TILT: "typology.tilt",
  SLIDING_2L: "typology.sliding2l",
  SLIDING_3L: "typology.sliding3l",
  SLIDING_4L: "typology.sliding4l",
  SLIDING: "typology.sliding",
  AWNING: "typology.awning",
  DOOR_ENTRY: "typology.doorEntry",
  DOOR_DOUBLE: "typology.doorDouble",
  CORNER: "typology.corner",
  BOW: "typology.bow",
  FRAMELESS: "typology.frameless",
  COMPOSITE: "typology.composite",
};

/** discount_pct persists as a fraction (0.10 = 10 %) — never print it raw. */
function pctLabel(raw: string | null | undefined): string {
  const fraction = Number(raw);
  if (!Number.isFinite(fraction)) return `${raw}%`;
  const pct = fraction <= 1 ? fraction * 100 : fraction;
  return `${pct.toFixed(2).replace(/\.?0+$/, "")}%`;
}

function typologyLabel(raw: string | null | undefined): string {
  const key = raw ? typologyKeys[raw] : undefined;
  return key ? t(key) : (raw ?? "");
}

/** Long location/index lists wrap horribly — first…last plus the count. */
function compactList(values: string[], max = 6): string {
  if (values.length === 0) return "—";
  return values.length <= max
    ? values.join(", ")
    : `${values[0]} … ${values[values.length - 1]} (${values.length})`;
}

/** Identical openings collapse into one proposal card — a 15-unit block of
 * the same window reads as one group with its locations, not fifteen cards. */
function groupPositions(positions: PortalPosition[]): {
  key: string;
  position: PortalPosition;
  locations: string[];
  indexes: string[];
  quantity: number;
  totalNet: number;
}[] {
  const groups = new Map<
    string,
    {
      key: string;
      position: PortalPosition;
      locations: string[];
      indexes: string[];
      quantity: number;
      totalNet: number;
    }
  >();
  for (const position of positions) {
    const key = JSON.stringify([
      position.typology,
      position.width_mm,
      position.height_mm,
      position.color_interior,
      position.color_exterior,
      position.glass_specs,
      position.price_net,
      position.parametric_tree,
    ]);
    const group = groups.get(key);
    const location = position.location_tag?.trim();
    const index = position.position_index != null ? String(position.position_index) : null;
    if (group) {
      if (location && !group.locations.includes(location)) group.locations.push(location);
      if (index) group.indexes.push(index);
      group.quantity += position.quantity ?? 1;
      group.totalNet += Number(position.price_net) || 0;
    } else {
      groups.set(key, {
        key,
        position,
        locations: location ? [location] : [],
        indexes: index ? [index] : [],
        quantity: position.quantity ?? 1,
        totalNet: Number(position.price_net) || 0,
      });
    }
  }
  return [...groups.values()];
}

function PositionGroupCard({
  group,
  currency,
  taxRate,
}: {
  group: ReturnType<typeof groupPositions>[number];
  currency: string;
  // IVA-included line totals reconcile with the headline Total — a customer
  // thinks in gross, so the card leads with it when the rate is derivable.
  taxRate: number | null;
}): JSX.Element {
  const { position } = group;
  const [variant, setVariant] = useState<"studio" | "elevation">("studio");
  const specs = position.glass_specs ?? [];
  const finished = position.finish ?? null;
  const members = positionMembers(position);
  const hasPrice = position.price_net != null;
  const locations =
    group.locations.length > 0
      ? compactList(group.locations)
      : `Pos. ${compactList(group.indexes)}`;
  return (
    <article className="portal-position">
      <div className="portal-position__thumb">
        <PositionThumb design={positionDesign(position)} variant={variant} members={members} />
        <div className="portal-position__views" role="group" aria-label={t("portal.views")}>
          <button
            type="button"
            className="portal-view-toggle"
            data-active={variant === "studio"}
            onClick={() => setVariant("studio")}
          >
            {t("portal.viewStudio")}
          </button>
          <button
            type="button"
            className="portal-view-toggle"
            data-active={variant === "elevation"}
            onClick={() => setVariant("elevation")}
          >
            {t("portal.viewTechnical")}
          </button>
        </div>
      </div>
      <div className="portal-position__body">
        <p className="portal-position__id">
          {locations}
          {group.quantity > 1 ? (
            <span className="portal-position__count">×{group.quantity}</span>
          ) : null}
        </p>
        <p className="portal-position__typology">{typologyLabel(position.typology)}</p>
        <dl className="portal-position__facts">
          <div>
            <dt>{t("portal.dims")}</dt>
            <dd>
              {Math.round(Number(position.width_mm))} × {Math.round(Number(position.height_mm))} mm
            </dd>
          </div>
          <div>
            <dt>{t("portal.qty")}</dt>
            <dd>{group.quantity}</dd>
          </div>
          {specs.length > 0 ? (
            <div>
              <dt>{t("portal.glass")}</dt>
              <dd>{specs.join(" · ")}</dd>
            </div>
          ) : null}
          {finished ? (
            <div>
              <dt>{t("portal.finish")}</dt>
              <dd>{finished}</dd>
            </div>
          ) : null}
          {Number(position.discount_pct) > 0 ? (
            <div>
              <dt>{t("portal.discount")}</dt>
              <dd>{pctLabel(position.discount_pct)}</dd>
            </div>
          ) : null}
        </dl>
        <p className="portal-position__price">
          {hasPrice && group.quantity > 1 && (
            <span className="portal-position__unit">
              {t("portal.unitNet")} {money(String(group.totalNet / group.quantity), currency)}
            </span>
          )}
          <span>
            {t("portal.lineNet")} {hasPrice ? money(String(group.totalNet), currency) : "—"}
          </span>
          <strong>
            {hasPrice
              ? taxRate !== null
                ? money(String(Math.round(group.totalNet * (1 + taxRate))), currency)
                : money(String(group.totalNet), currency)
              : "—"}
            {taxRate !== null && hasPrice ? (
              <span className="portal-position__taxincl"> {t("portal.taxIncluded")}</span>
            ) : null}
          </strong>
        </p>
      </div>
    </article>
  );
}

export function PortalQuotePage(): JSX.Element {
  const { token = "" } = useParams();
  const [quote, setQuote] = useState<PortalQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [rut, setRut] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [decideError, setDecideError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await portalQuoteRetrieve(token);
        if (!active) return;
        if (response.status !== 200) {
          // Revoked/expired/superseded links carry a precise public detail —
          // a generic "check the link" would blame the customer's URL.
          setError(
            response.status === 404
              ? t("portal.notFound")
              : (errorDetail(response.data) ?? t("portal.loadError")),
          );
          return;
        }
        setQuote(response.data);
      } catch (error) {
        if (!active) return;
        // apiMutator throws on non-OK — the link's real state (revoked 410,
        // expired 410, gone 404) must surface, not a generic load error.
        setError(
          error instanceof ApiError
            ? error.status === 404
              ? t("portal.notFound")
              : (errorDetail(error.payload) ?? t("portal.loadError"))
            : t("portal.loadError"),
        );
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  // The only page a customer ever sees carries the issuer's name in the tab.
  useEffect(() => {
    const issuer = quote?.organization?.commercial_name || quote?.organization?.name || "";
    document.title = issuer
      ? `${issuer} · ${t("portal.proposalTitle")} · ${quote?.project_code ?? ""}`
      : t("portal.proposalTitle");
  }, [quote]);

  async function decide(decision: "APPROVED" | "DECLINED"): Promise<void> {
    if (!name.trim() || busy) return;
    if (decision === "DECLINED" && !note.trim()) return;
    setBusy(true);
    try {
      const response = await portalQuoteDecide(token, {
        decision,
        decided_by: name.trim(),
        decided_rut: rut.trim() || undefined,
        note: note.trim() || undefined,
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      setQuote(response.data);
      setDecideError(null);
    } catch (error) {
      // A failed decision must not erase the proposal — show the reason over
      // the still-visible quote; a stale link re-fetches into the banner.
      if (error instanceof ApiError && error.status === 409) {
        void portalQuoteRetrieve(token).then((fresh) => {
          if (fresh.status === 200) setQuote(fresh.data);
        });
      }
      setDecideError(
        error instanceof ApiError
          ? (errorDetail(error.payload) ?? t("portal.decideError"))
          : t("portal.decideError"),
      );
    } finally {
      setBusy(false);
    }
  }

  if (error !== null) {
    return (
      <main className="portal-page">
        <section className="portal-card portal-card--narrow">
          <h1>{t("portal.proposalTitle")}</h1>
          <p role="alert">{error}</p>
        </section>
      </main>
    );
  }

  if (quote === null) {
    return (
      <main className="portal-page">
        <p role="status">{t("portal.loading")}</p>
      </main>
    );
  }

  const decided = quote.approval_status !== "PENDING";
  // Line-level IVA: net + tax are the sealed truth — the implied rate lets
  // product cards show the gross the customer will actually pay.
  const taxRate =
    quote.total_price_net && quote.total_price_tax
      ? Number(quote.total_price_tax) / Number(quote.total_price_net)
      : null;
  const org = quote.organization;
  const issuer = org?.commercial_name || org?.name || "DEKOPEN";
  const issuerContact =
    [org?.brand_address, org?.brand_phone, org?.brand_email]
      .filter((part) => part != null && part !== "")
      .join(" · ") || "";
  const groups = groupPositions(quote.positions);
  // The hero is the customer's own largest glazed unit — rendered, not stock.
  const hero = groups.reduce<ReturnType<typeof groupPositions>[number] | null>((best, group) => {
    const area = Number(group.position.width_mm) * Number(group.position.height_mm);
    const bestArea = best ? Number(best.position.width_mm) * Number(best.position.height_mm) : -1;
    return area > bestArea ? group : best;
  }, null);

  return (
    <main className="portal-page">
      <article className="portal-proposal">
        <header className="portal-proposal__head">
          <div className="portal-proposal__issuer">
            {org?.brand_logo_url ? (
              <img className="portal-proposal__logo" src={org.brand_logo_url} alt={issuer} />
            ) : (
              <p className="portal-proposal__org">{issuer}</p>
            )}
            {org?.tax_id ? <p className="portal-proposal__taxid">{org.tax_id}</p> : null}
            {issuerContact ? <p className="portal-proposal__taxid">{issuerContact}</p> : null}
          </div>
          <div className="portal-proposal__refs">
            <h1>{t("portal.proposalTitle")}</h1>
            <p className="portal-proposal__ref">
              {quote.project_name ? `${quote.project_name} · ` : ""}
              {quote.project_code} · {formatRevision(quote.revision_code)} ·{" "}
              <time dateTime={quote.emitted_at}>{formatDate(quote.emitted_at)}</time>
            </p>
            {quote.valid_until ? (
              <p className="portal-proposal__ref">
                {t("portal.validUntil")}{" "}
                <time dateTime={quote.valid_until}>{formatDate(quote.valid_until)}</time>
              </p>
            ) : null}
          </div>
        </header>

        {hero !== null ? (
          <figure className="portal-proposal__hero">
            <PositionThumb
              design={positionDesign(hero.position)}
              variant="studio"
              members={positionMembers(hero.position)}
            />
            <figcaption>
              {typologyLabel(hero.position.typology)} · {Math.round(Number(hero.position.width_mm))}{" "}
              × {Math.round(Number(hero.position.height_mm))} mm
            </figcaption>
          </figure>
        ) : null}

        <section className="portal-proposal__summary">
          <dl className="portal-facts">
            <div>
              <dt>{t("portal.client")}</dt>
              <dd>{quote.client_name}</dd>
            </div>
            <div>
              <dt>{t("portal.validUntil")}</dt>
              <dd>
                <time dateTime={quote.valid_until ?? ""}>
                  {quote.valid_until ? formatDate(quote.valid_until) : "—"}
                </time>
              </dd>
            </div>
          </dl>
          <dl className="portal-totals">
            {(quote.extras ?? []).map((item, index) => (
              <div key={`${String(item.label)}-${index}`}>
                <dt>{String(item.label ?? "")}</dt>
                <dd>{money(String(item.amount ?? "0"), quote.currency)}</dd>
              </div>
            ))}
            <div>
              <dt>{t("portal.net")}</dt>
              <dd>{money(quote.total_price_net, quote.currency)}</dd>
            </div>
            <div>
              <dt>{t("portal.tax")}</dt>
              <dd>{money(quote.total_price_tax, quote.currency)}</dd>
            </div>
            <div className="portal-totals__gross">
              <dt>{t("portal.gross")}</dt>
              <dd>{money(quote.total_price_gross, quote.currency)}</dd>
            </div>
          </dl>
        </section>

        {quote.positions.length > 0 ? (
          <section className="portal-proposal__positions">
            <h2>{t("portal.positions")}</h2>
            <div className="portal-positions">
              {groups.map((group) => (
                <PositionGroupCard
                  key={group.key}
                  group={group}
                  currency={quote.currency}
                  taxRate={taxRate}
                />
              ))}
            </div>
          </section>
        ) : null}

        {quote.notes_commercial ? (
          <section className="portal-proposal__notes">
            <h2>{t("portal.notes")}</h2>
            <p>{quote.notes_commercial}</p>
          </section>
        ) : null}

        {(quote.payment_terms || quote.payment) && (
          <section className="portal-proposal__commercial">
            {quote.payment_terms ? (
              <div className="portal-terms">
                <h3>{t("portal.terms")}</h3>
                <p>{quote.payment_terms}</p>
              </div>
            ) : null}
            {quote.payment ? (
              <dl className="portal-payment">
                <div>
                  <dt>{t("portal.paymentLabel")}</dt>
                  <dd>
                    <span
                      className={`portal-payment__state portal-payment__state--${quote.payment.status.toLowerCase()}`}
                    >
                      {t(
                        quote.payment.status === "PAID"
                          ? "portal.payment.PAID"
                          : quote.payment.status === "PARTIAL"
                            ? "portal.payment.PARTIAL"
                            : "portal.payment.PENDING",
                      )}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt>{t("portal.collected")}</dt>
                  <dd>{money(quote.payment.collected, quote.currency)}</dd>
                </div>
                <div>
                  <dt>{t("portal.balance")}</dt>
                  <dd>{money(quote.payment.balance, quote.currency)}</dd>
                </div>
              </dl>
            ) : null}
            {quote.payment_url && !quote.superseded && !quote.validity_expired ? (
              <a
                className="portal-pay"
                href={quote.payment_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                {quote.payment
                  ? `${t("portal.payBalance")} ${money(quote.payment.balance, quote.currency)}`
                  : t("portal.payNow")}
              </a>
            ) : null}
          </section>
        )}

        {quote.quote_pdf_url ? (
          <a
            className="portal-doc"
            href={quote.quote_pdf_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("portal.openPdf")}
          </a>
        ) : null}

        <ol className="portal-steps" aria-label={t("portal.stepsLabel")}>
          <li className="portal-step" data-state="done">
            {t("portal.stepProposal")}
          </li>
          <li
            className="portal-step"
            data-state={
              quote.approval_status === "APPROVED"
                ? "done"
                : quote.approval_status === "DECLINED"
                  ? "declined"
                  : "current"
            }
          >
            {t("portal.stepDecision")}
          </li>
          <li
            className="portal-step"
            data-state={quote.approval_status === "APPROVED" ? "current" : "pending"}
          >
            {t("portal.stepProduction")}
          </li>
        </ol>

        {decided ? (
          <div
            className="portal-decided"
            data-state={quote.approval_status === "APPROVED" ? "approved" : "declined"}
            role="status"
          >
            <p className="portal-decided__state">
              {quote.approval_status === "APPROVED"
                ? t("portal.wasApproved")
                : t("portal.wasDeclined")}
            </p>
            <p>
              {quote.approval_status === "APPROVED"
                ? t("portal.wasApprovedDetail")
                : t("portal.wasDeclinedDetail")}
            </p>
            {issuerContact ? <p className="portal-decided__contact">{issuerContact}</p> : null}
          </div>
        ) : quote.superseded ? (
          <p className="portal-decided" role="status">
            {t("portal.superseded")}
          </p>
        ) : quote.validity_expired ? (
          <p className="portal-decided" role="status">
            {t("portal.validityExpired")}
          </p>
        ) : (
          <form
            className="portal-decision"
            onSubmit={(event: FormEvent<HTMLFormElement>) => {
              event.preventDefault();
              void decide("APPROVED");
            }}
          >
            <h2>{t("portal.decisionTitle")}</h2>
            <div className="portal-decision__recap">
              <dl>
                <div>
                  <dt>{t("portal.decisionTotal")}</dt>
                  <dd>{money(quote.total_price_gross, quote.currency)}</dd>
                </div>
                <div>
                  <dt>{t("portal.project")}</dt>
                  <dd>
                    {quote.project_code} · {formatRevision(quote.revision_code)}
                  </dd>
                </div>
                {quote.valid_until ? (
                  <div>
                    <dt>{t("portal.validUntil")}</dt>
                    <dd>
                      <time dateTime={quote.valid_until}>{formatDate(quote.valid_until)}</time>
                    </dd>
                  </div>
                ) : null}
              </dl>
              <p className="portal-decision__hint">{t("portal.approveHint")}</p>
            </div>
            <label htmlFor="portal-name">{t("portal.nameLabel")}</label>
            <input
              id="portal-name"
              required
              maxLength={255}
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={busy}
              autoComplete="name"
            />
            <label htmlFor="portal-rut">{t("portal.rutLabel")}</label>
            <input
              id="portal-rut"
              maxLength={32}
              value={rut}
              onChange={(event) => setRut(event.target.value)}
              disabled={busy}
              placeholder={t("portal.rutPlaceholder")}
            />
            <label htmlFor="portal-note">{t("portal.noteLabel")}</label>
            <textarea
              id="portal-note"
              maxLength={500}
              rows={3}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              disabled={busy}
              placeholder={t("portal.notePlaceholder")}
            />
            {decideError !== null ? (
              <p role="alert" className="portal-decision__error">
                {decideError}
              </p>
            ) : null}
            <div className="projects-actions">
              <button className="primary-action" disabled={busy || !name.trim()}>
                {t("portal.approve")}
              </button>
              <button
                type="button"
                disabled={busy || !name.trim() || !note.trim()}
                onClick={() => void decide("DECLINED")}
              >
                {t("portal.requestChange")}
              </button>
            </div>
            {!note.trim() ? (
              <p className="portal-decision__notehint">{t("portal.noteRequired")}</p>
            ) : null}
          </form>
        )}

        <footer className="portal-proposal__brand">{t("portal.brand")}</footer>
      </article>
    </main>
  );
}
