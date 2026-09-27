BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(2);

-- confirm_delivery's SELECT … FOR UPDATE on public.projects needs BOTH the
-- FOR UPDATE policy and an UPDATE column privilege; missing either returns
-- project_not_found / 42501 and delivery can never legally close.
SELECT ok(
    has_column_privilege('documentary_backend', 'public.projects', 'status', 'UPDATE'),
    'documentary_backend holds the lock admission grant on projects.status'
);
SELECT ok(
    has_column_privilege('documentary_backend', 'public.projects', 'status', 'SELECT')
    AND NOT has_column_privilege('documentary_backend', 'public.projects', 'name', 'UPDATE')
    AND NOT has_column_privilege('documentary_backend', 'public.projects', 'total_price_gross', 'UPDATE'),
    'the grant stays single-column — project rows remain read-only to the role'
);

SELECT * FROM finish();
ROLLBACK;
