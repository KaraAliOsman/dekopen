import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/apiMutator";
import {
  projectPaymentIntegrationStatus,
  projectPaymentLinkCreate,
  projectPaymentLinkRecover,
  projectPaymentLinksList,
} from "../../api/generated/dekopen";
import type {
  PaymentKindEnum,
  PaymentLink,
  PaymentLinkStatusEnum,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { formatMoney } from "../../format";

const KIND_LABEL: Record<string, TranslationKey> = {
  ANTICIPO: "projects.paymentKindAnticipo",
  PARCIAL: "projects.paymentKindParcial",
  SALDO: "projects.paymentKindSaldo",
};
const LINK_STATUS_LABEL: Record<PaymentLinkStatusEnum, TranslationKey> = {
  DISPATCHING: "projects.paymentLinkStatusDispatching",
  PENDING: "projects.paymentLinkStatusPending",
  PAID: "projects.paymentLinkStatusPaid",
  FAILED: "projects.paymentLinkStatusFailed",
  UNCERTAIN: "projects.paymentLinkStatusUncertain",
  CANCELLED: "projects.paymentLinkStatusCancelled",
};

function formatClp(value: string): string {
  return formatMoney(value, "CLP");
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("es-CL", { dateStyle: "medium" }).format(new Date(value));
}

export function ProjectPaymentLinksPanel({
  projectId,
  orgId,
  canWrite,
  isOwner = false,
  onChanged,
  onDirtyChange,
}: {
  projectId: string;
  orgId: string;
  canWrite: boolean;
  isOwner?: boolean;
  onChanged: () => void;
  onDirtyChange?: (dirty: boolean) => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  // Dedupe under react-query: StrictMode double-mounts and the cobranza
  // summary were each re-firing this list.
  const linksKey = ["projects", "payment-links", orgId, projectId] as const;
  const linksQuery = useQuery<PaymentLink[]>({
    queryKey: linksKey,
    queryFn: async ({ signal }) => {
      const response = await projectPaymentLinksList(projectId, {
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data.links;
    },
  });
  const links = linksQuery.data ?? [];
  const setLinks = (updater: (previous: PaymentLink[]) => PaymentLink[]) =>
    queryClient.setQueryData(linksKey, updater(linksQuery.data ?? []));
  // Integration status is write-scoped — readers (e.g. taller) only need the
  // links list; fetching it would 403 for them.
  const integrationQuery = useQuery({
    queryKey: ["projects", "payment-integration", orgId],
    enabled: canWrite,
    queryFn: async ({ signal }) => {
      const response = await projectPaymentIntegrationStatus({
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
    // An absent/unconfigured provider only hides the hint — never fails the list.
    retry: false,
  });
  const integration = integrationQuery.data ?? null;
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [kind, setKind] = useState<PaymentKindEnum>("ANTICIPO");
  const [amount, setAmount] = useState("");
  const [payerEmail, setPayerEmail] = useState("");
  const [subject, setSubject] = useState("");
  const [baseline, setBaseline] = useState(kind);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const generation = useRef(0);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );

  useEffect(() => {
    if (linksQuery.isError) setMessage(t("projects.paymentLinksLoadError"));
  }, [linksQuery.isError]);

  const formDirty =
    showForm &&
    (kind !== baseline ||
      amount.trim() !== "" ||
      payerEmail.trim() !== "" ||
      subject.trim() !== "");
  useEffect(() => {
    onDirtyChange?.(formDirty);
  }, [formDirty, onDirtyChange]);

  async function create(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      const response = await projectPaymentLinkCreate(
        projectId,
        {
          operation_key: crypto.randomUUID(),
          kind,
          amount: amount.replace(",", "."),
          payer_email: payerEmail.trim(),
          ...(subject.trim() ? { subject: subject.trim() } : {}),
        },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      setLinks((previous) => [response.data.link, ...previous]);
      setShowForm(false);
      setAmount("");
      setPayerEmail("");
      setSubject("");
    } catch {
      setMessage(t("projects.paymentLinkCreateError"));
    } finally {
      setBusy(false);
    }
  }

  async function copy(link: PaymentLink): Promise<void> {
    if (!link.url) return;
    try {
      await navigator.clipboard.writeText(link.url);
      setCopiedId(link.id);
    } catch {
      setMessage(t("projects.paymentLinkCopyError"));
    }
  }

  async function recover(link: PaymentLink): Promise<void> {
    setBusy(true);
    setMessage("");
    try {
      const response = await projectPaymentLinkRecover(projectId, link.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setLinks((previous) =>
        previous.map((item) => (item.id === link.id ? response.data.link : item)),
      );
      if (response.data.link.status === "PAID") onChanged();
    } catch {
      setMessage(t("projects.paymentLinkRecoverError"));
    } finally {
      setBusy(false);
    }
  }

  const configured = integration?.configured === true && integration.enabled === true;

  return (
    <section
      className="projects-payments payment-links"
      aria-label={t("projects.paymentLinksTitle")}
    >
      <div className="projects-actions">
        <h3>{t("projects.paymentLinksTitle")}</h3>
        {canWrite && configured && !showForm && (
          <button
            type="button"
            className="primary-action"
            onClick={() => {
              setBaseline(kind);
              setShowForm(true);
            }}
            disabled={busy}
          >
            {t("projects.paymentLinkCreate")}
          </button>
        )}
      </div>
      {message && <p className="form-error">{message}</p>}
      {integration !== null && !configured && (
        <p className="settings-hint">
          {isOwner
            ? t("projects.paymentLinkFlowRequired")
            : t("projects.paymentLinkFlowRequiredOwner")}
        </p>
      )}
      {showForm && (
        <form noValidate className="payments-form" onSubmit={create}>
          <label>
            {t("projects.paymentKind")}
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as PaymentKindEnum)}
            >
              <option value="ANTICIPO">{t("projects.paymentKindAnticipo")}</option>
              <option value="PARCIAL">{t("projects.paymentKindParcial")}</option>
              <option value="SALDO">{t("projects.paymentKindSaldo")}</option>
            </select>
          </label>
          <label>
            {t("projects.paymentAmount")}
            <input
              required
              inputMode="numeric"
              data-pattern="[0-9]+"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="250000"
            />
          </label>
          <label>
            {t("projects.paymentLinkEmail")}
            <input
              required
              type="email"
              value={payerEmail}
              onChange={(event) => setPayerEmail(event.target.value)}
              placeholder="cliente@correo.cl"
            />
          </label>
          <label className="payments-form-wide">
            {t("projects.paymentLinkSubject")}
            <input value={subject} onChange={(event) => setSubject(event.target.value)} />
          </label>
          <div className="payments-form-actions">
            <button type="submit" className="primary-action" disabled={busy}>
              {t("projects.paymentLinkCreate")}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={busy}>
              {t("projects.paymentCancel")}
            </button>
          </div>
        </form>
      )}
      {links.length > 0 && (
        <table className="payments-table">
          <thead>
            <tr>
              <th>{t("projects.paymentDate")}</th>
              <th>{t("projects.paymentKind")}</th>
              <th className="num">{t("projects.paymentAmount")}</th>
              <th>{t("projects.paymentLinkEmail")}</th>
              <th>{t("projects.paymentLinkStatus")}</th>
              <th>{t("projects.paymentLinkUrl")}</th>
              {canWrite && <th />}
            </tr>
          </thead>
          <tbody>
            {links.map((link) => (
              <tr key={link.id}>
                <td>{formatDate(link.created_at)}</td>
                <td>{t(KIND_LABEL[link.kind] ?? "projects.paymentKindParcial")}</td>
                <td className="num">{formatClp(link.amount)}</td>
                <td>{link.payer_email}</td>
                <td>
                  <span className={`production-chip link-${link.status.toLowerCase()}`}>
                    {t(LINK_STATUS_LABEL[link.status])}
                  </span>
                </td>
                <td>
                  {link.url ? (
                    <button type="button" onClick={() => copy(link)} disabled={busy}>
                      {copiedId === link.id
                        ? t("projects.paymentLinkCopied")
                        : t("projects.paymentLinkCopy")}
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
                {canWrite && (
                  <td>
                    {link.status !== "PAID" && link.status !== "DISPATCHING" && (
                      <button type="button" onClick={() => recover(link)} disabled={busy}>
                        {t("projects.paymentLinkRecover")}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {links.length === 0 && !showForm && !message && (
        <p className="settings-hint">{t("projects.paymentLinksEmpty")}</p>
      )}
    </section>
  );
}
