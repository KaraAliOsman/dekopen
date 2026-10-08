BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(49);

-- P24 — Analítica: conversión, margen real vs. cotizado, merma, tiempos,
-- instalación/postventa. Todos los valores esperados están calculados a
-- mano sobre el fixture (comentario por bloque). Período del test:
-- 2027-09-01 .. 2027-09-30 (días calendario America/Santiago).

SELECT has_function('private', 'analytics_access', ARRAY['uuid'],
    'analytics_access existe');
SELECT has_function('private', 'analytics_sales', ARRAY['uuid','date','date'],
    'analytics_sales existe');
SELECT has_function('private', 'analytics_margins', ARRAY['uuid','date','date'],
    'analytics_margins existe');
SELECT has_function('private', 'analytics_margin_breakdown', ARRAY['uuid','uuid'],
    'analytics_margin_breakdown existe');
SELECT has_function('private', 'analytics_production', ARRAY['uuid','date','date'],
    'analytics_production existe');
SELECT has_function('private', 'analytics_field', ARRAY['uuid','date','date'],
    'analytics_field existe');
SELECT has_column('public', 'tenancy_organizations',
    'analytics_financial_roles', 'roles con acceso a montos');
SELECT has_column('public', 'tenancy_organizations',
    'analytics_hourly_rate_clp', 'tarifa horaria de mano de obra');

-- ══ Fixture ═══════════════════════════════════════════════════════════
-- Org A con datos; org B vacía (aislamiento RLS + «sin datos»).
INSERT INTO tenancy_organizations(id, name, tax_id, analytics_hourly_rate_clp)
VALUES ('9924a000-0000-4000-8000-000000000001', 'Org A24', 'R24-A', 5000);
INSERT INTO tenancy_organizations(id, name, tax_id)
VALUES ('9924b000-0000-4000-8000-000000000001', 'Org B24', 'R24-B');

-- La lista de roles financieros no puede quedar vacía.
SELECT throws_ok(
    $$UPDATE tenancy_organizations SET analytics_financial_roles = '{}'
      WHERE id = '9924a000-0000-4000-8000-000000000001'$$,
    '23514', NULL,
    'analytics_financial_roles vacío viola el CHECK'
);

INSERT INTO auth.users (id, aud, role, email, email_confirmed_at,
                        created_at, updated_at) VALUES
    ('9924a001-0000-4000-8000-000000000001','authenticated','authenticated',
     'owner-a@p24.test', now(), now(), now()),
    ('9924a002-0000-4000-8000-000000000001','authenticated','authenticated',
     'wm-a@p24.test', now(), now(), now()),
    ('9924a003-0000-4000-8000-000000000001','authenticated','authenticated',
     'est-a@p24.test', now(), now(), now()),
    ('9924b001-0000-4000-8000-000000000001','authenticated','authenticated',
     'owner-b@p24.test', now(), now(), now());
INSERT INTO tenancy_memberships(org_id, user_id, role) VALUES
    ('9924a000-0000-4000-8000-000000000001',
     '9924a001-0000-4000-8000-000000000001', 'OWNER'),
    ('9924a000-0000-4000-8000-000000000001',
     '9924a002-0000-4000-8000-000000000001', 'WORKSHOP_MANAGER'),
    ('9924a000-0000-4000-8000-000000000001',
     '9924a003-0000-4000-8000-000000000001', 'ESTIMATOR'),
    ('9924b000-0000-4000-8000-000000000001',
     '9924b001-0000-4000-8000-000000000001', 'OWNER');

-- Obras y revisiones emitidas (cohorte ventas: V1, V2, V3 dentro; V4 fuera).
INSERT INTO projects(id, org_id, code, name, client_name, created_by) VALUES
    ('9924a100-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
     'P-A1', 'Casa uno', 'Cliente', '9924a001-0000-4000-8000-000000000001'),
    ('9924a100-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
     'P-A2', 'Casa dos', 'Cliente', '9924a001-0000-4000-8000-000000000001'),
    ('9924a100-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
     'P-A3', 'Casa tres', 'Cliente', '9924a001-0000-4000-8000-000000000001'),
    ('9924a100-0000-4000-8000-000000000004', '9924a000-0000-4000-8000-000000000001',
     'P-A4', 'Casa fuera', 'Cliente', '9924a001-0000-4000-8000-000000000001'),
    ('9924a100-0000-4000-8000-000000000005', '9924a000-0000-4000-8000-000000000001',
     'P-A5', 'Casa taller', 'Cliente', '9924a001-0000-4000-8000-000000000001');

-- Posiciones: la tipología alimenta los cortes por tipología. price_net
-- queda en 0 — la guardia comercial prohíbe escribirlo fuera del flujo de
-- precio y el test no lo necesita (una posición por proyecto).
INSERT INTO project_positions(id, org_id, project_id, position_index,
    system_id, typology, width_mm, height_mm, quantity,
    parametric_tree, bom_snapshot) VALUES
    ('9924a130-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
     '9924a100-0000-4000-8000-000000000001', 0,
     '3067da09-3119-5ad0-a1d5-498cd2dfd753', 'corredera',
     1000, 1000, 1, '{}', '{}'),
    ('9924a130-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
     '9924a100-0000-4000-8000-000000000002', 0,
     '3067da09-3119-5ad0-a1d5-498cd2dfd753', 'fijo',
     1000, 1000, 1, '{}', '{}'),
    ('9924a130-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
     '9924a100-0000-4000-8000-000000000003', 0,
     '3067da09-3119-5ad0-a1d5-498cd2dfd753', 'corredera',
     1000, 1000, 1, '{}', '{}');

-- Operaciones de pricing selladas que autorizan cada versión (la guardia
-- require_applied_pricing_authority exige una APPLIED por REV-A).
INSERT INTO pricing_operations(id, org_id, project_id, requested_by, request,
    input_snapshot, result, source_revision, revision_code, state, reason,
    approved_at) VALUES
('9924a120-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000001', '9924a001-0000-4000-8000-000000000001',
 '{}', '{}', '{}', 'REV-A', 'REV-A', 'APPLIED', 'oficial',
 '2027-09-10 12:00+00'),
('9924a120-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000002', '9924a001-0000-4000-8000-000000000001',
 '{}', '{}', '{}', 'REV-A', 'REV-A', 'APPLIED', 'oficial',
 '2027-09-05 12:00+00'),
('9924a120-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000003', '9924a002-0000-4000-8000-000000000001',
 '{}', '{}', '{}', 'REV-A', 'REV-A', 'APPLIED', 'oficial',
 '2027-09-20 12:00+00'),
('9924a120-0000-4000-8000-000000000004', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000004', '9924a001-0000-4000-8000-000000000001',
 '{}', '{}', '{}', 'REV-A', 'REV-A', 'APPLIED', 'oficial',
 '2027-08-05 12:00+00');

-- Snapshot de V1 (la revisión aprobada de PA1): neto 100000, costo 60000,
-- materiales cotizados 30000, mano de obra 20000, instalación 15000,
-- descuento sellado 10 % sobre una línea de 100000 → 10000.
INSERT INTO project_versions(id, org_id, project_id, revision_code,
    emitted_by, emitted_at, authority_version, pricing_operation_id,
    canonical_version, bom_hash, snapshot_sha256, production_allowed,
    documentary_complete, snapshot_json) VALUES
('9924a110-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000001', 'REV-A',
 '9924a001-0000-4000-8000-000000000001', '2027-09-10 12:00+00', 'SHOT09_V1',
 '9924a120-0000-4000-8000-000000000001', 'DOCUMENTARY_CANONICAL_V1',
 repeat('a', 64), repeat('b', 64), TRUE, TRUE,
 '{
   "pricing": {
     "input_snapshot": {"positions": [
       {"position_index": "0", "materials_cost": 30000, "area_m2": 10,
        "labor_rate_per_m2": 2000, "installation_rate_per_m2": 1500,
        "typology": "corredera", "quantity": 1}
     ]},
     "result": {
       "project_net": 100000, "deal_cost_net": 60000, "option_indexes": [],
       "line_detail": [{"position_index": "0", "quantity": 1,
                        "unit_price": 100000, "discount_pct": 0.10}]
     }
   },
   "project": {"total_price_net": 100000}
 }'::jsonb),
('9924a110-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000002', 'REV-A',
 '9924a001-0000-4000-8000-000000000001', '2027-09-05 12:00+00', 'SHOT09_V1',
 '9924a120-0000-4000-8000-000000000002', 'DOCUMENTARY_CANONICAL_V1',
 repeat('a', 64), repeat('b', 64), TRUE, TRUE,
 '{"pricing":{"result":{"project_net":500000,"deal_cost_net":300000}},
   "project":{"total_price_net":500000}}'::jsonb),
('9924a110-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000003', 'REV-A',
 '9924a002-0000-4000-8000-000000000001', '2027-09-20 12:00+00', 'SHOT09_V1',
 '9924a120-0000-4000-8000-000000000003', 'DOCUMENTARY_CANONICAL_V1',
 repeat('a', 64), repeat('b', 64), TRUE, TRUE,
 '{"pricing":{"result":{"project_net":777000,"deal_cost_net":400000}},
   "project":{"total_price_net":777000}}'::jsonb),
('9924a110-0000-4000-8000-000000000004', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000004', 'REV-A',
 '9924a001-0000-4000-8000-000000000001', '2027-08-05 12:00+00', 'SHOT09_V1',
 '9924a120-0000-4000-8000-000000000004', 'DOCUMENTARY_CANONICAL_V1',
 repeat('a', 64), repeat('b', 64), TRUE, TRUE,
 '{"pricing":{"result":{"project_net":90000}},"project":{"total_price_net":90000}}'::jsonb);

-- Decisiones: V1 aprobada +2 días, V2 rechazada +6 días, V3 pendiente
-- (vence en el futuro → fase PENDIENTE del pipeline).
INSERT INTO customer_approvals(id, org_id, project_id, project_version_id,
    token_hash, expires_at, created_by, status, decided_at, channel) VALUES
('9924a120-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000001', '9924a110-0000-4000-8000-000000000001',
 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
 now() + interval '10 days', '9924a001-0000-4000-8000-000000000001',
 'APPROVED', '2027-09-12 12:00+00', 'EMAIL'),
('9924a120-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000002', '9924a110-0000-4000-8000-000000000002',
 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
 now() + interval '10 days', '9924a001-0000-4000-8000-000000000001',
 'DECLINED', '2027-09-11 12:00+00', 'EMAIL'),
('9924a120-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000003', '9924a110-0000-4000-8000-000000000003',
 'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
 now() + interval '10 days', '9924a001-0000-4000-8000-000000000001',
 'PENDING', NULL, 'EMAIL'),
('9924a120-0000-4000-8000-000000000004', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000004', '9924a110-0000-4000-8000-000000000004',
 'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
 now() + interval '10 days', '9924a001-0000-4000-8000-000000000001',
 'APPROVED', '2027-08-10 12:00+00', 'EMAIL');

INSERT INTO customer_approval_events(org_id, project_id, approval_id,
    decided_by, decision, decided_note) VALUES
('9924a000-0000-4000-8000-000000000001', '9924a100-0000-4000-8000-000000000002',
 '9924a120-0000-4000-8000-000000000002', '9924a001-0000-4000-8000-000000000001',
 'DECLINED', 'precio alto');

-- ── VENTAS ─────────────────────────────────────────────────────────────
-- Esperado: emitted=3 (V4 fuera del período), approved=1, declined=1,
-- pending=1, decided=2, conversión 50.0 %, media 4.0 días.
SELECT set_config('request.jwt.claims',
    '{"sub":"9924a001-0000-4000-8000-000000000001"}', TRUE);

WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' ->> 'emitted', '3',
    'ventas: 3 cotizaciones emitidas en el período')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'conversion_pct' ->> 'value', '50.0',
    'conversión 50.0 % (1 aprobada de 2 decididas)')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'avg_decision_days' ->> 'value', '4.0',
    'media emisión→decisión: (2.0 + 6.0)/2 = 4.0 días')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'pipeline_net' ->> 'value', '777000',
    'pipeline: una PENDIENTE de $777.000')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT count(*)::int FROM jsonb_array_elements(v -> 'by_estimator')),
    2, 'by_estimator agrupa por emisor (owner 2, wm 1)')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'rejection_reasons' -> 0 ->> 'note', 'precio alto',
    'motivo de rechazo declarado desde el evento')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT elem ->> 'emitted' FROM jsonb_array_elements(v -> 'by_typology') elem
     WHERE elem ->> 'typology' = 'corredera'),
    '2', 'corredera: 2 emitidas (PA1 aprobada + PA3 pendiente)')
FROM s;

-- ══ Margen: OT-1 con consumo medido + remake OT-2 + horas ═══════════════
-- Precio: lista de costos PERFIL-A = 100/un; retazos a 0.2 CLP/mm vía
-- profile_purchase_mappings (barra comercial 6000 mm @ 1200).
-- Las tablas de costo auditan: el actor de JWT exige app.pricing_reason.
SELECT set_config('app.pricing_reason', 'fixture P24', TRUE);
INSERT INTO cost_lists(id, org_id, supplier_name, is_active, valid_from)
VALUES ('9924aa00-0000-4000-8000-000000000001',
        '9924a000-0000-4000-8000-000000000001', 'Lista A24', TRUE, '2026-01-01');
INSERT INTO cost_list_items(org_id, cost_list_id, sku, description,
    item_type, unit, unit_cost) VALUES
('9924a000-0000-4000-8000-000000000001', '9924aa00-0000-4000-8000-000000000001',
 'PERFIL-A', 'Perfil barra', 'PROFILE', 'BAR', 100),
('9924a000-0000-4000-8000-000000000001', '9924aa00-0000-4000-8000-000000000001',
 'PERFIL-COM', 'Barra comercial', 'PROFILE', 'BAR', 1200);

-- Sistema propio del fixture (los catálogos referenciados por OT se
-- bloquean técnicamente y rechazan escrituras ajenas).
INSERT INTO profile_systems(id, org_id, name, code, depth_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm)
VALUES ('9924a510-0000-4000-8000-000000000001',
        '9924a000-0000-4000-8000-000000000001', 'Sistema P24', 'P24_SYS',
        60, 0, 0, 0);
INSERT INTO profile_articles(id, system_id, org_id, sku, name, role,
    face_width_mm, commercial_length_mm, material, data_provenance,
    section_revision)
VALUES ('9924a520-0000-4000-8000-000000000001',
        '9924a510-0000-4000-8000-000000000001', NULL,
        'PERFIL-TEC', 'Perfil técnico', 'SASH', 40, 6000, 'PVC', 'MANUAL', 1);
INSERT INTO profile_purchase_mappings(id, org_id, profile_article_id,
    commercial_sku, manufacturer_name, purchase_unit)
VALUES ('9924a530-0000-4000-8000-000000000001',
        '9924a000-0000-4000-8000-000000000001',
        '9924a520-0000-4000-8000-000000000001',
        'PERFIL-COM', 'Fab A24', 'BAR');

INSERT INTO inventory_items(id, org_id, sku, name, category, unit) VALUES
('9924a500-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 'PERFIL-A', 'Perfil A', 'PROFILE', 'BAR'),
('9924a500-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 'PERFIL-B', 'Perfil B', 'PROFILE', 'BAR');

-- OT-1 sobre PA1: plan 6000 mm de barras PERFIL-A, productivo 55000 mm,
-- devuelve un retazo de 3000 mm y declara merma 2000 mm.
INSERT INTO orders(id, org_id, project_id, order_type, order_code, status,
    created_at, payload_json) VALUES
('9924a400-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000001', 'WORKSHOP_OT', 'OT-A1', 'COMPLETED',
 '2027-09-15 12:00+00',
 '{"position_id":"9924a130-0000-4000-8000-000000000001",
   "optimization":{"bars":{
     "workshop_cut_plan":[{"stock_sku":"PERFIL-A","stock_length_mm":6000}],
     "metrics":{"process_waste_mm":2000,"productive_length_mm":55000,
                "reusable_remnant_mm":0}},
   "produced_bars":[{"remainder_mm":3000,"remnant_code":"RT-000003"}]}}'::jsonb),
('9924a400-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000001', 'WORKSHOP_OT', 'OT-A1R', 'COMPLETED',
 '2027-09-18 12:00+00',
 '{"remake_of":"9924a400-0000-4000-8000-000000000001",
   "remake_reason":{"qc_item":"VID_TEMPLADO","note":"vidrio trizado"}}'::jsonb),
('9924a400-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
 '9924a100-0000-4000-8000-000000000005', 'WORKSHOP_OT', 'OT-A5', 'COMPLETED',
 '2027-09-22 12:00+00',
 '{"optimization":{"bars":{
     "workshop_cut_plan":[{"stock_sku":"PERFIL-B","stock_length_mm":6000}],
     "metrics":{"process_waste_mm":500,"productive_length_mm":9500,
                "reusable_remnant_mm":0}},
   "produced_bars":[]}}'::jsonb);

-- Retazos: RT-000001 consumido por OT-1 (800 mm @ 0.2 = 160),
-- RT-000002 desechado por OT-1 (200 mm @ 0.2 = 40),
-- RT-000003 generado por producción de OT-1.
INSERT INTO inventory_remnants(id, org_id, kind, length_mm,
    stock_authority_id, status, origin, remnant_code, origin_order_id) VALUES
('9924a510-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 'BAR', 800, '9924a530-0000-4000-8000-000000000001',
 'CONSUMED', 'RECEIPT', 'RT-000001', NULL),
('9924a510-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 'BAR', 200, '9924a530-0000-4000-8000-000000000001',
 'SCRAPPED', 'RECEIPT', 'RT-000002', NULL),
('9924a510-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
 'BAR', 3000, '9924a530-0000-4000-8000-000000000001',
 'AVAILABLE', 'PRODUCTION', 'RT-000003',
 '9924a400-0000-4000-8000-000000000001');

-- Ledger: OT-1 consume 10 barras PERFIL-A (1000) + retazo RT-000001 (160)
-- y desecha RT-000002 (40). OT-2 (remake) consume 5 PERFIL-A (500).
INSERT INTO inventory_movements(org_id, order_id, item_id, remnant_id,
    movement_type, quantity, created_at) VALUES
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 '9924a500-0000-4000-8000-000000000001', NULL, 'CONSUMPTION', 10,
 '2027-09-16 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 NULL, '9924a510-0000-4000-8000-000000000001', 'CONSUMPTION', NULL,
 '2027-09-16 13:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 NULL, '9924a510-0000-4000-8000-000000000002', 'SCRAP', NULL,
 '2027-09-16 14:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000002',
 '9924a500-0000-4000-8000-000000000001', NULL, 'CONSUMPTION', 5,
 '2027-09-19 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000003',
 '9924a500-0000-4000-8000-000000000002', NULL, 'CONSUMPTION', 2,
 '2027-09-23 12:00+00');

-- Pasos: OT-1 CUT 2 h, OT-2 GLAZE 1 h (remake), OT-3 CUT 4 h.
INSERT INTO production_steps(id, org_id, order_id, code, label, sequence,
    status, started_at, finished_at) VALUES
('9924a600-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 '9924a400-0000-4000-8000-000000000001', 'CUT', 'Corte', 1, 'DONE',
 '2027-09-16 12:00+00', '2027-09-16 14:00+00'),
('9924a600-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 '9924a400-0000-4000-8000-000000000002', 'GLAZE', 'Acristalamiento', 1, 'DONE',
 '2027-09-19 12:00+00', '2027-09-19 13:00+00'),
('9924a600-0000-4000-8000-000000000003', '9924a000-0000-4000-8000-000000000001',
 '9924a400-0000-4000-8000-000000000003', 'CUT', 'Corte', 1, 'DONE',
 '2027-09-23 12:00+00', '2027-09-23 16:00+00');

-- Eventos de cumplimiento: OT-1 y OT-3 completadas en período,
-- OT-2 también (sin plazo → SIN_PLAZO), instalación y entrega de OT-1.
INSERT INTO production_step_events(org_id, order_id, event, created_at) VALUES
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 'WO_COMPLETED', '2027-09-25 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000002',
 'WO_COMPLETED', '2027-09-20 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000003',
 'WO_COMPLETED', '2027-09-28 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 'WO_DELIVERY_DELIVERED', '2027-09-26 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000003',
 'WO_DELIVERY_DELIVERED', '2027-09-29 12:00+00'),
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 'WO_INSTALLED', '2027-09-29 12:00+00');

-- Entregas: OT-1 programada 2027-09-26 entregada ese día → A_TIEMPO;
-- OT-3 programada 2027-09-27 entregada 2027-09-29 → ATRASADA.
INSERT INTO deliveries(id, org_id, order_id, scheduled_date, address, status,
    updated_at) VALUES
('9924a700-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 '9924a400-0000-4000-8000-000000000001', '2027-09-26', 'Calle 1', 'DELIVERED',
 '2027-09-26 12:00+00'),
('9924a700-0000-4000-8000-000000000002', '9924a000-0000-4000-8000-000000000001',
 '9924a400-0000-4000-8000-000000000003', '2027-09-27', 'Calle 2', 'DELIVERED',
 '2027-09-29 12:00+00');

-- Checklist + incidencia DAMAGE abierta + ticket WARRANTY abierto con
-- garantía que vence dentro de 60 días (hoy < 2026-12-06).
INSERT INTO installation_checks(org_id, order_id, unit_index, items,
    operation_key, checked_at) VALUES
('9924a000-0000-4000-8000-000000000001', '9924a400-0000-4000-8000-000000000001',
 1, '{"installed":true,"leveled":true,"sealed":true,"adjusted":true,"clean":true}',
 'op-p24-1', '2027-09-28 12:00+00');
INSERT INTO site_incidents(id, org_id, code, order_id, kind, note,
    operation_key, reported_by, reported_at) VALUES
('9924a800-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 'IN-000001', '9924a400-0000-4000-8000-000000000001', 'DAMAGE',
 'vidrio trizado en traslado', 'op-p24-2',
 '9924a002-0000-4000-8000-000000000001', '2027-09-27 12:00+00');
INSERT INTO service_tickets(id, org_id, code, project_id, order_id, kind,
    description, operation_key, created_by, status, warranty_until) VALUES
('9924a900-0000-4000-8000-000000000001', '9924a000-0000-4000-8000-000000000001',
 'PV-000001', '9924a100-0000-4000-8000-000000000001',
 '9924a400-0000-4000-8000-000000000001', 'WARRANTY',
 'vidrio trizado en garantía', 'op-p24-3',
 '9924a002-0000-4000-8000-000000000001', 'OPEN', '2026-11-15');

-- ── MARGEN ─────────────────────────────────────────────────────────────
-- Mano a mano: material normal = 10×100 + retazo 800×0.2 = 1160;
-- descarte = 200×0.2 = 40; remake = 5×100 + 1h×5000 = 5500;
-- horas normales = 2h×5000 = 10000. Costo real = 16700.
-- Cotizado: neto 100000, costo 60000 → margen 40.0 %.
-- Real: (100000 − 16700)/100000 → 83.3 %; desviación +43.3 pp.
WITH m AS (SELECT private.analytics_margins(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' ->> 'obras', '1',
    'margen: una obra aprobada en el período')
FROM m;
WITH m AS (SELECT private.analytics_margins(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'real_avg_margin_pct' ->> 'value', '83.3',
    'margen real promedio 83.3 % sobre obra terminada')
FROM m;
WITH m AS (SELECT private.analytics_margins(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'deviation_pp' ->> 'value', '43.3',
    'desviación margen real−cotizado = +43.3 pp')
FROM m;
WITH m AS (SELECT private.analytics_margins(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT obra ->> 'real_cost' FROM jsonb_array_elements(v -> 'obras') obra
     WHERE obra ->> 'code' = 'P-A1'),
    '16700.0000000000000000000000', 'costo real de P-A1 = 16700 (material 1160 + descarte 40 + remake 5500 + horas 10000)')
FROM m;

-- Descomposición §8: causas con monto y orígenes enlazados.
WITH b AS (SELECT private.analytics_margin_breakdown(
    '9924a000-0000-4000-8000-000000000001',
    '9924a100-0000-4000-8000-000000000001') v)
SELECT is(
    (SELECT c ->> 'amount' FROM jsonb_array_elements(v -> 'causes') c
     WHERE c ->> 'key' = 'remake'),
    '5500', 'causa remake = 5500 (material 500 + 1 h × 5000)')
FROM b;
WITH b AS (SELECT private.analytics_margin_breakdown(
    '9924a000-0000-4000-8000-000000000001',
    '9924a100-0000-4000-8000-000000000001') v)
SELECT is(
    (SELECT c ->> 'amount' FROM jsonb_array_elements(v -> 'causes') c
     WHERE c ->> 'key' = 'descuento'),
    '10000', 'causa descuento = 10 % de la línea de 100000')
FROM b;
WITH b AS (SELECT private.analytics_margin_breakdown(
    '9924a000-0000-4000-8000-000000000001',
    '9924a100-0000-4000-8000-000000000001') v)
SELECT is(
    (SELECT count(*)::int FROM jsonb_array_elements(v -> 'movements')),
    4, 'drill F6: 4 movimientos valorizados detrás del costo')
FROM b;
WITH b AS (SELECT private.analytics_margin_breakdown(
    '9924a000-0000-4000-8000-000000000001',
    '9924a100-0000-4000-8000-000000000001') v)
SELECT is(
    (SELECT c ->> 'amount' FROM jsonb_array_elements(v -> 'causes') c
     WHERE c ->> 'key' = 'horas'),
    '-10000', 'causa horas = 10000 reales − 20000 cotizadas')
FROM b;

-- ── PRODUCCIÓN ─────────────────────────────────────────────────────────
-- OT-1: consumidas 60800 mm (10×6000 + retazo 800), productivo 55000,
-- devuelto 3000, desechado 200 → merma real 3000 vs plan 2000.
-- OT-3: consumidas 12000, productivo 9500 → real 2500 vs plan 500.
-- OT-2: consume barras sin plan → «sin medir», fuera del agregado.
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'merma_real_mm' ->> 'value', '5500.00',
    'merma real agregada = 3000 + 2500 = 5500 mm')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'merma_plan_mm' ->> 'value', '2500',
    'merma plan = 2000 + 500 = 2500 mm')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'aprovechamiento_pct' ->> 'value', '88.6',
    'aprovechamiento = (55000+9500)/(60800+12000) = 88.6 %')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT ot ->> 'unmeasured' FROM jsonb_array_elements(v -> 'ot_waste') ot
     WHERE ot ->> 'order_code' = 'OT-A1R'),
    'true', 'la OT remake sin plan queda «sin medir», no en 0')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT count(*)::int FROM jsonb_array_elements(v -> 'station_times')),
    2, 'tiempos por estación: CUT (2+4 h) y GLAZE (1 h)')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT st ->> 'avg_hours' FROM jsonb_array_elements(v -> 'station_times') st
     WHERE st ->> 'code' = 'CUT'),
    '3.00', 'CUT promedio = (2 h + 4 h)/2 = 3.0 h')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    v -> 'metrics' -> 'ot_punctuality' -> 'on_time_pct' ->> 'value', '50.0',
    'OT a tiempo: 1 de 2 con plazo (OT-1 ok, OT-3 atrasada)')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'ot_punctuality' ->> 'sin_plazo', '1',
    'OT-2 completada sin entrega agendada → SIN_PLAZO')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    v -> 'retazos' ->> 'consumed', '1',
    'un retazo consumido en el período')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT count(*)::int FROM jsonb_array_elements(v -> 'remakes')),
    1, 'un remake en el período con su OT origen')
FROM p;
WITH p AS (SELECT private.analytics_production(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'merma_placas_mm2' ->> 'value' IS NOT NULL,
    FALSE, 'merma de placas sin datos → «Sin dato», no 0')
FROM p;

-- ── INSTALACIÓN Y POSTVENTA ────────────────────────────────────────────
WITH f AS (SELECT private.analytics_field(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'deliveries_on_time_pct' ->> 'value', '50.0',
    'entregas a tiempo: 1 de 2 entregadas')
FROM f;
WITH f AS (SELECT private.analytics_field(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' ->> 'installations', '1',
    'una instalación confirmada (WO_INSTALLED) en el período')
FROM f;
WITH f AS (SELECT private.analytics_field(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' ->> 'incidents_open', '1',
    'una incidencia abierta a la fecha')
FROM f;
WITH f AS (SELECT private.analytics_field(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(
    (SELECT k ->> 'count' FROM jsonb_array_elements(v -> 'incidents_by_kind') k
     WHERE k ->> 'kind' = 'DAMAGE'),
    '1', 'incidencias por tipo: DAMAGE = 1')
FROM f;
WITH f AS (SELECT private.analytics_field(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' ->> 'warranties_expiring', '1',
    'una garantía abierta vence dentro de 60 días')
FROM f;

-- ── AISLAMIENTO Y PERMISOS ──────────────────────────────────────────────
-- Org B no ve datos de A; el estimador no es lector de analítica.
SELECT set_config('request.jwt.claims',
    '{"sub":"9924b001-0000-4000-8000-000000000001"}', TRUE);
SELECT throws_ok(
    $$SELECT private.analytics_sales(
        '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30')$$,
    '42501', 'analytics_forbidden',
    'la org B no lee la analítica de la org A'
);

-- «Sin datos suficientes» con causa, nunca 0 ni cifra parcial.
WITH s AS (SELECT private.analytics_sales(
    '9924b000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'conversion_pct' ->> 'value' IS NOT NULL, FALSE,
    'org sin datos: conversión es NULL')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924b000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT ok(v -> 'metrics' -> 'conversion_pct' ->> 'cause' IS NOT NULL,
    'org sin datos: la causa declara por qué no hay cifra')
FROM s;
WITH m AS (SELECT private.analytics_margins(
    '9924b000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' ->> 'obras', '0',
    'org sin datos: cero obras, no cifras inventadas')
FROM m;

SELECT set_config('request.jwt.claims',
    '{"sub":"9924a003-0000-4000-8000-000000000001"}', TRUE);
SELECT throws_ok(
    $$SELECT private.analytics_sales(
        '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30')$$,
    '42501', 'analytics_forbidden',
    'el ESTIMATOR no es lector de analítica'
);

-- Permiso financiero: WORKSHOP_MANAGER lee el panel pero los montos salen
-- NULL (analytics_financial_roles por defecto sólo incluye OWNER).
SELECT set_config('request.jwt.claims',
    '{"sub":"9924a002-0000-4000-8000-000000000001"}', TRUE);
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v ->> 'financial', 'false',
    'WM lee analítica pero sin permiso financiero')
FROM s;
WITH s AS (SELECT private.analytics_sales(
    '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30') v)
SELECT is(v -> 'metrics' -> 'pipeline_net' ->> 'value' IS NOT NULL, FALSE,
    'sin permiso financiero el pipeline en CLP sale NULL, no 0')
FROM s;

-- EXECUTE llega al rol authenticated real (la API corre bajo ese rol).
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"9924a001-0000-4000-8000-000000000001"}', TRUE);
SELECT lives_ok(
    $$SELECT private.analytics_sales(
        '9924a000-0000-4000-8000-000000000001','2027-09-01','2027-09-30')$$,
    'authenticated puede ejecutar analytics_sales'
);
SELECT throws_ok(
    $$SELECT private.analytics_sales(
        '9924b000-0000-4000-8000-000000000001','2027-09-01','2027-09-30')$$,
    '42501', 'analytics_forbidden',
    'con rol authenticated la org ajena sigue fuera'
);

SELECT * FROM finish();
ROLLBACK;
