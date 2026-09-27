BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(23);

SELECT has_table('public', 'work_centers', 'work centers table exists');
SELECT has_table('public', 'production_steps', 'routing steps table exists');
SELECT has_table('public', 'production_step_events', 'append-only step events table exists');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'orders_workshop_position_uq'
    ),
    'one work order per sealed position per version'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'order_status' AND e.enumlabel = 'IN_PROGRESS'
    ),
    'workshop order statuses include production lifecycle values'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.production_step_events', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.production_step_events', 'DELETE'),
    'step events are append-only for tenant roles'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.production_step_events', 'INSERT')
    AND has_table_privilege('authenticated', 'public.production_step_events', 'SELECT'),
    'tenant roles can read but not forge step events'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.production_steps', 'INSERT')
    AND NOT has_table_privilege('authenticated', 'public.production_steps', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.production_steps', 'DELETE'),
    'tenant roles cannot write production steps directly'
);
SELECT ok(
    NOT has_table_privilege('authenticated', 'public.work_centers', 'INSERT')
    AND NOT has_table_privilege('authenticated', 'public.work_centers', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.work_centers', 'DELETE'),
    'tenant roles cannot write work centers directly'
);
SELECT ok(
    NOT has_table_privilege('service_role', 'public.production_step_events', 'UPDATE')
    AND NOT has_table_privilege('service_role', 'public.production_step_events', 'DELETE'),
    'step events are append-only for service_role too'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_tables
        WHERE schemaname = 'public'
          AND tablename = 'production_steps'
          AND rowsecurity = true
    ),
    'routing steps enforce row level security'
);
SELECT throws_ok(
    $$INSERT INTO public.production_steps
        (org_id, order_id, sequence, code, label, status)
      VALUES ('00000000-0000-0000-0000-000000000000',
              '00000000-0000-0000-0000-000000000000',
              1, 'CUT', 'x', 'DONE')$$,
    '23503',
    NULL,
    'steps cannot reference a non-existent work order'
);
SELECT throws_ok(
    $$INSERT INTO public.production_step_events
        (org_id, order_id, event)
      VALUES ('00000000-0000-0000-0000-000000000000',
              '00000000-0000-0000-0000-000000000000', 'STEP_STARTED')$$,
    '23503',
    NULL,
    'events cannot reference a non-existent work order'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public' AND c.relname = 'work_centers_org_id_code_key'
    ) OR EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname LIKE 'work_centers%code%'
    ),
    'work center codes unique per org'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'orders'
          AND policyname = 'workshop_orders_backend_access'
          AND 'documentary_backend' = ANY(roles)
    ),
    'workshop orders stay visible to floor transitions under the backend role'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND indexname = 'orders_workshop_position_uq'
          AND indexdef LIKE '%remake_of%'
    ),
    'release uniqueness excludes remake orders'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'order_status' AND e.enumlabel = 'DISPATCHED'
    ),
    'order status includes DISPATCHED for shipped work orders'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'order_status' AND e.enumlabel = 'INSTALLED'
    ),
    'order status includes INSTALLED for delivered work'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'production_step_events_event_check'
          AND pg_get_constraintdef(oid) LIKE '%WO_PACKED%'
          AND pg_get_constraintdef(oid) LIKE '%WO_DISPATCHED%'
          AND pg_get_constraintdef(oid) LIKE '%WO_INSTALLED%'
    ),
    'step events accept packing, dispatch and installation outcomes'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'production_step_events_event_check'
          AND pg_get_constraintdef(oid) LIKE '%WO_OPS_EXPORTED%'
          AND pg_get_constraintdef(oid) LIKE '%WO_REMNANTS_SETTLED%'
          AND pg_get_constraintdef(oid) LIKE '%WO_STOCK_CONSUMED%'
    ),
    'step events accept operations export, remnant settlement and stock consumption outcomes'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'production_step_events_event_check'
          AND pg_get_constraintdef(oid) LIKE '%QC_CHECK%'
    ),
    'step events accept per-check QC records'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'production_steps_code_check'
          AND pg_get_constraintdef(oid) LIKE '%MACHINING%'
          AND pg_get_constraintdef(oid) LIKE '%WELD%'
          AND pg_get_constraintdef(oid) LIKE '%CRIMP%'
          AND pg_get_constraintdef(oid) LIKE '%HARDWARE%'
          AND pg_get_constraintdef(oid) LIKE '%CLEAN%'
    ),
    'routing steps accept the real shop vocabulary (§29/§30)'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'work_centers_kind_check'
          AND pg_get_constraintdef(oid) LIKE '%MACHINING%'
          AND pg_get_constraintdef(oid) LIKE '%WELDING%'
          AND pg_get_constraintdef(oid) LIKE '%CRIMPING%'
          AND pg_get_constraintdef(oid) LIKE '%CLEANING%'
          AND pg_get_constraintdef(oid) LIKE '%SASH_ASSEMBLY%'
    ),
    'work center kinds accept the real shop vocabulary (§29/§30)'
);
SELECT * FROM finish();
ROLLBACK;
