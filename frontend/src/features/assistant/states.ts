import type { TranslationKey } from "../../i18n/es-CL";

/** AI job state → i18n key. Lives in its own module so the AppShell presence
 * chip can label jobs without pulling the lazily-chunked workspace page. */
export const STATE_LABELS: Record<string, TranslationKey> = {
  QUEUED: "aiws.state.queued",
  PLANNING: "aiws.state.planning",
  RUNNING: "aiws.state.running",
  WAITING_FOR_USER: "aiws.state.waitingUser",
  WAITING_FOR_APPROVAL: "aiws.state.waitingApproval",
  FAILED_RETRYABLE: "aiws.state.failedRetryable",
  FAILED: "aiws.state.failed",
  SUCCEEDED: "aiws.state.succeeded",
  CANCELED: "aiws.state.canceled",
};
