BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path=public,extensions;
SELECT plan(85);
SELECT has_column('public','profile_purchase_mappings','id','profile_purchase_mappings.id exists');
SELECT has_column('public','profile_purchase_mappings','profile_article_id','profile_purchase_mappings.profile_article_id exists');
SELECT has_column('public','profile_purchase_mappings','org_id','profile_purchase_mappings.org_id exists');
SELECT has_column('public','profile_purchase_mappings','commercial_sku','profile_purchase_mappings.commercial_sku exists');
SELECT has_column('public','profile_purchase_mappings','manufacturer_name','profile_purchase_mappings.manufacturer_name exists');
SELECT has_column('public','profile_purchase_mappings','supplier_name','profile_purchase_mappings.supplier_name exists');
SELECT has_column('public','profile_purchase_mappings','purchase_unit','profile_purchase_mappings.purchase_unit exists');
SELECT has_column('public','profile_purchase_mappings','is_active','profile_purchase_mappings.is_active exists');
SELECT has_column('public','profile_purchase_mappings','created_at','profile_purchase_mappings.created_at exists');
SELECT ok(NOT has_table_privilege('anon','public.profile_purchase_mappings','SELECT'),'anon cannot read profile_purchase_mappings');
SELECT has_column('public','reinforcement_articles','id','reinforcement_articles.id exists');
SELECT has_column('public','reinforcement_articles','system_id','reinforcement_articles.system_id exists');
SELECT has_column('public','reinforcement_articles','org_id','reinforcement_articles.org_id exists');
SELECT has_column('public','reinforcement_articles','parent_profile_article_id','reinforcement_articles.parent_profile_article_id exists');
SELECT has_column('public','reinforcement_articles','sku','reinforcement_articles.sku exists');
SELECT has_column('public','reinforcement_articles','commercial_sku','reinforcement_articles.commercial_sku exists');
SELECT has_column('public','reinforcement_articles','name','reinforcement_articles.name exists');
SELECT has_column('public','reinforcement_articles','manufacturer_name','reinforcement_articles.manufacturer_name exists');
SELECT has_column('public','reinforcement_articles','supplier_name','reinforcement_articles.supplier_name exists');
SELECT has_column('public','reinforcement_articles','stock_length_mm','reinforcement_articles.stock_length_mm exists');
SELECT has_column('public','reinforcement_articles','thickness_mm','reinforcement_articles.thickness_mm exists');
SELECT has_column('public','reinforcement_articles','ix_cm4','reinforcement_articles.ix_cm4 exists');
SELECT has_column('public','reinforcement_articles','purchase_unit','reinforcement_articles.purchase_unit exists');
SELECT has_column('public','reinforcement_articles','is_default','reinforcement_articles.is_default exists');
SELECT has_column('public','reinforcement_articles','is_active','reinforcement_articles.is_active exists');
SELECT has_column('public','reinforcement_articles','created_at','reinforcement_articles.created_at exists');
SELECT ok(NOT has_table_privilege('anon','public.reinforcement_articles','SELECT'),'anon cannot read reinforcement_articles');
SELECT has_column('public','cutting_profiles','id','cutting_profiles.id exists');
SELECT has_column('public','cutting_profiles','org_id','cutting_profiles.org_id exists');
SELECT has_column('public','cutting_profiles','code','cutting_profiles.code exists');
SELECT has_column('public','cutting_profiles','name','cutting_profiles.name exists');
SELECT has_column('public','cutting_profiles','kerf_mm','cutting_profiles.kerf_mm exists');
SELECT has_column('public','cutting_profiles','head_trim_mm','cutting_profiles.head_trim_mm exists');
SELECT has_column('public','cutting_profiles','tail_trim_mm','cutting_profiles.tail_trim_mm exists');
SELECT has_column('public','cutting_profiles','is_default','cutting_profiles.is_default exists');
SELECT has_column('public','cutting_profiles','is_active','cutting_profiles.is_active exists');
SELECT has_column('public','cutting_profiles','created_at','cutting_profiles.created_at exists');
SELECT ok(NOT has_table_privilege('anon','public.cutting_profiles','SELECT'),'anon cannot read cutting_profiles');
SELECT has_column('public','inspector_rule_configs','id','inspector_rule_configs.id exists');
SELECT has_column('public','inspector_rule_configs','system_id','inspector_rule_configs.system_id exists');
SELECT has_column('public','inspector_rule_configs','org_id','inspector_rule_configs.org_id exists');
SELECT has_column('public','inspector_rule_configs','rule_id','inspector_rule_configs.rule_id exists');
SELECT has_column('public','inspector_rule_configs','params','inspector_rule_configs.params exists');
SELECT has_column('public','inspector_rule_configs','is_active','inspector_rule_configs.is_active exists');
SELECT has_column('public','inspector_rule_configs','created_at','inspector_rule_configs.created_at exists');
SELECT has_column('public','inspector_rule_configs','updated_at','inspector_rule_configs.updated_at exists');
SELECT ok(NOT has_table_privilege('anon','public.inspector_rule_configs','SELECT'),'anon cannot read inspector_rule_configs');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='profile_systems' AND column_name='chamber_clearance_mm' AND data_type='numeric' AND numeric_precision=10 AND numeric_scale=2 AND is_nullable='YES'),'exact profile_systems.chamber_clearance_mm');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='hardware_kits' AND column_name='carriage_capacity_kg' AND data_type='numeric' AND numeric_precision=8 AND numeric_scale=2 AND is_nullable='YES'),'exact hardware_kits.carriage_capacity_kg');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='reinforcement_articles' AND column_name='stock_length_mm' AND data_type='numeric' AND numeric_precision=10 AND numeric_scale=2 AND is_nullable='NO'),'exact reinforcement_articles.stock_length_mm');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='reinforcement_articles' AND column_name='ix_cm4' AND data_type='numeric' AND numeric_precision=12 AND numeric_scale=4 AND is_nullable='YES'),'exact reinforcement_articles.ix_cm4');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='reinforcement_articles' AND column_name='thickness_mm' AND data_type='numeric' AND numeric_precision=6 AND numeric_scale=2 AND is_nullable='YES'),'exact reinforcement_articles.thickness_mm');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cutting_profiles' AND column_name='kerf_mm' AND data_type='numeric' AND numeric_precision=10 AND numeric_scale=2 AND is_nullable='NO'),'exact cutting_profiles.kerf_mm');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cutting_profiles' AND column_name='head_trim_mm' AND data_type='numeric' AND numeric_precision=10 AND numeric_scale=2 AND is_nullable='NO'),'exact cutting_profiles.head_trim_mm');
SELECT ok(EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cutting_profiles' AND column_name='tail_trim_mm' AND data_type='numeric' AND numeric_precision=10 AND numeric_scale=2 AND is_nullable='NO'),'exact cutting_profiles.tail_trim_mm');
SELECT is((SELECT count(*) FROM public.inspector_rule_configs),168::BIGINT,'fourteen global configs per reference family');
-- Exercise mutable catalog permissions on independent, unreferenced global rows.
INSERT INTO public.profile_systems
SELECT (jsonb_populate_record(NULL::public.profile_systems,to_jsonb(source)||
 jsonb_build_object('id','55700000-0000-4000-8000-000000000001','code','PGTAP07','technical_locked',false,'is_demo',false))).*
FROM public.profile_systems source WHERE code='DEMO_60';
INSERT INTO public.profile_articles
SELECT (jsonb_populate_record(NULL::public.profile_articles,to_jsonb(source)||
 jsonb_build_object('id','55700000-0000-4000-8000-000000000002','system_id','55700000-0000-4000-8000-000000000001','sku','PGTAP07-FRAME'))).*
FROM public.profile_articles source WHERE sku='MARCO';
INSERT INTO public.inspector_rule_configs(system_id,rule_id,params)
VALUES ('55700000-0000-4000-8000-000000000001','R01','{}');
INSERT INTO public.profile_purchase_mappings(profile_article_id,commercial_sku,manufacturer_name,purchase_unit)
VALUES ('55700000-0000-4000-8000-000000000002','PGTAP07-BAR','DEMO','BAR');
INSERT INTO public.reinforcement_articles(system_id,parent_profile_article_id,sku,commercial_sku,name,stock_length_mm,purchase_unit)
VALUES ('55700000-0000-4000-8000-000000000001','55700000-0000-4000-8000-000000000002','PGTAP07-STEEL','PGTAP07-STEEL','DEMO',6000,'BAR');
INSERT INTO public.cutting_profiles(code,name,kerf_mm,head_trim_mm,tail_trim_mm)
VALUES ('PGTAP07-SAW','DEMO',4,15,15);
SELECT throws_ok($q$INSERT INTO public.inspector_rule_configs(system_id,rule_id,params) SELECT id,'R00','{}' FROM public.profile_systems WHERE code='PGTAP07'$q$,'23514',NULL,'reject R00');
SELECT throws_ok($q$INSERT INTO public.inspector_rule_configs(system_id,rule_id,params) SELECT id,'R15','{}' FROM public.profile_systems WHERE code='PGTAP07'$q$,'23514',NULL,'reject R15');
SELECT throws_ok($q$UPDATE public.inspector_rule_configs SET params='[]' WHERE rule_id='R01' AND system_id='55700000-0000-4000-8000-000000000001'$q$,'23514',NULL,'params must be object');
SELECT throws_ok($q$UPDATE public.profile_systems SET chamber_clearance_mm=NULL WHERE code='PGTAP07'$q$,'P0001','Active Inspector requires chamber clearance','cannot remove live clearance');
SELECT throws_ok($q$INSERT INTO public.profile_purchase_mappings(profile_article_id,commercial_sku,manufacturer_name,purchase_unit) VALUES ('00000000-0000-4000-8000-000000000000','INVALID','DEMO','BAR')$q$,'23503',NULL,'mapping parent FK');
SELECT throws_ok($q$INSERT INTO public.reinforcement_articles(system_id,parent_profile_article_id,sku,commercial_sku,name,stock_length_mm,purchase_unit) SELECT id,'00000000-0000-4000-8000-000000000000','INVALID','INVALID','DEMO',6000,'BAR' FROM public.profile_systems WHERE code='PGTAP07'$q$,'23503',NULL,'steel parent FK');
INSERT INTO public.tenancy_organizations(id,name,tax_id) VALUES
 ('11111111-1111-4111-8111-111111111111','A','SHOT07-A'),
 ('22222222-2222-4222-8222-222222222222','B','SHOT07-B');
INSERT INTO public.tenancy_memberships(org_id,user_id) VALUES
 ('11111111-1111-4111-8111-111111111111','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'),
 ('22222222-2222-4222-8222-222222222222','bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb');
INSERT INTO public.profile_purchase_mappings(profile_article_id,org_id,commercial_sku,manufacturer_name,purchase_unit)
 SELECT id,'11111111-1111-4111-8111-111111111111','TENANT-BAR','DEMO','BAR' FROM public.profile_articles WHERE sku='PGTAP07-FRAME';
 INSERT INTO public.reinforcement_articles(system_id,org_id,parent_profile_article_id,sku,commercial_sku,name,stock_length_mm,purchase_unit,is_default)
 SELECT system_id,'11111111-1111-4111-8111-111111111111',id,'TENANT-STEEL','TENANT-STEEL-BAR','DEMO',5800,'BAR',TRUE FROM public.profile_articles WHERE sku='PGTAP07-FRAME';
 INSERT INTO public.cutting_profiles(org_id,code,name,kerf_mm,head_trim_mm,tail_trim_mm,is_default)
 VALUES ('11111111-1111-4111-8111-111111111111','TENANT-SAW','DEMO',4,15,15,TRUE);
 INSERT INTO public.inspector_rule_configs(system_id,org_id,rule_id,params)
 SELECT id,'11111111-1111-4111-8111-111111111111','R01','{}' FROM public.profile_systems WHERE code='PGTAP07';
INSERT INTO public.profile_purchase_mappings(profile_article_id,org_id,commercial_sku,manufacturer_name,purchase_unit)
 SELECT id,'22222222-2222-4222-8222-222222222222','TENANT-BAR','DEMO','BAR' FROM public.profile_articles WHERE sku='PGTAP07-FRAME';
 INSERT INTO public.reinforcement_articles(system_id,org_id,parent_profile_article_id,sku,commercial_sku,name,stock_length_mm,purchase_unit,is_default)
 SELECT system_id,'22222222-2222-4222-8222-222222222222',id,'TENANT-STEEL','TENANT-STEEL-BAR','DEMO',5800,'BAR',TRUE FROM public.profile_articles WHERE sku='PGTAP07-FRAME';
 INSERT INTO public.cutting_profiles(org_id,code,name,kerf_mm,head_trim_mm,tail_trim_mm,is_default)
 VALUES ('22222222-2222-4222-8222-222222222222','TENANT-SAW','DEMO',4,15,15,TRUE);
 INSERT INTO public.inspector_rule_configs(system_id,org_id,rule_id,params)
 SELECT id,'22222222-2222-4222-8222-222222222222','R01','{}' FROM public.profile_systems WHERE code='PGTAP07';
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims','{"sub":"aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa","role":"authenticated"}',TRUE);
SELECT set_config('request.jwt.claim.sub','aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',TRUE);
SELECT ok((SELECT count(*)>0 FROM public.profile_purchase_mappings WHERE org_id IS NULL),'A reads global profile_purchase_mappings');
SELECT is((SELECT count(*) FROM public.profile_purchase_mappings WHERE org_id='11111111-1111-4111-8111-111111111111'),1::BIGINT,'A reads own profile_purchase_mappings');
SELECT is((SELECT count(*) FROM public.profile_purchase_mappings WHERE org_id='22222222-2222-4222-8222-222222222222'),0::BIGINT,'A cannot read B profile_purchase_mappings');
SELECT throws_ok($$UPDATE public.profile_purchase_mappings SET is_active=FALSE WHERE org_id IS NULL$$, '42501', NULL, 'tenant cannot modify global profile_purchase_mappings — member writes are grant-denied');
SET LOCAL ROLE service_role;
WITH changed AS (UPDATE public.profile_purchase_mappings SET is_active=is_active WHERE org_id IS NULL AND profile_article_id='55700000-0000-4000-8000-000000000002' RETURNING id) SELECT ok((SELECT count(*)>0 FROM changed),'service maintenance profile_purchase_mappings');
SET LOCAL ROLE authenticated;
SELECT ok((SELECT count(*)>0 FROM public.reinforcement_articles WHERE org_id IS NULL),'A reads global reinforcement_articles');
SELECT is((SELECT count(*) FROM public.reinforcement_articles WHERE org_id='11111111-1111-4111-8111-111111111111'),1::BIGINT,'A reads own reinforcement_articles');
SELECT is((SELECT count(*) FROM public.reinforcement_articles WHERE org_id='22222222-2222-4222-8222-222222222222'),0::BIGINT,'A cannot read B reinforcement_articles');
SELECT throws_ok($$UPDATE public.reinforcement_articles SET is_active=FALSE WHERE org_id IS NULL$$, '42501', NULL, 'tenant cannot modify global reinforcement_articles — member writes are grant-denied');
SET LOCAL ROLE service_role;
WITH changed AS (UPDATE public.reinforcement_articles SET is_active=is_active WHERE org_id IS NULL AND system_id='55700000-0000-4000-8000-000000000001' RETURNING id) SELECT ok((SELECT count(*)>0 FROM changed),'service maintenance reinforcement_articles');
SET LOCAL ROLE authenticated;
SELECT ok((SELECT count(*)>0 FROM public.cutting_profiles WHERE org_id IS NULL),'A reads global cutting_profiles');
SELECT is((SELECT count(*) FROM public.cutting_profiles WHERE org_id='11111111-1111-4111-8111-111111111111'),1::BIGINT,'A reads own cutting_profiles');
SELECT is((SELECT count(*) FROM public.cutting_profiles WHERE org_id='22222222-2222-4222-8222-222222222222'),0::BIGINT,'A cannot read B cutting_profiles');
SELECT throws_ok($$UPDATE public.cutting_profiles SET is_active=FALSE WHERE org_id IS NULL$$, '42501', NULL, 'tenant cannot modify global cutting_profiles — member writes are grant-denied');
SET LOCAL ROLE service_role;
WITH changed AS (UPDATE public.cutting_profiles SET is_active=is_active WHERE org_id IS NULL AND code='PGTAP07-SAW' RETURNING id) SELECT ok((SELECT count(*)>0 FROM changed),'service maintenance cutting_profiles');
SET LOCAL ROLE authenticated;
SELECT ok((SELECT count(*)>0 FROM public.inspector_rule_configs WHERE org_id IS NULL),'A reads global inspector_rule_configs');
SELECT is((SELECT count(*) FROM public.inspector_rule_configs WHERE org_id='11111111-1111-4111-8111-111111111111'),1::BIGINT,'A reads own inspector_rule_configs');
SELECT is((SELECT count(*) FROM public.inspector_rule_configs WHERE org_id='22222222-2222-4222-8222-222222222222'),0::BIGINT,'A cannot read B inspector_rule_configs');
SELECT throws_ok($$UPDATE public.inspector_rule_configs SET is_active=FALSE WHERE org_id IS NULL$$, '42501', NULL, 'tenant cannot modify global inspector_rule_configs — member writes are grant-denied');
SET LOCAL ROLE service_role;
WITH changed AS (UPDATE public.inspector_rule_configs SET is_active=is_active WHERE org_id IS NULL AND system_id='55700000-0000-4000-8000-000000000001' RETURNING id) SELECT ok((SELECT count(*)>0 FROM changed),'service maintenance inspector_rule_configs');
SET LOCAL ROLE authenticated;
RESET ROLE;
INSERT INTO public.profile_purchase_mappings SELECT (jsonb_populate_record(NULL::public.profile_purchase_mappings,to_jsonb(t)||jsonb_build_object('id',gen_random_uuid()))).* FROM public.profile_purchase_mappings t WHERE org_id='11111111-1111-4111-8111-111111111111' LIMIT 1;
SELECT is((SELECT count(*) FROM public.profile_purchase_mappings WHERE org_id='11111111-1111-4111-8111-111111111111'),2::BIGINT,'ambiguity representable profile_purchase_mappings');
INSERT INTO public.cutting_profiles SELECT (jsonb_populate_record(NULL::public.cutting_profiles,to_jsonb(t)||jsonb_build_object('id',gen_random_uuid()))).* FROM public.cutting_profiles t WHERE org_id='11111111-1111-4111-8111-111111111111' LIMIT 1;
SELECT is((SELECT count(*) FROM public.cutting_profiles WHERE org_id='11111111-1111-4111-8111-111111111111'),2::BIGINT,'ambiguity representable cutting_profiles');
INSERT INTO public.reinforcement_articles SELECT (jsonb_populate_record(NULL::public.reinforcement_articles,to_jsonb(t)||jsonb_build_object('id',gen_random_uuid()))).* FROM public.reinforcement_articles t WHERE org_id='11111111-1111-4111-8111-111111111111' LIMIT 1;
SELECT is((SELECT count(*) FROM public.reinforcement_articles WHERE org_id='11111111-1111-4111-8111-111111111111'),2::BIGINT,'ambiguity representable reinforcement_articles');
SELECT * FROM finish();
ROLLBACK;
