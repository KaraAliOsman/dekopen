BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(18);

-- §B RBAC matrix — functional verification that PostgREST (the
-- `authenticated` role) is at least as restrictive as the Django role gates.
-- Domain writes flow through the documentary authority (`documentary_backend`
-- with the member's claims), so the tenant role gets SELECT-only on every
-- backend-owned table and role-gated writes only where the app itself writes
-- under `authenticated` (clients, ai_audit_logs inserts).

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('33333333-3333-4333-8333-333333333333', 'Tenant C', 'C-1');

INSERT INTO public.tenancy_memberships (org_id, user_id, role)
VALUES
    ('33333333-3333-4333-8333-333333333333',
     'cccccccc-0000-4000-8000-000000000001', 'ESTIMATOR'),
    ('33333333-3333-4333-8333-333333333333',
     'cccccccc-0000-4000-8000-000000000002', 'WORKSHOP_MANAGER'),
    ('33333333-3333-4333-8333-333333333333',
     'cccccccc-0000-4000-8000-000000000003', 'INSTALLER');

INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES (
    '33333333-aaaa-4333-8333-333333333333',
    '33333333-3333-4333-8333-333333333333',
    'QUOTE-C', 'Quote C', 'Client C',
    'cccccccc-0000-4000-8000-000000000001'
);

INSERT INTO public.orders (id, org_id, project_id, order_type, order_code, payload_json)
VALUES (
    '33333333-bbbb-4333-8333-333333333333',
    '33333333-3333-4333-8333-333333333333',
    '33333333-aaaa-4333-8333-333333333333',
    'WORKSHOP_OT', 'OT-C-1', '{}'::jsonb
);

INSERT INTO public.production_steps (org_id, order_id, sequence, code, label)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    '33333333-bbbb-4333-8333-333333333333',
    1, 'CUT', 'Corte'
);

INSERT INTO public.ai_audit_logs (
    org_id, user_id, tool_name, model_used, prompt_version, retention_until,
    input_payload, output_payload, state_hash_before
)
VALUES (
    '33333333-3333-4333-8333-333333333333',
    'cccccccc-0000-4000-8000-000000000001',
    'design_assist', 'primalabs-ai/MiMo-V2.6-Pro-RL', 'v1', now() + interval '30 days',
    '{}'::jsonb, '{}'::jsonb, 'hash'
);

-- ── ESTIMATOR under `authenticated` (the PostgREST surface) ────────────────
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-0000-4000-8000-000000000001', TRUE);

SELECT lives_ok(
    $$INSERT INTO public.clients (org_id, created_by, name)
      VALUES ('33333333-3333-4333-8333-333333333333',
              'cccccccc-0000-4000-8000-000000000001', 'Cliente Estimador')$$,
    'ESTIMATOR may create clients'
);
SELECT is(
    (SELECT count(*) FROM public.production_steps),
    1::BIGINT,
    'ESTIMATOR reads production steps'
);
SELECT throws_ok(
    $$UPDATE public.production_steps SET label='x'$$,
    '42501',
    NULL,
    'production steps are writable only through the backend role'
);
SELECT throws_ok(
    $$INSERT INTO public.inventory_items (org_id, sku, name, category, unit)
      VALUES ('33333333-3333-4333-8333-333333333333','S-1','n','c','u')$$,
    '42501',
    NULL,
    'inventory is writable only through the backend role'
);
SELECT throws_ok(
    $$INSERT INTO public.document_imports (org_id, project_id, created_by, file_name, kind, storage_path)
      VALUES ('33333333-3333-4333-8333-333333333333',
              '33333333-aaaa-4333-8333-333333333333',
              'cccccccc-0000-4000-8000-000000000001','f.pdf','QUOTE','k/f.pdf')$$,
    '42501',
    NULL,
    'document imports are writable only through the backend role'
);
SELECT throws_ok(
    $$INSERT INTO public.catalog_imports (org_id, created_by, file_name, kind, storage_path)
      VALUES ('33333333-3333-4333-8333-333333333333',
              'cccccccc-0000-4000-8000-000000000001','c.pdf','CATALOG','k/c.pdf')$$,
    '42501',
    NULL,
    'catalog imports are writable only through the backend role'
);
SELECT throws_ok(
    $$SELECT snapshot_json FROM public.project_versions LIMIT 1$$,
    '42501',
    NULL,
    'frozen snapshot column is denied to the tenant role'
);
SELECT throws_ok(
    $$UPDATE public.ai_audit_logs SET model_used='x'$$,
    '42501',
    NULL,
    'audit rows cannot be mutated by members'
);
SELECT is(
    (SELECT count(*) FROM public.ai_audit_logs),
    1::BIGINT,
    'members read their own usage ledger'
);

-- ── WORKSHOP_MANAGER under `authenticated` ─────────────────────────────────
RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-0000-4000-8000-000000000002","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-0000-4000-8000-000000000002', TRUE);

SELECT throws_ok(
    $$INSERT INTO public.clients (org_id, created_by, name)
      VALUES ('33333333-3333-4333-8333-333333333333',
              'cccccccc-0000-4000-8000-000000000002', 'Cliente Taller')$$,
    '42501',
    NULL,
    'WORKSHOP_MANAGER cannot create clients'
);
SELECT throws_ok(
    $$UPDATE public.production_steps SET label='Corte perfil'$$,
    '42501',
    NULL,
    'WORKSHOP_MANAGER cannot mutate steps via PostgREST'
);
SELECT throws_ok(
    $$INSERT INTO public.catalog_imports (org_id, created_by, file_name, kind, storage_path)
      VALUES ('33333333-3333-4333-8333-333333333333',
              'cccccccc-0000-4000-8000-000000000002','c.pdf','CATALOG','k/c2.pdf')$$,
    '42501',
    NULL,
    'WORKSHOP_MANAGER cannot insert catalog imports via PostgREST'
);

-- ── INSTALLER: read-only ───────────────────────────────────────────────────
RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-0000-4000-8000-000000000003","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-0000-4000-8000-000000000003', TRUE);

SELECT is(
    (SELECT count(*) FROM public.deliveries),
    0::BIGINT,
    'INSTALLER reads deliveries'
);
SELECT throws_ok(
    $$INSERT INTO public.deliveries (org_id, order_id, address, scheduled_date)
      VALUES ('33333333-3333-4333-8333-333333333333',
              '33333333-bbbb-4333-8333-333333333333','addr','2026-10-01')$$,
    '42501',
    NULL,
    'INSTALLER cannot schedule deliveries'
);

-- ── The backend path still works: documentary authority + member claims ────
RESET ROLE;
SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-0000-4000-8000-000000000002","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-0000-4000-8000-000000000002', TRUE);

SELECT lives_ok(
    $$INSERT INTO public.inventory_items (org_id, sku, name, category, unit)
      VALUES ('33333333-3333-4333-8333-333333333333','S-1','n','c','u')$$,
    'backend write succeeds under WORKSHOP_MANAGER claims'
);

RESET ROLE;
SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-0000-4000-8000-000000000003","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-0000-4000-8000-000000000003', TRUE);

SELECT throws_ok(
    $$INSERT INTO public.inventory_items (org_id, sku, name, category, unit)
      VALUES ('33333333-3333-4333-8333-333333333333','S-2','n','c','u')$$,
    '42501',
    NULL,
    'backend write denied under INSTALLER claims'
);

RESET ROLE;
SELECT policies_are(
    'public', 'clients',
    ARRAY['clients_member_read', 'clients_member_insert', 'clients_member_update'],
    'clients exposes member-read + estimator-write policies only'
);

SELECT enum_has_labels(
    'public', 'org_role',
    ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER', 'INSTALLER', 'OPERATOR'],
    'org_role carries the OPERATOR station role'
);

SELECT * FROM finish();
ROLLBACK;
