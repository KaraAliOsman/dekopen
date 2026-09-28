BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(8);

SELECT has_table('public', 'cnc_machines', 'cnc_machines exists');
SELECT has_table('public', 'cnc_tools', 'cnc_tools exists');
SELECT has_table('public', 'cnc_programs', 'cnc_programs exists');

SELECT ok(
    has_column_privilege('documentary_backend', 'public.cnc_programs', 'status', 'UPDATE')
    AND NOT has_column_privilege('authenticated', 'public.cnc_programs', 'files', 'UPDATE'),
    'programs update only through documentary_backend status flips'
);
SELECT ok(
    NOT has_table_privilege('documentary_backend', 'public.cnc_programs', 'DELETE')
    AND NOT has_table_privilege('service_role', 'public.cnc_programs', 'DELETE'),
    'cnc programs are never deleted — history stays SUPERSEDED'
);
SELECT ok(
    has_table_privilege('authenticated', 'public.cnc_machines', 'SELECT')
    AND NOT has_table_privilege('authenticated', 'public.cnc_machines', 'INSERT'),
    'authenticated reads machines; writes stay behind the API'
);
SELECT ok(
    has_table_privilege('documentary_backend', 'public.cnc_tools', 'INSERT')
    AND has_table_privilege('documentary_backend', 'public.cnc_tools', 'UPDATE'),
    'tool library is org-managed through the API'
);
-- Guard against the 20261220000500 regression: an event-check rewrite must
-- never drop WO_CNC_PROGRAM again.
SELECT ok(
    (SELECT pg_get_constraintdef(oid) FROM pg_constraint
     WHERE conname = 'production_step_events_event_check')
        LIKE '%WO_CNC_PROGRAM%',
    'step event check accepts WO_CNC_PROGRAM'
);

SELECT * FROM finish();
ROLLBACK;
