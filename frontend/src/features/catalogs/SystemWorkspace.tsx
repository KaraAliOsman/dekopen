import { useEffect, useState } from "react";
import { WorkCenterRequestKindEnum } from "../../api/generated/models";
import type {
  ArticleResponse,
  EvidenceRow,
  BeadResponse,
  KitResponse,
  PurchaseMappingRow,
  ReinforcementRow,
  SystemWorkspace,
  WorkCenter,
  WorkCenterRequestRequest,
} from "../../api/generated/models";
import { t } from "../../i18n/es-CL";
import { domainLabel } from "../../i18n/domainLabels";
import { Icon } from "../../ui/icons";
import { fmtMm, shortTechnicalId } from "../../format";
import { centerKindLabel, opKindLabel, stationCodeLabel } from "../production/labels";
import { SectionPreviewSvg } from "../canvas/SectionPreviewSvg";
import type { Resource, Row, catalogApi } from "./catalogModel";

type Label = Parameters<typeof t>[0];
const ct = (key: string) => t(`catalog.${key}` as Label);
const wst = (key: string) => t(`catalog.ws.${key}` as Label);

function provenanceLabel(value: string | null | undefined): string {
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

function productKindLabel(kind: string): string {
  const key = `catalog.productKind.${kind}` as Label;
  return ["catalog.productKind.STANDARD", "catalog.productKind.FRAMELESS"].includes(key)
    ? t(key)
    : kind;
}

function joiningMethodLabel(method: string | null | undefined): string {
  if (!method) return "—";
  const key = `catalog.joining.${method}` as Label;
  return ["catalog.joining.WELD", "catalog.joining.CRIMP", "catalog.joining.NONE"].includes(key)
    ? t(key)
    : method;
}

/** Readiness blocker codes → the workspace section where they resolve. */
const BLOCKER_SECTION: Record<string, string> = {
  technical_catalog: "ws.articles",
  inspection: "ws.system",
  manufacturing: "ws.process",
  fabrication: "ws.system",
  catalog_review: "ws.articles",
  purchase: "ws.purchase",
  process_profile: "ws.process",
  work_centers: "ws.process",
  station_map: "ws.process",
};

/** Entity references in blocker text carry raw UUIDs — a record id means
 * nothing read as prose. The system's own id renders as its name; any other
 * keeps a short code. */
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

function levelOk(level: { ok?: boolean; state?: string; blockers: unknown[] }): boolean {
  if (level.state) return level.state === "COMPLETE";
  return level.ok === true;
}

function ProvenanceBadge({
  row,
}: {
  row: {
    data_provenance?: string;
    review_pending?: boolean;
    technical_reviewed_at?: string | null;
  };
}) {
  // "Verificado" is reserved for an actual technical review — provenance
  // alone (manual entry, an import, a demo seed) is not verification.
  if (row.technical_reviewed_at)
    return <span className="ws-badge ws-badge--ok">{wst("verified")}</span>;
  if (row.data_provenance === "LEGACY_UNVERIFIED")
    return <span className="ws-badge ws-badge--warn">{ct("provenanceLegacy")}</span>;
  if (row.review_pending)
    return <span className="ws-badge ws-badge--warn">{ct("reviewPending")}</span>;
  return <span className="ws-badge">{provenanceLabel(row.data_provenance)}</span>;
}

function ArticleCard({
  article,
  purchased,
  beads,
  canEdit,
  onEdit,
}: {
  article: ArticleResponse;
  purchased: boolean;
  beads: number;
  canEdit: boolean;
  onEdit: () => void;
}) {
  const depth = article.section?.depth_mm;
  return (
    <article className="ws-article-card">
      <div className="ws-article-section" aria-hidden="true">
        <SectionPreviewSvg
          section={article.section}
          faceWidthMm={Number(article.face_width_mm) || 60}
          depthMm={depth ? Number(depth) : undefined}
          material={article.material}
        />
        <small>
          {article.section
            ? `${ct(`sectionSource.${article.section.source}`)}${depth ? ` · ${depth} mm` : ""}`
            : wst("sectionApprox")}
        </small>
      </div>
      <div className="ws-article-body">
        <header>
          <strong>{article.name}</strong>
          <code>{article.sku}</code>
        </header>
        <dl>
          <div>
            <dt>{wst("role")}</dt>
            <dd>{ct(`option.${article.role}`)}</dd>
          </div>
          <div>
            <dt>{wst("face")}</dt>
            <dd>{fmtMm(article.face_width_mm)} mm</dd>
          </div>
          <div>
            <dt>{wst("commercialLength")}</dt>
            <dd>
              {article.commercial_length_mm
                ? `${fmtMm(article.commercial_length_mm)} mm`
                : wst("unknown")}
            </dd>
          </div>
          <div>
            <dt>{wst("weight")}</dt>
            <dd>{article.weight_kg_m ? `${fmtMm(article.weight_kg_m)} kg/m` : wst("unknown")}</dd>
          </div>
          <div>
            <dt>{wst("purchaseState")}</dt>
            <dd>
              {purchased ? (
                <span className="ws-badge ws-badge--ok">{wst("mapped")}</span>
              ) : (
                <span className="ws-badge ws-badge--warn">{wst("unmapped")}</span>
              )}
            </dd>
          </div>
          <div>
            <dt>{wst("beads")}</dt>
            <dd>{beads === 0 ? wst("noBeads") : `${beads}`}</dd>
          </div>
        </dl>
        <footer>
          <ProvenanceBadge row={article} />
          {canEdit && (
            <button type="button" className="ui-button ui-button--small" onClick={onEdit}>
              {ct(article.read_only === false ? "edit" : "view")}
            </button>
          )}
          {!canEdit && (
            <button type="button" className="ui-button ui-button--small" onClick={onEdit}>
              {ct("view")}
            </button>
          )}
        </footer>
      </div>
    </article>
  );
}

function ReadinessLadder({
  system,
  onJump,
}: {
  system: Row<"systems">;
  onJump: (anchor: string) => void;
}) {
  const readiness = system.readiness;
  if (!readiness) return <p className="ws-empty">{ct("readinessUnknown")}</p>;
  const levels = readiness.levels ?? [];
  /** Blocker text arrives with the raw system UUID embedded — it means
   * this very record, so name it instead of showing a hex fragment. */
  const labelFor = (text: string) =>
    text.replace(UUID_RE, (id) =>
      id.toLowerCase() === String(system.id).toLowerCase() ? system.name : shortTechnicalId(id),
    );
  // Levels carry cumulative blocker lists — attribute each blocker to the
  // first level that reports it so nothing repeats down the ladder.
  const blockerRows: { level: string; blocker: (typeof levels)[number]["blockers"][number] }[] = [];
  const seen = new Set<string>();
  for (const level of levels) {
    for (const blocker of level.blockers) {
      const key = `${blocker.code}|${blocker.affected}`;
      if (!seen.has(key)) {
        seen.add(key);
        blockerRows.push({ level: level.level, blocker });
      }
    }
  }
  return (
    <>
      <ol className="ws-ladder">
        {levels.map((level) => {
          const ok = levelOk(level);
          return (
            <li key={level.level} className={`ws-ladder-level ${ok ? "is-ok" : "is-blocked"}`}>
              <header>
                <span className="ws-ladder-state" aria-hidden="true">
                  {ok ? "●" : "◐"}
                </span>
                <strong>{wst(`level.${level.level}`)}</strong>
                <em>
                  {level.state
                    ? t(`catalog.ws.state.${level.state}` as Label)
                    : ok
                      ? wst("complete")
                      : wst("incomplete")}
                </em>
              </header>
            </li>
          );
        })}
      </ol>
      {blockerRows.length > 0 && (
        <ul className="ws-blockers">
          {blockerRows.map(({ level, blocker }, index) => (
            <li key={`${level}-${blocker.code}-${index}`} className="ws-blocker">
              <div className="ws-blocker-head">
                <span className="ws-blocker-level">{wst(`level.${level}`)}</span>
                <button
                  type="button"
                  className="ws-blocker-target"
                  onClick={() => onJump(BLOCKER_SECTION[blocker.code] ?? "ws.system")}
                  title={wst("jumpToSection")}
                >
                  {ct(`readiness.${blocker.code}`)}
                  <span className="ws-blocker-affected"> — {labelFor(blocker.affected)}</span>
                </button>
              </div>
              <p className="ws-blocker-detail">
                <strong>{wst("missingAuthority")}:</strong> {labelFor(blocker.missing_authority)}
                <br />
                <strong>{wst("consequence")}:</strong> {labelFor(blocker.why)}
                <br />
                <strong>{wst("resolution")}:</strong> {labelFor(blocker.action)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

type WorkspaceProps = {
  api: ReturnType<typeof catalogApi>;
  systemId: string;
  canEdit: boolean;
  onEdit: (resource: Resource, id?: string) => void;
  onDeleted: (resource: Resource, id: string) => void;
  /** Jump to the tabbed record list for one resource (articles, kits, …). */
  onShowRecords: (resource: Resource) => void;
  reloadKey: number;
};

/** §06 system home — the profile system's whole technical authority in one
 * view: who/what it is, how far it can carry a product (readiness ladder with
 * per-blocker deep links), and every entity bound to it. Relationship map is
 * the §06-C section below. */
export function SystemWorkspaceView({
  api,
  systemId,
  canEdit,
  onEdit,
  onDeleted,
  onShowRecords,
  reloadKey,
}: WorkspaceProps): JSX.Element {
  const [workspace, setWorkspace] = useState<SystemWorkspace | null>(null);
  const [centers, setCenters] = useState<WorkCenter[] | null>(null);
  const [evidenceRows, setEvidenceRows] = useState<EvidenceRow[] | null>(null);
  const [error, setError] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);

  useEffect(() => {
    // Per-effect flag: a shared ref lets a superseded fetch's AbortError
    // set the error banner after the fresh one already loaded data.
    let alive = true;
    const controller = new AbortController();
    setWorkspace(null);
    setCenters(null);
    setError(false);
    void api
      .workspace(systemId, controller.signal)
      .then((result) => {
        if (alive) setWorkspace(result);
      })
      .catch(() => {
        if (alive && !controller.signal.aborted) setError(true);
      });
    void api
      .workCenters(controller.signal)
      .then((result) => {
        if (alive) setCenters(result);
      })
      .catch(() => {
        if (alive) setCenters([]);
      });
    void api
      .evidence(systemId, controller.signal)
      .then((result) => {
        if (alive) setEvidenceRows(result);
      })
      .catch(() => {
        if (alive) setEvidenceRows([]);
      });
    return () => {
      alive = false;
      controller.abort();
    };
  }, [api, systemId, reloadKey]);

  const [centerForm, setCenterForm] = useState<{
    code: string;
    name: string;
    kind: WorkCenterRequestRequest["kind"];
  } | null>(null);
  const [centerSaving, setCenterSaving] = useState(false);
  const [centerSeeding, setCenterSeeding] = useState(false);
  const [centerError, setCenterError] = useState<string | null>(null);

  /** One-click standard station set — the read no longer self-seeds, so an
   * empty org resolves its work_centers blocker here (or at first release). */
  const seedCenters = async () => {
    setCenterSeeding(true);
    setCenterError(null);
    try {
      setCenters(await api.seedWorkCenters());
    } catch {
      setCenterError(t("catalog.errorNetwork"));
    } finally {
      setCenterSeeding(false);
    }
  };

  const reactivateCenter = async (center: WorkCenter) => {
    try {
      await api.upsertWorkCenter({
        code: center.code,
        name: center.name,
        kind: center.kind as WorkCenterRequestRequest["kind"],
        display_order: center.display_order,
      });
      setCenters(await api.workCenters());
    } catch {
      /* the centers list keeps its last state; the readiness ladder still shows the blocker */
    }
  };

  /** A readiness blocker that says 'missing work centers' resolves here —
   * the upsert endpoint creates or revives the row the routing needs. */
  const createCenter = async () => {
    if (!centerForm) return;
    const code = centerForm.code.trim().toUpperCase();
    const name = centerForm.name.trim();
    if (!code || !name) return;
    setCenterSaving(true);
    setCenterError(null);
    try {
      await api.upsertWorkCenter({
        code,
        name,
        kind: centerForm.kind,
        display_order: (centers?.length ?? 0) + 1,
      });
      setCenters(await api.workCenters());
      setCenterForm(null);
    } catch (createError) {
      setCenterError(
        createError instanceof Error ? createError.message : "work_center_write_failed",
      );
    } finally {
      setCenterSaving(false);
    }
  };

  if (error) return <p role="alert">{ct("errorNetwork")}</p>;
  if (!workspace) return <p role="status">{ct("loading")}</p>;

  const { system, articles, beads, kits, reinforcements, purchase_mappings, process_profile } =
    workspace;

  const purchased = new Set(purchase_mappings.map((map) => map.profile_article_id));
  const beadsByArticle = new Map<string, number>();
  for (const bead of beads) {
    beadsByArticle.set(bead.bead_article_id, (beadsByArticle.get(bead.bead_article_id) ?? 0) + 1);
  }

  const jump = (anchor: string) => {
    const target =
      anchor === "ws.articles" || anchor === "ws.purchase" || anchor === "ws.process"
        ? anchor
        : "ws.system";
    document.getElementById(target)?.scrollIntoView({ block: "start" });
  };

  // §06-C relationship map — nodes are the authority groups; clicking one
  // shows dependencies, consumers and the impact if it changes.
  const nodes: { id: string; label: string; count: number; deps: string[]; uses: string[] }[] = [
    {
      id: "system",
      label: system.name,
      count: 1,
      deps: [],
      uses: ["articles", "beads", "kits", "reinforcements", "process"],
    },
    {
      id: "articles",
      label: wst("articles"),
      count: articles.length,
      deps: ["system"],
      uses: ["beads", "reinforcements", "purchase"],
    },
    {
      id: "beads",
      label: wst("beads"),
      count: beads.length,
      deps: ["system", "articles"],
      uses: [],
    },
    {
      id: "reinforcements",
      label: wst("reinforcements"),
      count: reinforcements.length,
      deps: ["system", "articles"],
      uses: [],
    },
    {
      id: "kits",
      label: wst("hardware"),
      count: kits.length,
      deps: ["system"],
      uses: [],
    },
    {
      id: "purchase",
      label: wst("purchase"),
      count: purchase_mappings.length,
      deps: ["articles"],
      uses: [],
    },
    {
      id: "process",
      label: wst("process"),
      count: process_profile ? 1 : 0,
      deps: ["system"],
      uses: [],
    },
  ];
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const activeNode = selectedNode ? nodeById.get(selectedNode) : undefined;

  // Fuentes: human-readable name for the row each evidence attests.
  const targetName = (row: EvidenceRow): string => {
    if (row.authority_table === "profile_systems" && row.row_id === system.id) return system.name;
    const article = articles.find((a) => a.id === row.row_id);
    if (article) return `${article.sku} · ${article.name}`;
    const bead = beads.find((b) => b.id === row.row_id);
    if (bead) return `${wst("bead")} ${bead.glass_thickness_mm} mm`;
    const kit = kits.find((k) => k.id === row.row_id);
    if (kit) return kit.name;
    const reinforcement = reinforcements.find((r) => r.id === row.row_id);
    if (reinforcement) return shortTechnicalId(reinforcement.id);
    return `${row.authority_table} · ${shortTechnicalId(row.row_id)}`;
  };
  const reviewEvidence = (row: EvidenceRow, state: "REVIEWED" | "REJECTED") => {
    void api.reviewEvidence(row.id, state).then((updated) => {
      setEvidenceRows((rows) =>
        rows ? rows.map((r) => (r.id === updated.id ? updated : r)) : rows,
      );
    });
  };

  return (
    <div className="ws">
      <header className="ws-identity" id="ws.system">
        <div className="ws-identity-head">
          <h2>
            {system.name}{" "}
            <code title={system.code}>
              {system.code.length > 16 ? `${system.code.slice(0, 16)}…` : system.code}
            </code>
          </h2>
          <div className="ws-identity-meta">
            {system.manufacturer && <span className="ws-chip">{system.manufacturer}</span>}
            {system.family && <span className="ws-chip">{system.family}</span>}
            <span className="ws-chip">
              {domainLabel("SystemFamilyEnum", system.system_family).label}
            </span>
            <span className="ws-chip">{ct(`option.${system.material}`)}</span>
            {(system.applications ?? []).map((app) => (
              <span key={app} className="ws-chip ws-chip--app">
                {app}
              </span>
            ))}
            <ProvenanceBadge row={system} />
            <span className="ws-badge">{system.is_active ? ct("active") : ct("inactive")}</span>
          </div>
          <dl className="ws-identity-facts">
            <div>
              <dt>{ct("field.depth_mm")}</dt>
              <dd>{fmtMm(system.depth_mm)} mm</dd>
            </div>
            <div>
              <dt>{ct("field.chamber_count")}</dt>
              <dd>{system.chamber_count}</dd>
            </div>
            <div>
              <dt>{wst("processAuthority")}</dt>
              <dd>
                {process_profile
                  ? `${process_profile.label} · v${process_profile.version}`
                  : wst("noProcess")}
              </dd>
            </div>
            <div>
              <dt>{wst("provenance")}</dt>
              <dd>{provenanceLabel(system.data_provenance)}</dd>
            </div>
          </dl>
          {canEdit && (
            <button
              type="button"
              className="ui-button ui-button--small"
              onClick={() => onEdit("systems", system.id)}
            >
              {ct("edit")}
            </button>
          )}
        </div>
        <ReadinessLadder system={system} onJump={jump} />
      </header>

      <section className="ws-map" aria-label={wst("map")}>
        <h3>{wst("map")}</h3>
        <div className="ws-map-row" role="list">
          {nodes.map((node, index) => (
            <div key={node.id} className="ws-map-item" role="listitem">
              {index > 0 && (
                <span className="ws-map-edge" aria-hidden="true">
                  →
                </span>
              )}
              <button
                type="button"
                className={`ws-map-node ${activeNode?.id === node.id ? "is-active" : ""}`}
                onClick={() => setSelectedNode(node.id === selectedNode ? null : node.id)}
              >
                <strong>{node.label}</strong>
                <small>
                  {node.count} {wst("entities")}
                </small>
              </button>
            </div>
          ))}
        </div>
        {activeNode && (
          <div className="ws-map-detail">
            <p>
              <strong>{wst("dependsOn")}:</strong>{" "}
              {activeNode.deps.length
                ? activeNode.deps.map((d) => nodeById.get(d)?.label ?? d).join(", ")
                : wst("none")}
            </p>
            <p>
              <strong>{wst("usedBy")}:</strong>{" "}
              {activeNode.uses.length
                ? activeNode.uses.map((u) => nodeById.get(u)?.label ?? u).join(", ")
                : wst("terminal")}
            </p>
            <p>
              <strong>{wst("impact")}:</strong>{" "}
              {activeNode.id === "system"
                ? wst("impactSystem")
                : activeNode.id === "articles"
                  ? wst("impactArticles")
                  : activeNode.id === "beads"
                    ? wst("impactBeads")
                    : activeNode.id === "reinforcements"
                      ? wst("impactReinforcements")
                      : activeNode.id === "kits"
                        ? wst("impactKits")
                        : activeNode.id === "purchase"
                          ? wst("impactPurchase")
                          : wst("impactProcess")}
            </p>
          </div>
        )}
      </section>

      <section className="ws-section" id="ws.articles">
        <header className="ws-section-head">
          <h3>
            {wst("articles")} <span className="ws-count">{articles.length}</span>
          </h3>
          <button
            type="button"
            className="ui-button ui-button--ghost ui-button--small"
            onClick={() => onShowRecords("articles")}
          >
            {wst("allRecords")}
          </button>
          {canEdit && (
            <button
              type="button"
              className="ui-button ui-button--small"
              onClick={() => onEdit("articles")}
            >
              {ct("create")}
            </button>
          )}
        </header>
        {!articles.length ? (
          <p className="ws-empty">{wst("noArticles")}</p>
        ) : (
          <div className="ws-article-grid">
            {articles.map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                purchased={purchased.has(article.id)}
                beads={beadsByArticle.get(article.id) ?? 0}
                canEdit={canEdit}
                onEdit={() => onEdit("articles", article.id)}
              />
            ))}
          </div>
        )}
      </section>

      <section className="ws-section">
        <header className="ws-section-head">
          <h3>
            {wst("glazing")} <span className="ws-count">{beads.length}</span>
          </h3>
          <button
            type="button"
            className="ui-button ui-button--ghost ui-button--small"
            onClick={() => onShowRecords("glazing")}
          >
            {wst("allRecords")}
          </button>
          {canEdit && (
            <button
              type="button"
              className="ui-button ui-button--small"
              onClick={() => onEdit("glazing")}
            >
              {ct("create")}
            </button>
          )}
        </header>
        {!beads.length ? (
          <p className="ws-empty">{wst("noBeadsRows")}</p>
        ) : (
          <div className="catalog-table-scroll">
            <table className="ws-table">
              <thead>
                <tr>
                  <th scope="col">{wst("bead")}</th>
                  <th scope="col">{ct("field.glass_thickness_mm")}</th>
                  <th scope="col">{ct("field.bead_width_mm")}</th>
                  <th scope="col">{ct("field.gasket_interior_mm")}</th>
                  <th scope="col">{ct("field.gasket_exterior_mm")}</th>
                  <th scope="col">{ct("field.cut_add_mm")}</th>
                  <th scope="col">{ct("actions")}</th>
                </tr>
              </thead>
              <tbody>
                {beads.map((bead: BeadResponse) => {
                  const article = articles.find((a) => a.id === bead.bead_article_id);
                  return (
                    <tr key={bead.id}>
                      <th scope="row">{article?.name ?? bead.bead_article_id}</th>
                      <td>{fmtMm(bead.glass_thickness_mm)} mm</td>
                      <td>{fmtMm(bead.bead_width_mm)} mm</td>
                      <td>{fmtMm(bead.gasket_interior_mm)} mm</td>
                      <td>{fmtMm(bead.gasket_exterior_mm)} mm</td>
                      <td>{fmtMm(bead.cut_add_mm)} mm</td>
                      <td>
                        <button
                          type="button"
                          className="ui-button ui-button--small"
                          onClick={() => onEdit("glazing", bead.id)}
                        >
                          {ct(canEdit && !bead.read_only ? "edit" : "view")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ws-section">
        <header className="ws-section-head">
          <h3>
            {wst("hardware")} <span className="ws-count">{kits.length}</span>
          </h3>
          <button
            type="button"
            className="ui-button ui-button--ghost ui-button--small"
            onClick={() => onShowRecords("hardware-kits")}
          >
            {wst("allRecords")}
          </button>
          {canEdit && (
            <button
              type="button"
              className="ui-button ui-button--small"
              onClick={() => onEdit("hardware-kits")}
            >
              {ct("create")}
            </button>
          )}
        </header>
        {!kits.length ? (
          <p className="ws-empty">{wst("noKits")}</p>
        ) : (
          <div className="ws-kit-row">
            {kits.map((kit: KitResponse) => (
              <button
                key={kit.id}
                type="button"
                className="ws-kit-card"
                onClick={() => onEdit("hardware-kits", kit.id)}
              >
                <strong>{kit.name}</strong>
                <span>{kit.sku}</span>
                <small>
                  {ct(`option.${kit.opening_type}`)} · {ct(`option.${kit.rail_type}`)}
                </small>
                <ProvenanceBadge row={kit} />
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="ws-section">
        <header className="ws-section-head">
          <h3>
            {wst("reinforcements")} <span className="ws-count">{reinforcements.length}</span>
          </h3>
        </header>
        {!reinforcements.length ? (
          <p className="ws-empty">{wst("noReinforcements")}</p>
        ) : (
          <div className="catalog-table-scroll">
            <table className="ws-table">
              <thead>
                <tr>
                  <th scope="col">{wst("parent")}</th>
                  <th scope="col">{ct("field.sku")}</th>
                  <th scope="col">{wst("name")}</th>
                  <th scope="col">{wst("thickness")}</th>
                  <th scope="col">{wst("inertia")}</th>
                  <th scope="col">{wst("stockLength")}</th>
                  <th scope="col">{wst("supplier")}</th>
                </tr>
              </thead>
              <tbody>
                {reinforcements.map((row: ReinforcementRow) => {
                  const parent = articles.find((a) => a.id === row.parent_profile_article_id);
                  return (
                    <tr key={row.id}>
                      <th scope="row">{parent?.name ?? row.parent_profile_article_id}</th>
                      <td>
                        <code>{row.sku}</code>
                        {row.is_default && <span className="ws-badge">{wst("default")}</span>}
                      </td>
                      <td>{row.name}</td>
                      <td>{row.thickness_mm ? `${fmtMm(row.thickness_mm)} mm` : wst("unknown")}</td>
                      <td>{row.ix_cm4 ? `${row.ix_cm4} cm⁴` : wst("unknown")}</td>
                      <td>{fmtMm(row.stock_length_mm)} mm</td>
                      <td>{row.supplier_name ?? row.manufacturer_name ?? wst("unknown")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ws-section" id="ws.purchase">
        <header className="ws-section-head">
          <h3>
            {wst("purchase")} <span className="ws-count">{purchase_mappings.length}</span>
          </h3>
        </header>
        {!purchase_mappings.length ? (
          <p className="ws-empty">{wst("noPurchase")}</p>
        ) : (
          <div className="catalog-table-scroll">
            <table className="ws-table">
              <thead>
                <tr>
                  <th scope="col">{wst("article")}</th>
                  <th scope="col">{wst("commercialSku")}</th>
                  <th scope="col">{wst("manufacturer")}</th>
                  <th scope="col">{wst("supplier")}</th>
                  <th scope="col">{wst("unit")}</th>
                  <th scope="col">{ct("state")}</th>
                </tr>
              </thead>
              <tbody>
                {purchase_mappings.map((map: PurchaseMappingRow) => {
                  const article = articles.find((a) => a.id === map.profile_article_id);
                  return (
                    <tr key={map.id}>
                      <th scope="row">{article?.name ?? map.profile_article_id}</th>
                      <td>
                        <code>{map.commercial_sku}</code>
                      </td>
                      <td>{map.manufacturer_name}</td>
                      <td>{map.supplier_name ?? wst("unknown")}</td>
                      <td>{map.purchase_unit}</td>
                      <td>{ct(map.is_active ? "active" : "inactive")}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="ws-section" id="ws.process">
        <header className="ws-section-head">
          <h3>{wst("process")}</h3>
        </header>
        {!process_profile ? (
          <p className="ws-empty">
            {wst("noProcessBound")}{" "}
            {canEdit && (
              <button
                type="button"
                className="ui-button ui-button--small"
                onClick={() => onEdit("systems", system.id)}
              >
                {wst("bindProcess")}
              </button>
            )}
          </p>
        ) : (
          <div className="ws-process">
            <header>
              <strong>
                {process_profile.label} <code>{process_profile.code}</code> v
                {process_profile.version}
              </strong>
              <div className="ws-identity-meta">
                {process_profile.org_id === null && <span className="ws-chip">{ct("global")}</span>}
                {process_profile.material && (
                  <span className="ws-chip">{ct(`option.${process_profile.material}`)}</span>
                )}
                {process_profile.product_kind && (
                  <span className="ws-chip">{productKindLabel(process_profile.product_kind)}</span>
                )}
                <span className="ws-chip">
                  {joiningMethodLabel(process_profile.joining_method)}
                </span>
              </div>
            </header>
            <div className="ws-process-cols">
              <div>
                <h4>{wst("stations")}</h4>
                <ul className="ws-stations">
                  {(
                    process_profile.stations as {
                      code?: string;
                      station?: string;
                      when?: string;
                      work_center?: string;
                    }[]
                  ).map((station, index) => (
                    <li key={index}>
                      <strong>{stationCodeLabel(station.code ?? station.station ?? "?")}</strong>
                      {station.when && <small> · {station.when}</small>}
                      {station.work_center && <small> · {station.work_center}</small>}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>{wst("operationMap")}</h4>
                <ul className="ws-stations">
                  {Object.entries(process_profile.operation_station_map).map(([op, station]) => (
                    <li key={op}>
                      <code>{opKindLabel(op)}</code> →{" "}
                      <strong>{stationCodeLabel(String(station))}</strong>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4>{wst("capabilities")}</h4>
                <ul className="ws-stations">
                  {[
                    ["sashAssembly", process_profile.sash_assembly_required],
                    ["hardwareStation", process_profile.hardware_station],
                    ["glazing", process_profile.glazing],
                    ["qc", process_profile.qc],
                    ["packaging", process_profile.packaging],
                  ].map(([key, enabled]) => (
                    <li key={String(key)} className={enabled ? "" : "ws-off"}>
                      {wst(String(key))}: {enabled ? <Icon name="check" size={11} /> : "—"}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
        {centers !== null ? (
          <div className="ws-centers">
            <h4>{wst("centers")}</h4>
            {centers.length === 0 && (
              <p className="ws-empty">
                {wst("noCenters")}
                {canEdit && (
                  <>
                    {" "}
                    <button
                      type="button"
                      className="ui-button ui-button--small"
                      disabled={centerSeeding}
                      onClick={() => void seedCenters()}
                    >
                      {centerSeeding ? wst("seedingCenters") : wst("seedCenters")}
                    </button>
                  </>
                )}
              </p>
            )}
            <ul className="ws-stations">
              {centers.map((center) => (
                <li key={center.id}>
                  <strong>{center.name}</strong>
                  <small>
                    {" "}
                    · <code>{center.code}</code> · {centerKindLabel(center.kind)}
                  </small>
                  {!center.active && (
                    <>
                      {" "}
                      <span className="ws-chip ws-chip--off">{wst("centerInactive")}</span>
                      {canEdit && (
                        <>
                          {" "}
                          <button
                            type="button"
                            className="link-button"
                            onClick={() => void reactivateCenter(center)}
                          >
                            {wst("centerActivate")}
                          </button>
                        </>
                      )}
                    </>
                  )}
                </li>
              ))}
            </ul>
            {canEdit &&
              (centerForm ? (
                <form
                  noValidate
                  className="ws-center-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void createCenter();
                  }}
                >
                  <input
                    value={centerForm.code}
                    placeholder={wst("centerCode")}
                    maxLength={50}
                    aria-label={wst("centerCode")}
                    onChange={(event) => setCenterForm({ ...centerForm, code: event.target.value })}
                  />
                  <input
                    value={centerForm.name}
                    placeholder={wst("centerName")}
                    maxLength={200}
                    aria-label={wst("centerName")}
                    onChange={(event) => setCenterForm({ ...centerForm, name: event.target.value })}
                  />
                  <select
                    value={centerForm.kind}
                    aria-label={wst("centerKind")}
                    onChange={(event) =>
                      setCenterForm({
                        ...centerForm,
                        kind: event.target.value as WorkCenterRequestRequest["kind"],
                      })
                    }
                  >
                    {Object.values(WorkCenterRequestKindEnum).map((kind) => (
                      <option key={kind} value={kind}>
                        {centerKindLabel(kind)}
                      </option>
                    ))}
                  </select>
                  <button
                    type="submit"
                    className="ui-button ui-button--small"
                    disabled={centerSaving || !centerForm.code.trim() || !centerForm.name.trim()}
                  >
                    {wst("centerCreate")}
                  </button>
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => {
                      setCenterForm(null);
                      setCenterError(null);
                    }}
                  >
                    {t("projects.cancel")}
                  </button>
                  {centerError ? <span role="alert">{centerError}</span> : null}
                </form>
              ) : (
                <button
                  type="button"
                  className="ui-button ui-button--small"
                  onClick={() => setCenterForm({ code: "", name: "", kind: "CUT" })}
                >
                  {wst("newCenter")}
                </button>
              ))}
          </div>
        ) : null}
      </section>

      <section className="ws-section" id="ws.sources">
        <header className="ws-section-head">
          <h3>{wst("sources")}</h3>
        </header>
        <p className="ws-hint">{wst("sourcesHint")}</p>
        {evidenceRows === null ? (
          <p className="ws-empty">{ct("loading")}</p>
        ) : !evidenceRows.length ? (
          <p className="ws-empty">{wst("noSources")}</p>
        ) : (
          <table className="ui-table ws-evidence">
            <thead>
              <tr>
                <th>{wst("evidenceTarget")}</th>
                <th>{wst("evidenceField")}</th>
                <th>{wst("evidenceValue")}</th>
                <th>{wst("evidenceSource")}</th>
                <th>{wst("evidenceScope")}</th>
                <th>{wst("evidenceStateCol")}</th>
                {canEdit && <th />}
              </tr>
            </thead>
            <tbody>
              {evidenceRows.map((row) => (
                <tr key={row.id}>
                  <td>{targetName(row)}</td>
                  <td>
                    <code>{row.field_name}</code>
                  </td>
                  <td>
                    {row.value_text ?? "—"}
                    {row.unit ? ` ${row.unit}` : ""}
                  </td>
                  <td>
                    {row.source_url ? (
                      <a href={row.source_url} target="_blank" rel="noreferrer">
                        {row.source_document}
                      </a>
                    ) : (
                      row.source_document
                    )}
                    {row.source_page ? ` · ${wst("evidencePage")} ${row.source_page}` : ""}
                    {row.applicability ? (
                      <small className="ws-evidence-applies">
                        {" "}
                        {wst("evidenceOn")} {row.applicability}
                      </small>
                    ) : null}
                  </td>
                  <td>{row.scope}</td>
                  <td>
                    <span
                      className={`ws-badge ${row.review_state === "REVIEWED" ? "ws-badge--ok" : row.review_state === "REJECTED" ? "ws-badge--warn" : ""}`}
                    >
                      {wst(`evidenceState.${row.review_state}`)}
                    </span>
                  </td>
                  {canEdit && (
                    <td>
                      {row.review_state === "PENDING" && (
                        <span className="ws-evidence-actions">
                          <button
                            type="button"
                            className="ui-button ui-button--small"
                            onClick={() => reviewEvidence(row, "REVIEWED")}
                          >
                            {wst("evidenceReview")}
                          </button>
                          <button
                            type="button"
                            className="ui-button ui-button--ghost ui-button--small"
                            onClick={() => reviewEvidence(row, "REJECTED")}
                          >
                            {wst("evidenceReject")}
                          </button>
                        </span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {canEdit && (
        <p className="ws-delete">
          <button
            type="button"
            className="ui-button ui-button--small ui-button--danger"
            onClick={() => onDeleted("systems", system.id)}
          >
            {ct("delete")}
          </button>
        </p>
      )}
    </div>
  );
}
