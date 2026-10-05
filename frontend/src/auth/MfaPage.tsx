import { type FormEvent, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";

import { t } from "../i18n/es-CL";
import { telemetry } from "../telemetry/telemetry";
import { useAuthSession } from "./AuthSessionProvider";
import { consumeReturnTo } from "./returnTo";
import { supabase } from "./supabaseClient";

type FactorState = {
  factorId: string;
  secret: string | null;
  qrCode: string | null;
};

export function MfaPage(): JSX.Element {
  const auth = useAuthSession();
  const [factor, setFactor] = useState<FactorState | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadingFactors, setLoadingFactors] = useState(true);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const client = supabase;
    if (client === null) return;
    let active = true;
    async function loadFactors(): Promise<void> {
      try {
        const assurance = await client!.auth.mfa.getAuthenticatorAssuranceLevel();
        if (assurance.error !== null) throw assurance.error;
        const listed = await client!.auth.mfa.listFactors();
        if (listed.error !== null) throw listed.error;
        if (!active) return;
        const existing = listed.data.totp.find((item) => item.status === "verified");
        if (existing) setFactor({ factorId: existing.id, secret: null, qrCode: null });
      } catch {
        if (active) setError(t("auth.mfaLoadError"));
      } finally {
        if (active) setLoadingFactors(false);
      }
    }
    void loadFactors();
    return () => {
      active = false;
    };
  }, []);

  if (auth.status === "ready") return <Navigate to={consumeReturnTo()} replace />;

  async function enroll(): Promise<void> {
    if (supabase === null) return;
    setError(null);
    setBusy(true);
    telemetry.capture("mfa_enrollment_started");
    const { data, error: enrollError } = await supabase.auth.mfa.enroll({
      factorType: "totp",
    });
    setBusy(false);
    if (enrollError !== null) {
      setError(t("auth.mfaEnrollError"));
      return;
    }
    setFactor({
      factorId: data.id,
      secret: data.totp.secret,
      qrCode: data.totp.qr_code,
    });
  }

  async function verify(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (supabase === null || factor === null) return;
    setError(null);
    setBusy(true);
    const challenge = await supabase.auth.mfa.challenge({ factorId: factor.factorId });
    if (challenge.error !== null) {
      setBusy(false);
      setError(t("auth.mfaChallengeError"));
      return;
    }
    const verified = await supabase.auth.mfa.verify({
      factorId: factor.factorId,
      challengeId: challenge.data.id,
      code,
    });
    if (verified.error !== null) {
      setBusy(false);
      setError(t("auth.mfaCodeError"));
      return;
    }
    const refreshed = await supabase.auth.refreshSession();
    const assurance = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    setBusy(false);
    if (
      refreshed.error !== null ||
      assurance.error !== null ||
      assurance.data.currentLevel !== "aal2"
    ) {
      setError(t("auth.mfaSessionError"));
      return;
    }
    telemetry.capture("mfa_verified", { aal: "aal2" });
    await auth.refreshContext();
  }

  return (
    <main className="auth-screen" data-testid="mfa-page">
      <section className="auth-card">
        <div className="auth-card__brand">
          <span className="brand">{t("app.brand")}</span>
          <span className="brand-os">{t("app.brandOs")}</span>
        </div>
        <header className="auth-card__header">
          <p className="eyebrow">{t("auth.mfaEyebrow")}</p>
          <h1>{t("auth.mfaTitle")}</h1>
          <p className="auth-hint">{t("auth.mfaWhy")}</p>
        </header>
        {factor === null ? (
          <button
            type="button"
            className="ui-button ui-button--primary"
            disabled={busy || loadingFactors}
            onClick={() => void enroll()}
          >
            {loadingFactors ? t("auth.mfaLoading") : t("auth.mfaEnroll")}
          </button>
        ) : (
          <>
            {factor.qrCode ? (
              <>
                <img className="auth-qr" src={factor.qrCode} alt={t("auth.mfaQr")} />
                <p className="auth-hint">{t("auth.mfaHow")}</p>
              </>
            ) : null}
            {factor.secret ? (
              <p className="auth-hint">
                {t("auth.mfaManual")} <code data-testid="totp-secret">{factor.secret}</code>
              </p>
            ) : null}
            <form noValidate className="auth-form" onSubmit={(event) => void verify(event)}>
              <label htmlFor="totp-code">{t("auth.mfaCode")}</label>
              <input
                id="totp-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={(event) => setCode(event.target.value)}
              />
              <button
                type="submit"
                className="ui-button ui-button--primary"
                disabled={busy || loadingFactors || code.trim() === ""}
              >
                {busy ? t("auth.mfaVerifying") : t("auth.mfaVerify")}
              </button>
            </form>
          </>
        )}
        {error ? (
          <p role="alert" className="auth-notice auth-notice--error">
            {error}
          </p>
        ) : null}
      </section>
    </main>
  );
}
