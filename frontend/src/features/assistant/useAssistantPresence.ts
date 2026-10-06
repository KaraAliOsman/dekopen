import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { aiJobList } from "../../api/generated/dekopen";
import type { AiJob } from "../../api/generated/models/aiJob";
import { orbStateFor, type OrbState } from "./Orb";
import { stableRefs } from "./assistantContext";

/** §P17 — el Orb conectado al estado real (F8): todo punto donde la IA
 * tiene presencia deriva su estado del trabajo de IA más reciente del
 * contexto actual (proyecto, posición, OT…), no de un reloj ni de una
 * animación libre. El mismo hook alimenta el lanzador de la barra
 * superior, el encabezado del dock, los avatares, las tarjetas de
 * artefacto y los estados vacíos. */

export const LIVE_JOB_STATES = new Set(["QUEUED", "PLANNING", "RUNNING"]);
export const WAITING_JOB_STATES = new Set(["WAITING_FOR_USER", "WAITING_FOR_APPROVAL"]);

/** Lo que merece insignia en la barra superior: una decisión pendiente
 * manda sobre el trabajo en vuelo; un fallo reintentable sigue siendo
 * accionable y no puede desaparecer de la vista. */
export const PRESSING_PRIORITY: Record<string, number> = {
  WAITING_FOR_APPROVAL: 0,
  WAITING_FOR_USER: 1,
  RUNNING: 2,
  PLANNING: 3,
  QUEUED: 4,
  FAILED_RETRYABLE: 5,
};
export const PRESSING_JOB_STATES = new Set(Object.keys(PRESSING_PRIORITY));

type JobRef = {
  surface?: string;
  /** Las refs del job llegan como uuid/unknown desde el API — el matcher
   * las normaliza a string antes de comparar. */
  refs?: Record<string, unknown>;
  state?: string;
  updated_at?: string;
};

/** Continuidad por refs estables (la misma regla que el dock): la superficie
 * coincide y las refs de identidad son simétricas — un job con refs extra no
 * se reasigna a otra ruta, y una selección volátil del canvas nunca rompe el
 * vínculo. */
export function jobMatchesContext(
  job: JobRef,
  surface: string,
  refs: Record<string, string>,
): boolean {
  if (job.surface !== surface) return false;
  const identity = stableRefs(refs);
  const jobRefs = job.refs ?? {};
  const identityKeys = Object.keys(identity);
  const jobKeys = Object.keys(jobRefs);
  return (
    identityKeys.length === jobKeys.length &&
    identityKeys.every((key) => String(jobRefs[key] ?? "") === identity[key])
  );
}

/** El trabajo que define la presencia: el más reciente del contexto.
 * `updated_at` decide — un job reactivado por un seguimiento vuelve a
 * mandar aunque haya otros más nuevos en la lista. */
export function presenceJob(
  jobs: JobRef[] | null | undefined,
  surface: string,
  refs: Record<string, string>,
): JobRef | null {
  const matching = (jobs ?? []).filter((job) => jobMatchesContext(job, surface, refs));
  if (!matching.length) return null;
  const stamp = (job: JobRef): number => Date.parse(job.updated_at ?? "") || 0;
  return matching.reduce((a, b) => (stamp(a) >= stamp(b) ? a : b));
}

/** El trabajo más apremiante de la org — prioridad de estado y después
 * `updated_at`. La insignia global sigue mostrando actividad real aunque el
 * contexto no tenga job propio (un agente en otra superficie no desaparece). */
export function pressingJob(jobs: JobRef[] | null | undefined): JobRef | null {
  const pressing = (jobs ?? []).filter((job) => PRESSING_JOB_STATES.has(String(job.state)));
  if (!pressing.length) return null;
  const stamp = (job: JobRef): number => Date.parse(job.updated_at ?? "") || 0;
  return pressing.reduce((a, b) => {
    const pa = PRESSING_PRIORITY[String(a.state)] ?? 9;
    const pb = PRESSING_PRIORITY[String(b.state)] ?? 9;
    return pa === pb ? (stamp(a) >= stamp(b) ? a : b) : pa < pb ? a : b;
  });
}

export function useAssistantPresence({
  organizationId,
  surface,
  refs,
}: {
  organizationId: string | null;
  surface: string;
  refs: Record<string, string>;
}): {
  /** Job del contexto actual (el más reciente que coincide) o null. */
  job: AiJob | null;
  /** Su estado traducido al Orb — idle seguro cuando no hay job. */
  orbState: OrbState;
  /** El trabajo más apremiante de la org (para la insignia global). */
  pressingJob: AiJob | null;
  loading: boolean;
} {
  const headers = useMemo(
    () => ({ headers: { "X-Organization-ID": organizationId ?? "" } }),
    [organizationId],
  );
  // Misma queryKey que la sala del asistente — la lista se comparte en caché
  // y un job recién lanzado desde cualquier superficie aparece sin refetch.
  const query = useQuery({
    queryKey: ["ai", "jobs", organizationId],
    enabled: Boolean(organizationId),
    staleTime: 10_000,
    refetchInterval: (result) =>
      (result.state.data ?? []).some((job) => PRESSING_JOB_STATES.has(String(job.state)))
        ? 4_000
        : 15_000,
    queryFn: async () => {
      const response = await aiJobList(undefined, headers);
      if (response.status !== 200) return [] as AiJob[];
      return response.data as unknown as AiJob[];
    },
  });
  const jobs = query.data ?? [];
  const job = presenceJob(jobs, surface, refs) as AiJob | null;
  const pressing = pressingJob(jobs) as AiJob | null;
  return {
    job,
    orbState: job ? orbStateFor(job.state) : "idle",
    pressingJob: pressing,
    loading: query.isPending,
  };
}
