BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(16);

-- P15 — recepción con guía del proveedor, libro de movimientos de retazos,
-- precio por línea en la propuesta, días de alerta configurables y correo
-- al proveedor por el outbox.

SELECT has_column('public', 'order_receipts', 'supplier_delivery_ref',
    'recepción registra la guía de despacho del proveedor');
SELECT has_column('public', 'order_receipts', 'supplier_delivery_date',
    'recepción registra la fecha del documento del proveedor');
SELECT has_column('public', 'inventory_movements', 'remnant_id',
    'el libro de movimientos puede apuntar a un retazo');
SELECT col_is_null('public', 'inventory_movements', 'item_id',
    'un movimiento de retazo no referencia item de stock');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_enum
        WHERE enumtypid = 'public.inventory_movement_type'::regtype
          AND enumlabel = 'MOVE'
    ),
    'MOVE existe como tipo de movimiento (cambio de rack)'
);
SELECT throws_ok(
    $$INSERT INTO public.inventory_movements (org_id, item_id, movement_type, quantity)
      VALUES ('00000000-0000-4000-8000-000000000000',
              '00000000-0000-4000-8000-000000000000', 'RECEIPT', NULL)$$,
    '23514',
    NULL,
    'un movimiento de item sigue exigiendo cantidad (CHECK)'
);
SELECT throws_ok(
    $$INSERT INTO public.inventory_movements (org_id, item_id, remnant_id, movement_type)
      VALUES ('00000000-0000-4000-8000-000000000000',
              '00000000-0000-4000-8000-000000000000',
              '00000000-0000-4000-8000-000000000000', 'MOVE')$$,
    '23514',
    NULL,
    'un movimiento no puede apuntar a item y retazo a la vez'
);
SELECT has_column('public', 'purchase_allocations', 'unit_price',
    'la propuesta por proveedor declara precio unitario por línea');
SELECT has_column('public', 'tenancy_organizations', 'remnant_alert_days',
    'días de alerta de retazos viejos configurables por org');
SELECT is(
    (SELECT column_default FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
       AND column_name = 'remnant_alert_days'),
    '30',
    '30 días es el valor por defecto registrado en decisiones'
);
SELECT ok(
    has_column_privilege(
        'documentary_backend', 'public.tenancy_organizations',
        'remnant_alert_days', 'UPDATE'
    ),
    'documentary_backend puede guardar el ajuste de retazos'
);
SELECT ok(
    NOT has_table_privilege(
        'authenticated', 'public.order_requirement_lines', 'SELECT'
    ),
    'authenticated no puede leer líneas de OC directamente — la lectura de '
    'entrantes en stock cruza a documentary_backend (causa raíz del error '
    'de carga de stock, corregida en a1b08c07)'
);
SELECT ok(
    has_table_privilege(
        'documentary_backend', 'public.order_requirement_lines', 'SELECT'
    ),
    'documentary_backend sí lee líneas de OC para el entrante de stock'
);

-- El invariante probado en vivo: bajo el rol authenticated la vista de stock
-- responde, y la tabla que rompía la carga lanza permiso denegado — la
-- aplicación la lee solo dentro de documentary_backend().
SET LOCAL ROLE authenticated;
SELECT lives_ok(
    $$SELECT item_id, sku, on_hand_qty, reserved_qty FROM public.inventory_stock$$,
    'stock carga bajo el rol authenticated (regresión: sección rota)'
);
SELECT throws_ok(
    $$SELECT count(*) FROM public.order_requirement_lines$$,
    '42501',
    NULL,
    'order_requirement_lines sigue fuera del alcance de authenticated'
);
RESET ROLE;

SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint c
        WHERE c.conrelid = 'public.mail_messages'::regclass
          AND c.conname = 'mail_messages_audience_check'
          AND pg_get_constraintdef(c.oid) LIKE '%SUPPLIER%'
    ),
    'el outbox admite audiencia SUPPLIER para el correo de OC'
);

SELECT * FROM finish();
ROLLBACK;
