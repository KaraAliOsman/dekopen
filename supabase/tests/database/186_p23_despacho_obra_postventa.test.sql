BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(27);

-- P23 — despacho planificado por cuadrilla, medición y checklist en obra,
-- incidencias con destino (remake/compra/servicio), postventa con plazo
-- de garantía y folios IN-/SC-/PV-.

SELECT has_table('public', 'field_crews', 'cuadrillas/vehículos');
SELECT has_table('public', 'field_photos', 'registro de evidencia');
SELECT has_table('public', 'site_measurements', 'mediciones de obra');
SELECT has_table('public', 'installation_checks', 'checklist de instalación');
SELECT has_table('public', 'site_incidents', 'incidencias de obra');
SELECT has_table('public', 'field_purchase_requests', 'solicitudes de compra de terreno');
SELECT has_table('public', 'service_tickets', 'tickets de postventa');

SELECT has_column('public', 'deliveries', 'crew_id', 'el viaje lleva cuadrilla');
SELECT has_column('public', 'deliveries', 'installer_user_id', 'el viaje lleva instalador asignado');
SELECT has_column('public', 'tenancy_organizations', 'doc_warranty_months', 'plazo de garantía por defecto');
SELECT has_column('public', 'project_documentary_inputs', 'warranty_months', 'override por cotización');

SELECT has_function(
    'private', 'apply_site_measurement', ARRAY['uuid', 'uuid', 'jsonb', 'uuid'],
    'apply_site_measurement existe'
);
SELECT has_function(
    'public', 'installation_items_valid', ARRAY['jsonb'],
    'installation_items_valid existe'
);

-- items del checklist: claves cerradas, todas booleanas.
SELECT ok(
    installation_items_valid(
        '{"installed":true,"leveled":true,"sealed":false,"adjusted":false,"clean":false}'::jsonb
    ),
    'un checklist completo válido pasa'
);
SELECT ok(
    NOT installation_items_valid('{"installed":true,"leveled":true}'::jsonb),
    'un checklist sin las cinco claves falla'
);
SELECT ok(
    NOT installation_items_valid(
        '{"installed":1,"leveled":true,"sealed":true,"adjusted":true,"clean":true,"extra":true}'::jsonb
    ),
    'clave extra o valor no booleano falla'
);

-- ── Fixture ──────────────────────────────────────────────────────────
INSERT INTO tenancy_organizations(id, name, tax_id) VALUES
    ('99cc0000-0000-4000-8000-000000000001', 'Org P23', 'R186-A');
INSERT INTO tenancy_memberships(org_id, user_id, role) VALUES
    ('99cc0000-0000-4000-8000-000000000001',
     '99cc1000-0000-4000-8000-000000000001', 'WORKSHOP_MANAGER'),
    ('99cc0000-0000-4000-8000-000000000001',
     '99cc2000-0000-4000-8000-000000000001', 'INSTALLER');
INSERT INTO projects(id, org_id, code, name, client_name, created_by) VALUES
    ('99cc3000-0000-4000-8000-000000000001',
     '99cc0000-0000-4000-8000-000000000001', 'P-R186', 'Casa P23', 'Cliente',
     '99cc1000-0000-4000-8000-000000000001');
INSERT INTO orders(id, org_id, project_id, order_type, order_code, status, payload_json)
VALUES (
    '99cc4000-0000-4000-8000-000000000001',
    '99cc0000-0000-4000-8000-000000000001',
    '99cc3000-0000-4000-8000-000000000001',
    'WORKSHOP_OT', 'OT-P-R186-REV-A-01', 'DISPATCHED',
    '{"position_id":"99cc5000-0000-4000-8000-000000000001","quantity":2}'::jsonb);

-- ── Folios IN-/SC-/PV- por org ───────────────────────────────────────
SELECT is(
    private.next_human_code('99cc0000-0000-4000-8000-000000000001', 'site_incidents'),
    'IN-000001',
    'primera incidencia folia IN-000001'
);
SELECT is(
    private.next_human_code('99cc0000-0000-4000-8000-000000000001', 'field_purchase_requests'),
    'SC-000001',
    'primera solicitud folia SC-000001'
);
SELECT is(
    private.next_human_code('99cc0000-0000-4000-8000-000000000001', 'service_tickets'),
    'PV-000001',
    'primer ticket folia PV-000001'
);

-- ── Incidencia: resolución coherente ─────────────────────────────────
INSERT INTO site_incidents(
    org_id, code, order_id, kind, note, operation_key, reported_by)
VALUES (
    '99cc0000-0000-4000-8000-000000000001', 'IN-000001',
    '99cc4000-0000-4000-8000-000000000001', 'DAMAGE', 'vidrio trizado',
    'op-inc-1', '99cc2000-0000-4000-8000-000000000001');

-- status=RESOLVED exige resolution_kind (el CHECK ata los dos).
SELECT throws_ok(
    $$UPDATE site_incidents SET status='RESOLVED'
      WHERE org_id='99cc0000-0000-4000-8000-000000000001'$$,
    '23514',
    NULL,
    'resolver sin resolution_kind viola el CHECK'
);
UPDATE site_incidents
SET status='RESOLVED', resolution_kind='REMAKE', resolved_at=now(),
    resolved_by='99cc1000-0000-4000-8000-000000000001'
WHERE org_id='99cc0000-0000-4000-8000-000000000001';
SELECT is(
    (SELECT resolution_kind FROM site_incidents
     WHERE code='IN-000001' AND org_id='99cc0000-0000-4000-8000-000000000001'),
    'REMAKE',
    'la incidencia queda resuelta con destino remake'
);

-- El código es inmutable (guard_human_code).
SELECT throws_ok(
    $$UPDATE site_incidents SET code='IN-999999'
      WHERE org_id='99cc0000-0000-4000-8000-000000000001'$$,
    '42501',
    'human_code_immutable',
    'el folio IN- no se puede reescribir'
);

-- ── Una compra de terreno por incidencia ─────────────────────────────
INSERT INTO field_purchase_requests(
    org_id, code, incident_id, item, quantity, unit, created_by)
VALUES (
    '99cc0000-0000-4000-8000-000000000001', 'SC-000001',
    (SELECT id FROM site_incidents WHERE code='IN-000001'
      AND org_id='99cc0000-0000-4000-8000-000000000001'),
    'Herraje bisagra', 2, 'un', '99cc1000-0000-4000-8000-000000000001');
SELECT throws_ok(
    $$INSERT INTO field_purchase_requests(
        org_id, code, incident_id, item, created_by)
      SELECT '99cc0000-0000-4000-8000-000000000001', 'SC-000002',
             i.id, 'Segundo', '99cc1000-0000-4000-8000-000000000001'
      FROM site_incidents i
      WHERE i.code='IN-000001' AND i.org_id='99cc0000-0000-4000-8000-000000000001'$$,
    '23505',
    NULL,
    'una incidencia genera una sola solicitud de compra'
);

-- ── Ticket: cerrado exige sello de cierre; uno por incidencia ────────
INSERT INTO service_tickets(
    org_id, code, project_id, order_id, incident_id, kind, description,
    operation_key, created_by)
SELECT
    '99cc0000-0000-4000-8000-000000000001', 'PV-000001',
    '99cc3000-0000-4000-8000-000000000001',
    '99cc4000-0000-4000-8000-000000000001',
    i.id, 'WARRANTY', 'vidrio trizado en instalación',
    'op-pv-1', '99cc1000-0000-4000-8000-000000000001'
FROM site_incidents i
WHERE i.code='IN-000001' AND i.org_id='99cc0000-0000-4000-8000-000000000001';
SELECT throws_ok(
    $$UPDATE service_tickets SET status='CLOSED'
      WHERE org_id='99cc0000-0000-4000-8000-000000000001'$$,
    '23514',
    NULL,
    'cerrar sin closed_at viola el CHECK'
);
UPDATE service_tickets
SET status='CLOSED', closed_at=now(), close_note='reemplazada en terreno',
    closed_by='99cc1000-0000-4000-8000-000000000001'
WHERE org_id='99cc0000-0000-4000-8000-000000000001';
SELECT is(
    (SELECT count(*)::int FROM service_tickets
     WHERE org_id='99cc0000-0000-4000-8000-000000000001'
       AND status='CLOSED' AND closed_at IS NOT NULL),
    1,
    'el ticket cierra con sello de cierre'
);

-- ── Checklist: una fila por (org, orden, unidad) ─────────────────────
INSERT INTO installation_checks(org_id, order_id, unit_index, items, operation_key)
VALUES (
    '99cc0000-0000-4000-8000-000000000001',
    '99cc4000-0000-4000-8000-000000000001', 1,
    '{"installed":true,"leveled":true,"sealed":true,"adjusted":true,"clean":true}'::jsonb,
    'op-check-1');
SELECT throws_ok(
    $$INSERT INTO installation_checks(org_id, order_id, unit_index, items, operation_key)
      VALUES ('99cc0000-0000-4000-8000-000000000001',
              '99cc4000-0000-4000-8000-000000000001', 1,
              '{"installed":true,"leveled":true,"sealed":true,"adjusted":true,"clean":true}'::jsonb,
              'op-check-2')$$,
    '23505',
    NULL,
    'la unidad solo se chequea una vez (NULLS NOT DISTINCT)'
);

-- ── Garantía por defecto ─────────────────────────────────────────────
SELECT is(
    (SELECT doc_warranty_months FROM tenancy_organizations
     WHERE id='99cc0000-0000-4000-8000-000000000001')::int,
    24,
    'el plazo de garantía por defecto es 24 meses'
);

SELECT * FROM finish();
ROLLBACK;
