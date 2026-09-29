BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(3);

SELECT has_column(
    'public', 'customer_approvals', 'view_count',
    'view_count exists on share links'
);
SELECT has_column(
    'public', 'customer_approvals', 'last_viewed_at',
    'last_viewed_at exists on share links'
);
SELECT col_default_is(
    'public', 'customer_approvals', 'view_count', 0,
    'view_count defaults to zero'
);

SELECT * FROM finish();
ROLLBACK;
