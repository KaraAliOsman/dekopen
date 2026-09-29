import type { CanvasDesignInputs } from "../canvas/canvasStore";

/** Unsaved-position draft buffer. A reload used to silently discard the
 * in-flight design — the draft survives in sessionStorage (same-tab scoped,
 * which is exactly the lifetime of an accidental refresh) and is offered
 * back as an explicit restore choice on the next open. */

const PREFIX = "dekopen:position-draft:";

export interface PositionDraft {
  inputs: CanvasDesignInputs;
  location: string;
  quantity: string;
  savedAt: number;
}

export function positionDraftKey(
  orgId: string,
  positionId: string | null,
  copyId: string | null,
): string {
  return `${PREFIX}${orgId}:${positionId ?? copyId ?? "new"}`;
}

export function readPositionDraft(key: string): PositionDraft | null {
  try {
    const raw = sessionStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PositionDraft;
    if (typeof parsed.savedAt !== "number" || typeof parsed.inputs !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writePositionDraft(key: string, draft: PositionDraft): void {
  try {
    sessionStorage.setItem(key, JSON.stringify(draft));
  } catch {
    // Quota/denied storage — the draft is best-effort, never a blocker.
  }
}

export function clearPositionDraft(key: string): void {
  try {
    sessionStorage.removeItem(key);
  } catch {
    /* best-effort */
  }
}
