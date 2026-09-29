BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(7);

-- §06 system identity — manufacturer/family/applications are declarative
-- metadata: NULL stays unknown and nothing downstream may infer them.

SELECT has_column('public', 'profile_systems', 'manufacturer',
    'systems carry a declared manufacturer');
SELECT col_is_null('public', 'profile_systems', 'manufacturer',
    'manufacturer nullable — NULL means unknown');
SELECT has_column('public', 'profile_systems', 'family',
    'systems carry a declared product family');
SELECT col_is_null('public', 'profile_systems', 'family',
    'family nullable — NULL means unknown');
SELECT has_column('public', 'profile_systems', 'applications',
    'systems carry declared applications');
SELECT col_not_null('public', 'profile_systems', 'applications',
    'applications defaults to an empty list, never NULL');
SELECT col_has_default('public', 'profile_systems', 'applications',
    'applications default declared');

SELECT * FROM finish();
ROLLBACK;
