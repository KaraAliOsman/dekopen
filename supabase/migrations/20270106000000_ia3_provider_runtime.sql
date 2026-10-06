BEGIN;

-- IA3 (real AI provider): transport options per capability, the durable
-- provider-call log, per-org AI settings (monthly budget), the model price
-- sheet, and the named intermediate progress phase the Orb renders.

-- 1) Per-capability transport options. Timeout and retry budget ride the
--    route so one capability can run patient and tool-rich while another
--    stays terse; NULL timeout keeps the provider's env/default value.
--    its own billing read + sealed provenance keep SELECT billing-scoped —
--    grant ai_backend the same config read. Nothing member-facing changes.
ALTER TABLE public.ai_routes
    ADD COLUMN timeout_s INT NULL
        CONSTRAINT ai_routes_timeout_range
        CHECK (timeout_s IS NULL OR timeout_s BETWEEN 1 AND 600),
    ADD COLUMN retry_max INT NOT NULL DEFAULT 2
        CONSTRAINT ai_routes_retry_range CHECK (retry_max BETWEEN 0 AND 4),
    ADD COLUMN tools_enabled BOOLEAN NOT NULL DEFAULT TRUE;
GRANT SELECT ON public.ai_routes TO ai_backend;

-- ai_backend reads routes for status/settings/activity (E2E finding: the
-- billing-only policy left _routes() empty → "Sin credencial" + dead probe).
CREATE POLICY ai_routes_ai_backend_read ON public.ai_routes
    FOR SELECT TO ai_backend
    USING (true);

-- 2) Named intermediate state alongside the numeric progress — the UI
--    renders "Consultando el proyecto" / "Calculando con el motor" /
--    "Preparando la propuesta" from a real phase, not a percent guess.
ALTER TABLE public.job_runs
    ADD COLUMN progress_phase VARCHAR(40) NULL;

-- 3) Estimated provider cost sealed at audit time (USD; NULL when the
--    model has no registered price — honest absence, never a fabricated
--    figure).
ALTER TABLE public.ai_audit_logs
    ADD COLUMN est_cost_usd NUMERIC(14,6) NULL;

-- 4) Provider price sheet — operational platform config like ai_routes:
--    backend roles read it to estimate cost; tenants never touch it.
CREATE TABLE public.ai_model_prices (
    provider VARCHAR(40) NOT NULL,
    provider_model VARCHAR(120) NOT NULL,
    usd_per_mtok_input NUMERIC(12,6) NOT NULL
        CHECK (usd_per_mtok_input >= 0),
    usd_per_mtok_output NUMERIC(12,6) NOT NULL
        CHECK (usd_per_mtok_output >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, provider_model)
);
ALTER TABLE public.ai_model_prices ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_model_prices_backend_read ON public.ai_model_prices
    FOR SELECT TO billing_backend, ai_backend
    USING (true);
GRANT SELECT ON public.ai_model_prices TO billing_backend, ai_backend;
REVOKE ALL ON public.ai_model_prices FROM anon, authenticated;

-- 5) Per-org AI settings — the monthly spend ceiling in wallet credits
--    (the unit the owner already reasons about). NULL = no cap. Members
--    may read their org's row; only the API writes it.
CREATE TABLE public.ai_org_settings (
    org_id UUID PRIMARY KEY REFERENCES public.tenancy_organizations(id),
    monthly_credit_budget INT NULL
        CONSTRAINT ai_org_settings_budget_nonneg
        CHECK (monthly_credit_budget IS NULL OR monthly_credit_budget >= 0),
    updated_by UUID NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.ai_org_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_org_settings_select ON public.ai_org_settings
    FOR SELECT TO authenticated, ai_backend, billing_backend
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY ai_org_settings_insert ON public.ai_org_settings
    FOR INSERT TO ai_backend
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY ai_org_settings_update ON public.ai_org_settings
    FOR UPDATE TO ai_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
GRANT SELECT ON public.ai_org_settings TO authenticated, billing_backend;
GRANT SELECT, INSERT, UPDATE ON public.ai_org_settings TO ai_backend;

-- 6) Durable AI call log — every committed provider invocation plus the
--    terminal error rows a failed run records post-rollback, with
--    capability, public model, tokens, latency, credits and estimated USD.
--    Content-free by design: no prompts, no outputs, no client payloads.
CREATE TABLE public.ai_invocations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    user_id UUID NULL,
    kind VARCHAR(16) NOT NULL DEFAULT 'call'
        CONSTRAINT ai_invocations_kind_check CHECK (kind IN ('call', 'probe')),
    capability VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100) NULL,
    operation_key VARCHAR(200) NULL,
    mode VARCHAR(12) NOT NULL DEFAULT 'live'
        CONSTRAINT ai_invocations_mode_check CHECK (mode IN ('live', 'test')),
    public_model VARCHAR(120) NULL,
    tokens_prompt INT NOT NULL DEFAULT 0,
    tokens_completion INT NOT NULL DEFAULT 0,
    latency_ms INT NOT NULL DEFAULT 0,
    credits INT NOT NULL DEFAULT 0,
    est_cost_usd NUMERIC(14,6) NULL,
    status VARCHAR(12) NOT NULL
        CONSTRAINT ai_invocations_status_check
        CHECK (status IN ('ok', 'error', 'blocked')),
    error_code VARCHAR(120) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.ai_invocations ENABLE ROW LEVEL SECURITY;
-- Reads mirror ai_audit_logs: the AI-caller role set, not plain membership.
CREATE POLICY ai_invocations_select ON public.ai_invocations
    FOR SELECT TO public
    USING (
        private.documentary_role(
            org_id, ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER']
        )
    );
CREATE POLICY ai_invocations_insert ON public.ai_invocations
    FOR INSERT TO ai_backend
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
GRANT SELECT ON public.ai_invocations TO authenticated;
GRANT INSERT, SELECT ON public.ai_invocations TO ai_backend;
CREATE INDEX ai_invocations_org_time_idx
    ON public.ai_invocations (org_id, created_at DESC);
CREATE INDEX ai_invocations_org_capability_idx
    ON public.ai_invocations (org_id, capability, created_at DESC);
CREATE INDEX ai_invocations_operation_idx
    ON public.ai_invocations (org_id, operation_key);

-- 7) Provider pin repair (IA1 finding #1, re-verified by IA3's probe): the
--    live credential is a xiaomimimo token-plan key whose endpoint serves
--    'mimo-v2.6-pro'; the primalabs pin 401s/429s against it. The wire
--    model follows the credential — operators may still override with
--    AI_GATEWAY_MIMO_MODEL when the account changes.
UPDATE public.ai_routes
SET provider_model = 'mimo-v2.6-pro', updated_at = NOW()
WHERE provider = 'MIMO' AND provider_model <> 'mimo-v2.6-pro';

COMMIT;
