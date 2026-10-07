import { useCallback, useEffect, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link, useParams } from "react-router-dom";

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
  organizationDocumentPreview,
  organizationExtrasConfigRead,
  organizationExtrasConfigUpdate,
  organizationIntegrationsRead,
  organizationMembersInvite,
  organizationMembersList,
  organizationMemberUpdate,
  organizationNumberingRead,
  organizationSecurityUpdate,
  organizationSettingsCommercialUpdate,
  organizationSettingsCompanyUpdate,
  organizationSettingsDocumentsUpdate,
  organizationSettingsProductionUpdate,
  organizationSettingsRead,
  productionWorkCenters,
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
  OrgDocumentsSettingsDocPaperSizeEnum,
  OrgProductionSettingsWorkshopLabelFormatEnum,
  OrgIntegrationItem,
  OrgMembersResponse,
  OrgNumberingItem,
  WorkCenter,
  ExtraArticleResponse,
  ExtraTemplateWriteRequest,
  MailStatus,
  Membership,
  PaymentIntegrationStatus,
  MembershipRoleEnum,
  ServiceArticleResponse,
  SiiCaf,
  SiiCertificate,
  SiiIntegrationState,
} from "../api/generated/models";
import { PageHeader } from "../ui";
import { StatusChip } from "../ui/StatusChip";
import { StatusBadge } from "../ui/StatusBadge";
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
        {status?.provider_mode === "mock" && (
          <StatusChip label={t("settings.flowSimulated")} tone="warn" value={null} />
        )}
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
  const [integration, setIntegration] = useState<SiiIntegrationState | null>(null);
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
      setIntegration(response.data.integration);
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
      {integration && (
        <p>
          <StatusChip
            label={
              integration.certified
                ? t("settings.siiConnected")
                : integration.adapter === "mock"
                  ? t("settings.siiSimulated")
                  : t("settings.siiNotConnected")
            }
            tone={integration.certified ? "ok" : "warn"}
            value={null}
          />
        </p>
      )}
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

/** P22 — Empresa: razón social, RUT, giro y el bloque de contacto que sale
 * en los documentos. Escribe por la API de ajustes (auditoría por sección). */
function CompanyCard({ orgId }: { orgId: string }): JSX.Element {
  const [form, setForm] = useState({
    name: "",
    tax_id: "",
    commercial_name: "",
    giro: "",
    brand_address: "",
    brand_phone: "",
    brand_email: "",
  });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    void (async () => {
      try {
        const response = await organizationSettingsRead(requestOptions);
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        const company = response.data.company as Record<string, string>;
        setForm({
          name: company.name ?? "",
          tax_id: company.tax_id ?? "",
          commercial_name: company.commercial_name ?? "",
          giro: company.giro ?? "",
          brand_address: company.brand_address ?? "",
          brand_phone: company.brand_phone ?? "",
          brand_email: company.brand_email ?? "",
        });
      } catch {
        setMessage({ text: t("settings.brandingLoadError"), error: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationSettingsCompanyUpdate(
        {
          name: form.name.trim() || undefined,
          tax_id: form.tax_id.trim() || undefined,
          commercial_name: form.commercial_name.trim() || undefined,
          giro: form.giro.trim() || undefined,
          brand_address: form.brand_address.trim() || undefined,
          brand_phone: form.brand_phone.trim() || undefined,
          brand_email: form.brand_email.trim() || undefined,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setMessage({ text: t("settings.brandingSaved"), error: false });
    } catch (caught) {
      const text =
        caught instanceof ApiError && caught.status === 400
          ? t("settings.companyRutError")
          : t("settings.brandingSaveError");
      setMessage({ text, error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.company")}</h3>
      <p className="settings-hint">{t("settings.companyHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <form noValidate className="payments-form" onSubmit={save}>
        <label>
          {t("settings.companyName")}
          <input
            required
            maxLength={255}
            value={form.name}
            onChange={(event) => setForm((p) => ({ ...p, name: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.companyRut")}
          <input
            maxLength={50}
            value={form.tax_id}
            onChange={(event) => setForm((p) => ({ ...p, tax_id: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingName")}
          <input
            maxLength={255}
            value={form.commercial_name}
            onChange={(event) => setForm((p) => ({ ...p, commercial_name: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingGiro")}
          <input
            maxLength={255}
            value={form.giro}
            onChange={(event) => setForm((p) => ({ ...p, giro: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingAddress")}
          <input
            maxLength={255}
            value={form.brand_address}
            onChange={(event) => setForm((p) => ({ ...p, brand_address: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingPhone")}
          <input
            maxLength={64}
            value={form.brand_phone}
            onChange={(event) => setForm((p) => ({ ...p, brand_phone: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.brandingEmail")}
          <input
            type="email"
            maxLength={255}
            value={form.brand_email}
            onChange={(event) => setForm((p) => ({ ...p, brand_email: event.target.value }))}
          />
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.companySave")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** P22 — marca del documento: logo y color de acento. El resto de la
 * identidad vive en la tarjeta Empresa (datos legales) y en Documentos
 * (papel, textos, pie). */
function BrandMarkCard({ orgId }: { orgId: string }): JSX.Element {
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [pickFile, setPickFile] = useState<File | null>(null);
  const pickRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [brandColor, setBrandColor] = useState("");
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  const [tealFallback] = useState(() =>
    typeof document === "undefined"
      ? ""
      : getComputedStyle(document.documentElement).getPropertyValue("--teal-800").trim(),
  );

  const load = useCallback(async () => {
    try {
      const response = await organizationBrandingGet(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setBrandColor(response.data.brand_color ?? "");
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
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationBrandingSave(
        { brand_color: brandColor.trim() ? brandColor.toUpperCase() : null },
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
      <h3 className="eyebrow">{t("settings.brandMark")}</h3>
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
          {t("settings.brandColor")}
          <span className="settings-branding-color">
            <input
              aria-label={t("settings.brandColor")}
              type="color"
              value={/^#[0-9A-Fa-f]{6}$/.test(brandColor) ? brandColor : tealFallback}
              onChange={(event) => setBrandColor(event.target.value.toUpperCase())}
            />
            <input
              maxLength={7}
              placeholder="#RRGGBB"
              value={brandColor}
              onChange={(event) => setBrandColor(event.target.value.toUpperCase())}
            />
          </span>
          <span className="settings-hint">{t("settings.brandColorHint")}</span>
          {brandColor !== "" &&
          /^#[0-9A-Fa-f]{6}$/.test(brandColor) &&
          !brandColorPassesAa(brandColor) ? (
            <span className="form-error">{t("settings.brandColorWarning")}</span>
          ) : null}
        </label>
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
/** P22 — Producción: reglas de montaje D07 (tolerancia de descuadre del
 * vano), antigüedad máxima de retazos y formato de etiquetas de taller. */
function ProductionRulesCard({ orgId }: { orgId: string }): JSX.Element {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const [tolerance, setTolerance] = useState("");
  const [remnantDays, setRemnantDays] = useState("");
  const [labelFormat, setLabelFormat] =
    useState<OrgProductionSettingsWorkshopLabelFormatEnum>("GRID");
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    void (async () => {
      try {
        const response = await organizationSettingsRead(requestOptions);
        if (response.status !== 200) return;
        const production = response.data.production as Record<string, string | number>;
        setTolerance(String(production.vano_spread_tolerance_mm ?? "10.00"));
        setRemnantDays(String(production.remnant_alert_days ?? 30));
        setLabelFormat(
          (production.workshop_label_format ??
            "GRID") as OrgProductionSettingsWorkshopLabelFormatEnum,
        );
      } catch {
        /* la tarjeta principal ya reporta el fallo de carga */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    const days = Number.parseInt(remnantDays.trim(), 10);
    if (!Number.isFinite(days) || days < 1 || days > 365) {
      setMessage({ text: t("settings.remnantDaysError"), error: true });
      setBusy(false);
      return;
    }
    try {
      const response = await organizationSettingsProductionUpdate(
        {
          vano_spread_tolerance_mm: tolerance.trim() || null,
          remnant_alert_days: days,
          workshop_label_format: labelFormat,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setMessage({ text: t("settings.workshopSaved"), error: false });
    } catch {
      setMessage({ text: t("settings.workshopSaveError"), error: true });
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
        <label>
          {t("settings.remnantDays")}
          <input
            inputMode="numeric"
            maxLength={3}
            value={remnantDays}
            onChange={(event) => setRemnantDays(event.target.value)}
          />
        </label>
        <label>
          {t("settings.labelFormat")}
          <select
            value={labelFormat}
            onChange={(event) =>
              setLabelFormat(event.target.value as OrgProductionSettingsWorkshopLabelFormatEnum)
            }
          >
            <option value="GRID">{t("settings.labelFormatGrid")}</option>
            <option value="THERMAL_100X50">{t("settings.labelFormatRoll")}</option>
          </select>
          <span className="settings-hint">{t("settings.labelFormatHint")}</span>
        </label>
        <p className="settings-hint">{t("settings.remnantDaysHint")}</p>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.workshopSave")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** P22 — Estaciones de la ruta productiva: lectura de los centros de trabajo
 * activos de la org (la edición vive en el flujo de producción). */
function StationsCard({ orgId }: { orgId: string }): JSX.Element {
  const [items, setItems] = useState<WorkCenter[] | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    let cancelled = false;
    void productionWorkCenters(requestOptions)
      .then((response) => {
        if (!cancelled && response.status === 200) setItems(response.data.centers);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.stations")}</h3>
      <p className="settings-hint">{t("settings.stationsHint")}</p>
      {items === null ? (
        <p className="settings-hint">{t("projects.loading")}</p>
      ) : items.length === 0 ? (
        <p className="settings-hint">{t("settings.stationsEmpty")}</p>
      ) : (
        <ul className="settings-list settings-plain">
          {items.map((item) => (
            <li className="settings-row" key={item.id}>
              <span>{item.name}</span>
              <StatusChip enumName="WorkCenterRequestKindEnum" value={item.kind} />
            </li>
          ))}
        </ul>
      )}
      <p className="settings-hint">
        <Link className="ui-backlink" to="/production">
          {t("settings.stationsOpen")}
        </Link>
      </p>
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

/** P22 — Comercial: moneda, IVA, vigencia por defecto, banda de margen y
 * umbral de descuento con aprobación. Las fracciones viajan como texto
 * decimal (la API habla Decimal). */
function CommercialCard({ orgId }: { orgId: string }): JSX.Element {
  const [form, setForm] = useState({
    currency: "CLP",
    tax_rate_pct: "0.19",
    doc_validity_days: "15",
    default_margin_pct: "",
    margin_min_pct: "",
    margin_max_pct: "",
    discount_approval_threshold_pct: "0.10",
  });
  const [rulesConfigured, setRulesConfigured] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    void (async () => {
      try {
        const response = await organizationSettingsRead(requestOptions);
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        const commercial = response.data.commercial as Record<string, string | number>;
        setRulesConfigured(Boolean(commercial.rules_configured));
        setForm({
          currency: String(commercial.currency ?? "CLP"),
          tax_rate_pct: String(commercial.tax_rate_pct ?? "0.19"),
          doc_validity_days: String(commercial.doc_validity_days ?? 15),
          default_margin_pct: String(commercial.default_margin_pct ?? ""),
          margin_min_pct: String(commercial.margin_min_pct ?? ""),
          margin_max_pct: String(commercial.margin_max_pct ?? ""),
          discount_approval_threshold_pct: String(
            commercial.discount_approval_threshold_pct ?? "0.10",
          ),
        });
      } catch {
        setMessage({ text: t("settings.brandingLoadError"), error: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    const days = Number.parseInt(form.doc_validity_days, 10);
    if (!Number.isFinite(days) || days < 1 || days > 365) {
      setMessage({ text: t("settings.validityError"), error: true });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationSettingsCommercialUpdate(
        {
          currency: form.currency as "CLP" | "USD" | "UF",
          tax_rate_pct: form.tax_rate_pct.trim() || undefined,
          doc_validity_days: days,
          default_margin_pct: form.default_margin_pct.trim() || undefined,
          margin_min_pct: form.margin_min_pct.trim() || null,
          margin_max_pct: form.margin_max_pct.trim() || null,
          discount_approval_threshold_pct: form.discount_approval_threshold_pct.trim() || undefined,
        },
        requestOptions,
      );
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setRulesConfigured(true);
      setMessage({ text: t("settings.brandingSaved"), error: false });
    } catch (caught) {
      const status = caught instanceof ApiError ? caught.status : 0;
      setMessage({
        text: t(status === 400 ? "settings.commercialError" : "settings.commercialSaveError"),
        error: true,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.commercial")}</h3>
      <p className="settings-hint">{t("settings.commercialHint")}</p>
      {!rulesConfigured && <p className="settings-hint">{t("settings.commercialNoRules")}</p>}
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <form noValidate className="payments-form" onSubmit={save}>
        <label>
          {t("settings.commercialCurrency")}
          <select
            value={form.currency}
            onChange={(event) => setForm((p) => ({ ...p, currency: event.target.value }))}
          >
            <option value="CLP">CLP</option>
            <option value="USD">USD</option>
            <option value="UF">UF</option>
          </select>
        </label>
        <label>
          {t("settings.commercialTax")}
          <input
            inputMode="decimal"
            maxLength={8}
            value={form.tax_rate_pct}
            onChange={(event) => setForm((p) => ({ ...p, tax_rate_pct: event.target.value }))}
          />
          <span className="settings-hint">{t("settings.commercialTaxHint")}</span>
        </label>
        <label>
          {t("settings.commercialValidity")}
          <input
            inputMode="numeric"
            maxLength={3}
            value={form.doc_validity_days}
            onChange={(event) => setForm((p) => ({ ...p, doc_validity_days: event.target.value }))}
          />
          <span className="settings-hint">{t("settings.commercialValidityHint")}</span>
        </label>
        <label>
          {t("settings.commercialMargin")}
          <input
            inputMode="decimal"
            maxLength={8}
            value={form.default_margin_pct}
            onChange={(event) => setForm((p) => ({ ...p, default_margin_pct: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.commercialMarginMin")}
          <input
            inputMode="decimal"
            maxLength={8}
            value={form.margin_min_pct}
            onChange={(event) => setForm((p) => ({ ...p, margin_min_pct: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.commercialMarginMax")}
          <input
            inputMode="decimal"
            maxLength={8}
            value={form.margin_max_pct}
            onChange={(event) => setForm((p) => ({ ...p, margin_max_pct: event.target.value }))}
          />
        </label>
        <label>
          {t("settings.commercialDiscount")}
          <input
            inputMode="decimal"
            maxLength={8}
            value={form.discount_approval_threshold_pct}
            onChange={(event) =>
              setForm((p) => ({ ...p, discount_approval_threshold_pct: event.target.value }))
            }
          />
          <span className="settings-hint">{t("settings.commercialDiscountHint")}</span>
        </label>
        <p className="settings-hint">{t("settings.commercialFractions")}</p>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.commercialSave")}
          </button>
        </div>
      </form>
    </div>
  );
}

const DOC_TERM_ROWS = [
  ["pago", "settings.docTermsPago"],
  ["plazo_entrega", "settings.docTermsPlazo"],
  ["instalacion", "settings.docTermsInstalacion"],
  ["exclusiones", "settings.docTermsExclusiones"],
  ["garantia", "settings.docTermsGarantia"],
  ["jurisdiccion", "settings.docTermsJurisdiccion"],
] as const;

/** P22 — Documentos: papel, textos legales y pie white-label, con vista
 * previa real del DOC-01 renderizado por el backend (momento de firma). */
function DocumentsCard({ orgId }: { orgId: string }): JSX.Element {
  const [form, setForm] = useState({
    doc_paper_size: "LETTER" as OrgDocumentsSettingsDocPaperSizeEnum,
    doc_dekopen_credit: false,
    doc_terms: {
      pago: "",
      plazo_entrega: "",
      instalacion: "",
      exclusiones: "",
      garantia: "",
      jurisdiccion: "",
    } as Record<string, string>,
  });
  const [previewHtml, setPreviewHtml] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };
  const previewTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshPreview = useCallback(
    async (draft: typeof form) => {
      try {
        const docTerms = Object.fromEntries(
          Object.entries(draft.doc_terms)
            .map(([key, value]) => [key, value.trim()])
            .filter(([, value]) => value !== ""),
        );
        const response = await organizationDocumentPreview(
          {
            doc_paper_size: draft.doc_paper_size,
            doc_dekopen_credit: draft.doc_dekopen_credit,
            doc_terms: docTerms,
          },
          requestOptions,
        );
        if (response.status === 200) setPreviewHtml(response.data.html);
      } catch {
        /* la vista previa es progresiva — el error lo informa el guardado */
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [orgId],
  );

  useEffect(() => {
    void (async () => {
      try {
        const response = await organizationSettingsRead(requestOptions);
        if (response.status !== 200) throw new ApiError(response.status, response.data);
        const documents = response.data.documents as Record<string, string | boolean>;
        const terms = (documents.doc_terms ?? {}) as Record<string, string>;
        setForm((previous) => {
          const next = {
            doc_paper_size: (documents.doc_paper_size ??
              "LETTER") as OrgDocumentsSettingsDocPaperSizeEnum,
            doc_dekopen_credit: Boolean(documents.doc_dekopen_credit),
            doc_terms: { ...previous.doc_terms, ...terms },
          };
          void refreshPreview(next);
          return next;
        });
      } catch {
        setMessage({ text: t("settings.brandingLoadError"), error: true });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  function queuePreview(next: typeof form): void {
    setForm(next);
    if (previewTimer.current) clearTimeout(previewTimer.current);
    previewTimer.current = setTimeout(() => void refreshPreview(next), 350);
  }

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();
    const docTerms = Object.fromEntries(
      Object.entries(form.doc_terms)
        .map(([key, value]) => [key, value.trim()])
        .filter(([, value]) => value !== ""),
    );
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationSettingsDocumentsUpdate(
        {
          doc_paper_size: form.doc_paper_size,
          doc_terms: docTerms,
          doc_dekopen_credit: form.doc_dekopen_credit,
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

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.documents")}</h3>
      <p className="settings-hint">{t("settings.documentsHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <form noValidate className="payments-form" onSubmit={save}>
        <label>
          {t("settings.docPaperSize")}
          <select
            value={form.doc_paper_size}
            onChange={(event) =>
              queuePreview({
                ...form,
                doc_paper_size: event.target.value as OrgDocumentsSettingsDocPaperSizeEnum,
              })
            }
          >
            <option value="LETTER">{t("settings.docPaperLetter")}</option>
            <option value="LEGAL">{t("settings.docPaperLegal")}</option>
            <option value="A4">{t("settings.docPaperA4")}</option>
          </select>
        </label>
        {DOC_TERM_ROWS.map(([key, labelKey]) => (
          <label key={key}>
            {t(labelKey)}
            <textarea
              maxLength={4000}
              rows={2}
              value={form.doc_terms[key] ?? ""}
              onChange={(event) =>
                queuePreview({
                  ...form,
                  doc_terms: { ...form.doc_terms, [key]: event.target.value },
                })
              }
            />
          </label>
        ))}
        <label className="settings-branding-credit">
          <input
            checked={form.doc_dekopen_credit}
            onChange={(event) =>
              queuePreview({ ...form, doc_dekopen_credit: event.target.checked })
            }
            type="checkbox"
          />
          {t("settings.brandCredit")}
          <span className="settings-hint">{t("settings.brandCreditHint")}</span>
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.documentsSave")}
          </button>
        </div>
      </form>
      <div className="settings-preview">
        <h4 className="eyebrow">{t("settings.previewTitle")}</h4>
        {previewHtml ? (
          <iframe
            className="settings-preview__frame"
            sandbox=""
            title={t("settings.previewTitle")}
            srcDoc={previewHtml}
          />
        ) : (
          <p className="settings-hint">{t("settings.previewLoading")}</p>
        )}
      </div>
    </div>
  );
}

/** P22 — Numeración: solo lectura — los contadores se muestran para
 * informar el siguiente folio; cambiarlos es una decisión explícita que
 * se hace con soporte (y queda auditada). */
function NumberingCard({ orgId }: { orgId: string }): JSX.Element {
  const [items, setItems] = useState<OrgNumberingItem[] | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    let cancelled = false;
    void organizationNumberingRead(requestOptions)
      .then((response) => {
        if (!cancelled && response.status === 200) setItems(response.data.items);
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  const KIND_LABELS: Record<string, string> = {
    projects: "Proyecto",
    workshop_orders: "Orden de trabajo",
    purchase_orders: "Orden de compra",
    remnants: "Retazo",
    order_receipts: "Recepción de insumos",
    dispatch_notes: "Guía de despacho",
    invoices: "Factura",
    payment_receipts: "Comprobante de pago",
    credit_notes: "Nota de crédito",
  };

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.numbering")}</h3>
      <p className="settings-hint">{t("settings.numberingHint")}</p>
      {items === null ? (
        <p className="settings-hint">{t("projects.loading")}</p>
      ) : (
        <table className="payments-table">
          <thead>
            <tr>
              <th>{t("settings.numberingDoc")}</th>
              <th>{t("settings.numberingPrefix")}</th>
              <th>{t("settings.numberingNext")}</th>
              <th>{t("settings.numberingPattern")}</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.kind}>
                <td>{KIND_LABELS[item.kind] ?? item.kind}</td>
                <td className="settings-mono">{item.prefix}</td>
                <td className="settings-mono">{item.next}</td>
                <td className="settings-mono">{item.pattern}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

/** P22 — Integraciones diferidas: estado real por integración
 * (configurado / no configurado / error) con el paso de ACTIVACION.md que
 * corresponde. Sin secretos — solo estado. */
function IntegrationsCard({ orgId }: { orgId: string }): JSX.Element {
  const [items, setItems] = useState<OrgIntegrationItem[] | null>(null);
  const [runbook, setRunbook] = useState("");
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    let cancelled = false;
    void organizationIntegrationsRead(requestOptions)
      .then((response) => {
        if (!cancelled && response.status === 200) {
          setItems(response.data.items);
          setRunbook(response.data.runbook);
        }
      })
      .catch(() => {
        if (!cancelled) setItems([]);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  const STATE_LABELS: Record<string, string> = {
    configured: t("settings.integrationConfigured"),
    partial: t("settings.integrationPartial"),
    not_configured: t("settings.integrationMissing"),
    error: t("settings.integrationError"),
  };

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.integrations")}</h3>
      <p className="settings-hint">{t("settings.integrationsHint")}</p>
      {items === null ? (
        <p className="settings-hint">{t("projects.loading")}</p>
      ) : (
        <ul className="settings-list settings-plain">
          {items.map((item) => (
            <li className="settings-integration" key={item.key}>
              <div className="settings-row">
                <strong>{item.name}</strong>
                <StatusBadge
                  tone={
                    item.state === "configured"
                      ? "success"
                      : item.state === "error"
                        ? "warning"
                        : "neutral"
                  }
                  label={STATE_LABELS[item.state] ?? item.state}
                />
              </div>
              <p className="settings-hint">{item.detail}</p>
              <p className="settings-hint">
                {t("settings.integrationActivation")} {item.activation}
              </p>
            </li>
          ))}
        </ul>
      )}
      {runbook ? <p className="settings-hint settings-mono">{runbook}</p> : null}
    </div>
  );
}

const MEMBER_ROLES = ["OWNER", "ESTIMATOR", "WORKSHOP_MANAGER", "OPERATOR", "INSTALLER"] as const;

/** P22 — Usuarios y roles: la membresía viva + invitaciones pendientes.
 * Solo el dueño gestiona; la desactivación propia y el último dueño están
 * bloqueados también en backend. */
function MembersCard({ orgId, myUserId }: { orgId: string; myUserId: string }): JSX.Element {
  const [data, setData] = useState<OrgMembersResponse | null>(null);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<string>("ESTIMATOR");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  const load = useCallback(async () => {
    try {
      const response = await organizationMembersList(requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setData(response.data);
    } catch {
      setMessage({ text: t("settings.membersError"), error: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function invite(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationMembersInvite(
        { email: email.trim(), role: role as "ESTIMATOR" },
        requestOptions,
      );
      if (response.status !== 201) throw new ApiError(response.status, response.data);
      setEmail("");
      setMessage({ text: t("settings.memberInvited"), error: false });
      await load();
    } catch (caught) {
      const status = caught instanceof ApiError ? caught.status : 0;
      setMessage({
        text: t(status === 409 ? "settings.memberDuplicate" : "settings.membersError"),
        error: true,
      });
    } finally {
      setBusy(false);
    }
  }

  async function patchMember(
    membershipId: string,
    patch: { role?: MembershipRoleEnum; is_active?: boolean },
  ): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationMemberUpdate(membershipId, patch, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      await load();
    } catch {
      setMessage({ text: t("settings.membersError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.members")}</h3>
      <p className="settings-hint">{t("settings.membersHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      {data === null ? (
        <p className="settings-hint">{t("projects.loading")}</p>
      ) : (
        <>
          <ul className="settings-list settings-plain">
            {data.members.map((member) => (
              <li className="settings-row" key={member.membership_id}>
                <span>
                  {member.email}
                  {member.user_id === myUserId ? ` · ${t("settings.memberYou")}` : ""}
                </span>
                <span className="settings-members-actions">
                  <select
                    aria-label={t("settings.memberRole")}
                    disabled={busy || member.user_id === myUserId}
                    value={member.role}
                    onChange={(event) =>
                      void patchMember(member.membership_id, {
                        role: event.target.value as MembershipRoleEnum,
                      })
                    }
                  >
                    {MEMBER_ROLES.map((option) => (
                      <option key={option} value={option}>
                        {t(ROLE_KEYS[option as MembershipRoleEnum])}
                      </option>
                    ))}
                  </select>
                  {member.is_active ? (
                    <button
                      type="button"
                      className="ui-button ui-button--danger"
                      disabled={busy || member.user_id === myUserId}
                      onClick={() => void patchMember(member.membership_id, { is_active: false })}
                    >
                      {t("settings.memberDeactivate")}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="ui-button"
                      disabled={busy}
                      onClick={() => void patchMember(member.membership_id, { is_active: true })}
                    >
                      {t("settings.memberReactivate")}
                    </button>
                  )}
                  {member.totp_enabled ? <StatusBadge tone="success" label="2FA" /> : null}
                </span>
              </li>
            ))}
          </ul>
          {data.invitations.length > 0 && (
            <ul className="settings-list settings-plain">
              {data.invitations.map((invite) => (
                <li className="settings-row" key={invite.id}>
                  <span>{invite.email}</span>
                  <span className="settings-mono">
                    {t("settings.memberPending")} ·{" "}
                    {t(ROLE_KEYS[invite.role as MembershipRoleEnum] ?? "role.estimator")}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <form noValidate className="payments-form" onSubmit={invite}>
        <label>
          {t("settings.memberEmail")}
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label>
          {t("settings.memberInviteRole")}
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            {MEMBER_ROLES.filter((option) => option !== "OWNER").map((option) => (
              <option key={option} value={option}>
                {t(ROLE_KEYS[option as MembershipRoleEnum])}
              </option>
            ))}
          </select>
          <span className="settings-hint">{t("settings.memberOwnerHint")}</span>
        </label>
        <div className="payments-form-actions">
          <button type="submit" className="primary-action" disabled={busy}>
            {t("settings.memberInvite")}
          </button>
        </div>
      </form>
    </div>
  );
}

/** P22 — 2FA obligatorio opcional por organización: solo el dueño. */
function SecurityCard({ orgId }: { orgId: string }): JSX.Element {
  const [required, setRequired] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; error: boolean } | null>(null);
  const requestOptions = { headers: { "X-Organization-ID": orgId } };

  useEffect(() => {
    void (async () => {
      try {
        const response = await organizationSettingsRead(requestOptions);
        if (response.status === 200) {
          const security = response.data.security as { require_totp?: boolean };
          setRequired(Boolean(security.require_totp));
        }
      } catch {
        /* el gestor de miembros ya reporta */
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orgId]);

  async function toggle(next: boolean): Promise<void> {
    setBusy(true);
    setMessage(null);
    try {
      const response = await organizationSecurityUpdate({ require_totp: next }, requestOptions);
      if (response.status !== 200) throw new ApiError(response.status, response.data);
      setRequired(next);
      setMessage({ text: t("settings.brandingSaved"), error: false });
    } catch {
      setMessage({ text: t("settings.brandingSaveError"), error: true });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="settings-card">
      <h3 className="eyebrow">{t("settings.security")}</h3>
      <p className="settings-hint">{t("settings.securityHint")}</p>
      {message && <p className={message.error ? "form-error" : "settings-hint"}>{message.text}</p>}
      <label className="settings-inline">
        <input
          type="checkbox"
          disabled={busy || required === null}
          checked={required === true}
          onChange={(event) => void toggle(event.target.checked)}
        />
        {t("settings.securityTotp")}
      </label>
    </div>
  );
}

const SECTION_KEYS = [
  "general",
  "empresa",
  "usuarios",
  "comercial",
  "documentos",
  "numeracion",
  "produccion",
  "integraciones",
  "plan",
] as const;

type SectionKey = (typeof SECTION_KEYS)[number];

const SECTION_LABELS: Record<SectionKey, TranslationKey> = {
  general: "settings.navGeneral",
  empresa: "settings.navEmpresa",
  usuarios: "settings.navUsuarios",
  comercial: "settings.navComercial",
  documentos: "settings.navDocumentos",
  numeracion: "settings.navNumeracion",
  produccion: "settings.navProduccion",
  integraciones: "settings.navIntegraciones",
  plan: "settings.navPlan",
};

/** La sección es escribible por OWNER+ESTIMATOR; usuarios y plan solo las
 * abre el dueño. OPERATOR/INSTALLER no ven ajustes (el backend tampoco
 * responde: READ_ROLES no los incluye). */
function sectionLocked(section: SectionKey, role: string | undefined): string | null {
  if (section === "usuarios" || section === "plan") {
    return role === "OWNER" ? null : t("settings.lockedOwner");
  }
  return null;
}

function DisabledSection({ reason }: { reason: string }): JSX.Element {
  return (
    <div className="settings-card settings-card--disabled">
      <p className="settings-hint">
        {t("settings.availableWhen")} {reason}
      </p>
    </div>
  );
}

/** Ajustes por dominio: navegación lateral por sección — /settings/<slug>
 * — con el contenido real de cada dominio y estados deshabilitados cuando
 * la sección no aplica al rol. */
export function SettingsPage(): JSX.Element {
  const auth = useAuthSession();
  const { theme, toggleTheme } = useTheme();
  const { section } = useParams<{ section?: string }>();
  const me = auth.me;
  const org = me?.active_organization;
  const role = org?.role;
  const canWrite = role === "OWNER" || role === "ESTIMATOR";
  const active: SectionKey = (SECTION_KEYS as readonly string[]).includes(section ?? "")
    ? (section as SectionKey)
    : "general";
  const locked = sectionLocked(active, role);

  return (
    <section className="settings" aria-labelledby="page-title">
      <PageHeader
        context={org?.name ?? t("org.none")}
        headingId="page-title"
        title={t("settings.title")}
      />
      <div className="settings-layout">
        <nav className="settings-nav" aria-label={t("settings.navAria")}>
          {SECTION_KEYS.map((key) => {
            const lock = sectionLocked(key, role);
            const isActive = key === active;
            return lock ? (
              <span
                key={key}
                className="settings-nav__link is-disabled"
                aria-disabled="true"
                title={lock}
              >
                {t(SECTION_LABELS[key])}
              </span>
            ) : (
              <Link
                key={key}
                aria-current={isActive ? "page" : undefined}
                className={`settings-nav__link${isActive ? " is-active" : ""}`}
                to={`/settings/${key}`}
              >
                {t(SECTION_LABELS[key])}
              </Link>
            );
          })}
        </nav>

        <div className="settings-content">
          {locked !== null ? (
            <DisabledSection reason={locked} />
          ) : active === "general" ? (
            <section className="settings-group">
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
          ) : active === "empresa" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                {canWrite ? (
                  <>
                    <CompanyCard orgId={org.id} />
                    <BrandMarkCard orgId={org.id} />
                  </>
                ) : (
                  <DisabledSection reason={t("settings.lockedWrite")} />
                )}
              </div>
            </section>
          ) : active === "usuarios" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                <MembersCard orgId={org.id} myUserId={me?.user.id ?? ""} />
                <SecurityCard orgId={org.id} />
              </div>
            </section>
          ) : active === "comercial" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                {canWrite ? (
                  <CommercialCard orgId={org.id} />
                ) : (
                  <DisabledSection reason={t("settings.lockedWrite")} />
                )}
              </div>
            </section>
          ) : active === "documentos" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                {canWrite ? (
                  <DocumentsCard orgId={org.id} />
                ) : (
                  <DisabledSection reason={t("settings.lockedWrite")} />
                )}
              </div>
            </section>
          ) : active === "numeracion" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                <NumberingCard orgId={org.id} />
              </div>
            </section>
          ) : active === "produccion" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                {canWrite ? (
                  <>
                    <ProductionRulesCard orgId={org.id} />
                    <OrgExtrasCard orgId={org.id} />
                  </>
                ) : (
                  <DisabledSection reason={t("settings.lockedWrite")} />
                )}
                <StationsCard orgId={org.id} />
              </div>
            </section>
          ) : active === "integraciones" && org ? (
            <section className="settings-group">
              <div className="settings-grid">
                <IntegrationsCard orgId={org.id} />
                {role === "OWNER" && (
                  <>
                    <FlowIntegrationCard orgId={org.id} />
                    <SiiCafCard orgId={org.id} />
                    <SiiCertificateCard orgId={org.id} />
                    <AiSettingsCard orgId={org.id} />
                  </>
                )}
                <MailStatusCard orgId={org.id} />
              </div>
            </section>
          ) : active === "plan" ? (
            <section className="settings-group">
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
          ) : null}
        </div>
      </div>
    </section>
  );
}
