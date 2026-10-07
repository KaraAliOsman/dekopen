BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(9);

SELECT has_column('public', 'cnc_machines', 'machine_type',
    'machines declare their type');
SELECT has_column('public', 'cnc_machines', 'axes_count',
    'machines declare their axes');
SELECT has_column('public', 'cnc_machines', 'travel_x_mm',
    'machines declare their work envelope');
SELECT has_table('public', 'cnc_authority_events',
    'authority audit table exists');

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('00000000-0000-0000-0000-00000000d014', 'P14 Org', '76.000.014-1');

PREPARE bad_type AS
    INSERT INTO public.cnc_machines (org_id, code, name, machine_type)
    VALUES ('00000000-0000-0000-0000-00000000d014', 'CNC-X', 'X', 'LASER');
SELECT throws_ok(
    'bad_type', '23514', NULL,
    'machine_type rejects an unlisted type'
);

PREPARE bad_axes AS
    INSERT INTO public.cnc_machines (org_id, code, name, axes_count)
    VALUES ('00000000-0000-0000-0000-00000000d014', 'CNC-X', 'X', 9);
SELECT throws_ok(
    'bad_axes', '23514', NULL,
    'axes_count rejects implausible values'
);

PREPARE bad_travel AS
    INSERT INTO public.cnc_machines (org_id, code, name, travel_x_mm)
    VALUES ('00000000-0000-0000-0000-00000000d014', 'CNC-X', 'X', -1);
SELECT throws_ok(
    'bad_travel', '23514', NULL,
    'travel rejects nonpositive values'
);

SELECT ok(
    has_table_privilege('authenticated', 'public.cnc_authority_events', 'SELECT')
    AND NOT has_table_privilege('authenticated', 'public.cnc_authority_events', 'INSERT'),
    'authenticated reads the audit trail; writes stay behind the API'
);
SELECT ok(
    NOT has_table_privilege('documentary_backend', 'public.cnc_authority_events', 'UPDATE')
    AND NOT has_table_privilege('documentary_backend', 'public.cnc_authority_events', 'DELETE')
    AND NOT has_table_privilege('authenticated', 'public.cnc_authority_events', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.cnc_authority_events', 'DELETE'),
    'authority events are append-only for API roles — history is never rewritten'
);

SELECT * FROM finish();
ROLLBACK;
