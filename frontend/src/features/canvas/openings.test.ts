import { describe, expect, it } from "vitest";

import type { OpeningOption } from "../../api/generated/models";
import { openingOptionAdmitted, OPENING_OPTIONS } from "./openings";

function option(key: string, unitKind = "WINDOW"): OpeningOption {
  return { key, name: key, unit_kind: unitKind };
}

describe("openingOptionAdmitted — el catálogo manda (D03)", () => {
  it("sistema sin corredera: ninguna opción SLIDING se admite", () => {
    const options = [option("TURN"), option("TILT_TURN"), option("FIXED")];
    const slidingChoices = OPENING_OPTIONS.map(([value]) => value).filter((value) =>
      value.startsWith("SLIDING"),
    );
    expect(slidingChoices.length).toBeGreaterThanOrEqual(4);
    for (const choice of slidingChoices) {
      expect(openingOptionAdmitted(choice, options)).toBe(false);
    }
  });

  it("SLIDE admite las correderas, incluida la forma PRESET", () => {
    const options = [option("SLIDE")];
    expect(openingOptionAdmitted("SLIDING_2L", options)).toBe(true);
    expect(openingOptionAdmitted("SLIDING", options)).toBe(true);
    expect(openingOptionAdmitted("TURN_LEFT", options)).toBe(false);
  });

  it("DOOR_ENTRY exige una hoja de puerta hacia adentro", () => {
    const door = option("DOOR:PRIMARY:TURN:LEFT:INWARD", "DOOR");
    expect(openingOptionAdmitted("DOOR_ENTRY", [door])).toBe(true);
    expect(
      openingOptionAdmitted("DOOR_ENTRY", [option("DOOR:PRIMARY:TURN:LEFT:OUTWARD", "DOOR")]),
    ).toBe(false);
  });

  it("opciones sin cargar (undefined) no ocultan nada", () => {
    for (const [choice] of OPENING_OPTIONS) {
      expect(openingOptionAdmitted(choice, undefined)).toBe(true);
    }
  });
});
