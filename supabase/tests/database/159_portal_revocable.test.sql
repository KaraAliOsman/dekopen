BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(2);

SELECT ok(
    EXISTS (
        SELECT 1
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'customer_approvals'
          AND c.conname = 'customer_approvals_status_check'
          AND pg_get_constraintdef(c.oid) LIKE '%REVOKED%'
    ),
    'customer_approvals status check admits REVOKED'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'customer_approvals'
          AND column_name = 'revoked_at'
    ),
    'revoked_at column exists for the revocation audit'
);

SELECT * FROM finish();
ROLLBACK;
