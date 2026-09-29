BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(17);

SELECT has_table('public', 'inventory_items', 'inventory items table exists');
SELECT has_table('public', 'inventory_movements', 'movement ledger table exists');
SELECT has_table('public', 'order_receipts', 'receipts table exists');
SELECT has_table('public', 'order_receipt_lines', 'receipt lines table exists');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_views
        WHERE schemaname = 'public' AND viewname = 'inventory_stock'
    ),
    'derived stock view exists'
);
SELECT ok(
    EXISTS (
        SELECT 1
        FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = 'inventory_movements'
          AND rowsecurity = true
    ),
    'movement ledger enforces row level security'
);
SELECT ok(
    EXISTS (
        SELECT 1
        FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public' AND c.relname = 'uk_org_inventory_item'
    ),
    'per-org sku+variant uniqueness is enforced'
);
SELECT ok(
    EXISTS (
        SELECT 1
        FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public' AND c.relname = 'uk_org_order_receipt_key'
    ),
    'per-org receipt idempotency key is enforced'
);
SELECT throws_ok(
    $$INSERT INTO public.inventory_movements (org_id, item_id, movement_type, quantity)
      VALUES ('00000000-0000-0000-0000-000000000000',
              '00000000-0000-0000-0000-000000000000', 'RECEIPT', -5)$$,
    '23514',
    NULL,
    'movement quantities stay positive; sign lives in the type'
);
SELECT throws_ok(
    $$INSERT INTO public.order_receipt_lines (receipt_id, order_line_id, received_qty, damaged_qty)
      VALUES ('00000000-0000-0000-0000-000000000000',
              '00000000-0000-0000-0000-000000000000', 5, 7)$$,
    '23514',
    NULL,
    'damaged quantity can never exceed the received quantity'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.inventory_movements', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.inventory_movements', 'DELETE'),
    'authenticated can only append to the movement ledger'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.inventory_movements', 'SELECT')
    AND NOT has_table_privilege('authenticated', 'public.inventory_movements', 'INSERT'),
    'authenticated reads the movement ledger; appends run through the documentary authority'
);
SELECT ok(
    has_table_privilege('documentary_backend', 'public.inventory_movements', 'INSERT')
    AND EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'inventory_movements'
          AND policyname = 'inventory_movements_member_insert'
          AND with_check LIKE '%documentary_role%'
    ),
    'movement writes require warehouse roles, not just org membership'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid
        WHERE n.nspname = 'private' AND p.proname = 'guard_inventory_org'
    ),
    'cross-tenant reference guard exists'
);
SELECT ok(
    (
        SELECT count(*) FROM pg_trigger
        WHERE tgname = 'guard_inventory_org' AND NOT tgisinternal
    ) = 3,
    'tenant guard protects receipts, receipt lines, and movements'
);
SELECT has_column(
    'public', 'inventory_movements', 'rack_location',
    'movements carry the physical rack the stock touched'
);
SELECT has_column(
    'public', 'inventory_movements', 'actor_label',
    'movements carry a human label of who recorded them'
);
SELECT * FROM finish();
ROLLBACK;
