BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(20);

-- ── Catalog integrity: provenance is backend-owned, member writes are
-- column-scoped, review re-opens on stale edits, NaN is unwritable. ─────────

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('55555555-5555-4555-8555-555555555555', 'Tenant CAT', 'CAT-1');

INSERT INTO public.tenancy_memberships (org_id, user_id, role)
VALUES ('55555555-5555-4555-8555-555555555555',
        'dddddddd-0000-4000-8000-000000000001', 'WORKSHOP_MANAGER');

-- Bead matrix carries the same provenance triple as every other catalog table.
SELECT has_column('public', 'glazing_bead_matrix', 'data_provenance',
    'beads carry data_provenance');
SELECT has_column('public', 'glazing_bead_matrix', 'technical_reviewed_at',
    'beads carry technical_reviewed_at');
SELECT has_column('public', 'glazing_bead_matrix', 'technical_reviewed_by',
    'beads carry technical_reviewed_by');
SELECT has_column('public', 'glazing_bead_matrix', 'review_pending',
    'beads carry review_pending');

-- The backend role holds full DML; the tenant role lost table-level INSERT/UPDATE.
SELECT ok(has_table_privilege('catalog_backend', 'public.profile_articles', 'INSERT'),
    'catalog_backend inserts catalog rows');
SELECT ok(has_table_privilege('catalog_backend', 'public.profile_articles', 'UPDATE'),
    'catalog_backend updates catalog rows');
SELECT ok(NOT has_table_privilege('authenticated', 'public.profile_articles', 'INSERT'),
    'authenticated has no table-level INSERT on catalog tables');
SELECT ok(NOT has_table_privilege('authenticated', 'public.profile_articles', 'UPDATE'),
    'authenticated has no table-level UPDATE on catalog tables');
SELECT ok(NOT has_table_privilege('authenticated', 'public.catalog_imports', 'UPDATE'),
    'authenticated cannot rewrite import rows');

-- Fixture rows written by the API role, marked already reviewed.
SET LOCAL ROLE catalog_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"dddddddd-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'dddddddd-0000-4000-8000-000000000001', TRUE);

INSERT INTO public.profile_systems (id, org_id, name, code, depth_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm)
VALUES ('55555555-aaaa-4555-8555-555555555555',
        '55555555-5555-4555-8555-555555555555', 'T60', 'T60', 60.00,
        0.00, 0.00, 0.00);

INSERT INTO public.profile_articles (
    id, org_id, system_id, sku, name, role, face_width_mm,
    data_provenance, technical_reviewed_at, technical_reviewed_by)
VALUES ('55555555-bbbb-4555-8555-555555555555',
        '55555555-5555-4555-8555-555555555555',
        '55555555-aaaa-4555-8555-555555555555',
        'T60-FRAME', 'T60 Marco', 'FRAME', 50.00,
        'IMPORT', now(), 'dddddddd-0000-4000-8000-000000000001');

INSERT INTO public.profile_articles (
    id, org_id, system_id, sku, name, role, face_width_mm)
VALUES ('55555555-bbbb-4555-8555-555555555556',
        '55555555-5555-4555-8555-555555555555',
        '55555555-aaaa-4555-8555-555555555555',
        'T60-BEAD', 'T60 Junquillo', 'GLAZING_BEAD', 14.00);

INSERT INTO public.glazing_bead_matrix (
    system_id, org_id, glass_thickness_mm, bead_article_id, bead_width_mm,
    cut_add_mm,
    data_provenance, technical_reviewed_at, technical_reviewed_by)
VALUES ('55555555-aaaa-4555-8555-555555555555',
        '55555555-5555-4555-8555-555555555555',
        20.00, '55555555-bbbb-4555-8555-555555555556', 14.00,
        2.00,
        'IMPORT', now(), 'dddddddd-0000-4000-8000-000000000001');

INSERT INTO public.hardware_kits (
    org_id, system_id, sku, name, opening_type,
    min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,
    max_leaf_weight_kg)
VALUES ('55555555-5555-4555-8555-555555555555',
        '55555555-aaaa-4555-8555-555555555555',
        'KIT-BOUND', 'Kit bound', 'TURN',
        400, 1200, 400, 2200, 80.00),
       ('55555555-5555-4555-8555-555555555555',
        NULL,
        'KIT-UNBOUND', 'Kit unbound', 'SLIDING',
        400, 1200, 400, 2200, 80.00);

RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"dddddddd-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'dddddddd-0000-4000-8000-000000000001', TRUE);

-- Member writes: writable columns pass, provenance columns are denied.
SELECT lives_ok(
    $$UPDATE public.profile_articles SET name='T60 Marco editado'
      WHERE id='55555555-bbbb-4555-8555-555555555555'$$,
    'member updates a writable article column'
);
SELECT throws_ok(
    $$UPDATE public.profile_articles SET data_provenance='MANUAL'
      WHERE id='55555555-bbbb-4555-8555-555555555555'$$,
    '42501', NULL,
    'member cannot stamp data_provenance'
);
SELECT throws_ok(
    $$UPDATE public.profile_articles SET technical_reviewed_at=now()
      WHERE id='55555555-bbbb-4555-8555-555555555555'$$,
    '42501', NULL,
    'member cannot stamp technical_reviewed_at'
);
SELECT throws_ok(
    $$UPDATE public.glazing_bead_matrix SET data_provenance='MANUAL'
      WHERE system_id='55555555-aaaa-4555-8555-555555555555'$$,
    '42501', NULL,
    'member cannot stamp bead provenance either'
);

-- The technical edit above re-opened the review: stamps cleared, pending set.
SELECT is(
    (SELECT (technical_reviewed_at IS NULL)::TEXT || ':' || review_pending::TEXT
       FROM public.profile_articles
      WHERE id='55555555-bbbb-4555-8555-555555555555'),
    'true:true',
    'editing a reviewed row clears stamps and flags review_pending'
);

-- NaN cannot enter numeric columns (CHECKs) or kit contents (shape guard).
SELECT throws_ok(
    $$UPDATE public.profile_articles SET weight_kg_m='NaN'::numeric
      WHERE id='55555555-bbbb-4555-8555-555555555555'$$,
    '23514', NULL,
    'NaN weight is rejected by the CHECK'
);
SELECT throws_ok(
    $$UPDATE public.glazing_bead_matrix SET glass_thickness_mm='NaN'::numeric
      WHERE system_id='55555555-aaaa-4555-8555-555555555555'$$,
    '23514', NULL,
    'NaN bead thickness is rejected by the CHECK'
);
SELECT throws_ok(
    $$INSERT INTO public.hardware_kits (
        org_id, system_id, sku, name, opening_type,
        min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm,
        max_leaf_height_mm, max_leaf_weight_kg, contents)
      VALUES ('55555555-5555-4555-8555-555555555555',
              '55555555-aaaa-4555-8555-555555555555',
              'KIT-NAN', 'Kit NaN', 'TURN',
              400, 1200, 400, 2200, 80.00,
              jsonb_build_array(jsonb_build_object(
                  'sku','X','name','n','qty','NaN','unit','u')))$$,
    '23514', NULL,
    'a non-number qty inside kit contents is rejected by the guard'
);

-- Enum discipline + unbound-kit uniqueness.
SELECT throws_ok(
    $$INSERT INTO public.hardware_kits (
        org_id, system_id, sku, name, opening_type,
        min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm,
        max_leaf_height_mm, max_leaf_weight_kg)
      VALUES ('55555555-5555-4555-8555-555555555555',
              '55555555-aaaa-4555-8555-555555555555',
              'KIT-BADTYPE', 'Kit bad', 'CASEMENT',
              400, 1200, 400, 2200, 80.00)$$,
    '23514', NULL,
    'opening_type outside the canonical set is rejected'
);
SELECT throws_ok(
    $$INSERT INTO public.hardware_kits (
        org_id, system_id, sku, name, opening_type,
        min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm,
        max_leaf_height_mm, max_leaf_weight_kg)
      VALUES ('55555555-5555-4555-8555-555555555555',
              NULL,
              'KIT-UNBOUND', 'Kit dup', 'AWNING',
              400, 1200, 400, 2200, 80.00)$$,
    '23505', NULL,
    'unbound kits are unique per (org_id, sku)'
);

-- Members can still insert rows listing only writable columns.
SELECT lives_ok(
    $$INSERT INTO public.profile_articles (
        org_id, system_id, sku, name, role, face_width_mm)
      VALUES ('55555555-5555-4555-8555-555555555555',
              '55555555-aaaa-4555-8555-555555555555',
              'T60-SASH', 'T60 Hoja', 'SASH', 60.00)$$,
    'member inserts a catalog row over writable columns'
);

SELECT * FROM finish();
ROLLBACK;
