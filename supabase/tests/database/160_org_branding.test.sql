BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(2);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'commercial_name'
    ),
    'commercial_name column exists for the document masthead'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'brand_logo_sha256'
    ),
    'brand_logo_sha256 pins the frozen logo bytes'
);

SELECT * FROM finish();
ROLLBACK;
