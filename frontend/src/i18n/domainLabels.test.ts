/** Exhaustividad de etiquetas — cada enum del API tiene una entrada en
 * DOMAIN_LABELS cubriendo TODOS sus valores, o está declarado interno en
 * ENUM_INTERNAL. Un enum nuevo sin etiquetas rompe este test: la interfaz
 * no puede mostrar un token crudo sin que alguien lo nombre. */
import { describe, expect, it } from "vitest";

import * as models from "../api/generated/models";
import { DOMAIN_LABELS, ENUM_INTERNAL, domainLabel } from "./domainLabels";

const exportedEnums = Object.entries(models).filter(
  ([name, value]) =>
    name.endsWith("Enum") && value !== null && typeof value === "object" && !Array.isArray(value),
) as [string, Record<string, string>][];

describe("domainLabels", () => {
  it("cada enum del API tiene etiqueta o está declarado interno", () => {
    const uncovered: string[] = [];
    for (const [name, values] of exportedEnums) {
      const vals = Object.values(values);
      if (vals.length === 0) continue; // enums vacíos del generador
      if (ENUM_INTERNAL.includes(name)) continue;
      if (!DOMAIN_LABELS[name]) uncovered.push(name);
    }
    expect(uncovered, `enums sin DOMAIN_LABELS ni ENUM_INTERNAL:\n${uncovered.join("\n")}`).toEqual(
      [],
    );
  });

  it("cada valor de enum tiene etiqueta en español", () => {
    const missing: string[] = [];
    for (const [name, values] of exportedEnums) {
      const labels = DOMAIN_LABELS[name];
      if (!labels) continue;
      for (const value of Object.values(values)) {
        const found = labels[value];
        // PVC→«PVC» y mm→«mm» son legítimos: la etiqueta en español ES el
        // token cuando el token ya es el nombre de dominio.
        if (!found || !found.label) {
          missing.push(`${name}.${value}`);
        }
      }
    }
    expect(missing, `valores sin etiqueta:\n${missing.join("\n")}`).toEqual([]);
  });

  it("no hay etiquetas huérfanas para valores que ya no existen", () => {
    const orphans: string[] = [];
    const byName = new Map(exportedEnums);
    for (const [name, labels] of Object.entries(DOMAIN_LABELS)) {
      const enumValues = byName.get(name);
      if (!enumValues) {
        orphans.push(`${name} (enum inexistente)`);
        continue;
      }
      for (const key of Object.keys(labels)) {
        if (!(key in enumValues)) orphans.push(`${name}.${key}`);
      }
    }
    expect(orphans, `etiquetas sin enum:\n${orphans.join("\n")}`).toEqual([]);
  });

  it("domainLabel devuelve tono desconocido ante un valor sin etiqueta", () => {
    const label = domainLabel("ProjectResponseStatusEnum", "SOME_FUTURE_STATE");
    expect(label.tone).toBe("unknown");
    expect(label.label).toBe("SOME_FUTURE_STATE");
  });
});
