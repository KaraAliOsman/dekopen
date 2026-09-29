import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "../../api/apiMutator";
import { engineCalculate, engineSystems } from "../../api/generated/dekopen";
import type {
  EngineCalculateRequestRequest,
  EngineCalculateResponse,
  ProfileSystemSummary,
} from "../../api/generated/models";
import { type CanvasDesignInputs, type DimensionAxis, useCanvasStore } from "./canvasStore";
import { normalizeDimensionCandidate } from "./snapping";

type CalculationPhase = "idle" | "submitting" | "painting" | "rejected";

export type PendingPaintMeasurement = {
  sequence: number;
  startedAt: number;
  nominalWidthMm: string;
  nominalHeightMm: string;
};

export type CommitMeasurement = {
  sequence: number;
  durationMs: number;
};

type EngineCalculationController = {
  demoSystem: ProfileSystemSummary | null;
  result: EngineCalculateResponse | null;
  isInitialLoading: boolean;
  phase: CalculationPhase;
  fatalErrorCode: string | null;
  commitErrorCode: string | null;
  pendingPaint: PendingPaintMeasurement | null;
  lastMeasurement: CommitMeasurement | null;
  commitDimension(axis: DimensionAxis, candidate: string): Promise<boolean>;
  completePaint(sequence: number, paintedAt: number): void;
  clearCommitError(): void;
};

function errorCode(error: unknown, fallback: string): string {
  if (!(error instanceof ApiError) || typeof error.payload !== "object" || error.payload === null) {
    return fallback;
  }
  const payload = error.payload as { error?: { code?: unknown } };
  return typeof payload.error?.code === "string" ? payload.error.code : fallback;
}

export function requestFromInputs(inputs: CanvasDesignInputs): EngineCalculateRequestRequest {
  if (inputs.systemId === null) throw new Error("Engine system has not been resolved");
  return {
    system_id: inputs.systemId,
    nominal_width_mm: inputs.nominalWidthMm,
    nominal_height_mm: inputs.nominalHeightMm,
    color: inputs.color,
    parametric_tree: inputs.parametricTree,
  };
}

export function calculationKey(
  organizationId: string,
  inputs: CanvasDesignInputs,
): readonly unknown[] {
  return [
    "engine-calculation",
    organizationId,
    inputs.systemId,
    inputs.nominalWidthMm,
    inputs.nominalHeightMm,
    inputs.color,
    inputs.parametricTree,
  ] as const;
}

async function calculate(inputs: CanvasDesignInputs): Promise<EngineCalculateResponse> {
  const response = await engineCalculate(requestFromInputs(inputs), {
    signal: AbortSignal.timeout(30_000),
  });
  if (response.status !== 200) throw new Error("Generated client returned an unexpected status");
  return response.data;
}

export function useEngineCalculation(organizationId: string): EngineCalculationController {
  const queryClient = useQueryClient();
  const inputs = useCanvasStore((state) => state.inputs);
  const setSystemId = useCanvasStore((state) => state.setSystemId);
  const setDraftDimension = useCanvasStore((state) => state.setDraftDimension);
  const acceptDimension = useCanvasStore((state) => state.acceptDimension);
  const [phase, setPhase] = useState<CalculationPhase>("idle");
  const [commitErrorCode, setCommitErrorCode] = useState<string | null>(null);
  const [pendingPaint, setPendingPaint] = useState<PendingPaintMeasurement | null>(null);
  const [lastMeasurement, setLastMeasurement] = useState<CommitMeasurement | null>(null);
  const sequence = useRef(0);

  const systemsQuery = useQuery({
    queryKey: ["engine-systems", organizationId],
    queryFn: async () => {
      const response = await engineSystems({ signal: AbortSignal.timeout(15_000) });
      if (response.status !== 200) {
        throw new Error("Generated client returned an unexpected status");
      }
      return response.data.systems;
    },
    retry: 2,
    retryDelay: (attempt) => 500 * (attempt + 1),
    staleTime: Number.POSITIVE_INFINITY,
  });

  const demoSystems = useMemo(
    () =>
      systemsQuery.data?.filter((system) => system.code === "DEMO_60" && system.is_demo === true) ??
      [],
    [systemsQuery.data],
  );
  const demoSystem = demoSystems.length === 1 ? (demoSystems[0] ?? null) : null;

  useEffect(() => {
    if (demoSystem !== null && inputs.systemId !== demoSystem.id) setSystemId(demoSystem.id);
  }, [demoSystem, inputs.systemId, setSystemId]);

  const calculationQuery = useQuery({
    queryKey: calculationKey(organizationId, inputs),
    queryFn: () => calculate(inputs),
    enabled: demoSystem !== null && inputs.systemId === demoSystem.id,
    retry: 2,
    retryDelay: (attempt) => 500 * (attempt + 1),
    staleTime: Number.POSITIVE_INFINITY,
  });

  let fatalErrorCode: string | null = null;
  if (systemsQuery.isError) {
    fatalErrorCode = errorCode(systemsQuery.error, "system_discovery_failed");
  } else if (systemsQuery.isSuccess && demoSystems.length === 0) {
    fatalErrorCode = "demo_system_unavailable";
  } else if (systemsQuery.isSuccess && demoSystems.length > 1) {
    fatalErrorCode = "demo_system_ambiguous";
  } else if (calculationQuery.isError) {
    fatalErrorCode = errorCode(calculationQuery.error, "calculation_failed");
  }

  const commitDimension = useCallback(
    async (axis: DimensionAxis, candidate: string): Promise<boolean> => {
      const normalized = normalizeDimensionCandidate(candidate);
      if (
        normalized === null ||
        inputs.systemId === null ||
        demoSystem === null ||
        inputs.systemId !== demoSystem.id
      ) {
        setDraftDimension(null);
        setCommitErrorCode(normalized === null ? "invalid_dimension" : "demo_system_unavailable");
        setPhase("rejected");
        return false;
      }

      const candidateInputs: CanvasDesignInputs = {
        ...inputs,
        ...(axis === "width" ? { nominalWidthMm: normalized } : { nominalHeightMm: normalized }),
      };
      setCommitErrorCode(null);
      setPhase("submitting");
      const startedAt = performance.now();
      try {
        await queryClient.fetchQuery({
          queryKey: calculationKey(organizationId, candidateInputs),
          queryFn: () => calculate(candidateInputs),
          retry: false,
          staleTime: Number.POSITIVE_INFINITY,
        });
      } catch (caught) {
        setDraftDimension(null);
        setCommitErrorCode(errorCode(caught, "calculation_failed"));
        setPhase("rejected");
        return false;
      }

      const nextSequence = sequence.current + 1;
      sequence.current = nextSequence;
      acceptDimension(axis, normalized);
      setPendingPaint({
        sequence: nextSequence,
        startedAt,
        nominalWidthMm: candidateInputs.nominalWidthMm,
        nominalHeightMm: candidateInputs.nominalHeightMm,
      });
      setPhase("painting");
      return true;
    },
    [acceptDimension, demoSystem, inputs, organizationId, queryClient, setDraftDimension],
  );

  const completePaint = useCallback(
    (completedSequence: number, paintedAt: number): void => {
      if (pendingPaint === null || pendingPaint.sequence !== completedSequence) return;
      setLastMeasurement({
        sequence: completedSequence,
        durationMs: paintedAt - pendingPaint.startedAt,
      });
      setPendingPaint(null);
      setPhase("idle");
    },
    [pendingPaint],
  );

  return {
    demoSystem,
    result: calculationQuery.data ?? null,
    isInitialLoading:
      systemsQuery.isPending ||
      (demoSystem !== null && inputs.systemId === demoSystem.id && calculationQuery.isPending),
    phase,
    fatalErrorCode,
    commitErrorCode,
    pendingPaint,
    lastMeasurement,
    commitDimension,
    completePaint,
    clearCommitError() {
      setCommitErrorCode(null);
      if (phase === "rejected") setPhase("idle");
    },
  };
}
