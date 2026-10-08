import type { ProjectResponse } from "../../api/generated/models";
import type { TranslationKey } from "../../i18n/es-CL";

/** Metadata fields shared by the create/edit form and the readout in the
 * Cotización tab — keep order and labels in one place so the editable form
 * and the `project-fact-*` anchors never drift apart. */
export const fields = [
  ["name", "projects.name", "text", 255],
  ["client_name", "projects.client", "text", 255],
  ["client_rut", "projects.rut", "text", 50],
  ["client_email", "projects.email", "email", undefined],
  ["client_phone", "projects.phone", "tel", 50],
  ["client_giro", "projects.clientGiro", "text", 80],
  ["client_comuna", "projects.clientComuna", "text", 20],
  ["client_address", "projects.clientAddress", "text", 70],
  ["delivery_address", "projects.address", "textarea", undefined],
  ["notes_commercial", "projects.commercialNotes", "textarea", undefined],
  ["notes_internal", "projects.internalNotes", "textarea", undefined],
] as const satisfies readonly [
  keyof ProjectResponse,
  TranslationKey,
  "text" | "email" | "tel" | "textarea",
  number | undefined,
][];

export const statuses: Record<ProjectResponse["status"], TranslationKey> = {
  DRAFT: "projects.draft",
  QUOTED: "projects.quoted",
  APPROVED: "projects.approved",
  IN_PRODUCTION: "projects.production",
  COMPLETED: "projects.completed",
  CANCELLED: "projects.cancelled",
};

/** Status-only next step for the list row — the list payload has no
 * payments/approvals, so this stays a coarse hint; the hub header runs the
 * full `projectNextAction` once those queries exist. */
export const listNextKeys: Record<ProjectResponse["status"], TranslationKey> = {
  DRAFT: "projects.nextDraft",
  QUOTED: "projects.nextQuoted",
  APPROVED: "projects.nextApproved",
  IN_PRODUCTION: "projects.nextInProduction",
  COMPLETED: "projects.nextCompleted",
  CANCELLED: "projects.nextCancelled",
};
