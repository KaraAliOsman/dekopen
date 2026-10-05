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
import type { ProductJson } from "../../../frontend/src/features/canvas/productEditing";

const [inputPath, outputPath] = process.argv.slice(2);
const payload = JSON.parse(readFileSync(inputPath, "utf8")) as {
  product: ProductJson;
  ops: unknown[];
};
try {
  const product = applyDesignOps(payload.product, payload.ops as never);
  writeFileSync(outputPath, JSON.stringify({ ok: true, product }));
} catch (error) {
  writeFileSync(outputPath, JSON.stringify({ ok: false, error: String(error) }));
}
