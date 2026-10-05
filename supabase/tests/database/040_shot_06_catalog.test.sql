BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path = public, extensions;
SELECT plan(36);

SELECT ok(EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'profile_systems'
      AND column_name = expected.name AND data_type = 'numeric'
      AND numeric_precision = 10 AND numeric_scale = 2
      AND is_nullable = 'NO' AND column_default IS NULL
), expected.name || ' requires an explicit exact authority')
FROM unnest(ARRAY['sliding_glazing_deduction_width_mm',
    'sliding_glazing_deduction_height_mm', 'door_leaf_side_clearance_mm']) AS expected(name);
SELECT ok(EXISTS (
    SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
    AND table_name = 'hardware_kits' AND column_name = 'weight_kg'
    AND numeric_precision = 8 AND numeric_scale = 2 AND is_nullable = 'YES'
), 'kit weight allows an explicit missing authority');
SELECT is((SELECT weight_kg_m2 FROM public.infill_articles
    WHERE sku = 'PANEL-SANDWICH-DEMO-24'), 10.0000, 'synthetic panel density');
SELECT is((SELECT count(*) FROM public.profile_articles WHERE sku = 'UMBRAL-ALU'
    AND role = 'THRESHOLD' AND material = 'ALUMINIUM' AND welding_loss_mm = 0.00
    AND reinforcement_gap_mm = 0.00 AND reinforcement_sku IS NULL), 1::BIGINT,
    'threshold has its own real material and no steel authority');
SELECT is((SELECT count(*) FROM public.hardware_kits WHERE weight_kg = 2.50
    AND sku IN ('KIT-TILT-TURN','KIT-TURN','KIT-AWNING-16','KIT-SLIDING','KIT-DOOR-MULTIPOINT')),
    5::BIGINT, 'all five DEMO kits persist their exact weight');
SELECT is((SELECT contents FROM public.hardware_kits WHERE sku = 'KIT-AWNING-16'),
    '[{"sku":"DEMO-STAY-16","name":"Compás a fricción 16\"","qty":2,"unit":"unit","category":"FITTING"},{"sku":"DEMO-MAN-PROY","name":"Manilla central proyectante Demo","qty":1,"unit":"unit","category":"HANDLE"}]'::JSONB,
    'awning retains approved nested contents');
SELECT is((SELECT contents FROM public.hardware_kits WHERE sku = 'KIT-DOOR-MULTIPOINT'),
    '[{"sku":"DEMO-LOCK-MULTIPOINT","name":"Cerradura multipunto Demo","qty":1,"unit":"unit","category":"LOCK"},{"sku":"DEMO-BIS-PUERTA","name":"Bisagra puerta reforzada Demo","qty":3,"unit":"unit","category":"HINGE"},{"sku":"DEMO-MAN-PUERTA","name":"Par manilla puerta + cilindro Demo","qty":1,"unit":"set","category":"HANDLE"}]'::JSONB,
    'door retains approved nested contents');
SELECT is((SELECT name::TEXT FROM public.hardware_kits WHERE sku = 'KIT-TILT-TURN'),
    'Kit Vorne OB 100kg', 'OB name changes without changing SKU');
SELECT ok(NOT has_table_privilege('anon', 'public.infill_articles', 'SELECT'),
    'anonymous cannot read infill catalog');

INSERT INTO public.tenancy_organizations (id, name, tax_id) VALUES
    ('11111111-1111-4111-8111-111111111111', 'Tenant A', 'A-1'),
    ('22222222-2222-4222-8222-222222222222', 'Tenant B', 'B-1');
INSERT INTO public.tenancy_memberships (org_id, user_id) VALUES
    ('11111111-1111-4111-8111-111111111111', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
    ('22222222-2222-4222-8222-222222222222', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
-- Permission writes use a new global authority; persisted DEMO authority is immutable.
INSERT INTO public.profile_systems
SELECT (jsonb_populate_record(NULL::public.profile_systems,to_jsonb(source)||
    jsonb_build_object('id',gen_random_uuid(),'code','PGTAP06','technical_locked',false,'is_demo',false))).*
FROM public.profile_systems source WHERE code='DEMO_60';
-- Deliberately attach tenant rows to a global system: org_id must still isolate them.
INSERT INTO public.infill_articles (system_id, org_id, sku, name, kind, thickness_mm)
SELECT system.id, fixture.org_id::UUID, fixture.sku, fixture.sku, 'SANDWICH_PANEL', 24.00
FROM public.profile_systems AS system CROSS JOIN (VALUES
    ('11111111-1111-4111-8111-111111111111', 'PANEL-A'),
    ('22222222-2222-4222-8222-222222222222', 'PANEL-B')) AS fixture(org_id, sku)
WHERE system.code = 'PGTAP06';

SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub', 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', TRUE);
SELECT is((SELECT count(*) FROM public.infill_articles WHERE org_id IS NULL),
    3::BIGINT, 'A reads global panel');
SELECT is((SELECT count(*) FROM public.infill_articles WHERE sku = 'PANEL-A'),
    1::BIGINT, 'A reads own panel');
SELECT is((SELECT count(*) FROM public.infill_articles WHERE sku = 'PANEL-B'),
    0::BIGINT, 'A cannot read B panel even in a global system');
SELECT throws_ok($$UPDATE public.infill_articles SET weight_kg_m2 = 99.00
    WHERE org_id IS NULL$$, '42501', NULL,
    'A cannot mutate global panel — member writes are grant-denied');
SELECT throws_ok($$INSERT INTO public.infill_articles (system_id, sku, name, kind, thickness_mm)
    SELECT id, 'FORBIDDEN-GLOBAL', 'X', 'SANDWICH_PANEL', 24.00
    FROM public.profile_systems WHERE code = 'PGTAP06'$$, '42501', NULL,
    'A cannot insert global panel');
SELECT throws_ok($$INSERT INTO public.infill_articles
    (system_id, org_id, sku, name, kind, thickness_mm)
    SELECT id, '11111111-1111-4111-8111-111111111111', 'A-NEW', 'X', 'SANDWICH_PANEL', 24.00
    FROM public.profile_systems WHERE code = 'PGTAP06'$$, '42501', NULL,
    'A cannot insert an org panel — infill is authority data, member read-only');
SELECT throws_ok($$INSERT INTO public.infill_articles
    (system_id, org_id, sku, name, kind, thickness_mm)
    SELECT id, '22222222-2222-4222-8222-222222222222', 'B-FORBIDDEN', 'X', 'SANDWICH_PANEL', 24.00
    FROM public.profile_systems WHERE code = 'PGTAP06'$$, '42501', NULL,
    'A cannot write B panel');
SELECT throws_ok($$UPDATE public.infill_articles SET weight_kg_m2 = 11.00
    WHERE sku = 'PANEL-A'$$, '42501', NULL, 'A cannot update an org panel');
SELECT throws_ok($$DELETE FROM public.infill_articles
    WHERE sku = 'PANEL-A'$$, '42501', NULL, 'A cannot delete an org panel');

RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb","role":"authenticated"}', TRUE);
SELECT set_config('request.jwt.claim.sub', 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb', TRUE);
SELECT is((SELECT array_agg(sku::TEXT ORDER BY sku) FROM public.infill_articles
    WHERE org_id IS NOT NULL), ARRAY['PANEL-B'], 'B sees only own tenant panel');
SELECT is((SELECT count(*) FROM public.infill_articles WHERE org_id IS NULL),
    3::BIGINT, 'B reads global panel');
RESET ROLE;

SELECT is((SELECT ARRAY[sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm, door_leaf_side_clearance_mm]
    FROM public.profile_systems WHERE code = 'DEMO_60'),
    ARRAY[20.00, 20.00, 7.00], 'DEMO_60 has exactly the three approved authorities');
SELECT is((SELECT count(*) FROM public.profile_articles WHERE sku <> 'UMBRAL-ALU'
    AND material = 'PVC'), 35::BIGINT, 'historical DEMO articles have explicit PVC material (31 + 4 D06 ensanche/tapajunta PVC)');
SELECT is((SELECT count(*) FROM pg_constraint WHERE conrelid = 'public.infill_articles'::REGCLASS
    AND contype = 'p'), 1::BIGINT, 'panel catalog has a primary key');
SELECT ok(EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.infill_articles'::REGCLASS
    AND contype = 'u' AND pg_get_constraintdef(oid) = 'UNIQUE (system_id, sku)'),
    'panel SKU uniqueness is scoped by system');
SELECT ok(EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.infill_articles'::REGCLASS
    AND confrelid = 'public.profile_systems'::REGCLASS AND confdeltype = 'c'),
    'panel system FK cascades');
SELECT ok(EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.infill_articles'::REGCLASS
    AND confrelid = 'public.tenancy_organizations'::REGCLASS AND confdeltype = 'c'),
    'panel tenant FK cascades');
SELECT ok(EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
    AND table_name = 'infill_articles' AND column_name = 'is_active'
    AND is_nullable = 'NO' AND column_default = 'true'), 'panels have an active flag');
SELECT ok(EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
    AND table_name = 'infill_articles' AND column_name = 'weight_kg_m2'
    AND is_nullable = 'YES' AND numeric_precision = 10 AND numeric_scale = 4),
    'panel density is nullable NUMERIC(10,4)');
SELECT is((SELECT thickness_mm FROM public.infill_articles WHERE sku = 'PANEL-SANDWICH-DEMO-24'),
    24.00, 'panel thickness uses the existing 24 mm bead rule');
SELECT throws_ok($$INSERT INTO public.profile_systems (code, name, depth_mm)
    VALUES ('MISSING-AUTHORITY', 'Missing test fixture', 60.00)$$,
    '23502', NULL, 'a new system cannot omit the approved explicit authorities');
SELECT throws_ok($$INSERT INTO public.infill_articles
    (system_id, sku, name, kind, thickness_mm)
    VALUES ('00000000-0000-0000-0000-000000000001', 'ORPHAN', 'X', 'SANDWICH_PANEL', 24.00)$$,
    '23503', NULL, 'an infill cannot reference a missing system');
SELECT throws_ok($$INSERT INTO public.infill_articles (system_id, sku, name, kind, thickness_mm)
    SELECT system_id, sku, name, kind, thickness_mm FROM public.infill_articles
    WHERE sku = 'PANEL-A'$$,
    '23505', NULL, 'duplicate panel SKU in a system is rejected');
SELECT throws_ok($$INSERT INTO public.infill_articles (system_id, sku, name, kind, thickness_mm)
    SELECT id, 'NOT-PANEL', 'X', 'GLASS', 24.00 FROM public.profile_systems WHERE code = 'PGTAP06'$$,
    '23514', NULL, 'unsupported infill kinds cannot enter the panel contract');
SELECT ok(has_table_privilege('service_role', 'public.infill_articles', 'INSERT,UPDATE,DELETE,SELECT'),
    'service_role has catalog maintenance privileges');
SELECT * FROM finish();
ROLLBACK;
