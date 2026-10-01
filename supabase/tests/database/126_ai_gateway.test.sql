BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(20);

SELECT has_table('public', 'ai_routes', 'AI routing table exists');
SELECT has_column('public', 'ai_routes', 'public_name', 'white-label name is stored');
SELECT has_column('public', 'ai_routes', 'provider_model', 'real model stays on the route');
SELECT has_column('public', 'ai_routes', 'credits_cost', 'per-invocation price on the route');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.ai_routes'::regclass
          AND pg_get_constraintdef(oid) LIKE '%UNIQUE%(capability)%'
    ),
    'capability names are unique'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.ai_routes'::regclass
          AND pg_get_constraintdef(oid) LIKE '%credits_cost > 0%'
    ),
    'route prices are strictly positive credits'
);
SELECT ok(
    (SELECT count(*) = 9 FROM public.ai_routes
      WHERE provider = 'MIMO' AND provider_model = 'primalabs-ai/MiMo-V2.6-Pro-RL' AND enabled),
    'all nine capabilities are pinned to primalabs-ai/MiMo-V2.6-Pro-RL'
);
SELECT ok(
    (SELECT count(*) = 0 FROM public.ai_routes
      WHERE provider <> 'MIMO' OR provider_model <> 'primalabs-ai/MiMo-V2.6-Pro-RL'),
    'no route may resolve to another provider or model'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM public.ai_routes
        WHERE capability = 'agent' AND enabled
    ),
    'the orchestrating agent capability is routed'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class WHERE relname = 'ai_routes'),
    'routing table enforces RLS'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_routes'
          AND policyname = 'ai_routes_backend_read'
    ),
    'only the billing-scoped backend role may read routes'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.ai_routes', 'SELECT')
    AND NOT has_table_privilege('anon', 'public.ai_routes', 'SELECT')
    AND NOT has_table_privilege('authenticated', 'public.ai_routes', 'INSERT'),
    'tenants can never see provider internals'
);
SELECT ok(
    has_table_privilege('billing_backend', 'public.ai_routes', 'SELECT'),
    'billing backend resolves routes inside the financial transaction'
);
-- Audit hardening: tenants read their own rows, only billing_backend writes.
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.ai_audit_logs', 'INSERT')
    AND NOT has_table_privilege('authenticated', 'public.ai_audit_logs', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.ai_audit_logs', 'DELETE'),
    'tenant roles can never write audit rows'
);
SELECT ok(
    has_table_privilege('billing_backend', 'public.ai_audit_logs', 'INSERT'),
    'billing backend seals each invocation into the audit log'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.ai_audit_logs', 'SELECT'),
    'tenants keep read access to their own audit trail'
);
-- Idempotency: every operation_key lands at most one audit row per org.
SELECT has_column('public', 'ai_audit_logs', 'operation_key',
    'audit rows carry the caller-supplied operation key');
SELECT col_type_is('public', 'ai_audit_logs', 'model_used', 'character varying(120)',
    'audit accepts the widest route model name');
SELECT col_type_is('public', 'ai_audit_logs', 'operation_key', 'character varying(120)',
    'operation keys fit inside the audit row');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'ai_audit_logs'
          AND indexname = 'ai_audit_logs_org_operation_key'
          AND indexdef LIKE '%WHERE%'
    ),
    'operation keys are unique per org when present'
);

SELECT * FROM finish();
ROLLBACK;
