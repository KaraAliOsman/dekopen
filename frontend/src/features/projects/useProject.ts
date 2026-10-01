import { useQuery } from "@tanstack/react-query";

import { projectsRetrieve } from "../../api/generated/dekopen";
import type { ProjectResponse } from "../../api/generated/models";
import { ApiError } from "../../api/apiMutator";
import { useAuthSession } from "../../auth/AuthSessionProvider";

export type ProjectView = { project: ProjectResponse; items: ProjectResponse[] };

export const projectKey = (orgId: string, id: string) => ["project", orgId, id] as const;

/** One shared cache entry for `GET /projects/{id}` — the page, the shell's
 * lock check, and the crumb's name resolution all observe the same query
 * instead of re-fetching the heaviest payload on the page several times. */
export function useProjectView(id: string | null) {
  const orgId = useAuthSession().me?.active_organization?.id ?? "";
  return useQuery<ProjectView>({
    queryKey: projectKey(orgId, id ?? ""),
    enabled: id !== null && orgId !== "",
    queryFn: async ({ signal }) => {
      const response = await projectsRetrieve(id!, {
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) {
        throw new ApiError(response.status, response.data);
      }
      return { project: response.data, items: [] };
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
}

export function useProject(id: string | null) {
  const view = useProjectView(id);
  return { ...view, data: view.data?.project };
}
