BEGIN;

CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path = public, extensions;

SELECT plan(14);

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES
    ('33333333-3333-4333-8333-333333333333', 'Tenant C', 'C-1'),
    ('44444444-4444-4444-8444-444444444444', 'Tenant D', 'D-1');

INSERT INTO public.tenancy_memberships (org_id, user_id, role)
VALUES
    ('33333333-3333-4333-8333-333333333333',
     'cccccccc-cccc-4ccc-8ccc-cccccccccccc', 'OWNER'),
    ('44444444-4444-4444-8444-444444444444',
     'eeeeeeee-0000-4000-8000-000000000002', 'ESTIMATOR');

INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES
    ('55555555-5555-4555-8555-555555555555',
     '33333333-3333-4333-8333-333333333333', 'PRJ-D06',
     'Obra Prueba D06', 'Cliente D06',
     'cccccccc-cccc-4ccc-8ccc-cccccccccccc');

-- D06 tables exist with the role split the catalog and tenant rows need.
SELECT ok(
    has_table_privilege('authenticated', 'public.extra_articles', 'SELECT'),
    'authenticated reads extra articles'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.extra_articles', 'INSERT'),
    'authenticated cannot write extra articles'
);
SELECT ok(
    has_table_privilege('catalog_backend', 'public.extra_articles', 'INSERT'),
    'catalog_backend writes extra articles'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.service_articles', 'SELECT'),
    'authenticated reads service articles'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.project_service_selections', 'INSERT'),
    'authenticated writes project service selections'
);
SELECT ok(
    has_column_privilege('documentary_backend', 'public.tenancy_organizations', 'extras_display', 'UPDATE'),
    'documentary_backend updates the org row (extras_display column grant)'
);

-- Seed: DEMO_60 declares the finishing catalog + sellable extras.
SELECT is(
    (
        SELECT count(*)
        FROM public.extra_articles e
        JOIN public.profile_systems s ON s.id = e.system_id
        WHERE s.code = 'DEMO_60' AND e.org_id IS NULL AND e.kind = 'SILL'
          AND e.vuelo_default_mm = 30.00
    ),
    1::BIGINT,
    'DEMO_60 seeds a vierteaguas with its 30 mm vuelo'
);
SELECT is(
    (
        SELECT count(*)
        FROM public.extra_articles e
        JOIN public.profile_systems s ON s.id = e.system_id
        WHERE s.code = 'DEMO_CORREDERA_60' AND e.org_id IS NULL
          AND e.kind = 'MOSQUITO_SCREEN'
          AND e.families = '{SLIDING}'::text[]
          AND e.suggestion_reason IS NOT NULL
    ),
    1::BIGINT,
    'DEMO_CORREDERA_60 seeds the sliding mosquitero with its reason'
);
SELECT is(
    (
        SELECT count(*)
        FROM public.service_articles
        WHERE org_id IS NULL AND code = 'INST-ML'
          AND kind = 'INSTALLATION' AND qty_rule = 'PER_LINEAR_METER'
    ),
    1::BIGINT,
    'a global installation service priced per perimeter meter exists'
);

-- Kind/unit contract: a counted extra cannot declare a cut profile, and a
-- cut kind cannot price per unit.
SELECT throws_ok(
    $$INSERT INTO public.extra_articles (
        system_id, org_id, sku, name, kind, pricing_unit,
        cut_profile_sku, cut_material)
      VALUES ((SELECT id FROM public.profile_systems WHERE code = 'DEMO_60'),
              NULL, 'EXT-BAD', 'Extra malo', 'MOSQUITO_SCREEN', 'EA',
              'VIERT-ALU-60', 'ALUMINIUM')$$,
    '23514', NULL,
    'a counted extra carrying a cut profile is rejected'
);

-- catalog_backend writes through the guarded path (parent coherence +
-- freeze authority); authenticated cannot insert catalog rows directly.
SET LOCAL ROLE authenticated;
SELECT throws_ok(
    $$INSERT INTO public.extra_articles (
        system_id, org_id, sku, name, kind, pricing_unit)
      VALUES ((SELECT id FROM public.profile_systems WHERE code = 'DEMO_60'),
              NULL, 'EXT-FAKE', 'Extra falso', 'SILL', 'M')$$,
    '42501', NULL,
    'authenticated cannot insert extra articles'
);
RESET ROLE;

GRANT USAGE ON SCHEMA extensions TO catalog_backend;
SET LOCAL ROLE catalog_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-cccc-4ccc-8ccc-cccccccccccc","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc', TRUE);

SELECT lives_ok(
    $$INSERT INTO public.service_articles (
        org_id, code, name, kind, qty_rule, unit_price, unit_price_currency)
      VALUES ('33333333-3333-4333-8333-333333333333',
              'FLETE-LOCAL', 'Flete local', 'FREIGHT', 'FIXED',
              15000.00, 'CLP')$$,
    'catalog_backend writes an org service article'
);
RESET ROLE;

-- Tenant scoping: selections write through the authenticated policy and
-- stay inside the org boundary.
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"cccccccc-cccc-4ccc-8ccc-cccccccccccc","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'cccccccc-cccc-4ccc-8ccc-cccccccccccc', TRUE);

SELECT lives_ok(
    $$INSERT INTO public.project_service_selections (project_id, org_id, service_article_id)
      VALUES ('55555555-5555-4555-8555-555555555555',
              '33333333-3333-4333-8333-333333333333',
              (SELECT id FROM public.service_articles WHERE code = 'INST-ML'))$$,
    'the project org selects a global service'
);

-- Cross-tenant: the other org's estimator must not see tenant C's
-- selections or write into tenant C's org.
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-000000000002","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-000000000002', TRUE);

SELECT is(
    (SELECT count(*) FROM public.project_service_selections),
    0::BIGINT,
    'tenant D sees no selections of tenant C'
);

RESET ROLE;

SELECT * FROM finish();
ROLLBACK;
