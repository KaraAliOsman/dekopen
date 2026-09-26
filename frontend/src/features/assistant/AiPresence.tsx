import { useQuery } from "@tanstack/react-query";

import { aiJobList } from "../../api/generated/dekopen";
import type { AiJob } from "../../api/generated/models/aiJob";
import { Orb, orbStateFor } from "./Orb";

const PRIORITY: Record<string, number> = {
  WAITING_FOR_APPROVAL: 0,
  WAITING_FOR_USER: 1,
  RUNNING: 2,
  PLANNING: 3,
  QUEUED: 4,
  FAILED_RETRYABLE: 5,
};

/** The orb in the topbar mirrors the org's most-pressing AI job: a waiting
 * decision outranks work in flight, which outranks a queued round. Polls
 * gently — the point is ambient awareness, not a ticker. */
export function AiPresence({
  organizationId,
  size = 22,
}: {
  organizationId: string | null;
  size?: number;
}): JSX.Element {
  const query = useQuery({
    queryKey: ["ai", "presence", organizationId],
    enabled: Boolean(organizationId),
    staleTime: 10_000,
    refetchInterval: 15_000,
    queryFn: async () => {
      const response = await aiJobList(
        {},
        { headers: { "X-Organization-ID": organizationId ?? "" } },
      );
      if (response.status !== 200) return [] as AiJob[];
      return response.data as AiJob[];
    },
  });
  const jobs = query.data ?? [];
  const active = jobs
    .filter((job) => job.state in PRIORITY)
    .sort((a, b) => (PRIORITY[a.state] ?? 9) - (PRIORITY[b.state] ?? 9))[0];
  return <Orb state={orbStateFor(active?.state)} size={size} />;
}
