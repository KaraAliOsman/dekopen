BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(12);

-- Floor-role RLS repair: OPERATOR and INSTALLER act on work orders through
-- the documentary backend; the org-member reads and the step/delivery write
-- policies must admit them or every order detail + transition fails.

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('44444444-4444-4444-8444-444444444444', 'Tenant D', 'D-1');

INSERT INTO public.tenancy_memberships (org_id, user_id, role) VALUES
    ('44444444-4444-4444-8444-444444444444',
     'dddddddd-0000-4000-8000-000000000001', 'OPERATOR'),
    ('44444444-4444-4444-8444-444444444444',
     'dddddddd-0000-4000-8000-000000000002', 'INSTALLER'),
    ('44444444-4444-4444-8444-444444444444',
     'dddddddd-0000-4000-8000-000000000003', 'ESTIMATOR');

INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES (
    '44444444-aaaa-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    'QUOTE-D', 'Quote D', 'Client D',
    'dddddddd-0000-4000-8000-000000000003'
);

INSERT INTO public.pricing_operations
    (id, org_id, project_id, requested_by, request, input_snapshot, result,
     source_revision, state, reason)
VALUES (
    '44444444-9999-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    '44444444-aaaa-4444-8444-444444444444',
    'dddddddd-0000-4000-8000-000000000003',
    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
    'BASE', 'APPLIED', 'fixture'
);

INSERT INTO public.project_versions
    (id, org_id, project_id, revision_code, snapshot_json, emitted_by,
     pricing_operation_id, canonical_version, bom_hash, snapshot_sha256,
     production_allowed, documentary_complete)
VALUES (
    '44444444-bbbb-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    '44444444-aaaa-4444-8444-444444444444',
    'REV-A', '{}'::jsonb,
    'dddddddd-0000-4000-8000-000000000003',
    '44444444-9999-4444-8444-444444444444',
    'DOCUMENTARY_CANONICAL_V1',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    TRUE, TRUE
);

INSERT INTO public.inventory_items (id, org_id, sku, name, category, unit)
VALUES (
    '44444444-ffff-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    'S-D', 'Perfil D', 'PROFILE', 'ML'
);

INSERT INTO public.orders (id, org_id, project_id, order_type, order_code, payload_json)
VALUES (
    '44444444-cccc-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    '44444444-aaaa-4444-8444-444444444444',
    'WORKSHOP_OT', 'OT-D-1', '{}'::jsonb
);

INSERT INTO public.production_steps (id, org_id, order_id, sequence, code, label)
VALUES (
    '44444444-dddd-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    '44444444-cccc-4444-8444-444444444444',
    1, 'CUT', 'Corte'
);

INSERT INTO public.deliveries (id, org_id, order_id, address, scheduled_date)
VALUES (
    '44444444-eeee-4444-8444-444444444444',
    '44444444-4444-4444-8444-444444444444',
    '44444444-cccc-4444-8444-444444444444',
    'addr', '2026-10-01'
);

-- ── OPERATOR through the documentary backend ──────────────────────────────
SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"dddddddd-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'dddddddd-0000-4000-8000-000000000001', TRUE);

SELECT is(
    (SELECT count(*) FROM public.projects
     WHERE id = '44444444-aaaa-4444-8444-444444444444'),
    1::BIGINT,
    'OPERATOR reads the project through the backend role'
);
SELECT is(
    (SELECT count(*) FROM public.project_versions
     WHERE id = '44444444-bbbb-4444-8444-444444444444'),
    1::BIGINT,
    'OPERATOR reads the sealed version through the backend role'
);
SELECT lives_ok(
    $$UPDATE public.production_steps SET status = 'IN_PROGRESS'
      WHERE id = '44444444-dddd-4444-8444-444444444444'$$,
    'OPERATOR locks and transitions a workshop step'
);
SELECT lives_ok(
    $$INSERT INTO public.production_step_events
        (org_id, order_id, step_id, event, actor_id)
      VALUES ('44444444-4444-4444-8444-444444444444',
              '44444444-cccc-4444-8444-444444444444',
              '44444444-dddd-4444-8444-444444444444',
              'NOTE', 'dddddddd-0000-4000-8000-000000000001')$$,
    'OPERATOR appends step events'
);
SELECT lives_ok(
    $$INSERT INTO public.inventory_movements
        (org_id, item_id, movement_type, quantity)
      VALUES ('44444444-4444-4444-8444-444444444444',
              '44444444-ffff-4444-8444-444444444444',
              'CONSUMPTION', 1)$$,
    'OPERATOR writes the consumption ledger at step completion'
);
SELECT throws_ok(
    $$UPDATE public.projects SET name = 'hax'$$,
    '42501',
    NULL,
    'OPERATOR cannot mutate the project row'
);

-- ── INSTALLER through the documentary backend ─────────────────────────────
RESET ROLE;
SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"dddddddd-0000-4000-8000-000000000002","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'dddddddd-0000-4000-8000-000000000002', TRUE);

SELECT is(
    (SELECT count(*) FROM public.project_versions
     WHERE id = '44444444-bbbb-4444-8444-444444444444'),
    1::BIGINT,
    'INSTALLER reads the sealed version (delivery context)'
);
SELECT lives_ok(
    $$UPDATE public.deliveries SET status = 'DELIVERED'
      WHERE id = '44444444-eeee-4444-8444-444444444444'$$,
    'INSTALLER updates the delivery row (POD flow)'
);
SELECT lives_ok(
    $$UPDATE public.production_steps SET status = 'DONE'
      WHERE id = '44444444-dddd-4444-8444-444444444444'$$,
    'INSTALLER transitions the delivery step'
);

-- ── Cross-tenant stays sealed ──────────────────────────────────────────────
RESET ROLE;
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('55555555-5555-4555-8555-555555555555', 'Tenant E', 'E-1');
INSERT INTO public.tenancy_memberships (org_id, user_id, role) VALUES
    ('55555555-5555-4555-8555-555555555555',
     'eeeeeeee-0000-4000-8000-000000000001', 'OPERATOR');


SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-000000000001', TRUE);

SELECT is(
    (SELECT count(*) FROM public.project_versions
     WHERE id = '44444444-bbbb-4444-8444-444444444444'),
    0::BIGINT,
    'OPERATOR from another org reads nothing'
);
SELECT is(
    (SELECT count(*) FROM public.production_steps
     WHERE id = '44444444-dddd-4444-8444-444444444444'),
    0::BIGINT,
    'foreign-org operator sees no steps'
);
SELECT is(
    (SELECT count(*) FROM public.deliveries
     WHERE id = '44444444-eeee-4444-8444-444444444444'),
    0::BIGINT,
    'foreign-org operator sees no deliveries'
);

SELECT * FROM finish();
ROLLBACK;
