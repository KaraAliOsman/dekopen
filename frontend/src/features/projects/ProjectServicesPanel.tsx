import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { projectServicesRead, projectServicesUpdate } from "../../api/generated/dekopen";
import { formatMoney } from "../../format";
import { t, tDynamic } from "../../i18n/es-CL";

/** D06 — «Servicios del proyecto»: instalación, sellado, retiro, andamio,
 * flete. Selections reference catalog articles; the engine measures each
 * over the declared positions (unidad / m² / ml de perímetro / cargo
 * único), so a checkbox never fabricates a quantity or a price. */

interface ProjectServicesPanelProps {
  projectId: string;
  orgId: string;
  canWrite: boolean;
}

export function ProjectServicesPanel({
  projectId,
  orgId,
  canWrite,
}: ProjectServicesPanelProps): JSX.Element {
  const queryClient = useQueryClient();
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  const queryKey = useMemo(
    () => ["project-services", orgId, projectId] as const,
    [orgId, projectId],
  );
  const query = useQuery({
    queryKey,
    queryFn: async () => {
      const response = await projectServicesRead(projectId, requestOptions);
      if (response.status !== 200) throw new Error("load");
      return response.data;
    },
    retry: false,
  });
  const [draft, setDraft] = useState<Set<string> | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const selected =
    draft ??
    new Set((query.data?.items ?? []).filter((item) => item.selected).map((item) => item.id));
  // Unsaved-note: a touched draft that differs from the server state.
  const dirty = draft !== null;

  useEffect(() => {
    setDraft(null);
    setMessage("");
  }, [projectId]);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setDraft(next);
    setMessage("");
  };

  async function save(): Promise<void> {
    if (busy || !canWrite) return;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectServicesUpdate(
        projectId,
        { service_article_ids: [...selected] },
        requestOptions,
      );
      if (response.status !== 200) throw new Error("save");
      setDraft(null);
      setMessage(t("projects.servicesSaved"));
      void queryClient.invalidateQueries({ queryKey });
    } catch {
      setMessage(t("projects.servicesError"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="project-services">
      <p className="assembly-hint">{t("projects.servicesHint")}</p>
      {query.isError && (
        <p className="project-services__status is-error">{t("projects.servicesError")}</p>
      )}
      {(query.data?.items ?? []).length === 0 && !query.isPending && (
        <p>{t("projects.servicesEmpty")}</p>
      )}
      <ul className="project-services__list">
        {(query.data?.items ?? []).map((item) => (
          <li key={item.id}>
            <label className="project-services__item">
              <input
                type="checkbox"
                disabled={!canWrite || busy || !item.is_active}
                checked={selected.has(item.id)}
                onChange={() => toggle(item.id)}
              />
              <span>
                {item.name}
                <em>
                  {" · "}
                  {tDynamic("catalog.serviceKind", item.kind)}
                  {" · "}
                  {tDynamic("projects.serviceRule", item.qty_rule)}
                  {item.unit_price !== null && item.unit_price_currency
                    ? ` — ${formatMoney(item.unit_price, item.unit_price_currency)}`
                    : ` — ${t("ui.noData")}`}
                  {item.read_only ? ` · ${item.code}` : ""}
                </em>
              </span>
            </label>
          </li>
        ))}
      </ul>
      {(query.data?.lines ?? []).length > 0 && (
        <table className="project-services__lines">
          <tbody>
            {(query.data?.lines ?? []).map((line) => (
              <tr key={line.code}>
                <td>
                  {line.name}
                  {line.detail ? <em> — {line.detail}</em> : null}
                </td>
                <td>
                  {line.unit_price === null || line.total_price === null
                    ? `${line.quantity} ${line.unit} · ${t("ui.noData")}`
                    : `${line.quantity} ${line.unit} × ${formatMoney(
                        line.unit_price,
                        line.unit_price_currency ?? "CLP",
                      )} = ${formatMoney(line.total_price, line.unit_price_currency ?? "CLP")}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canWrite && (
        <button
          type="button"
          className="primary-action"
          disabled={busy || !dirty || query.isPending}
          onClick={() => void save()}
        >
          {t("projects.servicesSave")}
        </button>
      )}
      {message && (
        <p
          className={`project-services__status${message === t("projects.servicesError") ? " is-error" : ""}`}
        >
          {message}
        </p>
      )}
    </div>
  );
}
