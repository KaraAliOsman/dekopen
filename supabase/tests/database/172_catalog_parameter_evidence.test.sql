-- ── Parameter evidence registry: members read, never write; stamps are
-- backend-only; half-stamped reviews are impossible; RLS walls orgs off. ──

BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(12);

SELECT has_table('public', 'catalog_parameter_evidence',
    'parameter evidence registry exists');
SELECT ok(NOT has_table_privilege('authenticated', 'public.catalog_parameter_evidence', 'INSERT'),
    'authenticated has no INSERT on the evidence registry');
SELECT ok(NOT has_table_privilege('authenticated', 'public.catalog_parameter_evidence', 'UPDATE'),
    'authenticated has no UPDATE on the evidence registry');
SELECT ok(NOT has_table_privilege('authenticated', 'public.catalog_parameter_evidence', 'DELETE'),
    'authenticated has no DELETE on the evidence registry');
SELECT ok(has_table_privilege('authenticated', 'public.catalog_parameter_evidence', 'SELECT'),
    'members can read the evidence registry');

-- Fixture authority row + two orgs.
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES
    ('77777777-0000-4000-8000-000000000001', 'Org Evidence A', 'EVD-A'),
    ('77777777-0000-4000-8000-000000000002', 'Org Evidence B', 'EVD-B')
    ON CONFLICT (id) DO NOTHING;
INSERT INTO public.tenancy_memberships (org_id, user_id, role)
VALUES ('77777777-0000-4000-8000-000000000001',
        'dddddddd-0000-4000-8000-000000000001', 'WORKSHOP_MANAGER');
INSERT INTO public.profile_systems (
    id, org_id, name, code, depth_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm)
VALUES ('77777777-aaaa-4555-8555-555555555555',
        '77777777-0000-4000-8000-000000000001',
        'Serie Evidencia 60', 'EVD-60', 60.00, 0.00, 0.00, 0.00);

INSERT INTO public.catalog_parameter_evidence (
    org_id, authority_table, row_id, field_name, value_text, unit, scope,
    source_document, source_page, declared_by)
VALUES
    ('77777777-0000-4000-8000-000000000001', 'profile_systems',
     '77777777-aaaa-4555-8555-555555555555', 'rebate_depth_mm',
     '6.5', 'mm', 'SYSTEM', 'Datasheet EVD-60 p.3', 3,
     'dddddddd-0000-4000-8000-000000000001'),
    ('77777777-0000-4000-8000-000000000002', 'profile_systems',
     '77777777-aaaa-4555-8555-555555555555', 'depth_mm',
     '60', 'mm', 'SYSTEM', 'Datasheet ajeno', 1,
     'dddddddd-0000-4000-8000-000000000002');

-- Member reads own evidence only — org B's row is invisible to org A.
RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"dddddddd-0000-4000-8000-000000000001","role":"authenticated"}', TRUE);

SELECT is(
    (SELECT count(*)::INT FROM public.catalog_parameter_evidence),
    1,
    'member sees own-org evidence only (RLS walls org B)'
);

-- A member cannot write evidence at all — declarations go through the API.
SELECT throws_ok(
    $$INSERT INTO public.catalog_parameter_evidence
      (org_id, authority_table, row_id, field_name, source_document, declared_by)
      VALUES ('77777777-0000-4000-8000-000000000001', 'profile_systems',
              '77777777-aaaa-4555-8555-555555555555', 'depth_mm',
              'Forged.pdf', 'dddddddd-0000-4000-8000-000000000001')$$,
    NULL, NULL,
    'member INSERT into evidence registry is denied'
);

-- And cannot stamp a review directly.
SELECT throws_ok(
    $$UPDATE public.catalog_parameter_evidence
      SET review_state='REVIEWED', reviewed_by='dddddddd-0000-4000-8000-000000000001',
          reviewed_at=now()$$,
    NULL, NULL,
    'member UPDATE stamping review_state is denied'
);

RESET ROLE;
SET LOCAL ROLE postgres;

-- Shape guards: half-stamps are impossible, URLs must be http(s), pages > 0.
SELECT throws_ok(
    $$INSERT INTO public.catalog_parameter_evidence
      (org_id, authority_table, row_id, field_name, source_document, declared_by,
       review_state)
      VALUES ('77777777-0000-4000-8000-000000000001', 'profile_systems',
              '77777777-aaaa-4555-8555-555555555555', 'depth_mm',
              'Doc.pdf', 'dddddddd-0000-4000-8000-000000000001', 'REVIEWED')$$,
    '23514', NULL,
    'REVIEWED without reviewer+timestamp violates the stamp CHECK'
);
SELECT throws_ok(
    $$INSERT INTO public.catalog_parameter_evidence
      (org_id, authority_table, row_id, field_name, source_document, source_url,
       declared_by)
      VALUES ('77777777-0000-4000-8000-000000000001', 'profile_systems',
              '77777777-aaaa-4555-8555-555555555555', 'depth_mm',
              'Doc.pdf', 'file:///etc/passwd',
              'dddddddd-0000-4000-8000-000000000001')$$,
    '23514', NULL,
    'a non-http source_url is rejected'
);
SELECT throws_ok(
    $$INSERT INTO public.catalog_parameter_evidence
      (org_id, authority_table, row_id, field_name, source_document,
       source_page, declared_by)
      VALUES ('77777777-0000-4000-8000-000000000001', 'profile_systems',
              '77777777-aaaa-4555-8555-555555555555', 'depth_mm',
              'Doc.pdf', 0,
              'dddddddd-0000-4000-8000-000000000001')$$,
    '23514', NULL,
    'source_page must be positive when given'
);
SELECT throws_ok(
    $$INSERT INTO public.catalog_parameter_evidence
      (org_id, authority_table, row_id, field_name, source_document, declared_by,
       unit)
      VALUES ('77777777-0000-4000-8000-000000000001', 'profile_systems',
              '77777777-aaaa-4555-8555-555555555555', 'depth_mm',
              'Doc.pdf', 'dddddddd-0000-4000-8000-000000000001', 'furlong')$$,
    '23514', NULL,
    'a unit outside the registry vocabulary is rejected'
);

SELECT * FROM finish();
ROLLBACK;
