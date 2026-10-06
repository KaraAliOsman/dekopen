import { useCallback, useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/apiMutator";
import {
  catalogExtraarticleList,
  catalogServicearticleList,
  getOrganizationBrandingLogoReadUrl,
  mailStatus,
  organizationBrandingGet,
  organizationBrandingLogoDelete,
  organizationBrandingLogoUpload,
  organizationBrandingSave,
  organizationExtrasConfigRead,
  organizationExtrasConfigUpdate,
  projectPaymentIntegrationSave,
  projectPaymentIntegrationStatus,
  siiCafRegister,
  siiCafsList,
  siiCertificateStatus,
  siiCertificateUpload,
} from "../api/generated/dekopen";
import { apiFetchBlob } from "../api/apiMutator";
import type {
  ApiUrlEnum,
  DocPaperSizeEnum,
  ExtraArticleResponse,
  ExtraTemplateWriteRequest,
  MailStatus,
  Membership,
  PaymentIntegrationStatus,
  MembershipRoleEnum,
  ServiceArticleResponse,
  SiiCaf,
  SiiCertificate,
} from "../api/generated/models";
import { PageHeader } from "../ui";
import { StatusChip } from "../ui/StatusChip";
import { useAuthSession } from "../auth/AuthSessionProvider";
import { AiSettingsCard } from "../features/assistant/AiSettingsCard";
import { formatDate } from "../format";
import { t, tDynamic, type TranslationKey } from "../i18n/es-CL";
import { MOD_K_HINT, MOD_KEY_HINT } from "../platform";
import { useTheme } from "../theme/ThemeProvider";

const ROLE_KEYS: Record<MembershipRoleEnum, TranslationKey> = {
  OWNER: "settings.roleOwner",
  ESTIMATOR: "settings.roleEstimator",
  WORKSHOP_MANAGER: "settings.roleWorkshopManager",
  INSTALLER: "settings.roleInstaller",
  OPERATOR: "settings.roleOperator",
};

function FilePick({
  inputRef,
  accept,
  file,
  onFile,
}: {
  inputRef: RefObject<HTMLInputElement>;
  accept: string;
  file: File | null;
  onFile: (file: File | null) => void;
}): JSX.Element {
  return (
    <span className="file-field">
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        className="file-input-hidden"
        onChange={(event) => onFile(event.target.files?.[0] ?? null)}
      />
      <button type="button" className="secondary-action" onClick={() => inputRef.current?.click()}>
        {t("settings.fileChoose")}
      </button>
      <span className="file-field__name">{file ? file.name : t("settings.fileNone")}</span>
    </span>
  );
}

function MembershipRow({ membership }: { membership: Membership }): JSX.Element {
  return (
    <li className="settings-row">
      <span>{membership.organization_name}</span>
      <span className="settings-role">{t(ROLE_KEYS[membership.role])}</span>
    </li>
  );
}

function FlowIntegrationCard({ orgId }: { orgId: string }): JSX.Element {
  const [status, setStatus] = useState<PaymentIntegrationStatus | null>(null);
  const [apiUrl, setApiUrl] = useState<ApiUrlEnum>("https://sandbox.flow.cl/api");
  const [apiKey, setApiKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [returnUrl, setReturnUrl] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  const load = useCallback(async () => {
    try {
      const response = await projectPaymentIntegrationStatus(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setStatus(response.data);
      if (response.data.configured) {
        setApiUrl(response.data.api_url as ApiUrlEnum);
        setReturnUrl(response.data.payer_return_url ?? "");
        setEnabled(response.data.enabled ?? true);
      }
    } catch {
      setMessage({ text: t("settings.flowLoadError"), error: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await projectPaymentIntegrationSave(
        {
          api_url: apiUrl,
          // Blank = keep the stored key — never echo the masked preview back
          // as if it were the credential.
          ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
          ...(secretKey.trim() ? { secret_key: secretKey.trim() } : {}),
          payer_return_url: returnUrl.trim(),
          enabled,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setStatus(response.data);
      setSecretKey("");
      setMessage({ text: t("settings.flowSaved"), error: false });
    } catch {
      setMessage({ text: t("settings.flowSaveError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.flow")}</h3>
      <p className="settings-hint">{t("settings.flowHint")}</p>
      <p>
        <StatusChip
          label={
            status?.configured ? t("settings.flowConfigured") : t("settings.flowNotConfigured")
          }
          tone={status?.configured ? "ok" : "warn"}
          value={null}
        />
        {status?.api_key_preview && (
          <span className="settings-mono"> · {status.api_key_preview}</span>
        )}
      </p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <form noValidate className="payments-form" onSubmit={save}>
        <label>
          {t("settings.flowEnv")}
          <select value={apiUrl} onChange={(event) => setApiUrl(event.target.value as ApiUrlEnum)}>
            <option value="https://sandbox.flow.cl/api">{t("settings.flowSandbox")}</option>
            <option value="https://www.flow.cl/api">{t("settings.flowProduction")}</option>
          </select>
        </label>
        <label>
          {t("settings.flowApiKey")}
          <input
            required={!status?.configured}
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder={status?.api_key_preview ?? "AB12CD34EF56"}
          />
        </label>
        <label>
          {t("settings.flowSecret")}
          <input
            type="password"
            value={secretKey}
            onChange={(event) => setSecretKey(event.target.value)}
            placeholder={status?.configured ? t("settings.flowSecretKeep") : ""}
          />
        </label>
        <label>
          {t("settings.flowReturnUrl")}
          <input
            value={returnUrl}
            onChange={(event) => setReturnUrl(event.target.value)}
            placeholder="https://taller.cl/pago/retorno"
          />
        </label>
        <label className="settings-inline">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(event) => setEnabled(event.target.checked)}
          />
          {t("settings.flowEnabled")}
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.flowSave")}
          </button>
        </div>
      </form>
    </div>
  );
}

function SiiCafCard({ orgId }: { orgId: string }): JSX.Element {
  const [items, setItems] = useState<SiiCaf[]>([]);
  const [pickFile, setPickFile] = useState<File | null>(null);
  const pickRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  const load = useCallback(async () => {
    try {
      const response = await siiCafsList(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setItems(response.data.items);
    } catch {
      setMessage({ text: t("settings.siiCafError"), error: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(event: FormEvent): Promise<void> {
    event.preventDefault();
    const file = pickFile;
    if (!file) return;
    const cafXml = await file.text();
    const form = event.target as HTMLFormElement;
    const field = (name: string) =>
      (form.elements.namedItem(name) as HTMLInputElement | null)?.value.trim() ?? "";
    const actecoRaw = field("acteco");
    setBusy(true);
    setMessage(null);
    try {
      const response = await siiCafRegister(
        {
          caf_xml: cafXml,
          giro_emis: field("giro_emis"),
          dir_origen: field("dir_origen"),
          cmna_origen: field("cmna_origen"),
          acteco: actecoRaw ? Number(actecoRaw) : null,
        },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (pickRef.current) pickRef.current.value = "";
      setPickFile(null);
      setMessage({ text: t("settings.siiCafUploaded"), error: false });
      await load();
    } catch {
      setMessage({ text: t("settings.siiCafError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.siiTitle")}</h3>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      {items.length === 0 ? (
        <p className="settings-hint">{t("settings.siiCafEmpty")}</p>
      ) : (
        <table className="payments-table">
          <thead>
            <tr>
              <th>{t("settings.siiCafType")}</th>
              <th>{t("settings.siiCafRange")}</th>
              <th>{t("settings.siiCafUsed")}</th>
              <th>{t("settings.siiCafRemaining")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((caf) => (
              <tr key={caf.id}>
                <td>{`DTE-${caf.tipo_dte}`}</td>
                <td>{`${caf.folio_desde}–${caf.folio_hasta}`}</td>
                <td>{caf.folio_actual < caf.folio_desde ? "—" : caf.folio_actual}</td>
                <td>{caf.remaining}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <form noValidate className="payments-form" onSubmit={upload}>
        <label>
          {t("settings.siiCafFile")}
          <FilePick
            inputRef={pickRef}
            accept=".xml,text/xml"
            file={pickFile}
            onFile={setPickFile}
          />
        </label>
        <label>
          {t("settings.siiGiro")}
          <input name="giro_emis" maxLength={80} required />
        </label>
        <label>
          {t("settings.siiAddress")}
          <input name="dir_origen" maxLength={70} required />
        </label>
        <label>
          {t("settings.siiComuna")}
          <input name="cmna_origen" maxLength={20} required />
        </label>
        <label>
          {t("settings.siiActeco")}
          <input name="acteco" type="number" min={1} required />
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.siiCafUpload")}
          </button>
        </div>
      </form>
    </div>
  );
}

function SiiCertificateCard({ orgId }: { orgId: string }): JSX.Element {
  const [certificate, setCertificate] = useState<SiiCertificate | null>(null);
  const [pickFile, setPickFile] = useState<File | null>(null);
  const pickRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  const load = useCallback(async () => {
    try {
      const response = await siiCertificateStatus(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setCertificate(response.data.certificate);
    } catch {
      setMessage({ text: t("settings.siiCertError"), error: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
  }, [load]);

  async function upload(event: FormEvent): Promise<void> {
    event.preventDefault();
    const file = pickFile;
    if (!file) return;
    const form = event.target as HTMLFormElement;
    const field = (name: string) =>
      (form.elements.namedItem(name) as HTMLInputElement | null)?.value.trim() ?? "";
    setBusy(true);
    setMessage(null);
    try {
      const pfx_b64 = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? "").split(",")[1] ?? "");
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
      });
      const response = await siiCertificateUpload(
        {
          pfx_b64,
          password: field("password"),
          nro_resol: Number(field("nro_resol") || "0"),
          fch_resol: field("fch_resol"),
        },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      if (pickRef.current) pickRef.current.value = "";
      setPickFile(null);
      setMessage({ text: t("settings.siiCertUploaded"), error: false });
      await load();
    } catch {
      setMessage({ text: t("settings.siiCertError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.siiCertTitle")}</h3>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      {certificate === null ? (
        <p className="settings-hint">{t("settings.siiCertEmpty")}</p>
      ) : (
        <dl className="settings-list">
          <div className="settings-row">
            <dt>{t("settings.siiCertSigner")}</dt>
            <dd className="settings-mono">{certificate.rut_firma}</dd>
          </div>
          <div className="settings-row">
            <dt>{t("settings.siiCertSubject")}</dt>
            <dd>{certificate.subject}</dd>
          </div>
          <div className="settings-row">
            <dt>{t("settings.siiCertValidUntil")}</dt>
            <dd>{formatDate(certificate.valid_to)}</dd>
          </div>
          <div className="settings-row">
            <dt>{t("settings.siiCertResolution")}</dt>
            <dd className="settings-mono">{`N° ${certificate.nro_resol} · ${certificate.fch_resol}`}</dd>
          </div>
        </dl>
      )}
      <form noValidate className="payments-form" onSubmit={upload}>
        <label>
          {t("settings.siiCertFile")}
          <FilePick inputRef={pickRef} accept=".pfx,.p12" file={pickFile} onFile={setPickFile} />
        </label>
        <label>
          {t("settings.siiCertPassword")}
          <input name="password" type="password" maxLength={200} autoComplete="off" />
        </label>
        <label>
          {t("settings.siiCertNroResol")}
          <input name="nro_resol" type="number" min={0} required />
        </label>
        <label>
          {t("settings.siiCertFchResol")}
          <input name="fch_resol" type="date" required />
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.siiCertUpload")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** WCAG AA contra papel blanco (4.5:1) — la misma matemática linearizada
 * que `backend/documents/brand.py`, duplicada para avisar antes de
 * guardar: si el color cae al fallback teal-800 el aviso aparece aquí. */
function brandColorPassesAa(hex: string): boolean {
  const channel = (slice: string): number => {
    const c = parseInt(slice, 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lum =
    0.2126 * channel(hex.slice(1, 3)) +
    0.7152 * channel(hex.slice(3, 5)) +
    0.0722 * channel(hex.slice(5, 7));
  return 1.05 / (lum + 0.05) >= 4.5;
}

function OrgBrandingCard({ orgId }: { orgId: string }): JSX.Element {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [pickFile, setPickFile] = useState<File | null>(null);
  const pickRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [form, setForm] = useState({
    commercial_name: "",
    giro: "",
    brand_address: "",
    brand_phone: "",
    brand_email: "",
    brand_color: "",
    doc_dekopen_credit: false,
    doc_paper_size: "LETTER" as DocPaperSizeEnum,
    doc_terms: {
      plazo_entrega: "",
      instalacion: "",
      exclusiones: "",
      garantia: "",
      jurisdiccion: "",
    } as Record<string, string>,
  });
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  // El color por defecto del control ES el token teal-800 — se resuelve
  // del CSS, nunca de un literal (guard de hex del §10).
  const [tealFallback] = useState(() =>
    typeof document === "undefined"
      ? ""
      : getComputedStyle(document.documentElement).getPropertyValue("--teal-800").trim(),
  );

  const load = useCallback(async () => {
    try {
      const response = await organizationBrandingGet(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setForm({
        commercial_name: response.data.commercial_name ?? "",
        giro: response.data.giro ?? "",
        brand_address: response.data.brand_address ?? "",
        brand_phone: response.data.brand_phone ?? "",
        brand_email: response.data.brand_email ?? "",
        brand_color: response.data.brand_color ?? "",
        doc_dekopen_credit: response.data.doc_dekopen_credit ?? false,
        doc_paper_size: (response.data.doc_paper_size ?? "LETTER") as DocPaperSizeEnum,
        doc_terms: {
          plazo_entrega: "",
          instalacion: "",
          exclusiones: "",
          garantia: "",
          jurisdiccion: "",
          ...(response.data.doc_terms ?? {}),
        },
      });
      if (response.data.brand_logo_key) {
        try {
          const { blob } = await apiFetchBlob(getOrganizationBrandingLogoReadUrl());
          setLogoUrl((previous) => {
            if (previous) URL.revokeObjectURL(previous);
            return URL.createObjectURL(blob);
          });
        } catch {
          setLogoUrl(null);
        }
      } else {
        setLogoUrl(null);
      }
    } catch {
      setMessage({ text: t("settings.brandingLoadError"), error: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
  }, [load]);

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    const field = (
      name: Exclude<keyof typeof form, "doc_dekopen_credit" | "doc_paper_size" | "doc_terms">,
    ) => form[name].trim() || null;
    // Vacío se sella como omisión — el documento imprime solo las
    // condiciones que la organización declara.
    const docTerms = Object.fromEntries(
      Object.entries(form.doc_terms)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value !== ""),
    );
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationBrandingSave(
        {
          commercial_name: field("commercial_name"),
          giro: field("giro"),
          brand_address: field("brand_address"),
          brand_phone: field("brand_phone"),
          brand_email: field("brand_email"),
          brand_color: field("brand_color")?.toUpperCase() ?? null,
          doc_dekopen_credit: form.doc_dekopen_credit,
          doc_paper_size: form.doc_paper_size,
          doc_terms: docTerms,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setMessage({ text: t("settings.brandingSaved"), error: false });
    } catch {
      setMessage({ text: t("settings.brandingSaveError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  async function upload(event: FormEvent): Promise<void> {
    event.preventDefault();
    const file = pickFile;
    if (!file) return;
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationBrandingLogoUpload({ file }, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      if (pickRef.current) pickRef.current.value = "";
      setPickFile(null);
      setMessage({ text: t("settings.brandingLogoUploaded"), error: false });
      await load();
    } catch {
      setMessage({ text: t("settings.brandingSaveError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  async function removeLogo(): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationBrandingLogoDelete(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setMessage({ text: t("settings.brandingSaved"), error: false });
      await load();
    } catch {
      setMessage({ text: t("settings.brandingSaveError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.branding")}</h3>
      <p className="settings-hint">{t("settings.brandingHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <div className="settings-branding-preview">
        {logoUrl ? (
          <img
            className="settings-branding-logo"
            src={logoUrl}
            alt={t("settings.brandingLogoAlt")}
          />
        ) : (
          <p className="settings-hint">{t("settings.brandingLogoEmpty")}</p>
        )}
      </div>
      <form noValidate className="payments-form" onSubmit={save}>
        <label>
          {t("settings.brandingName")}
          <input
            maxLength={255}
            value={form.commercial_name}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, commercial_name: event.target.value }))
            }
          />
        </label>
        <label>
          {t("settings.brandingGiro")}
          <input
            maxLength={255}
            value={form.giro}
            onChange={(event) => setForm((prev) => ({ ...prev, giro: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingAddress")}
          <input
            maxLength={255}
            value={form.brand_address}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, brand_address: event.target.value }))
            }
          />
        </label>
        <label>
          {t("settings.brandingPhone")}
          <input
            maxLength={64}
            value={form.brand_phone}
            onChange={(event) => setForm((prev) => ({ ...prev, brand_phone: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingEmail")}
          <input
            type="email"
            maxLength={255}
            value={form.brand_email}
            onChange={(event) => setForm((prev) => ({ ...prev, brand_email: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandColor")}
          <span className="settings-branding-color">
            <input
              aria-label={t("settings.brandColor")}
              type="color"
              value={/^#[0-9A-Fa-f]{6}$/.test(form.brand_color) ? form.brand_color : tealFallback}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, brand_color: event.target.value.toUpperCase() }))
              }
            />
            <input
              maxLength={7}
              placeholder="#RRGGBB"
              value={form.brand_color}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, brand_color: event.target.value.toUpperCase() }))
              }
            />
          </span>
          <span className="settings-hint">{t("settings.brandColorHint")}</span>
          {form.brand_color !== "" &&
          /^#[0-9A-Fa-f]{6}$/.test(form.brand_color) &&
          !brandColorPassesAa(form.brand_color) ? (
            <span className="form-error">{t("settings.brandColorWarning")}</span>
          ) : null}
        </label>
        <label className="settings-branding-credit">
          <input
            checked={form.doc_dekopen_credit}
            onChange={(event) =>
              setForm((prev) => ({ ...prev, doc_dekopen_credit: event.target.checked }))
            }
            type="checkbox"
          />
          {t("settings.brandCredit")}
          <span className="settings-hint">{t("settings.brandCreditHint")}</span>
        </label>
        <fieldset className="settings-docs">
          <legend>{t("settings.documents")}</legend>
          <p className="settings-hint">{t("settings.documentsHint")}</p>
          <label>
            {t("settings.docPaperSize")}
            <select
              value={form.doc_paper_size}
              onChange={(event) =>
                setForm((prev) => ({
                  ...prev,
                  doc_paper_size: event.target.value as DocPaperSizeEnum,
                }))
              }
            >
              <option value="LETTER">{t("settings.docPaperLetter")}</option>
              <option value="LEGAL">{t("settings.docPaperLegal")}</option>
              <option value="A4">{t("settings.docPaperA4")}</option>
            </select>
          </label>
          {(
            [
              ["plazo_entrega", "settings.docTermsPlazo"],
              ["instalacion", "settings.docTermsInstalacion"],
              ["exclusiones", "settings.docTermsExclusiones"],
              ["garantia", "settings.docTermsGarantia"],
              ["jurisdiccion", "settings.docTermsJurisdiccion"],
            ] as const
          ).map(([key, labelKey]) => (
            <label key={key}>
              {t(labelKey)}
              <textarea
                maxLength={4000}
                rows={2}
                value={form.doc_terms[key] ?? ""}
                onChange={(event) =>
                  setForm((prev) => ({
                    ...prev,
                    doc_terms: { ...prev.doc_terms, [key]: event.target.value },
                  }))
                }
              />
            </label>
          ))}
          <p className="settings-hint">{t("settings.docTermsHint")}</p>
        </fieldset>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.brandingSave")}
          </button>
        </div>
      </form>
      <form noValidate className="payments-form" onSubmit={upload}>
        <label>
          {t("settings.brandingLogo")}
          <FilePick
            inputRef={pickRef}
            accept="image/png,image/jpeg,image/webp"
            file={pickFile}
            onFile={setPickFile}
          />
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.brandingLogoUpload")}
          </button>
          {logoUrl && (
            <button type="button" className="secondary-action" disabled={busy} onClick={removeLogo}>
              {t("settings.brandingLogoRemove")}
            </button>
          )}
        </div>
      </form>
    </div>
  );
}

/** P25 — estado de la bandeja de correo transaccional: proveedor activo
 * (sandbox por defecto), remitente y conteo de la última semana. El
 * adaptador real se activa por variables de entorno (ver ACTIVACION.md). */
function MailStatusCard({ orgId }: { orgId: string }): JSX.Element {
  const [status, setStatus] = useState<MailStatus | null>(null);
  const [failed, setFailed] = useState(false);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    let cancelled = false;
    void mailStatus(requestOptions)
      .then((response) => {
        if (!cancelled && response.status === 200) setStatus(response.data);
        if (!cancelled && response.status !== 200) setFailed(true);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.mailTitle")}</h3>
      <p className="settings-hint">{t("settings.mailHint")}</p>
      {failed && <p className="form-error">{t("settings.mailLoadError")}</p>}
      {status !== null && (
        <dl className="settings-mail-grid">
          <div>
            <dt>{t("settings.mailProvider")}</dt>
            <dd>
              {status.provider === "smtp"
                ? t("settings.mailProviderSmtp")
                : t("settings.mailProviderSandbox")}
            </dd>
          </div>
          <div>
            <dt>{t("settings.mailFrom")}</dt>
            <dd>{status.from_address}</dd>
          </div>
          <div>
            <dt>{t("settings.mailQueued")}</dt>
            <dd>{status.queued}</dd>
          </div>
          <div>
            <dt>{t("settings.mailSent7d")}</dt>
            <dd>{status.sent_7d}</dd>
          </div>
          <div>
            <dt>{t("settings.mailFailed7d")}</dt>
            <dd>{status.failed_7d}</dd>
          </div>
        </dl>
      )}
    </div>
  );
}

/** D07 — reglas de taller: la tolerancia de descuadre que el motor aplica
 * al comparar los puntos del vano (manda la menor; sobre ella avisa). */
function WorkshopRulesCard({ orgId }: { orgId: string }): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [tolerance, setTolerance] = useState("");
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    void (async () => {
      try {
        const response = await organizationBrandingGet(requestOptions);
        if (response.status === 200)
          setTolerance(response.data.vano_spread_tolerance_mm ?? "10.00");
      } catch {
        /* la tarjeta principal ya reporta el fallo de carga */
      }
    })();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationBrandingSave(
        { vano_spread_tolerance_mm: tolerance.trim() || null },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setMessage({ text: t("settings.brandingSaved"), error: false });
    } catch {
      setMessage({ text: t("settings.brandingSaveError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.workshop")}</h3>
      <p className="settings-hint">{t("settings.workshopHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <form noValidate className="payments-form" onSubmit={save}>
        <label>
          {t("settings.vanoTolerance")}
          <input
            inputMode="decimal"
            maxLength={8}
            value={tolerance}
            onChange={(event) => setTolerance(event.target.value)}
          />
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.brandingSave")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** D06 — org extras policy: how sublines print on the offer, plus the
 * default templates preselected into new vanos (extra articles, per
 * system) and new projects (services). All references are catalog rows —
 * a template never carries a price, the engine re-measures it. */
function OrgExtrasCard({ orgId }: { orgId: string }): JSX.Element {
  const [display, setDisplay] = useState<"DETAILED" | "GROUPED">("DETAILED");
  const [extraTemplates, setExtraTemplates] = useState<ExtraTemplateWriteRequest[]>([]);
  const [serviceTemplates, setServiceTemplates] = useState<string[]>([]);
  const [extras, setExtras] = useState<ExtraArticleResponse[]>([]);
  const [services, setServices] = useState<ServiceArticleResponse[]>([]);
  const [pickExtra, setPickExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  const load = useCallback(async () => {
    try {
      const [config, extraList, serviceList] = await Promise.all([
        organizationExtrasConfigRead(requestOptions),
        catalogExtraarticleList({}, requestOptions),
        catalogServicearticleList({}, requestOptions),
      ]);
      if (config.status !== 200 || extraList.status !== 200 || serviceList.status !== 200)
        throw new ApiError(config.status, config.data);
      setDisplay(config.data.extras_display === "GROUPED" ? "GROUPED" : "DETAILED");
      setExtraTemplates(
        (config.data.extra_templates ?? []).map((template) => ({
          extra_article_id: template.extra_article_id,
          sides: (template.sides ?? []) as ExtraTemplateWriteRequest["sides"],
          qty: template.qty,
        })),
      );
      setServiceTemplates([...(config.data.service_templates ?? [])]);
      setExtras(extraList.data.items);
      setServices(serviceList.data.items);
    } catch {
      setMessage({ text: t("settings.extrasLoadError"), error: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void load();
  }, [load]);

  const chosen = new Set(extraTemplates.map((template) => template.extra_article_id));
  const serviceChosen = new Set(serviceTemplates);
  const extraById = new Map(extras.map((article) => [article.id, article]));

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationExtrasConfigUpdate(
        {
          extras_display: display,
          extra_templates: extraTemplates,
          service_templates: serviceTemplates,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setMessage({ text: t("settings.extrasSaved"), error: false });
    } catch {
      setMessage({ text: t("settings.extrasError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.extras")}</h3>
      <p className="settings-hint">{t("settings.extrasHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <form noValidate className="payments-form" onSubmit={save}>
        <fieldset>
          <legend>{t("settings.extrasDisplay")}</legend>
          {(["DETAILED", "GROUPED"] as const).map((option) => (
            <label key={option} className="settings-choice">
              <input
                type="radio"
                name="extras-display"
                checked={display === option}
                onChange={() => setDisplay(option)}
              />
              <span>{tDynamic("settings.extrasDisplay", option)}</span>
            </label>
          ))}
        </fieldset>
        <fieldset>
          <legend>{t("settings.extraTemplates")}</legend>
          {extraTemplates.length === 0 && (
            <p className="settings-hint">{t("settings.extraTemplatesEmpty")}</p>
          )}
          <ul className="settings-list settings-plain">
            {extraTemplates.map((template, index) => {
              const article = extraById.get(template.extra_article_id);
              return (
                <li key={template.extra_article_id}>
                  <span>
                    {article?.name ?? template.extra_article_id}
                    {article ? ` · ${article.sku}` : ""}
                  </span>{" "}
                  <button
                    type="button"
                    className="ui-button ui-button--ghost"
                    disabled={busy}
                    onClick={() =>
                      setExtraTemplates((prev) => prev.filter((_, at) => at !== index))
                    }
                  >
                    {t("settings.extraTemplateRemove")}
                  </button>
                </li>
              );
            })}
          </ul>
          <select
            className="assembly-select"
            aria-label={t("settings.extraTemplateAdd")}
            disabled={busy}
            value={pickExtra}
            onChange={(event) => {
              const articleId = event.target.value;
              setPickExtra("");
              const article = extraById.get(articleId);
              if (!article || chosen.has(articleId)) return;
              setExtraTemplates((prev) => [...prev, { extra_article_id: articleId }]);
            }}
          >
            <option value="">{t("settings.extraTemplateAdd")}</option>
            {extras
              .filter((article) => !chosen.has(article.id))
              .map((article) => (
                <option key={article.id} value={article.id}>
                  {article.name} · {article.sku}
                  {tDynamic("catalog.extraKind", article.kind)
                    ? ` · ${tDynamic("catalog.extraKind", article.kind)}`
                    : ""}
                </option>
              ))}
          </select>
        </fieldset>
        <fieldset>
          <legend>{t("settings.serviceTemplates")}</legend>
          {services.length === 0 && (
            <p className="settings-hint">{t("settings.serviceTemplatesEmpty")}</p>
          )}
          <ul className="settings-list settings-plain">
            {services.map((service) => (
              <li key={service.id}>
                <label className="settings-choice">
                  <input
                    type="checkbox"
                    disabled={busy}
                    checked={serviceChosen.has(service.id)}
                    onChange={() =>
                      setServiceTemplates((prev) =>
                        prev.includes(service.id)
                          ? prev.filter((id) => id !== service.id)
                          : [...prev, service.id],
                      )
                    }
                  />
                  <span>
                    {service.name} · {service.code}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.extrasSave")}
          </button>
        </div>
      </form>
    </div>
  );
}

export function SettingsPage(): JSX.Element {
  const auth = useAuthSession();
  const { theme, toggleTheme } = useTheme();
  const me = auth.me;
  const org = me?.active_organization;
  const isOwner = org?.role === "OWNER";
  const canWriteDocs = org?.role === "OWNER" || org?.role === "ESTIMATOR";

  return (
    <section className="settings" aria-labelledby="page-title">
      <PageHeader
        context={org?.name ?? t("org.none")}
        headingId="page-title"
        title={t("settings.title")}
      />

      <section aria-labelledby="settings-group-account" className="settings-group">
        <h2 id="settings-group-account" className="settings-group__title">
          {t("settings.groupAccount")}
        </h2>
        <div className="settings-grid">
          <div className="settings-card">
            <h3 className="eyebrow">{t("settings.account")}</h3>
            <dl className="settings-list">
              <div className="settings-row">
                <dt>{t("settings.email")}</dt>
                <dd className="settings-mono">{me?.user.email}</dd>
              </div>
              <div className="settings-row">
                <dt>{t("settings.twoFactor")}</dt>
                <dd>{me?.aal === "aal2" ? t("settings.aal2") : t("settings.aal1")}</dd>
              </div>
              <div className="settings-row">
                <dt>{t("settings.role")}</dt>
                <dd>{org ? t(ROLE_KEYS[org.role]) : "—"}</dd>
              </div>
            </dl>
          </div>

          <div className="settings-card">
            <h3 className="eyebrow">{t("settings.appearance")}</h3>
            <div
              className="settings-theme"
              role="radiogroup"
              aria-label={t("settings.theme")}
              onKeyDown={(event) => {
                // Roving radio contract — arrows move the checked choice.
                if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
                event.preventDefault();
                const next = theme === "light" ? "dark" : "light";
                if (next !== theme) {
                  toggleTheme();
                  const options = event.currentTarget.querySelectorAll('[role="radio"]');
                  (options[next === "light" ? 0 : 1] as HTMLElement | undefined)?.focus();
                }
              }}
            >
              {(["light", "dark"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  role="radio"
                  aria-checked={theme === option}
                  className="settings-theme-option"
                  data-active={theme === option}
                  tabIndex={theme === option ? 0 : -1}
                  onClick={() => {
                    if (theme !== option) toggleTheme();
                  }}
                >
                  {option === "light" ? t("settings.light") : t("settings.dark")}
                </button>
              ))}
            </div>
          </div>

          {me !== null && me.memberships.length > 0 && (
            <div className="settings-card">
              <h3 className="eyebrow">{t("settings.memberships")}</h3>
              <ul className="settings-list settings-plain">
                {me.memberships.map((membership) => (
                  <MembershipRow key={membership.organization_id} membership={membership} />
                ))}
              </ul>
            </div>
          )}

          {/* Every role gets the shortcuts reference — without it the
           * non-owner settings page ends after three small cards (review m9). */}
          <div className="settings-card">
            <h3 className="eyebrow">{t("settings.shortcuts")}</h3>
            <dl className="settings-list">
              <div className="settings-row">
                <dt>{t("settings.shortcutPalette")}</dt>
                <dd>
                  <kbd>{MOD_K_HINT}</kbd> / <kbd>/</kbd>
                </dd>
              </div>
              <div className="settings-row">
                <dt>{t("settings.shortcutEsc")}</dt>
                <dd>
                  <kbd>Esc</kbd>
                </dd>
              </div>
              <div className="settings-row">
                <dt>{t("settings.shortcutUndo")}</dt>
                <dd>
                  <kbd>{MOD_KEY_HINT}Z</kbd> / <kbd>{MOD_KEY_HINT}Shift Z</kbd>
                </dd>
              </div>
            </dl>
          </div>
        </div>
      </section>

      {canWriteDocs && org !== undefined && (
        <section aria-labelledby="settings-group-docs" className="settings-group">
          <h2 id="settings-group-docs" className="settings-group__title">
            {t("settings.groupDocs")}
          </h2>
          <div className="settings-grid">
            <OrgBrandingCard orgId={org.id} />
            <MailStatusCard orgId={org.id} />
            <WorkshopRulesCard orgId={org.id} />
            <OrgExtrasCard orgId={org.id} />
          </div>
        </section>
      )}

      {isOwner && org !== undefined && (
        <section aria-labelledby="settings-group-charging" className="settings-group">
          <h2 id="settings-group-charging" className="settings-group__title">
            {t("settings.groupCharging")}
          </h2>
          <div className="settings-grid">
            <FlowIntegrationCard orgId={org.id} />
            <SiiCafCard orgId={org.id} />
            <SiiCertificateCard orgId={org.id} />
          </div>
        </section>
      )}

      {isOwner && org !== undefined && (
        <section aria-labelledby="settings-group-ai" className="settings-group">
          <h2 id="settings-group-ai" className="settings-group__title">
            {t("settings.groupAi")}
          </h2>
          <div className="settings-grid">
            <AiSettingsCard orgId={org.id} />
          </div>
        </section>
      )}

      {isOwner && (
        <section aria-labelledby="settings-group-plan" className="settings-group">
          <h2 id="settings-group-plan" className="settings-group__title">
            {t("settings.groupPlan")}
          </h2>
          <div className="settings-grid">
            <div className="settings-card">
              <h3 className="eyebrow">{t("settings.billing")}</h3>
              <p className="settings-hint">{t("settings.billingHint")}</p>
              <div className="settings-links">
                <Link className="ui-backlink" to="/settings/billing">
                  {t("settings.billingPage")}
                </Link>
                <Link className="ui-backlink" to="/settings/wallet">
                  {t("settings.walletPage")}
                </Link>
                <Link className="ui-backlink" to="/pricing/cost-lists">
                  {t("pricing.lists")}
                </Link>
              </div>
            </div>
          </div>
        </section>
      )}
    </section>
  );
}
