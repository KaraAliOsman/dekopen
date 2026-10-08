import { useQuery } from "@tanstack/react-query";

import { aiProviderStatus } from "../../api/generated/dekopen";
import { t } from "../../i18n/es-CL";

/** §IA3+§P17 — la insignia discreta «Proveedor de prueba»: solo en DEV y
 * solo cuando el modo de servicio es el de prueba. En producción el hilo
 * nunca habla del proveedor — el estado real vive en Ajustes. */
export function AiTestModeBadge({
  organizationId,
}: {
  organizationId: string | null;
}): JSX.Element | null {
  const query = useQuery({
    queryKey: ["ai", "provider-status", organizationId],
    enabled: Boolean(organizationId),
    staleTime: 30_000,
    refetchInterval: 60_000,
    queryFn: async ({ signal }) => {
      const response = await aiProviderStatus({
        signal,
        headers: { "X-Organization-ID": organizationId ?? "" },
      });
      if (response.status !== 200) return null;
      return response.data;
    },
  });
  if (!import.meta.env.DEV || query.data?.mock !== true) return null;
  return (
    <span className="ai-test-mode-badge" role="status" title={t("ai.testModeHint")}>
      {t("ai.testMode")}
    </span>
  );
}
