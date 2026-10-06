/** Etiqueta + tono del ciclo de vida de una importación de catálogo —
 * compartido por el panel de catálogos y el de proyectos (el valor llega
 * como string suelto, no como enum orval). */
import type { TranslationKey } from "../../i18n/es-CL";

export const IMPORT_STATUS_LABEL: Record<string, TranslationKey> = {
  UPLOADED: "projects.importsStatusUploaded",
  EXTRACTING: "projects.importsStatusExtracting",
  REVIEW_READY: "projects.importsStatusReviewReady",
  CONFIRMED: "projects.importsStatusConfirmed",
  FAILED: "projects.importsStatusFailed",
};

export const IMPORT_STATUS_TONE: Record<string, string> = {
  UPLOADED: "neutral",
  EXTRACTING: "info",
  REVIEW_READY: "warn",
  CONFIRMED: "ok",
  FAILED: "danger",
};

export const IMPORT_CONFIDENCE_LABEL: Record<string, TranslationKey> = {
  VERIFIED_STRUCTURED: "catalog.importsConfidenceVerified",
  HIGH_CANDIDATE: "catalog.importsConfidenceCandidate",
  REVIEW_REQUIRED: "catalog.importsConfidenceReview",
  LOW: "catalog.importsConfidenceLow",
  ERROR: "catalog.importsConfidenceError",
};

export const IMPORT_CONFIDENCE_TONE: Record<string, string> = {
  VERIFIED_STRUCTURED: "ok",
  HIGH_CANDIDATE: "info",
  REVIEW_REQUIRED: "warn",
  LOW: "neutral",
  ERROR: "danger",
};
