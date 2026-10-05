BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path=public,extensions;
SELECT plan(101);
SELECT ok(relrowsecurity,relname||' has RLS') FROM pg_class
 WHERE relnamespace='public'::regnamespace AND relname IN
 ('manufacturing_placement_policies','handle_requirement_policies','reinforcement_cut_policies',
  'glass_purchase_mappings','hardware_purchase_mappings','panel_purchase_authorities',
  'project_documentary_inputs','position_documentary_inputs','purchase_projections',
  'purchase_requirement_lines','supplier_eligibility_versions','purchase_allocations',
  'order_allocation_batches','order_requirement_lines','document_artifacts','suppliers') ORDER BY relname;
SELECT ok(EXISTS(SELECT 1 FROM pg_roles WHERE rolname='documentary_backend'
   AND NOT rolsuper AND NOT rolbypassrls AND NOT rolcanlogin),
  'documentary_backend has no login or RLS bypass');
SELECT ok(NOT pg_has_role('authenticated','documentary_backend','MEMBER'),
  'public role has no membership in documentary_backend');

INSERT INTO tenancy_organizations(id,name,tax_id) VALUES
 ('88600000-0000-4000-8000-000000000001','Documentary A','SHOT09-A'),
 ('88600000-0000-4000-8000-000000000002','Documentary B','SHOT09-B');
INSERT INTO tenancy_memberships(org_id,user_id,role) VALUES
 ('88600000-0000-4000-8000-000000000001','88610000-0000-4000-8000-000000000001','OWNER'),
 ('88600000-0000-4000-8000-000000000001','88610000-0000-4000-8000-000000000002','ESTIMATOR'),
 ('88600000-0000-4000-8000-000000000001','88610000-0000-4000-8000-000000000003','WORKSHOP_MANAGER'),
 ('88600000-0000-4000-8000-000000000002','88610000-0000-4000-8000-000000000099','OWNER');
INSERT INTO projects(id,org_id,code,name,client_name,created_by) VALUES
 ('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','S09-A1','Doc A1','Fixture','88610000-0000-4000-8000-000000000001'),
 ('88620000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001','S09-A2','Doc A2','Fixture','88610000-0000-4000-8000-000000000001'),
 ('88620000-0000-4000-8000-000000000003','88600000-0000-4000-8000-000000000001','S09-A3','Doc A3','Fixture','88610000-0000-4000-8000-000000000001');
INSERT INTO project_positions(id,org_id,project_id,position_index,typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot)
 SELECT '88630000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001',1,'FIXED',id,1000,1000,'{}','{}' FROM profile_systems WHERE code='DEMO_60';
INSERT INTO project_positions(id,org_id,project_id,position_index,typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot)
 SELECT '88630000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000002',1,'FIXED',id,1000,1000,'{}','{}' FROM profile_systems WHERE code='DEMO_60';
INSERT INTO project_positions(id,org_id,project_id,position_index,typology,system_id,width_mm,height_mm,parametric_tree,bom_snapshot)
 SELECT '88630000-0000-4000-8000-000000000003','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000003',1,'FIXED',id,1000,1000,'{}','{}' FROM profile_systems WHERE code='DEMO_60';
INSERT INTO pricing_operations(id,org_id,project_id,requested_by,request,input_snapshot,result,source_revision,state,reason) VALUES
 ('88640000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88610000-0000-4000-8000-000000000001','{}','{}','{}','REV-A','PREVIEW','shot09 preview fixture'),
 ('88640000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88610000-0000-4000-8000-000000000001','{}','{}','{}','REV-A','APPLIED','shot09 applied fixture'),
 ('88640000-0000-4000-8000-000000000003','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88610000-0000-4000-8000-000000000001','{}','{}','{}','REV-A','APPLIED','shot09 second applied fixture');

SELECT lives_ok($$INSERT INTO project_documentary_inputs(project_id,org_id,payment_terms,quotation_valid_until,created_by)
 VALUES('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','50/50','2026-10-14','88610000-0000-4000-8000-000000000001')$$,'typed project inputs save before sealing');
SELECT lives_ok($$INSERT INTO position_documentary_inputs(position_id,project_id,org_id,manufacturing_placement_policy_id,handle_requirement_policy_id,reinforcement_cut_policy_id,workshop_annotations,structural_inputs,glass_polishing,handle_intents,accessory_schedule,created_by)
 SELECT '88630000-0000-4000-8000-000000000002','88620000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001',placement.id,handles.id,steel.id,'[]','[]','[]','[]','{"coverage":"NONE_REQUIRED","items":[]}','88610000-0000-4000-8000-000000000001'
 FROM manufacturing_placement_policies placement,handle_requirement_policies handles,reinforcement_cut_policies steel
 WHERE placement.system_id=handles.system_id AND handles.system_id=steel.system_id
   AND placement.org_id IS NULL AND handles.org_id IS NULL AND steel.org_id IS NULL
   AND handles.version=(SELECT max(h2.version) FROM handle_requirement_policies h2 WHERE h2.system_id=handles.system_id AND h2.org_id IS NULL)
   AND placement.version=(SELECT max(p2.version) FROM manufacturing_placement_policies p2 WHERE p2.system_id=placement.system_id AND p2.org_id IS NULL)
   AND steel.version=(SELECT max(s2.version) FROM reinforcement_cut_policies s2 WHERE s2.system_id=steel.system_id AND s2.org_id IS NULL)
   AND placement.system_id=(SELECT id FROM profile_systems WHERE code='DEMO_60')$$,'typed position inputs accept global scoped policies');
INSERT INTO manufacturing_placement_policies(id,system_id,org_id,version,authority)
 SELECT '88690000-0000-4000-8000-000000000009',id,'88600000-0000-4000-8000-000000000002',1,
        '{"schema_version":1,"policy_id":"B-POLICY","version":1,"sliding_leaf_offsets":{},"sliding_infill_offsets":{},"bead_offsets":{}}'
 FROM profile_systems WHERE code='DEMO_60';
SELECT throws_ok($$INSERT INTO position_documentary_inputs(position_id,project_id,org_id,manufacturing_placement_policy_id,handle_requirement_policy_id,reinforcement_cut_policy_id,workshop_annotations,structural_inputs,glass_polishing,handle_intents,accessory_schedule,created_by)
 SELECT '88630000-0000-4000-8000-000000000003','88620000-0000-4000-8000-000000000003','88600000-0000-4000-8000-000000000001','88690000-0000-4000-8000-000000000009',handles.id,steel.id,'[]','[]','[]','[]','{"coverage":"NONE_REQUIRED","items":[]}','88610000-0000-4000-8000-000000000001'
 FROM handle_requirement_policies handles,reinforcement_cut_policies steel
 WHERE handles.system_id=steel.system_id AND handles.org_id IS NULL AND steel.org_id IS NULL
   AND handles.version=(SELECT max(h2.version) FROM handle_requirement_policies h2 WHERE h2.system_id=handles.system_id AND h2.org_id IS NULL)
   AND handles.system_id=(SELECT id FROM profile_systems WHERE code='DEMO_60')$$,'23503','documentary_policy_scope_mismatch','foreign tenant policy cannot bind');

SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','REV-A','{}','88610000-0000-4000-8000-000000000001','88640000-0000-4000-8000-000000000001','DOCUMENTARY_CANONICAL_V1','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',TRUE,TRUE)$$,'23514','applied_pricing_authority_required','preview operation cannot seal a revision');
SELECT lives_ok($$INSERT INTO project_versions(id,project_id,org_id,revision_code,snapshot_json,emitted_by,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88650000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','REV-A','{}','88610000-0000-4000-8000-000000000001','88640000-0000-4000-8000-000000000002','DOCUMENTARY_CANONICAL_V1','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',TRUE,TRUE)$$,'exact APPLIED operation seals initial REV-A');
SELECT throws_ok($$UPDATE project_versions SET snapshot_json='{}'::jsonb$$,'42501','documentary_evidence_immutable','sealed version update forbidden');
SELECT throws_ok($$DELETE FROM project_versions$$,'42501','documentary_evidence_immutable','sealed version delete forbidden');
SELECT throws_ok($$UPDATE pricing_operations SET reason='drift' WHERE id='88640000-0000-4000-8000-000000000002'$$,'42501','sealed_pricing_operation_immutable','sealed operation update forbidden');
SELECT throws_ok($$DELETE FROM pricing_operations WHERE id='88640000-0000-4000-8000-000000000002'$$,'42501','sealed_pricing_operation_immutable','sealed operation delete forbidden');
SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','REV-B','{}','88610000-0000-4000-8000-000000000001','88640000-0000-4000-8000-000000000003','DOCUMENTARY_CANONICAL_V1','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',TRUE,TRUE)$$,'23514',NULL,'REV-B is out of SHOT-09 scope');
SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','REV-A','{}','88610000-0000-4000-8000-000000000001','88640000-0000-4000-8000-000000000003','DOCUMENTARY_CANONICAL_V1','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',TRUE,TRUE)$$,'23505',NULL,'only one REV-A exists per project');
SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001','REV-A','{}','88610000-0000-4000-8000-000000000001','88640000-0000-4000-8000-000000000003','DOCUMENTARY_CANONICAL_V1','not-a-hash','dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',TRUE,TRUE)$$,'23514',NULL,'bom_hash must be 64 lowercase hex');
SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000002','REV-A','{}','88610000-0000-4000-8000-000000000001','88640000-0000-4000-8000-000000000002','DOCUMENTARY_CANONICAL_V1','eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee','ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',TRUE,TRUE)$$,'23514',NULL,'cross-tenant version binding cannot be forged');

SELECT throws_ok($$INSERT INTO project_documentary_inputs(project_id,org_id,payment_terms,quotation_valid_until,created_by)
 VALUES('88620000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','changed','2026-10-15','88610000-0000-4000-8000-000000000001')$$,'42501','sealed_documentary_inputs_immutable','sealed project input insert forbidden');
SELECT throws_ok($$UPDATE project_documentary_inputs SET payment_terms='changed'$$,'42501','sealed_documentary_inputs_immutable','sealed project input update forbidden');
SELECT throws_ok($$DELETE FROM project_documentary_inputs$$,'42501','sealed_documentary_inputs_immutable','sealed project input delete forbidden');

SELECT throws_ok($$INSERT INTO purchase_projections(project_id,project_version_id,org_id,bom_hash,snapshot_sha256,schema_version,projection_hash,snapshot_json,created_by)
 VALUES('88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',1,'1111111111111111111111111111111111111111111111111111111111111111','{}','88610000-0000-4000-8000-000000000001')$$,'23503',NULL,'forged BOM hash cannot bind a projection');
SELECT lives_ok($$INSERT INTO purchase_projections(id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,schema_version,projection_hash,snapshot_json,created_by)
 VALUES('88660000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',1,'1111111111111111111111111111111111111111111111111111111111111111','{}','88610000-0000-4000-8000-000000000001')$$,'projection binds to the exact version identity');
SELECT throws_ok($$INSERT INTO purchase_requirement_lines(id,requirement_key,projection_id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,category,technical_identity,purchasing_sku,physical_stock_identity,unit,quantity,specification,source_trace)
 VALUES('88670000-0000-4000-8000-000000000009','2222222222222222222222222222222222222222222222222222222222222222','88660000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','9999999999999999999999999999999999999999999999999999999999999999','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_GLASS_PO','GLASS','{}','GLASS-BUY',NULL,'EA',1,'{}','[]')$$,'23503',NULL,'forged requirement hash binding is rejected');
SELECT lives_ok($$INSERT INTO purchase_requirement_lines(id,requirement_key,projection_id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,category,technical_identity,purchasing_sku,physical_stock_identity,unit,quantity,specification,source_trace)
 VALUES('88670000-0000-4000-8000-000000000001','2222222222222222222222222222222222222222222222222222222222222222','88660000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_GLASS_PO','GLASS','{}','GLASS-BUY',NULL,'EA',2,'{}','[]')$$,'requirement line binds to the projection');
SELECT lives_ok($$INSERT INTO purchase_requirement_lines(id,requirement_key,projection_id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,category,technical_identity,purchasing_sku,physical_stock_identity,unit,quantity,specification,source_trace)
 VALUES('88670000-0000-4000-8000-000000000002','3333333333333333333333333333333333333333333333333333333333333333','88660000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_GLASS_PO','GLASS','{}','GLASS-BUY-2',NULL,'EA',1,'{}','[]')$$,'second requirement line binds to the projection');
SELECT lives_ok($$INSERT INTO supplier_eligibility_versions(id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,supplier_identity,supplier_name,supplier_details,eligible_requirement_keys,evidence,version,content_hash,created_by)
 VALUES('88680000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_GLASS_PO','SUP-1','Proveedor 1','{}','["2222222222222222222222222222222222222222222222222222222222222222","3333333333333333333333333333333333333333333333333333333333333333"]','{}',1,'4444444444444444444444444444444444444444444444444444444444444444','88610000-0000-4000-8000-000000000003')$$,'explicit eligibility binds to the frozen version');
SELECT throws_ok($$INSERT INTO purchase_allocations(id,requirement_line_id,supplier_eligibility_id,project_id,project_version_id,org_id,order_type,allocated_by)
 VALUES('88690000-0000-4000-8000-000000000009','88670000-0000-4000-8000-000000000001','88680000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','SUPPLIER_PROFILE_PO','88610000-0000-4000-8000-000000000003')$$,'23503',NULL,'forged allocation order type cannot bind');
SELECT lives_ok($$INSERT INTO purchase_allocations(id,requirement_line_id,supplier_eligibility_id,project_id,project_version_id,org_id,order_type,allocated_by)
 VALUES('88690000-0000-4000-8000-000000000001','88670000-0000-4000-8000-000000000001','88680000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','SUPPLIER_GLASS_PO','88610000-0000-4000-8000-000000000003')$$,'whole-line allocation binds requirement and eligibility');
SELECT lives_ok($$INSERT INTO order_allocation_batches(id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,allocation_hash,confirmed_by,confirmed_at)
 VALUES('88700000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_GLASS_PO','5555555555555555555555555555555555555555555555555555555555555555','88610000-0000-4000-8000-000000000003',now())$$,'one confirmed batch exists per version and order type');
SELECT throws_ok($$INSERT INTO order_allocation_batches(project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,allocation_hash,confirmed_by,confirmed_at)
 VALUES('88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_GLASS_PO','6666666666666666666666666666666666666666666666666666666666666666','88610000-0000-4000-8000-000000000003',now())$$,'23505',NULL,'a second batch for the same order type is rejected');
SELECT throws_ok($$INSERT INTO purchase_allocations(id,requirement_line_id,supplier_eligibility_id,project_id,project_version_id,org_id,order_type,allocated_by)
 VALUES('88690000-0000-4000-8000-000000000002','88670000-0000-4000-8000-000000000002','88680000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','SUPPLIER_GLASS_PO','88610000-0000-4000-8000-000000000003')$$,'42501','confirmed_allocation_immutable','allocation insert after confirmed batch is forbidden');
SELECT throws_ok($$UPDATE purchase_allocations SET allocated_by='88610000-0000-4000-8000-000000000001'$$,'42501','confirmed_allocation_immutable','allocation update after confirmed batch is forbidden');
SELECT throws_ok($$DELETE FROM purchase_allocations$$,'42501','confirmed_allocation_immutable','allocation delete after confirmed batch is forbidden');

SELECT lives_ok($$INSERT INTO orders(id,org_id,project_id,order_type,order_code,status,supplier_name,payload_json,project_version_id,allocation_batch_id,supplier_eligibility_id,bom_hash,revision_snapshot_sha256,purchase_projection_hash,allocation_identity,order_snapshot_hash,supplier_identity,supplier_details,confirmed_by,confirmed_at)
 VALUES('88710000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','SUPPLIER_GLASS_PO','PO-S09-1','DRAFT','Proveedor 1','{}','88650000-0000-4000-8000-000000000001','88700000-0000-4000-8000-000000000001','88680000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','1111111111111111111111111111111111111111111111111111111111111111','7777777777777777777777777777777777777777777777777777777777777777','8888888888888888888888888888888888888888888888888888888888888888','SUP-1','{}','88610000-0000-4000-8000-000000000003',now())$$,'supplier order binds batch, eligibility, and frozen hashes');
SELECT lives_ok($$UPDATE orders SET status='SENT',sent_by='88610000-0000-4000-8000-000000000003',sent_at=now(),expected_at='2026-12-31',sent_to='compras@proveedor.cl',updated_at=now() WHERE id='88710000-0000-4000-8000-000000000001'$$,'explicit send transitions DRAFT to SENT and captures the promised date and destination');
SELECT col_is_null('public','orders','expected_at','promised delivery date is optional (captured, never invented)');
SELECT col_is_null('public','orders','sent_to','send destination is optional (captured, never invented)');
SELECT throws_ok($$UPDATE orders SET expected_at='2027-01-15' WHERE id='88710000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','promised date is immutable once sent');
SELECT throws_ok($$UPDATE orders SET sent_to='otro@proveedor.cl' WHERE id='88710000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','send destination is immutable once sent');
SELECT throws_ok($$UPDATE orders SET order_code='PO-S09-X' WHERE id='88710000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','confirmed order payload is immutable');
SELECT throws_ok($$DELETE FROM orders WHERE id='88710000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','supplier order cannot be deleted');
SELECT lives_ok($$UPDATE orders SET status='PARTIALLY_RECEIVED',updated_at=now() WHERE id='88710000-0000-4000-8000-000000000001'$$,'a sent order advances to partially received when goods arrive');
SELECT lives_ok($$UPDATE orders SET status='FULFILLED',updated_at=now() WHERE id='88710000-0000-4000-8000-000000000001'$$,'a partially received order advances to fulfilled');
SELECT throws_ok($$UPDATE orders SET status='CANCELLED',cancelled_by='88610000-0000-4000-8000-000000000003',cancelled_at=now(),updated_at=now() WHERE id='88710000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','a fulfilled order can never be cancelled');
SELECT lives_ok($$INSERT INTO orders(id,org_id,project_id,order_type,order_code,status,supplier_name,payload_json,project_version_id,allocation_batch_id,supplier_eligibility_id,bom_hash,revision_snapshot_sha256,purchase_projection_hash,allocation_identity,order_snapshot_hash,supplier_identity,supplier_details,confirmed_by,confirmed_at)
 VALUES('88740000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','SUPPLIER_GLASS_PO','PO-S09-3','DRAFT','Proveedor 2','{}','88650000-0000-4000-8000-000000000001','88700000-0000-4000-8000-000000000001','88680000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','2222222222222222222222222222222222222222222222222222222222222222','3333333333333333333333333333333333333333333333333333333333333333','9999999999999999999999999999999999999999999999999999999999999999','SUP-2','{}','88610000-0000-4000-8000-000000000003',now())$$,'a second draft order exists for cancellation');
SELECT throws_ok($$UPDATE orders SET status='CANCELLED',updated_at=now() WHERE id='88740000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','cancel requires operator identity and timestamp');
SELECT lives_ok($$UPDATE orders SET status='SENT',sent_by='88610000-0000-4000-8000-000000000003',sent_at=now(),updated_at=now() WHERE id='88740000-0000-4000-8000-000000000001'$$,'a draft order sends with operator evidence');
SELECT lives_ok($$UPDATE orders SET status='PARTIALLY_RECEIVED',updated_at=now() WHERE id='88740000-0000-4000-8000-000000000001'$$,'a sent order receives partially');
SELECT lives_ok($$UPDATE orders SET status='CANCELLED',cancelled_by='88610000-0000-4000-8000-000000000003',cancelled_at=now(),updated_at=now() WHERE id='88740000-0000-4000-8000-000000000001'$$,'a partially received order can be cancelled — received lines stay as evidence');
SELECT throws_ok($$UPDATE orders SET status='SENT',sent_by='88610000-0000-4000-8000-000000000003',sent_at=now(),updated_at=now() WHERE id='88740000-0000-4000-8000-000000000001'$$,'42501','order_evidence_immutable','a cancelled order cannot be sent');
SELECT lives_ok($$INSERT INTO order_requirement_lines(id,order_id,requirement_line_id,project_id,project_version_id,org_id,order_type,bom_hash,revision_snapshot_sha256,quantity,line_snapshot,line_hash)
 VALUES('88720000-0000-4000-8000-000000000001','88710000-0000-4000-8000-000000000001','88670000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','SUPPLIER_GLASS_PO','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',2,'{}','9999999999999999999999999999999999999999999999999999999999999999')$$,'order line binds the exact order and requirement');
SELECT lives_ok($$INSERT INTO orders(org_id,project_id,order_type,order_code,payload_json)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','WORKSHOP_OT','OT-S09-1','{}')$$,'workshop OT keeps its inherited lifecycle');
SELECT lives_ok($$DELETE FROM orders WHERE order_code='OT-S09-1'$$,'workshop OT deletion stays allowed');
SELECT throws_ok($$INSERT INTO orders(org_id,project_id,order_type,order_code,payload_json)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','SUPPLIER_PANEL_PO','PO-S09-2','{}')$$,'23514',NULL,'supplier order without evidence binding is rejected');

SELECT lives_ok($$INSERT INTO document_artifacts(id,org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88730000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','PROJECT_REVISION','88650000-0000-4000-8000-000000000001','DOC-05','PDF','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000001/projects/88620000-0000-4000-8000-000000000001/REV-A/doc05.pdf','abababababababababababababababababababababababababababababababab','application/pdf',1024,'88610000-0000-4000-8000-000000000001')$$,'revision artifact records an immutable slot');
SELECT throws_ok($$INSERT INTO document_artifacts(org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','PROJECT_REVISION','88650000-0000-4000-8000-000000000001','DOC-05','PDF','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000001/projects/88620000-0000-4000-8000-000000000001/REV-A/doc05b.pdf','cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd','application/pdf',1024,'88610000-0000-4000-8000-000000000001')$$,'23505',NULL,'occupied artifact slot cannot be replaced');
SELECT throws_ok($$INSERT INTO document_artifacts(org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','PROJECT_REVISION','88650000-0000-4000-8000-000000000001','DOC-02','XLSX','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000001/projects/88620000-0000-4000-8000-000000000001/REV-A/doc02.xlsx','efefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',1024,'88610000-0000-4000-8000-000000000001')$$,'23514',NULL,'DOC-02 cannot claim the revision scope');
SELECT throws_ok($$INSERT INTO document_artifacts(org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','PROJECT_REVISION','88650000-0000-4000-8000-000000000001','DOC-01','PDF','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000002/projects/88620000-0000-4000-8000-000000000001/REV-A/doc01.pdf','0101010101010101010101010101010101010101010101010101010101010101','application/pdf',1024,'88610000-0000-4000-8000-000000000001')$$,'23514',NULL,'artifact storage key must stay inside the org prefix');
SELECT throws_ok($$UPDATE document_artifacts SET file_sha256='0202020202020202020202020202020202020202020202020202020202020202'$$,'42501','documentary_evidence_immutable','artifact update forbidden');
SELECT throws_ok($$DELETE FROM document_artifacts$$,'42501','documentary_evidence_immutable','artifact delete forbidden');

SELECT set_config('request.jwt.claims','{"sub":"88610000-0000-4000-8000-000000000001","role":"authenticated","aal":"aal2"}',true);
SELECT set_config('request.jwt.claim.sub','88610000-0000-4000-8000-000000000001',true);
SET LOCAL ROLE documentary_backend;
SELECT is((SELECT count(*) FROM project_versions),1::bigint,'owner backend reads own sealed version');
SELECT lives_ok($$UPDATE project_positions SET location_tag='OBRA-NORTE',updated_at=now() WHERE id='88630000-0000-4000-8000-000000000002'$$,'documentary backend may tag an unsealed position');
SELECT throws_ok($$UPDATE project_positions SET cost_net=1 WHERE id='88630000-0000-4000-8000-000000000002'$$,'42501',NULL,'documentary backend cannot touch priced columns');
SELECT set_config('request.jwt.claims','{"sub":"88610000-0000-4000-8000-000000000099","role":"authenticated","aal":"aal2"}',true);
SELECT set_config('request.jwt.claim.sub','88610000-0000-4000-8000-000000000099',true);
SELECT is((SELECT count(*) FROM project_versions),0::bigint,'foreign tenant sees no sealed versions');
WITH changed AS (UPDATE project_positions SET location_tag='HACK' WHERE id='88630000-0000-4000-8000-000000000002' RETURNING id)
SELECT is((SELECT count(*) FROM changed),0::bigint,'foreign tenant cannot tag positions');
SELECT set_config('request.jwt.claims','{"sub":"88610000-0000-4000-8000-000000000003","role":"authenticated","aal":"aal2"}',true);
SELECT set_config('request.jwt.claim.sub','88610000-0000-4000-8000-000000000003',true);
SELECT is((SELECT count(*) FROM purchase_requirement_lines),2::bigint,'workshop manager reads frozen requirements');
SELECT is((SELECT count(*) FROM document_artifacts),1::bigint,'workshop manager reads artifact metadata');
SET LOCAL ROLE authenticated;
SELECT throws_ok($$SELECT * FROM document_artifacts$$,'42501',NULL,'authenticated cannot read the artifact registry directly');
SELECT is((SELECT count(*) FROM project_versions),1::bigint,'org member reads the version through safe columns');
RESET ROLE;
SELECT is((SELECT public FROM storage.buckets WHERE id='documents'),FALSE,'documents bucket stays private');

-- Populated-upgrade compatibility: a PRE_SHOT09 row stays typed, immutable,
-- and unable to bind documentary evidence; V1 keeps the full strict contract.
ALTER TABLE public.project_versions DISABLE TRIGGER require_applied_pricing_authority;
INSERT INTO project_versions(id,project_id,org_id,revision_code,snapshot_json,emitted_by,authority_version)
 VALUES('88740000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000003','88600000-0000-4000-8000-000000000001','REV-0','{}','88610000-0000-4000-8000-000000000001','PRE_SHOT09');
ALTER TABLE public.project_versions ENABLE TRIGGER require_applied_pricing_authority;
SELECT is((SELECT authority_version FROM project_versions WHERE id='88740000-0000-4000-8000-000000000001'),'PRE_SHOT09','pre-upgrade row keeps the explicit PRE_SHOT09 type');
SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,authority_version)
 VALUES('88620000-0000-4000-8000-000000000003','88600000-0000-4000-8000-000000000001','REV-9','{}','88610000-0000-4000-8000-000000000001','PRE_SHOT09')$$,'23514','legacy_version_insert_forbidden','new PRE_SHOT09 rows cannot be fabricated');
SELECT throws_ok($$UPDATE project_versions SET revision_code='REV-X' WHERE id='88740000-0000-4000-8000-000000000001'$$,'42501','documentary_evidence_immutable','legacy row stays immutable');
SELECT throws_ok($$INSERT INTO document_artifacts(org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000003','88740000-0000-4000-8000-000000000001','PROJECT_REVISION','88740000-0000-4000-8000-000000000001','DOC-05','PDF','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000001/projects/88620000-0000-4000-8000-000000000003/REV-0/doc05.pdf','1212121212121212121212121212121212121212121212121212121212121212','application/pdf',1024,'88610000-0000-4000-8000-000000000001')$$,'23503',NULL,'legacy version cannot bind a documentary artifact');
SELECT set_config('app.pricing_reason','pgTAP V1 authority fixture',true);
INSERT INTO pricing_operations(id,org_id,project_id,requested_by,request,input_snapshot,result,source_revision,state,reason) VALUES
 ('88640000-0000-4000-8000-000000000004','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000002','88610000-0000-4000-8000-000000000001','{}','{}','{}','REV-A','APPLIED','shot09 upgrade-applied fixture');
SELECT throws_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,authority_version,pricing_operation_id,canonical_version,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001','REV-A','{}','88610000-0000-4000-8000-000000000001','SHOT09_V1','88640000-0000-4000-8000-000000000004','DOCUMENTARY_CANONICAL_V1','dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',TRUE,TRUE)$$,'23514',NULL,'V1 revision without bom_hash is rejected');
SELECT lives_ok($$INSERT INTO project_versions(project_id,org_id,revision_code,snapshot_json,emitted_by,authority_version,pricing_operation_id,canonical_version,bom_hash,snapshot_sha256,production_allowed,documentary_complete)
 VALUES('88620000-0000-4000-8000-000000000002','88600000-0000-4000-8000-000000000001','REV-A','{}','88610000-0000-4000-8000-000000000001','SHOT09_V1','88640000-0000-4000-8000-000000000004','DOCUMENTARY_CANONICAL_V1','cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc','dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',TRUE,TRUE)$$,'a new V1 revision still satisfies the full contract after upgrade');
SELECT lives_ok($$INSERT INTO supplier_eligibility_versions(id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,supplier_identity,supplier_name,supplier_details,eligible_requirement_keys,evidence,version,content_hash,created_by)
 VALUES('88680000-0000-4000-8000-000000000009','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_HARDWARE_PO','SUP-3','Vorne SPA','{}','["2222222222222222222222222222222222222222222222222222222222222222"]','{}',1,'5454545454545454545454545454545454545454545454545454545454545454','88610000-0000-4000-8000-000000000003')$$,'hardware supplier eligibility binds to the frozen version');
SELECT lives_ok($$INSERT INTO order_allocation_batches(id,project_id,project_version_id,org_id,bom_hash,snapshot_sha256,order_type,allocation_hash,confirmed_by,confirmed_at)
 VALUES('88700000-0000-4000-8000-000000000009','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','SUPPLIER_HARDWARE_PO','5656565656565656565656565656565656565656565656565656565656565656','88610000-0000-4000-8000-000000000003',now())$$,'hardware allocation batch exists for the DOC-08 fixture');
SELECT lives_ok($$INSERT INTO orders(id,org_id,project_id,order_type,order_code,status,supplier_name,payload_json,project_version_id,allocation_batch_id,supplier_eligibility_id,bom_hash,revision_snapshot_sha256,purchase_projection_hash,allocation_identity,order_snapshot_hash,supplier_identity,supplier_details,confirmed_by,confirmed_at)
 VALUES('88750000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','SUPPLIER_HARDWARE_PO','PO-S09-9','DRAFT','Vorne SPA','{}','88650000-0000-4000-8000-000000000001','88700000-0000-4000-8000-000000000009','88680000-0000-4000-8000-000000000009','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','1111111111111111111111111111111111111111111111111111111111111111','5757575757575757575757575757575757575757575757575757575757575757','5858585858585858585858585858585858585858585858585858585858585858','SUP-3','{}','88610000-0000-4000-8000-000000000003',now())$$,'hardware order exists for the generic order document');
SELECT lives_ok($$INSERT INTO document_artifacts(id,org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,order_id,order_type,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88760000-0000-4000-8000-000000000001','88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','ORDER','88750000-0000-4000-8000-000000000001','DOC-08','PDF','88750000-0000-4000-8000-000000000001','SUPPLIER_HARDWARE_PO','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000001/projects/88620000-0000-4000-8000-000000000001/REV-A/doc08.pdf','5959595959595959595959595959595959595959595959595959595959595959','application/pdf',1024,'88610000-0000-4000-8000-000000000001')$$,'DOC-08 binds the hardware order slot');
SELECT throws_ok($$INSERT INTO document_artifacts(org_id,project_id,project_version_id,artifact_scope,artifact_scope_id,document_type,format,order_id,order_type,bom_hash,revision_snapshot_sha256,storage_bucket,storage_object_key,file_sha256,media_type,byte_size,created_by)
 VALUES('88600000-0000-4000-8000-000000000001','88620000-0000-4000-8000-000000000001','88650000-0000-4000-8000-000000000001','ORDER','88710000-0000-4000-8000-000000000001','DOC-08','PDF','88710000-0000-4000-8000-000000000001','SUPPLIER_GLASS_PO','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa','bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb','documents','org_88600000-0000-4000-8000-000000000001/projects/88620000-0000-4000-8000-000000000001/REV-A/doc08g.pdf','6060606060606060606060606060606060606060606060606060606060606060','application/pdf',1024,'88610000-0000-4000-8000-000000000001')$$,'23514',NULL,'DOC-08 cannot claim a glass order');
SELECT lives_ok($$INSERT INTO suppliers(org_id,tax_id,name) VALUES('88600000-0000-4000-8000-000000000001','76.111-2','Vorne SPA')$$,'org supplier entry binds a tax id');
SELECT lives_ok($$INSERT INTO suppliers(org_id,tax_id,name) VALUES('88600000-0000-4000-8000-000000000001','76.111-3','Seguridad Alu')$$,'a second supplier coexists');
SELECT throws_ok($$INSERT INTO suppliers(org_id,tax_id,name) VALUES('88600000-0000-4000-8000-000000000001','76.111-2','Otra Vidrieria')$$,'23505',NULL,'one supplier per org tax id');
SELECT lives_ok($$INSERT INTO suppliers(org_id,tax_id,name) VALUES('88600000-0000-4000-8000-000000000002','76.111-2','Otra Org')$$,'same tax id may exist for another org');
SELECT throws_ok($$INSERT INTO suppliers(org_id,tax_id,name) VALUES('88600000-0000-4000-8000-000000000001','','Sin nombre')$$,'23514',NULL,'empty tax id rejected');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'projects'
          AND policyname = 'project_documentary_backend_lock'
          AND cmd = 'UPDATE'
    ),
    'documentary_backend can lock project rows (POD confirm) without gaining UPDATE grants'
);
SELECT * FROM finish();
ROLLBACK;
