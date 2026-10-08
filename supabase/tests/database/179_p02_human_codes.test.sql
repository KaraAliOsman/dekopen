BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(21);

-- P02 — folios humanos por organización: OC- (órdenes de compra),
-- RT- (retazos), REC- (recepciones). Contador por org serializado por
-- advisory lock de transacción, relleno determinista por created_at,
-- formato cerrado por CHECK, unicidad por org e inmutabilidad del folio.

SELECT has_function(
    'private', 'next_human_code', ARRAY['uuid', 'text'],
    'next_human_code existe como función compartida'
);
SELECT has_column(
    'public', 'inventory_remnants', 'remnant_code',
    'inventory_remnants lleva el folio RT-'
);
SELECT has_column(
    'public', 'order_receipts', 'receipt_code',
    'order_receipts lleva el folio REC-'
);
SELECT col_has_check(
    'public', 'inventory_remnants', 'remnant_code',
    'remnant_code tiene formato cerrado RT-NNNNNN'
);
SELECT col_has_check(
    'public', 'order_receipts', 'receipt_code',
    'receipt_code tiene formato cerrado REC-NNNNNN'
);

-- El relleno fue determinista: para cada org, el folio coincide con el
-- orden estricto (created_at, id) de la migración. Vacío ⇒ verdad.
SELECT ok(
    COALESCE((
        SELECT bool_and(remnant_code = 'RT-' || lpad(rn::text, 6, '0'))
        FROM (
            SELECT id, remnant_code,
                   ROW_NUMBER() OVER (
                       PARTITION BY org_id ORDER BY created_at, id
                   ) AS rn
            FROM inventory_remnants
        ) numbered
    ), TRUE),
    'los retazos existentes quedaron foliados en orden created_at'
);
SELECT ok(
    COALESCE((
        SELECT bool_and(receipt_code = 'REC-' || lpad(rn::text, 6, '0'))
        FROM (
            SELECT id, receipt_code,
                   ROW_NUMBER() OVER (
                       PARTITION BY org_id ORDER BY created_at, id
                   ) AS rn
            FROM order_receipts
        ) numbered
    ), TRUE),
    'las recepciones existentes quedaron foliadas en orden created_at'
);

-- ── Fixture: dos orgs con un proyecto cada una ───────────────────────
INSERT INTO tenancy_organizations(id, name, tax_id) VALUES
    ('99aa0000-0000-4000-8000-000000000001', 'Org P02 A', 'R179-A'),
    ('99bb0000-0000-4000-8000-000000000001', 'Org P02 B', 'R179-B');
INSERT INTO tenancy_memberships(org_id, user_id, role) VALUES
    ('99aa0000-0000-4000-8000-000000000001',
     '99aa1000-0000-4000-8000-000000000001', 'WORKSHOP_MANAGER'),
    ('99bb0000-0000-4000-8000-000000000001',
     '99bb1000-0000-4000-8000-000000000001', 'WORKSHOP_MANAGER');
INSERT INTO projects(id, org_id, code, name, client_name, created_by) VALUES
    ('99aa2000-0000-4000-8000-000000000001',
     '99aa0000-0000-4000-8000-000000000001', 'P-R179-A', 'Casa A', 'Cliente',
     '99aa1000-0000-4000-8000-000000000001'),
    ('99bb2000-0000-4000-8000-000000000001',
     '99bb0000-0000-4000-8000-000000000001', 'P-R179-B', 'Casa B', 'Cliente',
     '99bb1000-0000-4000-8000-000000000001');

-- ── RT-: consecutivos por org, independientes entre orgs ─────────────
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'inventory_remnants'),
    'RT-000001',
    'primer retazo de la org A folia RT-000001'
);
INSERT INTO inventory_remnants(
    org_id, kind, sheet_workshop_sku, width_mm, height_mm, remnant_code)
VALUES (
    '99aa0000-0000-4000-8000-000000000001', 'SHEET', 'DEKO-GLASS-6MM',
    1200, 800,
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'inventory_remnants'));
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'inventory_remnants'),
    'RT-000002',
    'el contador ve la fila insertada en la misma transacción'
);
SELECT is(
    private.next_human_code(
        '99bb0000-0000-4000-8000-000000000001', 'inventory_remnants'),
    'RT-000001',
    'la org B tiene contador propio'
);

-- ── OC-: las OT del taller no consumen folio de compra ───────────────
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'orders'),
    'OC-000001',
    'sin órdenes de compra previas, el primer folio es OC-000001'
);
INSERT INTO orders(id, org_id, project_id, order_type, order_code, payload_json)
VALUES (
    '99aa3000-0000-4000-8000-000000000001',
    '99aa0000-0000-4000-8000-000000000001',
    '99aa2000-0000-4000-8000-000000000001',
    'WORKSHOP_OT', 'OT-P-R179-A-REV-A-01', '{}');
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'orders'),
    'OC-000001',
    'una OT no consume folios de compra'
);

-- Cadena documental mínima para una orden de proveedor real.
INSERT INTO pricing_operations(
    id, org_id, project_id, requested_by, request, input_snapshot, result,
    source_revision, state, reason) VALUES (
    '99aa3500-0000-4000-8000-000000000001',
    '99aa0000-0000-4000-8000-000000000001',
    '99aa2000-0000-4000-8000-000000000001',
    '99aa1000-0000-4000-8000-000000000001', '{}', '{}', '{}',
    'REV-A', 'APPLIED', '179 fixture');
INSERT INTO project_versions(
    id, project_id, org_id, revision_code, snapshot_json, emitted_by,
    pricing_operation_id, canonical_version, bom_hash, snapshot_sha256,
    production_allowed, documentary_complete) VALUES (
    '99aa4000-0000-4000-8000-000000000001',
    '99aa2000-0000-4000-8000-000000000001',
    '99aa0000-0000-4000-8000-000000000001', 'REV-A', '{}',
    '99aa1000-0000-4000-8000-000000000001',
    '99aa3500-0000-4000-8000-000000000001',
    'DOCUMENTARY_CANONICAL_V1',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    TRUE, TRUE);
INSERT INTO order_allocation_batches(
    id, project_id, project_version_id, org_id, bom_hash, snapshot_sha256,
    order_type, allocation_hash, confirmed_by, confirmed_at, attempt) VALUES (
    '99aa5000-0000-4000-8000-000000000001',
    '99aa2000-0000-4000-8000-000000000001',
    '99aa4000-0000-4000-8000-000000000001',
    '99aa0000-0000-4000-8000-000000000001',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'SUPPLIER_PROFILE_PO',
    '5555555555555555555555555555555555555555555555555555555555555555',
    '99aa1000-0000-4000-8000-000000000001', now(), 1);
INSERT INTO supplier_eligibility_versions(
    id, project_id, project_version_id, org_id, bom_hash, snapshot_sha256,
    order_type, supplier_identity, supplier_name, supplier_details,
    eligible_requirement_keys, evidence, version, content_hash, created_by)
VALUES (
    '99aa6000-0000-4000-8000-000000000001',
    '99aa2000-0000-4000-8000-000000000001',
    '99aa4000-0000-4000-8000-000000000001',
    '99aa0000-0000-4000-8000-000000000001',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    'SUPPLIER_PROFILE_PO', 'SUP-1', 'Proveedor 1', '{}', '[]', '{}', 1,
    '4444444444444444444444444444444444444444444444444444444444444444',
    '99aa1000-0000-4000-8000-000000000001');
INSERT INTO orders(
    id, org_id, project_id, order_type, order_code, status, supplier_name,
    payload_json, project_version_id, allocation_batch_id,
    supplier_eligibility_id, bom_hash, revision_snapshot_sha256,
    purchase_projection_hash, allocation_identity, order_snapshot_hash,
    supplier_identity, supplier_details, confirmed_by, confirmed_at) VALUES (
    '99aa7000-0000-4000-8000-000000000001',
    '99aa0000-0000-4000-8000-000000000001',
    '99aa2000-0000-4000-8000-000000000001',
    'SUPPLIER_PROFILE_PO', 'OC-000001', 'DRAFT', 'Proveedor 1', '{}',
    '99aa4000-0000-4000-8000-000000000001',
    '99aa5000-0000-4000-8000-000000000001',
    '99aa6000-0000-4000-8000-000000000001',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    '1111111111111111111111111111111111111111111111111111111111111111',
    '7777777777777777777777777777777777777777777777777777777777777777',
    '8888888888888888888888888888888888888888888888888888888888888888',
    'SUP-1', '{}', '99aa1000-0000-4000-8000-000000000001', now());
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'orders'),
    'OC-000002',
    'la orden de compra existente empuja el siguiente folio a OC-000002'
);

-- ── REC-: folio de recepción ─────────────────────────────────────────
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'order_receipts'),
    'REC-000001',
    'primera recepción de la org A folia REC-000001'
);
INSERT INTO order_receipts(
    org_id, order_id, receipt_key, receipt_code, received_by) VALUES (
    '99aa0000-0000-4000-8000-000000000001',
    '99aa7000-0000-4000-8000-000000000001', 'p02-fixture-key-1',
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'order_receipts'),
    '99aa1000-0000-4000-8000-000000000001');
SELECT is(
    private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'order_receipts'),
    'REC-000002',
    'el folio de recepción avanza tras el insert'
);

-- ── Formato cerrado, unicidad e inmutabilidad ────────────────────────
SELECT throws_ok(
    $$INSERT INTO inventory_remnants(
        org_id, kind, sheet_workshop_sku, width_mm, height_mm, remnant_code)
      VALUES ('99aa0000-0000-4000-8000-000000000001', 'SHEET',
              'DEKO-GLASS-6MM', 100, 100, 'RT-1')$$,
    '23514', NULL,
    'un folio mal formado no entra'
);
SELECT throws_ok(
    $$INSERT INTO inventory_remnants(
        org_id, kind, sheet_workshop_sku, width_mm, height_mm, remnant_code)
      VALUES ('99aa0000-0000-4000-8000-000000000001', 'SHEET',
              'DEKO-GLASS-6MM', 100, 100, 'RT-000001')$$,
    '23505', NULL,
    'el folio RT- es único por org'
);
SELECT throws_ok(
    $$UPDATE inventory_remnants SET remnant_code = 'RT-999999'
      WHERE org_id = '99aa0000-0000-4000-8000-000000000001'$$,
    '42501', 'human_code_immutable',
    'el folio RT- no se reasigna por UPDATE'
);
SELECT lives_ok(
    $$UPDATE inventory_remnants SET status = 'SCRAPPED'
      WHERE org_id = '99aa0000-0000-4000-8000-000000000001'$$,
    'el ciclo de vida del retazo sigue moviendo el resto de la fila'
);
SELECT throws_ok(
    $$UPDATE order_receipts SET receipt_code = 'REC-999999'
      WHERE org_id = '99aa0000-0000-4000-8000-000000000001'$$,
    '42501', 'human_code_immutable',
    'el folio REC- no se reasigna por UPDATE'
);
SELECT throws_ok(
    $$SELECT private.next_human_code(
        '99aa0000-0000-4000-8000-000000000001', 'otra_cosa')$$,
    'P0001', NULL,
    'un kind desconocido rechaza en vez de inventar un prefijo'
);

SELECT finish();
ROLLBACK;
