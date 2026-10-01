import { ApiError } from "../api/apiMutator";

/** Contract errors carry actionable detail (e.g. `sii_caf_exhausted` tells
 * the operator to load a CAF, `pricing_rules_not_found` names the missing
 * authority) — surface it instead of the generic toast. */
export function actionErrorDetail(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    const payload = error.payload as { error?: { detail?: unknown } } | null;
    const detail = payload?.error?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}
