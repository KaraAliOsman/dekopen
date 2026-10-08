import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import {
  clientsRetrieve,
  positionsRetrieve,
  productionOrderDetail,
  projectsRetrieve,
} from "../../api/generated/dekopen";
import type { PositionResponse } from "../../api/generated/models/positionResponse";
import type { ProductionOrderDetail } from "../../api/generated/models/productionOrderDetail";
import type { ProjectResponse } from "../../api/generated/models/projectResponse";
import { SURFACE_LABELS } from "./surfaces";

/** «Sabe dónde está el usuario»: el encabezado del dock no muestra el nombre
 * técnico de la superficie sino el objeto real en lenguaje humano —
 * «Pos. 03 Living · P-000012», «OT-0042», «Cotización P-000012». Las refs
 * llevan UUIDs; este hook los traduce a los códigos que la persona lee en
 * el resto de la app. */
export function useAssistantWhereAmI({
  organizationId,
  surface,
  refs,
}: {
  organizationId: string | null;
  surface: string;
  refs: Record<string, string>;
}): string {
  const positionId = refs.position_id ?? "";
  const projectId = refs.project_id ?? "";
  const orderId = refs.work_order_id ?? "";
  const clientId = refs.client_id ?? "";

  const headers = useMemo(
    () => ({ headers: { "X-Organization-ID": organizationId ?? "" } }),
    [organizationId],
  );

  const positionQuery = useQuery({
    queryKey: ["assistant", "where", "position", positionId],
    enabled: Boolean(organizationId && surface === "position" && positionId),
    staleTime: 30_000,
    queryFn: async () => {
      const response = await positionsRetrieve(positionId, headers);
      return response.status === 200 ? (response.data as PositionResponse) : null;
    },
  });
  const projectQuery = useQuery({
    queryKey: ["assistant", "where", "project", projectId],
    enabled: Boolean(organizationId && projectId),
    staleTime: 30_000,
    queryFn: async () => {
      const response = await projectsRetrieve(projectId, headers);
      return response.status === 200 ? (response.data as ProjectResponse) : null;
    },
  });
  const orderQuery = useQuery({
    queryKey: ["assistant", "where", "order", orderId],
    enabled: Boolean(organizationId && surface === "work_order" && orderId),
    staleTime: 30_000,
    queryFn: async () => {
      const response = await productionOrderDetail(orderId, headers);
      return response.status === 200 ? (response.data as ProductionOrderDetail) : null;
    },
  });
  const clientQuery = useQuery({
    queryKey: ["assistant", "where", "client", clientId],
    enabled: Boolean(organizationId && surface === "client" && clientId),
    staleTime: 30_000,
    queryFn: async () => {
      const response = await clientsRetrieve(clientId, headers);
      return response.status === 200 ? response.data.client : null;
    },
  });

  const surfaceLabel = SURFACE_LABELS[surface] ?? surface;
  const projectCode = projectQuery.data?.code?.trim();

  if (surface === "position") {
    const position = positionQuery.data;
    if (position) {
      const index = `Pos. ${String(position.position_index).padStart(2, "0")}`;
      const place = position.location_tag?.trim();
      const tail = [place, projectCode].filter(Boolean).join(" · ");
      if (place) return `${index} ${tail}`;
      return projectCode ? `${index} · ${projectCode}` : index;
    }
    return projectCode ? `${surfaceLabel} · ${projectCode}` : surfaceLabel;
  }
  if (surface === "work_order") {
    const code = orderQuery.data?.order_code?.trim();
    return code ? `${code} · ${surfaceLabel}` : surfaceLabel;
  }
  if (surface === "client") {
    const name = clientQuery.data?.name?.trim();
    return name ? `${name} · ${surfaceLabel}` : surfaceLabel;
  }
  return projectCode ? `${surfaceLabel} · ${projectCode}` : surfaceLabel;
}
