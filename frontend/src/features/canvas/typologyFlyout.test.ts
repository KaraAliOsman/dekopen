import { describe, expect, it } from "vitest";

import type { OpeningOption } from "../../api/generated/models";
import { STARTER_DEFINITIONS } from "./designLibrary";
import { openingSpecKeyAdmitted } from "./openings";
import { starterAdmittingSystems, starterCompatible } from "./TypologyFlyout";

function option(key: string, unit_kind = "WINDOW"): OpeningOption {
  return { key, name: key, unit_kind } as OpeningOption;
}

const starter = (key: string) => STARTER_DEFINITIONS.find((d) => d.key === key)!;

/** The DEMO_60 repertoire — casement classics, nothing advanced. */
const demo60Options: OpeningOption[] = [
  option("PRIMARY:FIXED"),
  option("PRIMARY:FIXED_SASH"),
  option("PRIMARY:TURN:LEFT:INWARD"),
  option("PRIMARY:TURN:RIGHT:INWARD"),
  option("PRIMARY:TILT_TURN:LEFT:INWARD"),
  option("PRIMARY:TILT_TURN:RIGHT:INWARD"),
];

const elevacionOptions: OpeningOption[] = [
  ...demo60Options,
  option("PRIMARY:LIFT_SLIDE"),
  option("DOOR:PRIMARY:LIFT_SLIDE", "DOOR"),
];

const plegableOptions: OpeningOption[] = [
  ...demo60Options,
  option("L1:FOLD:LEFT:INWARD:ACTIVE|L2:FOLD:LEFT:INWARD:PASSIVE|L3:FOLD:LEFT:INWARD:PASSIVE"),
];

const pivotanteOptions: OpeningOption[] = [
  ...demo60Options,
  option("DOOR:PRIMARY:PIVOT_V", "DOOR"),
];

const guillotinaOptions: OpeningOption[] = [
  ...demo60Options,
  option("TOP:FIXED|BOTTOM:VERTICAL_SLIDE"),
];

const puertaCorrederaOptions: OpeningOption[] = [
  ...demo60Options,
  option("DOOR:PRIMARY:SLIDE", "DOOR"),
];

describe("starterCompatible — tipologías avanzadas solo donde el catálogo las declara (D08)", () => {
  it("ofrece corredera elevable solo en series que emiten PRIMARY:LIFT_SLIDE", () => {
    expect(starterCompatible(starter("hst"), elevacionOptions)).toBe(true);
    expect(starterCompatible(starter("hst"), demo60Options)).toBe(false);
  });

  it("ofrece osciloparalela solo en series que emiten PRIMARY:PARALLEL_SLIDE", () => {
    expect(starterCompatible(starter("psk"), [option("PRIMARY:PARALLEL_SLIDE")])).toBe(true);
    expect(starterCompatible(starter("psk"), demo60Options)).toBe(false);
  });

  it("ofrece plegable solo cuando la serie emite la composición 3+0 con hoja de paso", () => {
    expect(starterCompatible(starter("foldable"), plegableOptions)).toBe(true);
    // Una capacidad FOLD sin hoja de paso emite el paquete all-PASSIVE — no
    // la composición del starter.
    expect(
      starterCompatible(starter("foldable"), [
        option(
          "L1:FOLD:LEFT:INWARD:PASSIVE|L2:FOLD:LEFT:INWARD:PASSIVE|L3:FOLD:LEFT:INWARD:PASSIVE",
        ),
      ]),
    ).toBe(false);
    expect(starterCompatible(starter("foldable"), demo60Options)).toBe(false);
  });

  it("ofrece puerta pivotante solo en series que emiten DOOR:PRIMARY:PIVOT_V", () => {
    expect(starterCompatible(starter("pivot"), pivotanteOptions)).toBe(true);
    expect(starterCompatible(starter("pivot"), demo60Options)).toBe(false);
  });

  it("ofrece guillotina solo cuando la serie emite el esquema fijo+corredera", () => {
    expect(starterCompatible(starter("guillotina"), guillotinaOptions)).toBe(true);
    // La guillotina doble no habilita la simple: la composición es otra.
    expect(
      starterCompatible(starter("guillotina"), [
        option("TOP:VERTICAL_SLIDE|BOTTOM:VERTICAL_SLIDE"),
      ]),
    ).toBe(false);
    expect(starterCompatible(starter("guillotina"), demo60Options)).toBe(false);
  });

  it("ofrece puerta corredera solo en series con hoja SLIDE en unidad DOOR", () => {
    expect(starterCompatible(starter("slidingDoor"), puertaCorrederaOptions)).toBe(true);
    expect(starterCompatible(starter("slidingDoor"), demo60Options)).toBe(false);
  });

  it("catálogo indefinido (cargando) muestra todo — nunca bloquea de más", () => {
    for (const key of ["hst", "psk", "foldable", "pivot", "guillotina", "slidingDoor"]) {
      expect(starterCompatible(starter(key), undefined)).toBe(true);
    }
  });

  it("los starters clásicos siguen resolviendo por enum", () => {
    expect(starterCompatible(starter("fixed"), demo60Options)).toBe(true);
    expect(starterCompatible(starter("sash"), demo60Options)).toBe(true);
    expect(starterCompatible(starter("sliding2"), [option("PRIMARY:SLIDE")])).toBe(true);
  });
});

describe("starterAdmittingSystems — §8: qué series la admiten (idea obligatoria)", () => {
  const systems = [
    { name: "DEMO 60 practicable", openingOptions: demo60Options },
    { name: "DEMO Elevación 90", openingOptions: elevacionOptions },
    { name: "DEMO Plegable 70", openingOptions: plegableOptions },
    { name: "DEMO Pivotante 120", openingOptions: pivotanteOptions },
    { name: "DEMO Guillotina 60", openingOptions: guillotinaOptions },
    { name: "DEMO Puerta Corredera 70", openingOptions: puertaCorrederaOptions },
  ];

  it("lista solo las series cuyo catálogo emite la composición", () => {
    expect(starterAdmittingSystems(starter("hst"), systems)).toEqual(["DEMO Elevación 90"]);
    expect(starterAdmittingSystems(starter("foldable"), systems)).toEqual(["DEMO Plegable 70"]);
    expect(starterAdmittingSystems(starter("pivot"), systems)).toEqual(["DEMO Pivotante 120"]);
    expect(starterAdmittingSystems(starter("guillotina"), systems)).toEqual(["DEMO Guillotina 60"]);
    expect(starterAdmittingSystems(starter("slidingDoor"), systems)).toEqual([
      "DEMO Puerta Corredera 70",
    ]);
  });

  it("devuelve vacío cuando ninguna serie la declara — nunca inventa", () => {
    expect(starterAdmittingSystems(starter("psk"), systems)).toEqual([]);
    expect(starterAdmittingSystems(starter("hst"), [systems[0]!])).toEqual([]);
  });
});

describe("openingSpecKeyAdmitted", () => {
  it("membership exacta sobre la clave emitida", () => {
    expect(openingSpecKeyAdmitted("PRIMARY:LIFT_SLIDE", elevacionOptions)).toBe(true);
    expect(openingSpecKeyAdmitted("PRIMARY:LIFT_SLIDE", demo60Options)).toBe(false);
    expect(openingSpecKeyAdmitted("PRIMARY:LIFT_SLIDE", undefined)).toBe(true);
  });
});
