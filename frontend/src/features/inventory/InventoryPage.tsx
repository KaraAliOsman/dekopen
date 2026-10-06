import { useCallback, useEffect, useRef, useState } from "react";

import { apiMutator } from "../../api/apiMutator";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { t } from "../../i18n/es-CL";
import { DeniedState, ErrorState, LoadingState, PageHeader } from "../../ui";
import { InventorySection } from "../purchasing/InventorySection";
import "../purchasing/purchasing.css";

type RequestFn = <T>(path: string, method?: string, body?: unknown) => Promise<T>;

type StockItem = {
  item_id: string;
  sku: string;
  name: string;
};

const INVENTORY_ROLES = ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "OPERATOR"];

function useInventoryRequest(orgId: string): RequestFn {
  const lifetime = useRef(new AbortController());
  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    return () => controller.abort();
  }, []);
  return useCallback(
    async <T,>(path: string, method = "GET", body?: unknown): Promise<T> => {
      const response = await apiMutator<{ data: T }>(`/api/v1/${path}`, {
        method,
        signal: lifetime.current.signal,
        headers: {
          "X-Organization-ID": orgId,
          "Content-Type": "application/json",
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      return response.data;
    },
    [orgId],
  );
}

/** Inventario — ruta propia para el stock del taller (reusa la sección que
 * ya convive en Compras; al separarlas el taller no entra a Compras solo
 * para mirar material). */
export function InventoryPage(): JSX.Element {
  const org = useAuthSession().me?.active_organization;
  const allowed = org != null && INVENTORY_ROLES.includes(org.role);
  const request = useInventoryRequest(org?.id ?? "");
  const [stock, setStock] = useState<StockItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    if (!org) return;
    setFailed(false);
    request<{ items?: StockItem[] }>("inventory/stock/")
      .then((data) => setStock(data.items ?? []))
      .catch((error: unknown) => {
        /* StrictMode/remount aborta el fetch en vuelo: esa petición abortada
         * no es un fallo del servidor y no debe pintar el estado de error
         * por encima de los datos que el segundo fetch sí trae. */
        if (error instanceof DOMException && error.name === "AbortError") return;
        setFailed(true);
      });
  }, [org, request]);

  useEffect(load, [load]);

  if (!allowed || !org) {
    return <DeniedState reason={t("inventory.denied")} />;
  }

  const canWrite = org.role === "OWNER" || org.role === "WORKSHOP_MANAGER";

  return (
    <section className="inventory-page" aria-labelledby="page-title">
      <PageHeader
        context={t("inventory.subtitle")}
        headingId="page-title"
        title={t("inventory.title")}
      />
      {stock !== null ? (
        <InventorySection
          request={request}
          canWrite={canWrite}
          stockItems={stock.map((item) => ({
            item_id: item.item_id,
            sku: item.sku,
            name: item.name,
          }))}
        />
      ) : failed ? (
        <ErrorState title={t("inventory.loadError")} onRetry={load} />
      ) : (
        <LoadingState shape="table" />
      )}
    </section>
  );
}
