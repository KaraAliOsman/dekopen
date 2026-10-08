import {
  CSSProperties,
  FormEvent,
  PointerEvent as ReactPointerEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/apiMutator";
import {
  portalQuoteDecide,
  portalQuoteFollow,
  portalQuotePay,
  portalQuoteRetrieve,
} from "../../api/generated/dekopen";
import type { PortalPosition, PortalQuote } from "../../api/generated/models";
import type { PositionDesign } from "../../api/generated/models";
import { t, tOptional, typologyLabel } from "../../i18n/es-CL";
import { formatRevision, isValidRut } from "../../format";
import { PositionThumb, THUMB_MEMBERS } from "../projects/PositionThumb";
import {
  addDecimal,
  compareDecimal,
  divideByInt,
  divideDecimal,
  formatDecimal,
  multiplyDecimal,
  parseDecimal,
  roundDecimalToInt,
  type DecimalValue,
} from "../projects/decimal";
import { finishFace, type MemberFinish } from "../canvas/finishes";
import { reSkinMembers, tintMembers, type MemberGeometry } from "../canvas/members";
import "./portal.css";
import { formatDate, formatDateTime, formatMoney, formatPercent } from "../../format";

const money = formatMoney;

/** Sealed finish text → the closest renderable member surface — a Nogal foil
 * quote must not draw a white PVC window beside "Terminación: Nogal". */
const FINISH_SURFACES: [RegExp, string][] = [
  [/madera|nogal|roble|caoba|wengue|cedro|sapeli|rovere|nuss|wood|foil|foliad/i, "PVC_FOIL"],
  [/antracit|grafito|negro|dark|black|bronce|bronze/i, "ALUMINIUM_ANTHRACITE"],
  [/aluminio|aluminum|anodiz|natural/i, "ALUMINIUM"],
];

function positionMembers(position: PortalPosition): MemberGeometry {
  // The sealed per-face finish detail is the authoritative swatch — a bicolor
  // quote draws its real interior/exterior pair, not a text-guessed skin.
  const finish: MemberFinish = {
    exterior: finishFace(position.color_exterior_detail),
    interior: finishFace(position.color_interior_detail),
  };
  if (
    finish.exterior.color ||
    finish.interior.color ||
    finish.exterior.texture ||
    finish.interior.texture
  ) {
    return tintMembers(THUMB_MEMBERS, finish);
  }
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

// Misma curva sRGB que backend/documents/brand.py (_contrast_ratio):
// elige la tinta que contrasta ≥ 4.5:1 con el acento de marca, sea cual
// sea el tema — la validación AA del backend mide el acento sobre papel.
function brandOnFill(hex: string): string {
  const channel = (i: number) => parseInt(hex.slice(i, i + 2), 16) / 255;
  const linear = (c: number) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
  const lum =
    0.2126 * linear(channel(1)) + 0.7152 * linear(channel(3)) + 0.0722 * linear(channel(5));
  return lum > 0.32 ? "var(--g-950)" : "var(--paper)";
}

/** discount_pct persists as a fraction (0.10 = 10 %) — never print it raw. */
function pctLabel(raw: string | null | undefined): string {
  const fraction = Number(raw);
  if (!Number.isFinite(fraction)) return `${raw}%`;
  return formatPercent(fraction, fraction <= 1 ? "fraction" : "points");
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
  totalNet: DecimalValue | null;
}[] {
  const groups = new Map<
    string,
    {
      key: string;
      position: PortalPosition;
      locations: string[];
      indexes: string[];
      quantity: number;
      totalNet: DecimalValue | null;
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
    // Sealed money stays exact decimal end to end — group totals never
    // round-trip through binary float before reaching the es-CL formatter.
    const lineNet = position.price_net != null ? parseDecimal(position.price_net) : null;
    if (group) {
      if (location && !group.locations.includes(location)) group.locations.push(location);
      if (index) group.indexes.push(index);
      group.quantity += position.quantity ?? 1;
      group.totalNet =
        group.totalNet !== null && lineNet !== null
          ? addDecimal(group.totalNet, lineNet)
          : (group.totalNet ?? lineNet);
    } else {
      groups.set(key, {
        key,
        position,
        locations: location ? [location] : [],
        indexes: index ? [index] : [],
        quantity: position.quantity ?? 1,
        totalNet: lineNet,
      });
    }
  }
  return [...groups.values()];
}

/** Zoom overlay — lightbox grande con paneo por arrastre, pinch táctil y
 * zoom por rueda/botones. El render sellado se inspecciona a detalle:
 * manillas, divisiones y aperturas se comprueban con los dedos. */
function ZoomOverlay({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}): JSX.Element {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const pinch = useRef<{ distance: number; scale: number } | null>(null);
  const stage = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  const down = (event: ReactPointerEvent<HTMLDivElement>) => {
    (event.target as HTMLElement).setPointerCapture?.(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      if (a && b) {
        pinch.current = {
          distance: Math.hypot(a.x - b.x, a.y - b.y),
          scale,
        };
      }
    }
  };
  const move = (event: ReactPointerEvent<HTMLDivElement>) => {
    const point = pointers.current.get(event.pointerId);
    if (!point) return;
    const dx = event.clientX - point.x;
    const dy = event.clientY - point.y;
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (pointers.current.size === 2 && pinch.current) {
      const [a, b] = [...pointers.current.values()];
      if (a && b) {
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch.current.distance > 0) {
          setScale(
            Math.min(6, Math.max(0.5, pinch.current.scale * (distance / pinch.current.distance))),
          );
        }
      }
      return;
    }
    setOffset((prev) => ({ x: prev.x + dx, y: prev.y + dy }));
  };
  const up = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointers.current.delete(event.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
  };
  const zoom = (factor: number) => setScale((prev) => Math.min(6, Math.max(0.5, prev * factor)));

  return (
    <div className="portal-zoom" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="portal-zoom__backdrop" onClick={onClose} tabIndex={-1} />
      <div className="portal-zoom__bar">
        <span className="portal-zoom__title">{title}</span>
        <div className="portal-zoom__tools" role="group" aria-label={t("portal.zoomTools")}>
          <button type="button" onClick={() => zoom(0.8)} aria-label={t("portal.zoomOut")}>
            −
          </button>
          <button
            type="button"
            onClick={() => {
              setScale(1);
              setOffset({ x: 0, y: 0 });
            }}
          >
            {t("portal.zoomReset")}
          </button>
          <button type="button" onClick={() => zoom(1.25)} aria-label={t("portal.zoomIn")}>
            +
          </button>
          <button type="button" className="portal-zoom__close" onClick={onClose}>
            {t("portal.zoomClose")}
          </button>
        </div>
      </div>
      <div
        ref={stage}
        className="portal-zoom__stage"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
        onWheel={(event) => zoom(event.deltaY < 0 ? 1.15 : 0.87)}
      >
        <div
          className="portal-zoom__content"
          style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})` }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

function PositionGroupCard({
  group,
  currency,
  taxRate,
  grossOverride,
  option,
  onZoom,
}: {
  group: ReturnType<typeof groupPositions>[number];
  currency: string;
  // IVA-included line totals reconcile with the headline Total — a customer
  // thinks in gross, so the card leads with it when the rate is derivable.
  taxRate: DecimalValue | null;
  // Rounded-to-the-sealed-total display value; when the page reconciles the
  // line it passes the adjusted integer string so Σ líneas = total header.
  grossOverride?: string;
  option?: boolean;
  onZoom: (payload: { title: string; body: React.ReactNode }) => void;
}): JSX.Element {
  const { position } = group;
  const [variant, setVariant] = useState<"studio" | "elevation">("studio");
  const specs = position.glass_specs ?? [];
  const finished = position.finish ?? null;
  const members = positionMembers(position);
  const hasPrice = position.price_net != null && group.totalNet !== null;
  const totalNet = group.totalNet;
  const grossLine =
    totalNet !== null && taxRate !== null
      ? multiplyDecimal(totalNet, addDecimal({ numerator: 1n, denominator: 1n }, taxRate))
      : null;
  const grossDisplay = grossOverride ?? (grossLine !== null ? roundDecimalToInt(grossLine) : null);
  const locations =
    group.locations.length > 0
      ? compactList(group.locations)
      : `Pos. ${compactList(group.indexes)}`;
  const title = `${typologyLabel(position.typology)} ${Math.round(Number(position.width_mm))} × ${Math.round(Number(position.height_mm))} mm`;
  const figure = (
    <PositionThumb design={positionDesign(position)} variant={variant} members={members} />
  );
  return (
    <article className="portal-position" data-option={option ? "true" : undefined}>
      <div className="portal-position__thumb">
        {figure}
        <button
          type="button"
          className="portal-position__zoom"
          onClick={() =>
            onZoom({
              title,
              body: figure,
            })
          }
          aria-label={t("portal.zoomFigure")}
        >
          <span className="portal-position__zoomhint">{t("portal.zoomFigure")}</span>
        </button>
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
        <p className="portal-position__viewname">
          {variant === "studio" ? t("portal.viewStudioName") : t("portal.viewTechnicalName")}
        </p>
      </div>
      <div className="portal-position__body">
        <p className="portal-position__id">
          {option ? <span className="portal-option-tag">{t("portal.optionTag")}</span> : null}
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
          {hasPrice && group.quantity > 1 && totalNet !== null && (
            <span className="portal-position__unit">
              {t("portal.unitNet")}{" "}
              {money(formatDecimal(divideByInt(totalNet, group.quantity)), currency)}
            </span>
          )}
          <span>
            {t("portal.lineNet")}{" "}
            {hasPrice && totalNet !== null ? money(formatDecimal(totalNet), currency) : "—"}
          </span>
          <strong>
            {hasPrice
              ? grossDisplay !== null
                ? money(grossDisplay, currency)
                : totalNet !== null
                  ? money(formatDecimal(totalNet), currency)
                  : "—"
              : "—"}
            {taxRate !== null && hasPrice ? (
              <span className="portal-position__taxincl"> {t("portal.taxIncluded")}</span>
            ) : null}
          </strong>
        </p>
        {option ? <p className="portal-option-note">{t("portal.optionExcluded")}</p> : null}
      </div>
    </article>
  );
}

/** Cada estado terminal tiene su página dedicada — qué pasó, con quién
 * hablar y qué hacer después, nunca un 410 pelado. */
function StatePage({
  quote,
  issuer,
  contact,
  accentStyle,
  kind,
}: {
  quote: PortalQuote;
  issuer: string;
  contact: string;
  accentStyle: CSSProperties | undefined;
  kind: "revoked" | "link_expired" | "validity_expired" | "superseded";
}): JSX.Element {
  const navigate = useNavigate();
  const { token = "" } = useParams();
  const [busy, setBusy] = useState(false);
  const [followError, setFollowError] = useState<string | null>(null);
  const titles: Record<typeof kind, string> = {
    revoked: t("portal.stateRevoked"),
    link_expired: t("portal.stateLinkExpired"),
    validity_expired: t("portal.stateValidityExpired"),
    superseded: t("portal.stateSuperseded"),
  };
  const bodies: Record<typeof kind, string> = {
    revoked: t("portal.stateRevokedBody"),
    link_expired: t("portal.stateLinkExpiredBody"),
    validity_expired: t("portal.stateValidityExpiredBody"),
    superseded: t("portal.stateSupersededBody"),
  };

  async function follow(): Promise<void> {
    setBusy(true);
    try {
      const response = await portalQuoteFollow(token);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      const next = response.data.follow_token;
      if (next) {
        // El token cambia en la ruta — el efecto [token] re-lee y el portal
        // muestra la revisión vigente sin recarga de página.
        navigate(`/cotizacion/${next}`, { replace: true });
      } else {
        setFollowError(t("portal.followError"));
      }
    } catch (error) {
      setFollowError(
        error instanceof ApiError
          ? (errorDetail(error.payload) ?? t("portal.followError"))
          : t("portal.followError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="portal-page" style={accentStyle}>
      <article className="portal-proposal">
        <header className="portal-proposal__head">
          <div className="portal-proposal__issuer">
            {quote.organization?.brand_logo_url ? (
              <img
                className="portal-proposal__logo"
                src={quote.organization.brand_logo_url}
                alt={issuer}
              />
            ) : null}
            <p className="portal-proposal__org">{issuer}</p>
            {contact ? <p className="portal-proposal__taxid">{contact}</p> : null}
          </div>
          <div className="portal-proposal__refs">
            <h1>{t("portal.proposalTitle")}</h1>
            <p className="portal-proposal__ref">
              {quote.project_code} · {formatRevision(quote.revision_code)}
              {kind === "superseded" ? ` → ${formatRevision(quote.current_revision)}` : ""}
            </p>
          </div>
        </header>
        <section className="portal-state">
          <h2 className="portal-state__title">{titles[kind]}</h2>
          <p className="portal-state__body">{bodies[kind]}</p>
          {contact ? (
            <p className="portal-state__contact">
              {t("portal.stateContact")} {contact}
            </p>
          ) : null}
          {kind === "superseded" && quote.follow_available ? (
            <button
              type="button"
              className="primary-action portal-state__follow"
              disabled={busy}
              onClick={() => void follow()}
            >
              {t("portal.followCurrent")}
            </button>
          ) : null}
          {followError ? (
            <p role="alert" className="portal-decision__error">
              {followError}
            </p>
          ) : null}
        </section>
        {quote.organization?.dekopen_credit !== false ? (
          <footer className="portal-proposal__brand">{t("portal.brand")}</footer>
        ) : null}
      </article>
    </main>
  );
}

export function PortalQuotePage(): JSX.Element {
  const { token = "" } = useParams();
  const [quote, setQuote] = useState<PortalQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [rut, setRut] = useState("");
  const [note, setNote] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [marked, setMarked] = useState<Set<string>>(new Set());
  const [payerEmail, setPayerEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [paying, setPaying] = useState(false);
  const [decideError, setDecideError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<{ title: string; body: React.ReactNode } | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await portalQuoteRetrieve(token);
        if (!active) return;
        if (response.status !== 200) {
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

  // La página que el cliente ve se identifica con el fabricante: pestaña y
  // favicon llevan su nombre y su marca, no los de DEKOPEN.
  useEffect(() => {
    const org = quote?.organization;
    const issuer = org?.commercial_name || org?.name || "";
    document.title = issuer
      ? `${issuer} · ${t("portal.proposalTitle")} · ${quote?.project_code ?? ""}`
      : t("portal.proposalTitle");
    const logo = org?.brand_logo_url;
    if (!logo) return;
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    const previous = link.href;
    link.href = logo;
    return () => {
      link.href = previous;
    };
  }, [quote]);

  async function decide(decision: "APPROVED" | "DECLINED" | "CHANGES_REQUESTED"): Promise<void> {
    if (!name.trim() || busy) return;
    if (decision === "APPROVED" && (!isValidRut(rut) || !rut.trim() || !accepted)) return;
    if (decision === "CHANGES_REQUESTED" && !note.trim()) return;
    setBusy(true);
    try {
      const response = await portalQuoteDecide(token, {
        decision,
        decided_by: name.trim(),
        decided_rut: rut.trim() || undefined,
        note: note.trim() || undefined,
        accepted: decision === "APPROVED" ? accepted : undefined,
        marked_position_ids: [...marked],
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

  async function pay(): Promise<void> {
    if (paying) return;
    setPaying(true);
    try {
      const response = await portalQuotePay(token, {
        payer_email: payerEmail.trim() || undefined,
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      const url = response.data.payment_url;
      if (!url) throw new Error("no_payment_url");
      window.location.assign(url);
    } catch (error) {
      setDecideError(
        error instanceof ApiError
          ? (errorDetail(error.payload) ?? t("portal.payError"))
          : t("portal.payError"),
      );
      setPaying(false);
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

  const org = quote.organization;
  const issuer = org?.commercial_name || org?.name || "DEKOPEN";
  const issuerContact =
    [org?.brand_address, org?.brand_phone, org?.brand_email]
      .filter((part) => part != null && part !== "")
      .join(" · ") || "";
  const accentStyle = org?.brand_color
    ? ({
        "--theme-accent": org.brand_color,
        "--theme-accent-strong": org.brand_color,
        "--theme-accent-soft": `${org.brand_color}20`,
        "--theme-accent-onfill": brandOnFill(org.brand_color),
      } as CSSProperties)
    : undefined;

  // Estados dedicados — cada uno explica qué pasó con este enlace.
  if (quote.state === "revoked") {
    return (
      <StatePage
        quote={quote}
        issuer={issuer}
        contact={issuerContact}
        accentStyle={accentStyle}
        kind="revoked"
      />
    );
  }
  if (quote.state === "link_expired") {
    return (
      <StatePage
        quote={quote}
        issuer={issuer}
        contact={issuerContact}
        accentStyle={accentStyle}
        kind="link_expired"
      />
    );
  }
  if (quote.state === "validity_expired") {
    return (
      <StatePage
        quote={quote}
        issuer={issuer}
        contact={issuerContact}
        accentStyle={accentStyle}
        kind="validity_expired"
      />
    );
  }
  if (quote.state === "superseded") {
    return (
      <StatePage
        quote={quote}
        issuer={issuer}
        contact={issuerContact}
        accentStyle={accentStyle}
        kind="superseded"
      />
    );
  }

  const state = quote.state ?? "live";
  const canDecide = state === "live" || state === "changes_requested";
  // Line-level IVA: net + tax are the sealed truth — the implied rate lets
  // product cards show the gross the customer will actually pay.
  const netTotal = quote.total_price_net ? parseDecimal(quote.total_price_net) : null;
  const taxTotal = quote.total_price_tax ? parseDecimal(quote.total_price_tax) : null;
  const taxRate =
    netTotal !== null && taxTotal !== null && netTotal.numerator !== 0n
      ? divideDecimal(taxTotal, netTotal)
      : null;
  const included = (quote.positions ?? []).filter((position) => !position.is_option);
  const options = (quote.positions ?? []).filter((position) => position.is_option);
  const groups = groupPositions(included);
  const optionGroups = groupPositions(options);
  // Σ líneas = total del encabezado: cada bruto de línea se redondea en su
  // tarjeta y el total se redondea una sola vez al sellar — la deriva típica
  // (±$1) se absorbe en la línea mayor, como el ajuste de redondeo del SII.
  // Solo se ajusta deriva pura (≤ $1 por línea); una inconsistencia real
  // entre líneas y total nunca se maquilla.
  const grossByKey = (() => {
    const map = new Map<string, string>();
    if (taxRate === null || !quote.total_price_gross) return map;
    const sealedGross = parseDecimal(quote.total_price_gross);
    if (sealedGross === null) return map;
    const sealedInt = BigInt(roundDecimalToInt(sealedGross));
    const one: DecimalValue = { numerator: 1n, denominator: 1n };
    let allPriced = groups.length > 0;
    let sum = 0n;
    let largest: { key: string; exact: DecimalValue; display: bigint } | null = null;
    for (const group of groups) {
      if (group.position.price_net == null || group.totalNet === null) {
        allPriced = false;
        continue;
      }
      const exact = multiplyDecimal(group.totalNet, addDecimal(one, taxRate));
      const display = BigInt(roundDecimalToInt(exact));
      map.set(group.key, String(display));
      sum += display;
      if (largest === null || compareDecimal(exact, largest.exact) > 0) {
        largest = { key: group.key, exact, display };
      }
    }
    if (!allPriced || largest === null) return map;
    const diff = sealedInt - sum;
    const drift = diff < 0n ? -diff : diff;
    if (drift <= BigInt(groups.length)) {
      map.set(largest.key, String(largest.display + diff));
    }
    return map;
  })();
  // La vigencia se lee en días — "quedan N días" es lo que la persona entiende.
  const daysLeft = (() => {
    if (!quote.valid_until) return null;
    const until = Date.parse(`${quote.valid_until}T23:59:59`);
    if (Number.isNaN(until)) return null;
    return Math.max(0, Math.ceil((until - Date.now()) / 86400000));
  })();
  // The hero is the customer's own largest glazed unit — rendered, not stock.
  const hero = groups.reduce<ReturnType<typeof groupPositions>[number] | null>((best, group) => {
    const area = Number(group.position.width_mm) * Number(group.position.height_mm);
    const bestArea = best ? Number(best.position.width_mm) * Number(best.position.height_mm) : -1;
    return area > bestArea ? group : best;
  }, null);
  const event = quote.decision_event;

  return (
    <main className="portal-page" style={accentStyle}>
      <article className="portal-proposal">
        <header className="portal-proposal__head">
          <div className="portal-proposal__issuer">
            {org?.brand_logo_url ? (
              <img className="portal-proposal__logo" src={org.brand_logo_url} alt={issuer} />
            ) : null}
            <p className="portal-proposal__org">{issuer}</p>
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
                {daysLeft !== null ? (
                  <span className="portal-daysleft">
                    {" "}
                    ·{" "}
                    {daysLeft === 1
                      ? t("portal.daysLeftOne")
                      : t("portal.daysLeft").replace("{count}", String(daysLeft))}
                  </span>
                ) : null}
              </p>
            ) : null}
          </div>
        </header>

        {hero !== null ? (
          <figure className="portal-proposal__hero">
            <div className="portal-proposal__hero-render">
              <PositionThumb
                design={positionDesign(hero.position)}
                variant="studio"
                members={positionMembers(hero.position)}
              />
              <button
                type="button"
                className="portal-position__zoom"
                onClick={() =>
                  setZoom({
                    title: `${typologyLabel(hero.position.typology)} ${Math.round(Number(hero.position.width_mm))} × ${Math.round(Number(hero.position.height_mm))} mm`,
                    body: (
                      <PositionThumb
                        design={positionDesign(hero.position)}
                        variant="studio"
                        members={positionMembers(hero.position)}
                      />
                    ),
                  })
                }
                aria-label={t("portal.zoomFigure")}
              >
                <span className="portal-position__zoomhint">{t("portal.zoomFigure")}</span>
              </button>
            </div>
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

        {groups.length > 0 ? (
          <section className="portal-proposal__positions">
            <h2>{t("portal.positions")}</h2>
            <div className="portal-positions">
              {groups.map((group) => (
                <PositionGroupCard
                  key={group.key}
                  group={group}
                  currency={quote.currency}
                  taxRate={taxRate}
                  grossOverride={grossByKey.get(group.key)}
                  onZoom={setZoom}
                />
              ))}
            </div>
          </section>
        ) : null}

        {optionGroups.length > 0 ? (
          <section className="portal-proposal__positions portal-options">
            <h2>{t("portal.optionsTitle")}</h2>
            <p className="portal-options__note">{t("portal.optionsNote")}</p>
            <div className="portal-positions">
              {optionGroups.map((group) => (
                <PositionGroupCard
                  key={group.key}
                  group={group}
                  currency={quote.currency}
                  taxRate={taxRate}
                  option
                  onZoom={setZoom}
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

        <section className="portal-proposal__commercial">
          {quote.payment_terms ? (
            <div className="portal-terms">
              <h3>{t("portal.terms")}</h3>
              <p>{quote.payment_terms}</p>
            </div>
          ) : null}
          {quote.doc_terms && Object.keys(quote.doc_terms).length > 0 ? (
            <div className="portal-terms">
              <h3>{t("portal.conditions")}</h3>
              <dl className="portal-condlist">
                {Object.entries(quote.doc_terms).map(([key, value]) => (
                  <div key={key}>
                    <dt>{tOptional(`portal.term.${key}`) ?? key}</dt>
                    <dd>{String(value)}</dd>
                  </div>
                ))}
              </dl>
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
          {quote.payment?.payable ? (
            <div className="portal-paybox">
              <label htmlFor="portal-payer" className="portal-paybox__label">
                {t("portal.payerEmail")}
              </label>
              <input
                id="portal-payer"
                type="email"
                maxLength={120}
                value={payerEmail}
                onChange={(event) => setPayerEmail(event.target.value)}
                placeholder={t("portal.payerEmailPlaceholder")}
              />
              <button
                type="button"
                className="portal-pay"
                disabled={paying}
                onClick={() => void pay()}
              >
                {paying
                  ? t("portal.payBusy")
                  : `${t("portal.payBalance")} ${money(quote.payment.balance, quote.currency)}`}
              </button>
              {quote.payment.simulated ? (
                <p className="portal-paybox__sim">{t("portal.paySimulated")}</p>
              ) : null}
            </div>
          ) : null}
        </section>

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
              state === "approved"
                ? "done"
                : state === "declined"
                  ? "declined"
                  : state === "changes_requested"
                    ? "changes"
                    : "current"
            }
          >
            {t("portal.stepDecision")}
          </li>
          <li className="portal-step" data-state={state === "approved" ? "current" : "pending"}>
            {t("portal.stepProduction")}
          </li>
        </ol>

        {state === "approved" ? (
          <div className="portal-decided" data-state="approved" role="status">
            <p className="portal-decided__state">{t("portal.wasApproved")}</p>
            <p>{t("portal.wasApprovedDetail")}</p>
            {event?.acceptance_text ? (
              <p className="portal-evidence">
                <span className="portal-evidence__label">{t("portal.evidence")}</span>“
                {event.acceptance_text}”
                {event.created_at ? ` · ${formatDateTime(event.created_at)}` : ""}
              </p>
            ) : null}
            {issuerContact ? <p className="portal-decided__contact">{issuerContact}</p> : null}
          </div>
        ) : state === "declined" ? (
          <div className="portal-decided" data-state="declined" role="status">
            <p className="portal-decided__state">{t("portal.wasDeclined")}</p>
            <p>{t("portal.wasDeclinedDetail")}</p>
            {issuerContact ? <p className="portal-decided__contact">{issuerContact}</p> : null}
          </div>
        ) : (
          <>
            {state === "changes_requested" && (
              <div className="portal-decided" data-state="changes" role="status">
                <p className="portal-decided__state">{t("portal.wasChangesRequested")}</p>
                <p>{t("portal.wasChangesRequestedDetail")}</p>
                {issuerContact ? <p className="portal-decided__contact">{issuerContact}</p> : null}
              </div>
            )}
            {canDecide ? (
              <form
                noValidate
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
                {options.length > 0 ? (
                  <fieldset className="portal-decision__options">
                    <legend>{t("portal.markOptions")}</legend>
                    {options.map((position) => (
                      <label key={position.id} className="portal-decision__option">
                        <input
                          type="checkbox"
                          checked={marked.has(position.id)}
                          onChange={(event_) => {
                            setMarked((prev) => {
                              const next = new Set(prev);
                              if (event_.target.checked) next.add(position.id);
                              else next.delete(position.id);
                              return next;
                            });
                          }}
                        />
                        <span>
                          {position.location_tag?.trim() || `Pos. ${position.position_index ?? ""}`}{" "}
                          · {typologyLabel(position.typology)}
                        </span>
                      </label>
                    ))}
                    <p className="portal-decision__notehint">{t("portal.markOptionsHint")}</p>
                  </fieldset>
                ) : null}
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
                <label htmlFor="portal-rut">{t("portal.rutLabelRequired")}</label>
                <input
                  id="portal-rut"
                  maxLength={32}
                  value={rut}
                  onChange={(event) => setRut(event.target.value)}
                  disabled={busy}
                  placeholder={t("portal.rutPlaceholder")}
                  inputMode="text"
                />
                {rut.trim() && !isValidRut(rut) ? (
                  <p className="portal-decision__notehint" role="alert">
                    {t("portal.rutInvalid")}
                  </p>
                ) : null}
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
                <label className="portal-decision__accept">
                  <input
                    type="checkbox"
                    checked={accepted}
                    onChange={(event) => setAccepted(event.target.checked)}
                    disabled={busy}
                  />
                  <span>{quote.acceptance_text ?? t("portal.acceptFallback")}</span>
                </label>
                {decideError !== null ? (
                  <p role="alert" className="portal-decision__error">
                    {decideError}
                  </p>
                ) : null}
                <div className="projects-actions">
                  <button
                    className="primary-action"
                    disabled={busy || !name.trim() || !rut.trim() || !isValidRut(rut) || !accepted}
                  >
                    {t("portal.approve")}
                  </button>
                  <button
                    type="button"
                    disabled={busy || !name.trim() || !note.trim()}
                    onClick={() => void decide("CHANGES_REQUESTED")}
                  >
                    {t("portal.requestChange")}
                  </button>
                  <button
                    type="button"
                    className="danger-action"
                    disabled={busy || !name.trim()}
                    onClick={() => void decide("DECLINED")}
                  >
                    {t("portal.decline")}
                  </button>
                </div>
                <p className="portal-decision__notehint">{t("portal.decisionHint")}</p>
              </form>
            ) : null}
          </>
        )}

        {org?.dekopen_credit !== false ? (
          <footer className="portal-proposal__brand">{t("portal.brand")}</footer>
        ) : null}
      </article>
      {zoom ? (
        <ZoomOverlay title={zoom.title} onClose={() => setZoom(null)}>
          {zoom.body}
        </ZoomOverlay>
      ) : null}
    </main>
  );
}
