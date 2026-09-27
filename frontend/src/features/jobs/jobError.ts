import type { TranslationKey } from "../../i18n/es-CL";

/** Backend failure codes grouped into operator-facing recovery language; the
 * raw code stays visible as a diagnostic tail, not as the message. */
export function jobErrorKey(code: string): TranslationKey {
  if (code.includes("cost_list") || code.includes("pricing_configuration"))
    return "jobs.fail.missingAuthority";
  if (code.endsWith("_not_found")) return "jobs.fail.notFound";
  if (code.includes("permission") || code.includes("access_denied")) return "jobs.fail.permission";
  if (code.startsWith("document_storage_")) return "jobs.fail.storage";
  if (code.includes("hash_mismatch") || code.includes("stale")) return "jobs.fail.stale";
  if (code === "ai_provider_quota") return "jobs.fail.providerQuota";
  if (code === "ai_provider_auth" || code === "ai_provider_rejected")
    return "jobs.fail.providerConfig";
  // Generic internal job failures (ai_job_failed, ingest handlers…) are ours,
  // not the provider's — saying "the provider didn't answer" sends users and
  // support chasing an outage that doesn't exist.
  if (code === "ai_job_failed" || code === "ai_context_error") return "jobs.fail.generic";
  if (
    code.startsWith("ai_") ||
    code.includes("provider") ||
    code.includes("timeout") ||
    code.includes("unavailable")
  )
    return "jobs.fail.provider";
  if (code.startsWith("invalid_") || code.endsWith("_invalid") || code.includes("required"))
    return "jobs.fail.invalid";
  return "jobs.fail.generic";
}
