import { useQuery } from "@tanstack/react-query";

import { aiProviderStatus } from "../../api/generated/dekopen";
import { t } from "../../i18n/es-CL";

/** §IA3 — the org-visible honesty badge: whenever the org's AI answers come
 * from the explicit test mode (MOCK), every member sees "Modo de prueba" in
 * the topbar instead of believing the answers are the real provider. The
 * endpoint leaks no provider internals — only the serving mode. */
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
  if (query.data?.mock !== true) return null;
  return (
    <span className="ai-test-mode-badge" role="status" title={t("ai.testModeHint")}>
      {t("ai.testMode")}
    </span>
  );
}
