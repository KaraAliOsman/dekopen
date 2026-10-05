import { ApiError } from "../../api/apiMutator";
import {
  positionsCreate,
  positionsDestroy,
  positionsRetrieve,
  positionsUpdate,
  projectDesignOptions,
} from "../../api/generated/dekopen";
import type { DesignOptions } from "../../api/generated/models/designOptions";
import type { PositionDesignRequest } from "../../api/generated/models/positionDesignRequest";
import type { PositionResponse } from "../../api/generated/models/positionResponse";
import type { DesignOp } from "../commands/types";
import { wrapTreeAsProduct } from "../canvas/productEditing";
import type { Opening } from "../canvas/intentEditing";
import type { IntentNode } from "../canvas/intentEditing";

/** IA2 — ops que no mutan el producto del canvas: campos de la posición
 * (sistema, acabado, ubicación, cantidad) y ops de lista de posiciones del
 * proyecto (crear, duplicar, quitar, actualizar). El resto son ops de
 * producto que el canvas aplica con applyDesignOps — mismo registro. */
export const POSITION_FIELD_OPS = new Set([
  "set_system",
  "set_finish",
  "set_location",
  "set_quantity",
]);
export const PROJECT_OPS = new Set([
  "add_position",
  "duplicate_position",
  "remove_position",
  "update_position",
]);
/** apply_to_positions se materializa como paso "batch_ops" (su propio
 * contrato) — nunca llega dentro del arreglo ops del paso "ops". */
const NON_PRODUCT_OPS = new Set([...POSITION_FIELD_OPS, ...PROJECT_OPS]);

export function isProductOp(op: DesignOp): boolean {
  return !NON_PRODUCT_OPS.has(op.op);
}

export function splitOps(ops: DesignOp[]): {
  product: DesignOp[];
  position: DesignOp[];
  project: DesignOp[];
} {
  return {
    product: ops.filter((op) => !NON_PRODUCT_OPS.has(op.op)),
    position: ops.filter((op) => POSITION_FIELD_OPS.has(op.op)),
    project: ops.filter((op) => PROJECT_OPS.has(op.op)),
  };
}

type Headers = { headers: { "X-Organization-ID": string } };

export interface OpOutcome {
  applied: DesignOp[];
  failed: { op: DesignOp; error: string }[];
}

function errorDetail(error: unknown, fallback: string): string {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload !== null) {
    const detail = (error.payload as { error?: { detail?: unknown } }).error?.detail;
    if (typeof detail === "string" && detail) return detail;
  }
  return error instanceof Error ? error.message : fallback;
}

/** Merge de los campos de posición sobre la fila actual — el PUT exige el
 * diseño completo y la marca de concurrencia, así que siempre leemos antes
 * de escribir. */
async function patchPosition(
  positionId: string,
  patch: {
    location_tag?: string;
    quantity?: number;
    system_id?: string;
    color?: string;
  },
  headers: Headers,
): Promise<void> {
  const detail = await positionsRetrieve(positionId, headers);
  if (detail.status !== 200) throw new ApiError(detail.status, detail.data);
  const current = detail.data as PositionResponse;
  const design: PositionDesignRequest = {
    ...(current.design as PositionDesignRequest),
    ...(patch.system_id !== undefined ? { system_id: patch.system_id } : {}),
    ...(patch.color !== undefined ? { color: patch.color } : {}),
  };
  const response = await positionsUpdate(
    positionId,
    {
      location_tag: patch.location_tag ?? current.location_tag ?? "",
      quantity: patch.quantity ?? current.quantity,
      design,
      expected_updated_at: current.updated_at,
    },
    headers,
  );
  if (response.status !== 200) throw new ApiError(response.status, response.data);
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function int(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

/** Ops de campo sobre UNA posición (la del contexto vivo). */
export async function applyPositionOps(
  ops: DesignOp[],
  positionId: string,
  headers: Headers,
): Promise<OpOutcome> {
  const outcome: OpOutcome = { applied: [], failed: [] };
  const patch: Parameters<typeof patchPosition>[1] = {};
  const applied: DesignOp[] = [];
  for (const op of ops) {
    if (op.op === "set_system" && text(op.system_id)) {
      patch.system_id = text(op.system_id)!;
      applied.push(op);
    } else if (op.op === "set_finish" && text(op.color)) {
      patch.color = text(op.color)!;
      applied.push(op);
    } else if (op.op === "set_location" && typeof op.location === "string") {
      patch.location_tag = op.location;
      applied.push(op);
    } else if (op.op === "set_quantity" && int(op.count) !== null) {
      patch.quantity = int(op.count)!;
      applied.push(op);
    } else {
      outcome.failed.push({ op, error: "parametros_invalidos" });
    }
  }
  if (!applied.length) return outcome;
  try {
    await patchPosition(positionId, patch, headers);
    outcome.applied.push(...applied);
  } catch (error) {
    for (const op of applied) {
      outcome.failed.push({ op, error: errorDetail(error, "update_failed") });
    }
  }
  return outcome;
}

function starterDesign(
  widthMm: string,
  heightMm: string,
  opening: string | null,
  systemId: string,
  color: string,
  options: DesignOptions,
): PositionDesignRequest {
  const tree: IntentNode = {
    id: crypto.randomUUID(),
    type: "BAY",
    opening_type: (opening ?? "FIXED") as Opening,
  };
  // Mismo autollenado del editor: un vidrio sólo se declara cuando la serie
  // ofrece exactamente una opción — nunca un SKU o espesor inventado.
  const glassThickness =
    options.glazing_thicknesses.length === 1 ? options.glazing_thicknesses[0] : undefined;
  const glassSku = options.glass_skus.length === 1 ? options.glass_skus[0] : undefined;
  if (glassThickness !== undefined) {
    tree.glass_thickness_mm = glassThickness;
    tree.glass_spec = glassThickness;
  }
  if (glassSku !== undefined && tree.glass_thickness_mm) {
    tree.glass_article_sku = glassSku;
  }
  return {
    system_id: systemId,
    nominal_width_mm: widthMm,
    nominal_height_mm: heightMm,
    color,
    parametric_tree: wrapTreeAsProduct(tree, widthMm, heightMm),
  };
}

/** Ops de lista de posiciones — cada una corre por su endpoint real, como
 * lo haría la UI (nada de atajos por debajo del contrato). */
export async function applyProjectOps(
  ops: DesignOp[],
  args: {
    projectId: string;
    /** Defaults honestos para add_position sin system/acabado: la posición
     * del contexto vivo (cuando hay una). */
    fallbackPositionId?: string | null;
  },
  headers: Headers,
): Promise<OpOutcome> {
  const outcome: OpOutcome = { applied: [], failed: [] };
  for (const op of ops) {
    try {
      if (op.op === "update_position") {
        const positionId = text(op.position_id);
        if (!positionId) throw new Error("position_id_invalido");
        const patch: Parameters<typeof patchPosition>[1] = {};
        if (typeof op.location === "string") patch.location_tag = op.location;
        if (int(op.quantity) !== null) patch.quantity = int(op.quantity)!;
        if (text(op.system_id)) patch.system_id = text(op.system_id)!;
        if (text(op.finish)) patch.color = text(op.finish)!;
        await patchPosition(positionId, patch, headers);
      } else if (op.op === "remove_position") {
        const positionId = text(op.position_id);
        if (!positionId) throw new Error("position_id_invalido");
        const detail = await positionsRetrieve(positionId, headers);
        if (detail.status !== 200) throw new ApiError(detail.status, detail.data);
        const response = await positionsDestroy(
          positionId,
          { expected_updated_at: (detail.data as PositionResponse).updated_at },
          headers,
        );
        if (response.status !== 204) throw new ApiError(response.status, response.data);
      } else if (op.op === "duplicate_position") {
        const positionId = text(op.position_id);
        if (!positionId) throw new Error("position_id_invalido");
        const detail = await positionsRetrieve(positionId, headers);
        if (detail.status !== 200) throw new ApiError(detail.status, detail.data);
        const current = detail.data as PositionResponse;
        const copies = int(op.count) ?? 1;
        for (let i = 0; i < copies; i += 1) {
          const response = await positionsCreate(
            args.projectId,
            {
              location_tag: current.location_tag ?? "",
              quantity: current.quantity,
              design: current.design as PositionDesignRequest,
            },
            headers,
          );
          if (response.status !== 201) throw new ApiError(response.status, response.data);
        }
      } else if (op.op === "add_position") {
        const width = text(op.width_mm);
        const height = text(op.height_mm);
        if (!width || !height) throw new Error("dimensiones_invalidas");
        let systemId = text(op.system_id);
        let color: string | null = null;
        // Sin sistema explícito, el de la posición viva — misma familia de
        // catálogo, ningún valor inventado.
        if (!systemId && args.fallbackPositionId) {
          const fallback = await positionsRetrieve(args.fallbackPositionId, headers);
          if (fallback.status === 200) {
            const design = (fallback.data as PositionResponse).design as PositionDesignRequest;
            systemId = design.system_id;
            color = design.color;
          }
        }
        if (!systemId) throw new Error("sistema_requerido");
        const options = await projectDesignOptions(systemId, headers);
        if (options.status !== 200) throw new ApiError(options.status, options.data);
        if (!color) {
          color = options.data.colors?.[0] ?? null;
        }
        if (!color) throw new Error("acabado_requerido");
        const response = await positionsCreate(
          args.projectId,
          {
            location_tag: typeof op.location === "string" ? op.location : "",
            quantity: int(op.quantity) ?? 1,
            design: starterDesign(width, height, text(op.opening), systemId, color, options.data),
          },
          headers,
        );
        if (response.status !== 201) throw new ApiError(response.status, response.data);
      } else {
        throw new Error("operacion_desconocida");
      }
      outcome.applied.push(op);
    } catch (error) {
      outcome.failed.push({ op, error: errorDetail(error, "op_failed") });
    }
  }
  return outcome;
}
