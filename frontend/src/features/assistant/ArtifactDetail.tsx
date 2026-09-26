import { t } from "../../i18n/es-CL";

/** The artifact kinds the agent produces — payloads come from the workflow
 * contracts in backend/ai_gateway/agent.py, which the backend validates
 * (grounded numbers, references) before storing. Shapes are loose here on
 * purpose: the renderer tolerates partial payloads instead of crashing on an
 * artifact whose contract evolved. */
export interface Artifact {
  kind?: string;
  tool?: string;
  title?: string;
  payload?: unknown;
  references?: string[];
}

type Dict = { [key: string]: unknown };

function asDict(value: unknown): Dict {
  return value && typeof value === "object" ? (value as Dict) : {};
}

function asList(value: unknown): Dict[] {
  return Array.isArray(value) ? value.filter((i): i is Dict => i && typeof i === "object") : [];
}

function text(value: unknown, fallback = "—"): string {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function money(value: unknown): string | null {
  const n = Number(value);
  return Number.isFinite(n)
    ? n.toLocaleString("es-CL", { style: "currency", currency: "CLP", maximumFractionDigits: 0 })
    : value != null
      ? String(value)
      : null;
}

function StatePill({ state }: { state: string }): JSX.Element {
  const tone =
    state === "ready" ? "ok" : state === "missing" || state === "blocked" ? "bad" : "warn";
  return (
    <span className="art-pill" data-tone={tone}>
      {text(state)}
    </span>
  );
}

function MessageView({ payload }: { payload: Dict }): JSX.Element {
  return (
    <div className="art-message">
      {payload.to ? (
        <p className="art-field">
          <span>{t("aiws.art.to")}</span>
          {text(payload.to)}
        </p>
      ) : null}
      {payload.subject ? (
        <p className="art-field">
          <span>{t("aiws.art.subject")}</span>
          {text(payload.subject)}
        </p>
      ) : null}
      <p className="art-body">{text(payload.body)}</p>
    </div>
  );
}

function QuoteDraftView({ payload }: { payload: Dict }): JSX.Element {
  const checklist = asList(payload.checklist);
  const totals = asDict(payload.totals);
  return (
    <div>
      {checklist.length ? (
        <ul className="art-checklist">
          {checklist.map((item, i) => (
            <li key={i}>
              <StatePill state={text(item.state)} />
              <strong>{text(item.item)}</strong>
              {item.detail ? <small>{text(item.detail)}</small> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {Object.keys(totals).length ? (
        <div className="art-totals">
          {(["net", "tax", "gross"] as const).map((key) =>
            totals[key] !== undefined ? (
              <span key={key}>
                {t(`aiws.art.${key}` as never)} <strong>{money(totals[key])}</strong>
              </span>
            ) : null,
          )}
        </div>
      ) : null}
    </div>
  );
}

function PurchasePlanView({ payload }: { payload: Dict }): JSX.Element {
  const groups = asList(payload.groups);
  return (
    <div>
      {groups.map((group, gi) => (
        <section key={gi} className="art-group">
          <h3>{text(group.order_type)}</h3>
          <ul className="art-lines">
            {asList(group.lines).map((line, li) => (
              <li key={li}>
                <strong>{text(line.sku ?? line.requirement_key)}</strong>
                <span>
                  {text(line.quantity)} {text(line.unit, "")}
                  {line.project_code ? ` · ${text(line.project_code)}` : ""}
                </span>
              </li>
            ))}
          </ul>
          {Array.isArray(group.suppliers) && group.suppliers.length ? (
            <p className="art-note">
              {t("aiws.art.suppliers")}: {group.suppliers.map((s) => text(s)).join(", ")}
            </p>
          ) : null}
        </section>
      ))}
    </div>
  );
}

function ProductionPlanView({ payload }: { payload: Dict }): JSX.Element {
  const schedule = asList(payload.schedule);
  const actions = asList(payload.material_actions);
  return (
    <div>
      {schedule.length ? (
        <ol className="art-lines art-lines--numbered">
          {schedule.map((item, i) => (
            <li key={i}>
              <strong>{text(item.order_code)}</strong>
              {item.reason ? <small>{text(item.reason)}</small> : null}
            </li>
          ))}
        </ol>
      ) : null}
      {actions.length ? (
        <>
          <h3 className="art-group-title">{t("aiws.art.materialActions")}</h3>
          <ul className="art-lines">
            {actions.map((item, i) => (
              <li key={i}>
                <strong>{text(item.order_code)}</strong>
                <span>{text(item.missing)}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}

function ProjectDraftView({ payload }: { payload: Dict }): JSX.Element {
  const positions = asList(payload.positions);
  const unresolved = Array.isArray(payload.unresolved) ? payload.unresolved : [];
  return (
    <div>
      {positions.length ? (
        <ul className="art-lines">
          {positions.map((pos, i) => (
            <li key={i}>
              <span className="art-line-head">
                <strong>{text(pos.label ?? pos.key)}</strong>
                <StatePill state={text(pos.state)} />
              </span>
              <small>
                {text(pos.width_mm)}×{text(pos.height_mm)}
                {pos.quantity ? ` ×${text(pos.quantity)}` : ""}
                {pos.opening_type ? ` · ${text(pos.opening_type)}` : ""}
                {pos.system_code ? ` · ${text(pos.system_code)}` : ""}
              </small>
              {pos.question ? <small className="art-note">{text(pos.question)}</small> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {unresolved.length ? (
        <p className="art-note">
          {t("aiws.art.unresolved")}: {unresolved.map((u) => text(u)).join(", ")}
        </p>
      ) : null}
    </div>
  );
}

function CatalogReviewView({ payload }: { payload: Dict }): JSX.Element {
  const queues = [
    { label: t("aiws.art.catalogAuto"), rows: asList(payload.auto), field: "why" },
    { label: t("aiws.art.catalogReview"), rows: asList(payload.review), field: "reason" },
    { label: t("aiws.art.catalogBlocked"), rows: asList(payload.blocked), field: "reason" },
  ];
  return (
    <div>
      {queues.map(({ label, rows, field }, gi) =>
        rows.length ? (
          <section key={gi} className="art-group">
            <h3>
              {label} <span className="art-count">{rows.length}</span>
            </h3>
            <ul className="art-lines">
              {rows.map((row, i) => (
                <li key={i}>
                  <strong>{text(row.sku ?? row.key)}</strong>
                  <small>{text(row[field] ?? row.needed)}</small>
                </li>
              ))}
            </ul>
          </section>
        ) : null,
      )}
    </div>
  );
}

const VIEWS: Record<string, (p: Dict) => JSX.Element> = {
  message: (p) => <MessageView payload={p} />,
  quote_draft: (p) => <QuoteDraftView payload={p} />,
  purchase_plan: (p) => <PurchasePlanView payload={p} />,
  production_plan: (p) => <ProductionPlanView payload={p} />,
  project_draft: (p) => <ProjectDraftView payload={p} />,
  catalog_review: (p) => <CatalogReviewView payload={p} />,
};

/** Artifacts are work products — they render as readable documents, not JSON
 * dumps. Kinds without a dedicated view still get a readable fallback. */
export function ArtifactDetail({ artifact }: { artifact: Artifact }): JSX.Element {
  const payload = asDict(artifact.payload);
  const view = artifact.kind ? VIEWS[artifact.kind] : undefined;
  return (
    <div className="art">
      {view ? (
        view(payload)
      ) : (
        <pre className="aiws-payload">{JSON.stringify(artifact.payload ?? {}, null, 2)}</pre>
      )}
    </div>
  );
}
