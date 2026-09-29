BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(10);

SELECT has_table('public', 'deliveries', 'deliveries table exists');
SELECT has_column('public', 'deliveries', 'scheduled_date', 'schedule date captured');
SELECT has_column('public', 'deliveries', 'installer_name', 'crew captured');
SELECT has_column('public', 'deliveries', 'unit_indexes', 'trip carries a manifest unit subset');
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'deliveries'
          AND indexname = 'deliveries_one_open_trip'
          AND indexdef LIKE '%UNIQUE%order_id%'
    ),
    'one open trip per order; resolved trips leave history'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class WHERE relname = 'deliveries'),
    'deliveries enforce RLS'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'deliveries'
          AND policyname = 'deliveries_member_read'
    ),
    'tenant isolation policy in place'
);
SELECT ok(
    has_table_privilege('documentary_backend', 'public.deliveries', 'SELECT')
    AND has_table_privilege('documentary_backend', 'public.deliveries', 'INSERT')
    AND has_table_privilege('documentary_backend', 'public.deliveries', 'UPDATE')
    AND NOT has_table_privilege('documentary_backend', 'public.deliveries', 'DELETE'),
    'backend role schedules and transitions, never deletes'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.deliveries', 'SELECT')
    AND NOT has_table_privilege('authenticated', 'public.deliveries', 'INSERT')
    AND NOT has_table_privilege('authenticated', 'public.deliveries', 'UPDATE'),
    'tenant roles read deliveries only'
);
SELECT ok(
    NOT has_table_privilege('anon', 'public.deliveries', 'SELECT'),
    'anonymous role cannot read deliveries'
);

SELECT * FROM finish();
ROLLBACK;
