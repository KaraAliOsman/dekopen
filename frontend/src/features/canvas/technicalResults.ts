import type { EngineCalculateResponse } from "../../api/generated/models";
import { fmtMm } from "../../format";

export type CanvasTechnicalValues = {
  frame: string;
  reinforcement: string;
  glass: string;
  glazingBead: string;
};

function uniqueLengths(lengths: string[]): string[] {
  return lengths.filter((length, index) => lengths.indexOf(length) === index);
}

function dimensions(lengths: string[]): string {
  if (lengths.length === 0) throw new Error("Engine response is missing a required result");
  return `${uniqueLengths(lengths).map(fmtMm).join(" × ")} mm`;
}

export function selectCanvasTechnicalValues(
  response: EngineCalculateResponse,
): CanvasTechnicalValues {
  const glass = response.glasses[0];
  if (glass === undefined) throw new Error("Engine response is missing glass");

  return {
    frame: dimensions(
      response.profile_cuts.filter((cut) => cut.role === "FRAME").map((cut) => cut.length_mm),
    ),
    reinforcement: dimensions(
      response.reinforcements
        .filter((piece) => piece.role === "FRAME")
        .map((piece) => piece.length_mm),
    ),
    glass: `${fmtMm(glass.width_mm)} × ${fmtMm(glass.height_mm)} mm`,
    glazingBead: dimensions(
      response.profile_cuts
        .filter((cut) => cut.role === "GLAZING_BEAD")
        .map((cut) => cut.length_mm),
    ),
  };
}
