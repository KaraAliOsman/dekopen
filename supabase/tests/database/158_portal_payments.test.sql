BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(3);

SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'project_payments'
          AND policyname = 'project_payments_portal_read'
          AND 'portal_backend' = ANY(roles)
    ),
    'portal_backend holds the org-scoped payment read policy'
);
SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'project_payments'
          AND policyname = 'project_payments_portal_read'
          AND 'authenticated' = ANY(roles)
    ),
    'members do NOT gain the portal payment read'
);

SELECT ok(
    has_table_privilege('portal_backend', 'public.project_payment_links', 'SELECT'),
    'portal_backend can read the live payment link the proposal renders'
);

SELECT * FROM finish();
ROLLBACK;
