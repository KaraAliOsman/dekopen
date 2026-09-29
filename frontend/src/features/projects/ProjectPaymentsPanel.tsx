import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api/apiMutator";
import {
  projectCreditNoteAccess,
  projectCreditNoteDteAccess,
  projectCreditNoteDteEmit,
  projectCreditNoteDteEnvioAccess,
  projectCreditNoteDteEnvioSend,
  projectCreditNoteEmit,
  projectInvoiceAccess,
  projectInvoiceDteAccess,
  projectInvoiceDteEmit,
  projectInvoiceDteEnvioAccess,
  projectInvoiceDteEnvioSend,
  projectInvoiceEmit,
  projectPaymentsList,
  projectPaymentsRecord,
  projectPaymentReceipt,
  projectPaymentVoid,
} from "../../api/generated/dekopen";
import type {
  MethodEnum,
  PaymentKindEnum,
  PaymentsSummary,
  ProjectCreditNote,
  ProjectInvoice,
  ProjectPayment,
} from "../../api/generated/models";
import { t, type TranslationKey } from "../../i18n/es-CL";
import { actionErrorDetail } from "../errors";
import { formatDate, formatMoney, parseMoneyInput } from "../money";
import { formatRevision } from "../../format";
import { ProjectPaymentLinksPanel } from "./ProjectPaymentLinksPanel";
import { useConfirm, usePrompt } from "../../ui";

const KIND_LABEL: Record<string, TranslationKey> = {
  ANTICIPO: "projects.paymentKindAnticipo",
  PARCIAL: "projects.paymentKindParcial",
  SALDO: "projects.paymentKindSaldo",
};
const METHOD_LABEL: Record<string, TranslationKey> = {
  TRANSFER: "projects.paymentMethodTransfer",
  CASH: "projects.paymentMethodCash",
  CARD: "projects.paymentMethodCard",
  CHECK: "projects.paymentMethodCheck",
  OTHER: "projects.paymentMethodOther",
};
const STATUS_LABEL: Record<string, TranslationKey> = {
  NO_DEAL: "projects.paymentStatusNoDeal",
  PENDING: "projects.paymentStatusPending",
  PARTIAL: "projects.paymentStatusPartial",
  PAID: "projects.paymentStatusPaid",
};

export function ProjectPaymentsPanel({
  projectId,
  orgId,
  canWrite,
  canSendEnvio = false,
  isOwner = false,
  onDirtyChange,
}: {
  projectId: string;
  orgId: string;
  canWrite: boolean;
  canSendEnvio?: boolean;
  isOwner?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
}): JSX.Element {
  const confirm = useConfirm();
  const prompt = usePrompt();
  const queryClient = useQueryClient();
  // Shares the project header's `payments-summary` query — one fetch serves
  // both consumers instead of the panel re-fetching the same endpoint.
  const paymentsKey = ["projects", "payments-summary", orgId, projectId] as const;
  const paymentsQuery = useQuery({
    queryKey: paymentsKey,
    queryFn: async ({ signal }) => {
      const response = await projectPaymentsList(projectId, {
        signal,
        headers: { "X-Organization-ID": orgId },
      });
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      return response.data;
    },
  });
  const summary = paymentsQuery.data ?? null;
  const setSummary = (data: PaymentsSummary) => queryClient.setQueryData(paymentsKey, data);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [operationKey, setOperationKey] = useState("");
  const [kind, setKind] = useState<PaymentKindEnum>("ANTICIPO");
  const [method, setMethod] = useState<MethodEnum>("TRANSFER");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [note, setNote] = useState("");
  const [baseline, setBaseline] = useState({ kind, method });
  const [linksDirty, setLinksDirty] = useState(false);
  const generation = useRef(0);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  useEffect(
    () => () => {
      generation.current += 1;
    },
    [],
  );

  const load = useCallback(async () => {
    setMessage("");
    const result = await paymentsQuery.refetch();
    if (result.isError) setMessage(t("projects.paymentsLoadError"));
  }, [paymentsQuery]);

  useEffect(() => {
    if (paymentsQuery.isError) setMessage(t("projects.paymentsLoadError"));
  }, [paymentsQuery.isError]);

  const formDirty =
    showForm &&
    (kind !== baseline.kind ||
      method !== baseline.method ||
      amount.trim() !== "" ||
      reference.trim() !== "" ||
      note.trim() !== "");
  useEffect(() => {
    onDirtyChange?.(formDirty || linksDirty);
  }, [formDirty, linksDirty, onDirtyChange]);

  function openForm(): void {
    setOperationKey(crypto.randomUUID());
    // Follow the deal's position — registering against an outstanding
    // balance should open as SALDO prefilled with what is owed, not the
    // anticipo the first payment was (review WM7).
    const collected = summary ? Number(summary.collected) : 0;
    const balance = summary ? Number(summary.balance) : 0;
    const nextKind: PaymentKindEnum = collected > 0 && balance > 0 ? "SALDO" : "ANTICIPO";
    setKind(nextKind);
    if (nextKind === "SALDO") setAmount(String(balance));
    setBaseline({ kind: nextKind, method });
    setShowForm(true);
  }

  async function record(event: FormEvent): Promise<void> {
    event.preventDefault();
    const amountParsed = parseMoneyInput(amount);
    if (amountParsed === null) {
      setMessage(t("projects.paymentAmountInvalid"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectPaymentsRecord(
        projectId,
        {
          operation_key: operationKey,
          kind,
          amount: amountParsed,
          method,
          ...(reference.trim() ? { reference: reference.trim() } : {}),
          ...(note.trim() ? { note: note.trim() } : {}),
        },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      setSummary(response.data);
      void queryClient.invalidateQueries({
        queryKey: ["projects", "payments-summary", orgId, projectId],
      });
      setShowForm(false);
      setAmount("");
      setReference("");
      setNote("");
    } catch (error) {
      if (generation.current === current)
        setMessage(actionErrorDetail(error, t("projects.paymentsRecordError")));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function voidPayment(payment: ProjectPayment): Promise<void> {
    if (!(await confirm({ title: t("projects.paymentVoidConfirm"), danger: true }))) return;
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectPaymentVoid(projectId, payment.id, {}, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      setSummary(response.data);
      void queryClient.invalidateQueries({
        queryKey: ["projects", "payments-summary", orgId, projectId],
      });
    } catch (error) {
      if (generation.current === current) {
        setMessage(actionErrorDetail(error, t("projects.paymentsVoidError")));
      }
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openReceipt(payment: ProjectPayment): Promise<void> {
    // Open during the click activation — a tab opened after the await is blocked.
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.paymentReceiptError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectPaymentReceipt(projectId, payment.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.paymentReceiptError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function emitInvoice(): Promise<void> {
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectInvoiceEmit(projectId, requestOptions);
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await load();
    } catch (error) {
      if (generation.current === current)
        setMessage(actionErrorDetail(error, t("projects.invoiceEmitError")));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openInvoice(invoice: ProjectInvoice): Promise<void> {
    // Open during the click activation — a tab opened after the await is blocked.
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.invoiceOpenError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectInvoiceAccess(projectId, invoice.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.invoiceOpenError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function emitDte(invoice: ProjectInvoice): Promise<void> {
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectInvoiceDteEmit(projectId, invoice.id, requestOptions);
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await load();
    } catch (error) {
      if (generation.current === current) {
        setMessage(actionErrorDetail(error, t("projects.dteEmitError")));
      }
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openDte(invoice: ProjectInvoice): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.dteOpenError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectInvoiceDteAccess(projectId, invoice.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.dteOpenError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function sendEnvio(invoice: ProjectInvoice, resubmit = false): Promise<void> {
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectInvoiceDteEnvioSend(
        projectId,
        invoice.id,
        { resubmit },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await load();
    } catch (error) {
      if (generation.current === current) {
        setMessage(actionErrorDetail(error, t("projects.envioSendError")));
      }
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openEnvio(invoice: ProjectInvoice): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.envioOpenError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectInvoiceDteEnvioAccess(projectId, invoice.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.envioOpenError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function sendCreditEnvio(note: ProjectCreditNote, resubmit = false): Promise<void> {
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectCreditNoteDteEnvioSend(
        projectId,
        note.id,
        { resubmit },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await load();
    } catch (error) {
      if (generation.current === current) {
        setMessage(actionErrorDetail(error, t("projects.envioSendError")));
      }
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openCreditEnvio(note: ProjectCreditNote): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.envioOpenError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectCreditNoteDteEnvioAccess(projectId, note.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.envioOpenError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function annulInvoice(invoice: ProjectInvoice): Promise<void> {
    if (!(await confirm({ title: t("projects.creditNoteAnnulConfirm"), danger: true }))) return;
    const reason = await prompt({ title: t("projects.creditNoteReason") });
    if (reason === null) return;
    const amountText = await prompt({
      title: t("projects.creditNoteAmount"),
      input: {
        label: t("projects.creditNoteAmount"),
        placeholder: t("projects.creditNoteAmountHint"),
      },
    });
    if (amountText === null) return;
    // Parse es-CL input ("1.500.000" / "1.500.000,50") into the canonical
    // decimal the API expects — stripping non-digits turned "100,50" into
    // "10050" and the sealed note locks whatever number lands.
    const amountParsed = amountText.trim() ? parseMoneyInput(amountText) : "";
    if (amountText.trim() && amountParsed === null) {
      setMessage(t("projects.creditNoteAmountInvalid"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectCreditNoteEmit(
        projectId,
        invoice.id,
        {
          ...(reason.trim() ? { reason: reason.trim() } : {}),
          ...(amountParsed ? { amount: amountParsed } : {}),
        },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await load();
    } catch (error) {
      if (generation.current === current) {
        setMessage(actionErrorDetail(error, t("projects.creditNoteEmitError")));
      }
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function emitCreditNoteDte(invoice: ProjectInvoice): Promise<void> {
    const reason = await prompt({ title: t("projects.creditNoteReason") });
    if (reason === null) return;
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectCreditNoteDteEmit(
        projectId,
        invoice.id,
        reason.trim() ? { reason: reason.trim() } : {},
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (generation.current !== current) return;
      await load();
    } catch (error) {
      if (generation.current === current)
        setMessage(actionErrorDetail(error, t("projects.dteEmitError")));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openCreditNoteDte(invoice: ProjectInvoice): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.dteOpenError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectCreditNoteDteAccess(projectId, invoice.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.dteOpenError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function openCreditNote(note: ProjectCreditNote): Promise<void> {
    const tab = window.open("", "_blank");
    if (!tab) {
      setMessage(t("projects.creditNoteOpenError"));
      return;
    }
    const current = generation.current;
    setBusy(true);
    setMessage("");
    try {
      const response = await projectCreditNoteAccess(projectId, note.id, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (generation.current !== current) {
        tab.close();
        return;
      }
      tab.opener = null;
      tab.location.href = response.data.signed_url;
    } catch {
      tab.close();
      if (generation.current === current) setMessage(t("projects.creditNoteOpenError"));
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  const payments = summary?.payments ?? [];
  const invoiceList = summary?.invoices ?? [];
  const percent =
    summary?.quote_total_gross && Number(summary.quote_total_gross) > 0
      ? Math.min(100, (Number(summary.collected) / Number(summary.quote_total_gross)) * 100)
      : null;

  return (
    <section className="projects-payments">
      <div className="projects-actions">
        <h2>{t("projects.paymentsTitle")}</h2>
        {canWrite && !showForm && (
          <button type="button" className="primary-action" onClick={openForm} disabled={busy}>
            {t("projects.paymentRecord")}
          </button>
        )}
      </div>
      {message && <p className="form-error">{message}</p>}
      {summary && (
        <div className="payments-summary">
          <span className={`production-chip delivery-${summary.status.toLowerCase()}`}>
            {t(STATUS_LABEL[summary.status] ?? "projects.paymentStatusNoDeal")}
          </span>
          <dl className="payments-summary-facts">
            <div>
              <dt>{t("projects.paymentCollected")}</dt>
              <dd>{formatMoney(summary.collected, summary.currency)}</dd>
            </div>
            <div>
              <dt>{t("projects.paymentDealTotal")}</dt>
              <dd>{formatMoney(summary.quote_total_gross, summary.currency)}</dd>
            </div>
            <div>
              <dt>{t("projects.paymentBalance")}</dt>
              <dd>{formatMoney(summary.balance, summary.currency)}</dd>
            </div>
          </dl>
          {percent !== null && (
            <div
              className="payments-progress"
              role="progressbar"
              aria-valuenow={Math.round(percent)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div style={{ width: `${percent}%` }} />
            </div>
          )}
        </div>
      )}
      {showForm && (
        <form className="payments-form" onSubmit={record}>
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
              inputMode="decimal"
              pattern="[0-9]{1,3}(\.[0-9]{3})+|[0-9]+"
              title={t("projects.paymentAmountHint")}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
              placeholder="500000"
            />
          </label>
          <label>
            {t("projects.paymentMethod")}
            <select
              value={method}
              onChange={(event) => setMethod(event.target.value as MethodEnum)}
            >
              <option value="TRANSFER">{t("projects.paymentMethodTransfer")}</option>
              <option value="CASH">{t("projects.paymentMethodCash")}</option>
              <option value="CARD">{t("projects.paymentMethodCard")}</option>
              <option value="CHECK">{t("projects.paymentMethodCheck")}</option>
              <option value="OTHER">{t("projects.paymentMethodOther")}</option>
            </select>
          </label>
          <label>
            {t("projects.paymentReference")}
            <input value={reference} onChange={(event) => setReference(event.target.value)} />
          </label>
          <label className="payments-form-wide">
            {t("projects.paymentNote")}
            <input value={note} onChange={(event) => setNote(event.target.value)} />
          </label>
          <div className="payments-form-actions">
            <button type="submit" className="primary-action" disabled={busy}>
              {t("projects.paymentSave")}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={busy}>
              {t("projects.paymentCancel")}
            </button>
          </div>
        </form>
      )}
      {payments.length > 0 && (
        <table className="payments-table">
          <thead>
            <tr>
              <th>{t("projects.paymentDate")}</th>
              <th>{t("projects.paymentKind")}</th>
              <th className="num">{t("projects.paymentAmount")}</th>
              <th>{t("projects.paymentMethod")}</th>
              <th>{t("projects.paymentReference")}</th>
              <th>{t("projects.paymentNote")}</th>
              <th>{t("projects.paymentReceipt")}</th>
              {canWrite && <th />}
            </tr>
          </thead>
          <tbody>
            {payments.map((payment) => (
              <tr key={payment.id} className={payment.voided_at ? "payments-voided" : undefined}>
                <td>{formatDate(payment.recorded_at)}</td>
                <td>{t(KIND_LABEL[payment.kind] ?? "projects.paymentKindParcial")}</td>
                <td className="num">{formatMoney(payment.amount, summary?.currency ?? "CLP")}</td>
                <td>{t(METHOD_LABEL[payment.method] ?? "projects.paymentMethodOther")}</td>
                <td>{payment.reference ?? "—"}</td>
                <td>
                  {payment.voided_at
                    ? `${t("projects.paymentVoided")}${payment.void_reason ? ` — ${payment.void_reason}` : ""}`
                    : (payment.note ?? "—")}
                </td>
                <td>
                  {payment.receipt_code ? (
                    <button type="button" onClick={() => void openReceipt(payment)} disabled={busy}>
                      {payment.receipt_code}
                    </button>
                  ) : (
                    "—"
                  )}
                </td>
                {canWrite && (
                  <td>
                    {!payment.voided_at && (
                      <button type="button" onClick={() => voidPayment(payment)} disabled={busy}>
                        {t("projects.paymentVoid")}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {summary && payments.length === 0 && !showForm && <p>{t("projects.paymentsEmpty")}</p>}
      {summary && (summary.sealed_revision || invoiceList.length > 0) && (
        <div className="projects-invoices">
          <div className="projects-actions">
            <h3>{t("projects.invoicesTitle")}</h3>
            {canWrite && summary.sealed_revision && (
              <button type="button" onClick={() => void emitInvoice()} disabled={busy}>
                {t("projects.invoiceEmit")}
              </button>
            )}
          </div>
          {invoiceList.length > 0 ? (
            <table className="payments-table">
              <thead>
                <tr>
                  <th>{t("projects.invoiceDate")}</th>
                  <th>{t("projects.invoiceCode")}</th>
                  <th>{t("projects.invoiceRevision")}</th>
                  <th>{t("projects.invoiceStatus")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {invoiceList.map((invoice) => (
                  <tr key={invoice.id}>
                    <td>{formatDate(invoice.created_at)}</td>
                    <td>{invoice.invoice_code}</td>
                    <td>{formatRevision(invoice.revision_code)}</td>
                    <td>
                      {invoice.credit_note ? (
                        <button
                          type="button"
                          className="production-chip delivery-cancelled"
                          title={invoice.credit_note.credit_code}
                          onClick={() => {
                            if (invoice.credit_note) void openCreditNote(invoice.credit_note);
                          }}
                          disabled={busy}
                        >
                          {`${t(invoice.credit_note.partial ? "projects.invoiceStatusCredited" : "projects.invoiceStatusAnnulled")} · ${invoice.credit_note.credit_code}`}
                        </button>
                      ) : (
                        <span className="production-chip">{t("projects.invoiceStatusIssued")}</span>
                      )}
                      {invoice.dte && (
                        <button
                          type="button"
                          className="production-chip"
                          title={`${t("projects.dteStatus")} · folio ${invoice.dte.folio}`}
                          onClick={() => void openDte(invoice)}
                          disabled={busy}
                        >
                          {`${t("projects.dteStatus")} · ${invoice.dte.folio}`}
                        </button>
                      )}
                      {invoice.credit_note?.dte && (
                        <button
                          type="button"
                          className="production-chip"
                          title={`${t("projects.dteCreditStatus")} · folio ${invoice.credit_note.dte.folio}`}
                          onClick={() => void openCreditNoteDte(invoice)}
                          disabled={busy}
                        >
                          {`${t("projects.dteCreditStatus")} · ${invoice.credit_note.dte.folio}`}
                        </button>
                      )}
                      {invoice.dte?.envio && (
                        <button
                          type="button"
                          className="production-chip"
                          title={`${t("projects.envioStatus")} · ${invoice.dte.envio.track_id ?? ""}`}
                          onClick={() => void openEnvio(invoice)}
                          disabled={busy}
                        >
                          {`${t("projects.envioStatus")} · ${invoice.dte.envio.status}`}
                        </button>
                      )}
                      {invoice.credit_note?.dte?.envio && (
                        <button
                          type="button"
                          className="production-chip"
                          title={`${t("projects.envioStatus")} · ${invoice.credit_note.dte.envio.track_id ?? ""}`}
                          onClick={() => {
                            if (invoice.credit_note) void openCreditEnvio(invoice.credit_note);
                          }}
                          disabled={busy}
                        >
                          {`${t("projects.envioStatus")} · ${invoice.credit_note.dte.envio.status}`}
                        </button>
                      )}
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => void openInvoice(invoice)}
                        disabled={busy}
                      >
                        {t("projects.invoiceOpen")}
                      </button>
                      {canWrite && !invoice.credit_note && !invoice.dte && (
                        <button type="button" onClick={() => void emitDte(invoice)} disabled={busy}>
                          {t("projects.dteEmit")}
                        </button>
                      )}
                      {canWrite && !invoice.credit_note && !invoice.dte && (
                        <button
                          type="button"
                          onClick={() => void annulInvoice(invoice)}
                          disabled={busy}
                        >
                          {t("projects.creditNoteAnnul")}
                        </button>
                      )}
                      {canWrite && invoice.dte && !invoice.credit_note?.dte && (
                        <button
                          type="button"
                          onClick={() => void emitCreditNoteDte(invoice)}
                          disabled={busy}
                        >
                          {t("projects.dteCreditEmit")}
                        </button>
                      )}
                      {canSendEnvio && invoice.dte && !invoice.dte.envio && (
                        <button
                          type="button"
                          onClick={() => void sendEnvio(invoice)}
                          disabled={busy}
                        >
                          {t("projects.envioSend")}
                        </button>
                      )}
                      {canSendEnvio && invoice.dte?.envio?.status === "PENDING" && (
                        <button
                          type="button"
                          onClick={() =>
                            void sendEnvio(
                              invoice,
                              invoice.dte?.envio?.attempted === true && !invoice.dte.envio.track_id,
                            )
                          }
                          disabled={busy}
                        >
                          {invoice.dte.envio.attempted === true && !invoice.dte.envio.track_id
                            ? t("projects.envioResend")
                            : t("projects.envioRefresh")}
                        </button>
                      )}
                      {canSendEnvio &&
                        invoice.credit_note?.dte &&
                        !invoice.credit_note.dte.envio && (
                          <button
                            type="button"
                            onClick={() => {
                              if (invoice.credit_note) void sendCreditEnvio(invoice.credit_note);
                            }}
                            disabled={busy}
                          >
                            {t("projects.envioSend")}
                          </button>
                        )}
                      {canSendEnvio && invoice.credit_note?.dte?.envio?.status === "PENDING" && (
                        <button
                          type="button"
                          onClick={() => {
                            if (invoice.credit_note) {
                              void sendCreditEnvio(
                                invoice.credit_note,
                                invoice.credit_note.dte?.envio?.attempted === true &&
                                  !invoice.credit_note.dte.envio.track_id,
                              );
                            }
                          }}
                          disabled={busy}
                        >
                          {invoice.credit_note.dte.envio.attempted === true &&
                          !invoice.credit_note.dte.envio.track_id
                            ? t("projects.envioResend")
                            : t("projects.envioRefresh")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p>{t("projects.invoicesEmpty")}</p>
          )}
        </div>
      )}
      <ProjectPaymentLinksPanel
        projectId={projectId}
        orgId={orgId}
        canWrite={canWrite}
        isOwner={isOwner}
        onChanged={load}
        onDirtyChange={setLinksDirty}
      />
    </section>
  );
}
