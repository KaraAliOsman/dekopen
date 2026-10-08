BEGIN;

CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path = public, extensions;

SELECT plan(10);

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES
    ('33333333-3333-4333-8333-333333333333', 'Tenant C', 'C-1');

INSERT INTO public.tenancy_memberships (org_id, user_id, role)
VALUES
    ('33333333-3333-4333-8333-333333333333',
     'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'OWNER'),
    ('33333333-3333-4333-8333-333333333333',
     'dddddddd-0000-4000-8000-000000000001', 'OWNER');

-- D04 tables exist with RLS enabled and row contents declared.
SELECT ok(
    has_table_privilege('authenticated', 'public.hardware_families', 'SELECT'),
    'authenticated reads hardware families'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.hardware_handle_models', 'SELECT'),
    'authenticated reads handle models'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.hardware_handle_colors', 'SELECT'),
    'authenticated reads handle colors'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.hardware_options', 'SELECT'),
    'authenticated reads hardware options'
);

-- Seed: DEMO_70 declares a TILT_TURN family with an editable height range.
SELECT is(
    (
        SELECT count(*)
        FROM public.hardware_families f
        JOIN public.profile_systems s ON s.id = f.system_id
        WHERE s.code = 'DEMO_70'
          AND f.opening_type = 'TILT_TURN'
          AND f.handle_height_rule = 'RANGE'
          AND f.handle_height_min_mm = 900.00
          AND f.handle_height_max_mm = 1300.00
    ),
    1::BIGINT,
    'DEMO_70 declares the TILT_TURN family with its 900-1300 mm range'
);

-- The validator rejects malformed component documents as 23514 — the
-- manual-write path (authenticated) is the one the guard covers.
SET LOCAL ROLE authenticated;
SELECT throws_ok(
    $$SELECT private.validate_hardware_components(
        jsonb_build_array(jsonb_build_object(
            'sku','X','name','n','unit','u')))$$,
    '23514', NULL,
    'an option component without qty or qty_rule is rejected'
);

-- The same role cannot insert catalog rows directly — writes go through
-- catalog_backend, so the privilege check is the 42501, not the guard.
SELECT throws_ok(
    $$INSERT INTO public.hardware_handle_models (
        id, org_id, system_id, sku, name, kind, opening_type, data_provenance)
      VALUES (gen_random_uuid(),
              '33333333-3333-4333-8333-333333333333',
              (SELECT id FROM public.profile_systems WHERE code = 'DEMO_70'),
              'MAN-FAKE', 'Manilla falsa', 'STANDARD', 'TILT_TURN', 'MANUAL')$$,
    '42501', NULL,
    'authenticated cannot insert handle models'
);

RESET ROLE;

-- catalog_backend writes a valid option through the guarded path.
-- Transaction-scoped USAGE: catalog_backend cannot see pgtap otherwise.
GRANT USAGE ON SCHEMA extensions TO catalog_backend;
SET LOCAL ROLE catalog_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"dddddddd-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'dddddddd-0000-4000-8000-000000000001', TRUE);
SELECT lives_ok(
    $$INSERT INTO public.hardware_options (
        org_id, system_id, sku, name, kind, opening_type, components)
      VALUES ('33333333-3333-4333-8333-333333333333',
              (SELECT id FROM public.profile_systems WHERE code = 'DEMO_70'),
              'OPT-TEST', 'Opción de prueba', 'SECURITY', 'TILT_TURN',
              jsonb_build_array(jsonb_build_object(
                  'sku','X','name','n','qty','1','unit','UNIT','category','FITTING')))$$,
    'catalog_backend writes a valid option'
);

-- NULLS NOT DISTINCT uniqueness: same org+system+opening+sku cannot repeat.
SELECT throws_ok(
    $$INSERT INTO public.hardware_options (
        org_id, system_id, sku, name, kind, opening_type, components)
      SELECT NULL, system_id, sku, name || ' bis', kind, opening_type, components
        FROM public.hardware_options
       WHERE sku = 'OPT-70-MICROVENT' AND org_id IS NULL$$,
    '23505', NULL,
    'global options stay unique per (system, opening, sku)'
);

RESET ROLE;

-- A tenant-visible count: DEMO_70 families + options seeded globally.
SET LOCAL ROLE authenticated;
SELECT set_config(
    'request.jwt.claims',
    '{"sub":"cccccccc-cccc-4ccc-8ccc-cccccccccccc","role":"authenticated"}',
    TRUE
);
SELECT set_config(
    'request.jwt.claim.sub',
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc',
    TRUE
);

SELECT ok(
    (SELECT count(*) FROM public.hardware_families) >= 3,
    'tenant sees the seeded hardware families'
);

SELECT * FROM finish();
ROLLBACK;
