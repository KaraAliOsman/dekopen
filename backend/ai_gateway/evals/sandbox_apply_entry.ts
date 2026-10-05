/** Punto de entrada del sandbox de evaluación IA1.
 *
 * Aplica una secuencia de design-ops sobre una copia del producto usando el
 * MISMO reducer que el canvas de la UI (`applyDesignOps` → `applyDesignOpOn`
 * → `ASSEMBLY_COMMANDS`). El arnés lo empaqueta con esbuild y lo ejecuta con
 * Node: lee {product, ops} de <in.json> y escribe {product} o {error} en
 * <out.json>. Nada persiste — es una copia descartable por caso.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { applyDesignOps } from "../../../frontend/src/features/canvas/designOps";
import { resolveMembers } from "../../../frontend/src/features/canvas/members";
import type { ProductJson } from "../../../frontend/src/features/canvas/productEditing";
import type { DesignOptions } from "../../../frontend/src/api/generated/models";

const [inputPath, outputPath] = process.argv.slice(2);
const payload = JSON.parse(readFileSync(inputPath, "utf8")) as {
  product: ProductJson;
  ops: unknown[];
  /** Geometría de miembros del sistema del caso (roles + caras mm) — la
   * misma que el canvas resuelve con resolveMembers: sin ella el reducer
   * no-opa las ops estructurales como hace la UI sin catálogo. */
  members?: {
    frame_mm?: string | number | null;
    sash_mm?: string | number | null;
    mullion_v_mm?: string | number | null;
    mullion_h_mm?: string | number | null;
    mullion_v_sku?: string | null;
    mullion_h_sku?: string | null;
  };
};
try {
  const m = payload.members ?? {};
  const options = {
    profiles: [
      { role: "FRAME", face_width_mm: m.frame_mm ?? 60 },
      { role: "SASH", face_width_mm: m.sash_mm ?? 72 },
      { role: "MULLION_V", face_width_mm: m.mullion_v_mm ?? 60, sku: m.mullion_v_sku },
      { role: "MULLION_H", face_width_mm: m.mullion_h_mm ?? 60, sku: m.mullion_h_sku },
    ],
  } as unknown as DesignOptions;
  const product = applyDesignOps(
    payload.product,
    payload.ops as never,
    undefined,
    resolveMembers(options),
  );
  writeFileSync(outputPath, JSON.stringify({ ok: true, product }));
} catch (error) {
  writeFileSync(outputPath, JSON.stringify({ ok: false, error: String(error) }));
}
