import { useEffect, useState } from "react";
import { walletRetrieve } from "../../api/generated/dekopen";
import type { Wallet } from "../../api/generated/models";
import { useAuthSession } from "../../auth/AuthSessionProvider";
import { Button, DeniedState, PageHeader } from "../../ui";
import { t } from "../../i18n/es-CL";
import "./billing.css";

export function WalletPage(): JSX.Element {
  const auth = useAuthSession();
  const org = auth.me?.active_organization;
  if (!org || org.role !== "OWNER") return <DeniedState reason={t("wallet.ownerOnly")} />;
  return <WalletWorkspace key={`${auth.session?.user.id}:${org.id}`} orgId={org.id} />;
}

function WalletWorkspace({ orgId }: { orgId: string }): JSX.Element {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    void walletRetrieve({ headers: { "X-Organization-ID": orgId }, signal: controller.signal })
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.status === 200) setWallet(result.data);
        else setFailed(true);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [orgId, revision]);
  const formatDate = (value: string) =>
    new Intl.DateTimeFormat("es-CL", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "America/Santiago",
    }).format(new Date(value));
  const number = (value: number) => new Intl.NumberFormat("es-CL").format(value);
  return (
    <section className="billing-page" aria-labelledby="page-title">
      <PageHeader
        actions={
          <Button onClick={() => setRevision((value) => value + 1)} variant="secondary">
            {t("wallet.refresh")}
          </Button>
        }
        headingId="page-title"
        title={t("wallet.title")}
      />
      {failed && <p role="alert">{t("wallet.error")}</p>}
      {!wallet && !failed && <p role="status">{t("wallet.loading")}</p>}
      {wallet && (
        <>
          <section aria-labelledby="wallet-balance" className="settings-group">
            <h2 id="wallet-balance" className="settings-group__title">
              {t("wallet.balanceTitle")}
            </h2>
            <div className="wallet-summary">
              <div>
                <p>{t("wallet.balance")}</p>
                <strong>{number(wallet.balance)}</strong>
              </div>
              <div>
                <p>{t("wallet.plan")}</p>
                <strong>{t(`billing.${wallet.plan}` as Parameters<typeof t>[0])}</strong>
              </div>
              {wallet.plan === "TRIAL" && wallet.trial_ends_at && (
                <div>
                  <p>{t("wallet.trialEnd")}</p>
                  <time dateTime={wallet.trial_ends_at}>{formatDate(wallet.trial_ends_at)}</time>
                </div>
              )}
            </div>
            {!wallet.ai_available && <p role="status">{t("wallet.manualAvailable")}</p>}
          </section>
          <section aria-labelledby="wallet-sources" className="settings-group">
            <h2 id="wallet-sources" className="settings-group__title">
              {t("wallet.sources")}
            </h2>
            <p>{t("wallet.sourcePolicy")}</p>
            <dl className="wallet-summary">
              {(["trial", "monthly", "pack", "legacy"] as const).map((origin) => (
                <div key={origin}>
                  <dt>{t(`wallet.origin.${origin}`)}</dt>
                  <dd>
                    {number(
                      wallet.lots
                        .filter((lot) => lot.origin === origin)
                        .reduce((sum, lot) => sum + lot.remaining, 0),
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          </section>
          <section aria-labelledby="wallet-history" className="settings-group">
            <h2 id="wallet-history" className="settings-group__title">
              {t("wallet.history")}
            </h2>
            <p>{t("wallet.historyLimit")}</p>
            {wallet.ledger.length === 0 ? (
              <p>{t("wallet.empty")}</p>
            ) : (
              <div className="wallet-table">
                <table>
                  <thead>
                    <tr>
                      <th>{t("wallet.date")}</th>
                      <th>{t("wallet.operation")}</th>
                      <th>{t("wallet.change")}</th>
                      <th>{t("wallet.balanceAfter")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {wallet.ledger.map((entry) => (
                      <tr key={entry.id}>
                        <td>
                          <time dateTime={entry.created_at}>{formatDate(entry.created_at)}</time>
                        </td>
                        <td>
                          {t(
                            entry.action_type === "TRIAL_GRANT"
                              ? "wallet.trialGrant"
                              : entry.action_type === "AI_DEBIT"
                                ? "wallet.aiDebit"
                                : entry.action_type === "CREDIT_EXPIRY"
                                  ? "wallet.expiry"
                                  : entry.action_type === "PAYMENT_GRANT" ||
                                      entry.action_type === "MONTHLY_GRANT" ||
                                      entry.action_type === "UPGRADE_GRANT"
                                    ? "wallet.paymentGrant"
                                    : "wallet.adjustment",
                          )}
                        </td>
                        <td>{number(entry.amount)}</td>
                        <td>{number(entry.balance_after)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
