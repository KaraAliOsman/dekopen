import type { PositionDesignRequest } from "../../api/generated/models/positionDesignRequest";
import { elevationEnvelopeMm, isSingleUnit, type ProductJson } from "../canvas/productEditing";

/** La forma de payload que el flujo Guardar del editor persiste: una unidad
 * suelta se guarda en la forma clásica documental, los ensambles reales como
 * product-v2 — la compuerta del motor (calculate_design / positions_update /
 * design_batch_preview) exige exactamente esta proyección. */
export function designFromProduct(
  product: ProductJson,
  systemId: string,
  color: PositionDesignRequest["color"],
): PositionDesignRequest {
  const single = isSingleUnit(product) ? product.assembly.modules[0] : undefined;
  const envelope = elevationEnvelopeMm(product);
  return single !== undefined
    ? {
        system_id: systemId,
        nominal_width_mm: single.width_mm,
        nominal_height_mm: single.height_mm,
        color,
        parametric_tree: single.tree,
      }
    : {
        system_id: systemId,
        nominal_width_mm: envelope.width.toFixed(2),
        nominal_height_mm: envelope.height.toFixed(2),
        color,
        parametric_tree: product,
      };
}
