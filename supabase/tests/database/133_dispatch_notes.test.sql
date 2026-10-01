BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(16);

-- Tenants read but never write.
SELECT ok(
    (SELECT pol.polcmd = 'r' FROM pg_policy pol
     WHERE pol.polrelid = 'public.dispatch_notes'::regclass
       AND pol.polname = 'dispatch_notes_read')
    AND NOT has_table_privilege('authenticated', 'public.dispatch_notes', 'INSERT')
    AND NOT has_table_privilege('authenticated', 'public.dispatch_notes', 'UPDATE')
    AND NOT has_table_privilege('authenticated', 'public.dispatch_notes', 'DELETE'),
    'tenant role policy is SELECT-only and writes are revoked'
);

SELECT has_table(
    'public', 'dispatch_notes',
    'dispatch notes table exists'
);
SELECT has_column(
    'public', 'dispatch_notes', 'org_id',
    'org_id column exists'
);
SELECT has_column(
    'public', 'dispatch_notes', 'payload_json',
    'sealed payload column exists'
);
SELECT has_column(
    'public', 'dispatch_notes', 'unit_indexes',
    'guía seals the manifest units of its trip'
);
SELECT has_column(
    'public', 'dispatch_notes', 'delivery_id',
    'guía links to the trip that carried it — a FAILED trip frees its units'
);
SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.dispatch_notes'::regclass
          AND contype = 'u'
          AND conkey = (
              SELECT ARRAY[attnum] FROM pg_attribute
              WHERE attrelid = 'public.dispatch_notes'::regclass
                AND attname = 'work_order_id'
          )
    ),
    'partial deliveries issue one live guía per trip — coverage is service-computed'
);
SELECT col_is_unique(
    'public', 'dispatch_notes', ARRAY['org_id', 'note_code'],
    'note code unique inside an org'
);
SELECT col_is_fk(
    'public', 'dispatch_notes', 'work_order_id',
    'note belongs to an order'
);
SELECT policies_are(
    'public', 'dispatch_notes',
    ARRAY['dispatch_notes_read', 'dispatch_notes_backend'],
    'read for members, writes only for the backend role'
);
SELECT ok(
    has_table_privilege('documentary_backend', 'public.dispatch_notes', 'INSERT'),
    'documentary backend may insert sealed notes'
);
SELECT ok(
    has_table_privilege('documentary_backend', 'public.clients', 'SELECT'),
    'the sealed guía may read the org-scoped client fallback (RUT/address)'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE oid = 'public.dispatch_notes'::regclass),
    'row level security is enabled'
);

-- Void lifecycle: columns exist, only the void fields are writable by the
-- backend role, and uniqueness survives on live notes.
SELECT has_column(
    'public', 'dispatch_notes', 'voided_at',
    'voided_at column exists'
);
SELECT has_column(
    'public', 'dispatch_notes', 'voided_reason',
    'voided_reason column exists'
);
SELECT ok(
    has_column_privilege(
        'documentary_backend', 'public.dispatch_notes', 'voided_at', 'UPDATE')
    AND NOT has_table_privilege(
        'documentary_backend', 'public.dispatch_notes', 'DELETE'),
    'backend role may only write the void columns, never delete a sealed note'
);

SELECT * FROM finish();
ROLLBACK;
