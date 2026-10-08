/** D07 del vano de obra a la medida de fabricación — helpers de cliente:
 * estado editable del registro del vano, el preview resuelto por el motor
 * y la cota doble del lienzo (vano + fabricación, con la holgura entre
 * ambas — el momento firma del encargo). */
import type {
  FabricationLockRequest,
  MeasurementResolveResponse,
  MeasurementResponse,
  PositionMeasurementRequest,
  VanoRecordRequest,
  WallTypeEnum,
} from "../../api/generated/models";
import type { VanoDim } from "../canvas/ProductFrontSvg";

/** El vano tal como lo escribe el medidor: 1–3 puntos por eje, muro,
 * escuadra/desplome y nota. Los puntos vacíos no se envían. */
export interface VanoDraft {
  widthPoints: string[];
  heightPoints: string[];
  wallType: WallTypeEnum | "";
  squareMm: string;
  plumbMm: string;
  notes: string;
  mountingRuleId: string;
  lockEnabled: boolean;
  lockWidthMm: string;
  lockHeightMm: string;
  lockReason: string;
}

export const EMPTY_VANO: VanoDraft = {
  widthPoints: [""],
  heightPoints: [""],
  wallType: "",
  squareMm: "",
  plumbMm: "",
  notes: "",
  mountingRuleId: "",
  lockEnabled: false,
  lockWidthMm: "",
  lockHeightMm: "",
  lockReason: "",
};

const MM = /^\d{0,8}(?:\.\d{0,2})?$/;

const points = (values: string[]): string[] | null => {
  const cleaned = values.map((value) => value.trim()).filter((value) => value !== "");
  if (cleaned.some((value) => !MM.test(value) || Number(value) <= 0)) return null;
  return cleaned;
};

/** ¿Hay registro del vano? Un punto con número o una fijación encendida.
 * Los campos de punto vacíos no cuentan — son la fila inicial sin tocar. */
export function vanoDraftHasContent(draft: VanoDraft): boolean {
  const widthPoints = points(draft.widthPoints);
  const heightPoints = points(draft.heightPoints);
  return (
    (widthPoints !== null && widthPoints.length > 0) ||
    (heightPoints !== null && heightPoints.length > 0) ||
    widthPoints === null || // un valor no-mm ya es contenido (inválido)
    heightPoints === null ||
    draft.lockEnabled ||
    draft.mountingRuleId !== "" ||
    draft.wallType !== "" ||
    draft.squareMm.trim() !== "" ||
    draft.plumbMm.trim() !== "" ||
    draft.notes.trim() !== ""
  );
}

/** Draft → payload del endpoint save/preview. `null` cuando no hay nada que
 * persistir, `"invalid"` cuando el borrador está incompleto (un eje sin el
 * otro, números no-mm, montaje sin vano). */
export function vanoDraftPayload(draft: VanoDraft): PositionMeasurementRequest | "invalid" | null {
  if (!vanoDraftHasContent(draft)) return null;
  const widthPoints = points(draft.widthPoints);
  const heightPoints = points(draft.heightPoints);
  const square = draft.squareMm.trim();
  const plumb = draft.plumbMm.trim();
  if (widthPoints === null || heightPoints === null) return "invalid";
  if (square !== "" && !MM.test(square)) return "invalid";
  if (plumb !== "" && !MM.test(plumb)) return "invalid";
  const hasVano = widthPoints.length > 0 && heightPoints.length > 0;
  if (widthPoints.length > 0 !== heightPoints.length > 0) return "invalid";
  if (draft.mountingRuleId !== "" && !hasVano) return "invalid";
  let fabricationLock: FabricationLockRequest | null = null;
  if (draft.lockEnabled) {
    const w = draft.lockWidthMm.trim();
    const h = draft.lockHeightMm.trim();
    if (!MM.test(w) || !MM.test(h) || Number(w) <= 0 || Number(h) <= 0) return "invalid";
    fabricationLock = { width_mm: w, height_mm: h };
    if (draft.lockReason.trim()) fabricationLock.reason = draft.lockReason.trim();
  }
  if (!hasVano && fabricationLock === null) return "invalid"; // solo nota/muro no es registro
  const vano: VanoRecordRequest | null = hasVano
    ? {
        width_points_mm: widthPoints,
        height_points_mm: heightPoints,
        ...(draft.wallType ? { wall_type: draft.wallType } : {}),
        ...(square ? { square_mm: square } : {}),
        ...(plumb ? { plumb_mm: plumb } : {}),
        ...(draft.notes.trim() ? { notes: draft.notes.trim() } : {}),
      }
    : null;
  return {
    vano,
    mounting_rule_id: draft.mountingRuleId || null,
    fabrication_lock: fabricationLock,
  };
}

/** La respuesta guardada → borrador para reabrir la sección. */
export function vanoDraftFromSaved(measurement: MeasurementResponse): VanoDraft {
  const record = measurement.vano;
  // El lock sellado viaja como JSONB libre — su forma es la del contrato.
  const lock = measurement.fabrication_lock as {
    width_mm?: string;
    height_mm?: string;
    reason?: string;
  } | null;
  return {
    widthPoints: record?.width_points_mm?.length ? [...record.width_points_mm] : [""],
    heightPoints: record?.height_points_mm?.length ? [...record.height_points_mm] : [""],
    wallType: (record?.wall_type ?? "") as WallTypeEnum | "",
    squareMm: record?.square_mm ?? "",
    plumbMm: record?.plumb_mm ?? "",
    notes: record?.notes ?? "",
    mountingRuleId: measurement.mounting_rule?.id ?? "",
    lockEnabled: lock !== null && lock !== undefined,
    lockWidthMm: lock?.width_mm ?? "",
    lockHeightMm: lock?.height_mm ?? "",
    lockReason: lock?.reason ?? "",
  };
}

/** Identidad estable del borrador — parte del chequeo «sin cambios». */
export function vanoIdentity(draft: VanoDraft): string {
  return JSON.stringify(vanoDraftPayload(draft) ?? null);
}

const SIDE_KEY: Record<string, keyof VanoDim["gap"]> = {
  top: "top",
  right: "right",
  bottom: "bottom",
  left: "left",
};

/** La resolución del motor → cota doble. `used` es la medida del vano que
 * mandó el cálculo; la fabricación se dibuja con sus cotas propias y el
 * vano toma el delta por lado con signo invertido (el desglose lleva el
 * ajuste fabricación−vano). */
export function vanoDimFromResolution(
  resolution: MeasurementResolveResponse["resolution"] | null,
  mountingLabel: string,
): VanoDim | null {
  if (!resolution || resolution.vano_width_mm === null || resolution.vano_height_mm === null)
    return null;
  const gap = { top: 0, right: 0, bottom: 0, left: 0 };
  for (const item of resolution.breakdown) {
    const side = SIDE_KEY[item.side];
    if (side) gap[side] = -Number(item.mm);
  }
  return {
    widthMm: Number(resolution.used_width_mm),
    heightMm: Number(resolution.used_height_mm),
    gap,
    mountingLabel,
  };
}
