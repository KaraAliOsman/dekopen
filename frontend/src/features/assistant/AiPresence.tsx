import { useEffect } from "react";

import type { AiJob } from "../../api/generated/models/aiJob";
import { Orb } from "./Orb";
import { useAssistantContext } from "./assistantContext";
import { PRESSING_JOB_STATES, useAssistantPresence } from "./useAssistantPresence";

/** El lanzador del asistente en la barra superior: el Orb refleja el trabajo
 * del CONTEXTO actual (useAssistantPresence) y la insignia lateral sigue
 * llevando al trabajo vivo más apremiante de la organización — una decisión
 * pendiente o una ronda en vuelo nunca queda inalcanzable aunque el usuario
 * esté en otra pantalla. */
export function AiPresence({
  organizationId,
  size = 22,
  onActiveJob,
}: {
  organizationId: string | null;
  size?: number;
  /** El job que la insignia anuncia — el objetivo del clic debe alcanzarlo. */
  onActiveJob?: (job: AiJob | null) => void;
}): JSX.Element {
  const { surface, refs } = useAssistantContext();
  const { job, orbState, pressingJob } = useAssistantPresence({
    organizationId,
    surface,
    refs,
  });
  const active = job && PRESSING_JOB_STATES.has(String(job.state)) ? job : pressingJob;
  useEffect(() => {
    onActiveJob?.(active ?? null);
  }, [active, onActiveJob]);
  return <Orb state={orbState} size={size} />;
}
