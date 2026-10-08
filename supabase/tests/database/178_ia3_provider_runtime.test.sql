BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(13);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_routes'
          AND column_name IN ('timeout_s', 'retry_max', 'tools_enabled')
          AND table_name = 'ai_routes'
          AND column_name = 'tools_enabled'
    ),
    'ai_routes carries timeout_s / retry_max / tools_enabled'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.ai_routes'::regclass
          AND conname = 'ai_routes_retry_range'
    ),
    'retry_max is bounded to 0..4'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_routes'
          AND policyname = 'ai_routes_ai_backend_read'
          AND 'ai_backend' = ANY (roles)
    ),
    'ai_backend can read ai_routes (settings, probe, activity)'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'ai_invocations'
    ),
    'ai_invocations exists'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.ai_invocations'::regclass
          AND conname = 'ai_invocations_status_check'
    ),
    'invocation status is ok | error | blocked'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.ai_invocations'::regclass
          AND conname = 'ai_invocations_kind_check'
    ),
    'invocation kind is call | probe'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class WHERE relname = 'ai_invocations'),
    'ai_invocations enforces RLS'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_org_settings'
          AND column_name = 'monthly_credit_budget'
    ),
    'ai_org_settings carries monthly_credit_budget'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class WHERE relname = 'ai_org_settings'),
    'ai_org_settings enforces RLS'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'ai_model_prices'
    ),
    'ai_model_prices exists'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_audit_logs'
          AND column_name = 'est_cost_usd'
    ),
    'ai_audit_logs seals est_cost_usd'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'job_runs'
          AND column_name = 'progress_phase'
    ),
    'job_runs carries progress_phase'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_model_prices'
          AND column_name IN ('usd_per_mtok_input', 'usd_per_mtok_output')
          AND data_type = 'numeric'
          AND table_name = 'ai_model_prices'
          AND column_name = 'usd_per_mtok_input'
    ),
    'model tariffs are NUMERIC (no floats for money)'
);

SELECT * FROM finish();
ROLLBACK;
