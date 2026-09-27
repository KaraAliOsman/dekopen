BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(4);

-- The delivery-confirm endpoint runs under the documentary backend; an
-- ESTIMATOR registering a cobro en terreno must be able to lock and update
-- the delivery row, while OPERATOR — a shop-floor role — stays denied.

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('66666666-6666-4666-8666-666666666666', 'Tenant F', 'F-1');

INSERT INTO public.tenancy_memberships (org_id, user_id, role) VALUES
    ('66666666-6666-4666-8666-666666666666',
     'ffffffff-0000-4000-8000-000000000001', 'ESTIMATOR'),
    ('66666666-6666-4666-8666-666666666666',
     'ffffffff-0000-4000-8000-000000000002', 'OPERATOR');

INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES (
    '66666666-aaaa-4666-8666-666666666666',
    '66666666-6666-4666-8666-666666666666',
    'QUOTE-F', 'Quote F', 'Client F',
    'ffffffff-0000-4000-8000-000000000001'
);

INSERT INTO public.orders (id, org_id, project_id, order_type, order_code, payload_json)
VALUES (
    '66666666-cccc-4666-8666-666666666666',
    '66666666-6666-4666-8666-666666666666',
    '66666666-aaaa-4666-8666-666666666666', 'WORKSHOP_OT', 'OT-F-1', '{}'::jsonb
);

INSERT INTO public.deliveries (id, org_id, order_id, address, scheduled_date)
VALUES (
    '66666666-eeee-4666-8666-666666666666',
    '66666666-6666-4666-8666-666666666666',
    '66666666-cccc-4666-8666-666666666666',
    'addr', '2026-10-01'
);

-- ── ESTIMATOR ────────────────────────────────────────────────────────────
SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"ffffffff-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'ffffffff-0000-4000-8000-000000000001', TRUE);

SELECT is(
    (SELECT count(*) FROM (
        SELECT id FROM public.deliveries
        WHERE id = '66666666-eeee-4666-8666-666666666666' FOR UPDATE
    ) t),
    1::BIGINT,
    'ESTIMATOR locks the delivery row for confirmation'
);
SELECT lives_ok(
    $$UPDATE public.deliveries SET status = 'DELIVERED'
      WHERE id = '66666666-eeee-4666-8666-666666666666'$$,
    'ESTIMATOR updates the delivery row (cobro en terreno POD flow)'
);

-- ── OPERATOR stays out ───────────────────────────────────────────────────
RESET ROLE;
SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"ffffffff-0000-4000-8000-000000000002","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'ffffffff-0000-4000-8000-000000000002', TRUE);

SELECT is(
    (SELECT count(*) FROM (
        SELECT id FROM public.deliveries
        WHERE id = '66666666-eeee-4666-8666-666666666666' FOR UPDATE
    ) t),
    0::BIGINT,
    'OPERATOR cannot lock the delivery row (view also rejects with 403)'
);
-- The RLS denial is silent: the UPDATE matches zero rows rather than
-- raising, so the proof is that the row keeps its previous status.
UPDATE public.deliveries SET status = 'SCHEDULED'
    WHERE id = '66666666-eeee-4666-8666-666666666666';
SELECT is(
    (SELECT status::text FROM public.deliveries
     WHERE id = '66666666-eeee-4666-8666-666666666666'),
    'DELIVERED'::text,
    'OPERATOR delivery update touches zero rows (still DELIVERED)'
);

SELECT * FROM finish();
ROLLBACK;
