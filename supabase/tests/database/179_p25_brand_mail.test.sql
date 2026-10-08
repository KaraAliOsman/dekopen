BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(10);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'brand_color'
    ),
    'tenancy_organizations carries brand_color'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'doc_dekopen_credit'
    ),
    'tenancy_organizations carries doc_dekopen_credit'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.tenancy_organizations'::regclass
          AND conname = 'brand_color_hex'
    ),
    'brand_color is constrained to #RRGGBB'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'mail_messages'
    ),
    'mail_messages exists'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class WHERE relname = 'mail_messages'),
    'mail_messages enforces RLS'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.mail_messages'::regclass
          AND conname = 'mail_messages_audience_check'
    ),
    'mail audience is CLIENT | INTERNAL'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.mail_messages'::regclass
          AND conname = 'mail_messages_status_check'
    ),
    'mail status is QUEUED | SENT | FAILED | SKIPPED'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'mail_messages'
          AND policyname = 'mail_messages_insert'
          AND 'documentary_backend' = ANY (roles)
          AND 'portal_backend' = ANY (roles)
    ),
    'backend roles may enqueue mail scoped to the caller org'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'mail_messages'
          AND policyname = 'mail_messages_select'
    ),
    'members can read their org mail tray'
);
SELECT ok(
    has_table_privilege('documentary_backend', 'public.mail_messages', 'INSERT')
    AND has_table_privilege('portal_backend', 'public.mail_messages', 'INSERT'),
    'documentary/portal backends hold INSERT on mail_messages'
);

SELECT * FROM finish();
ROLLBACK;
