BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(27);

-- clients: tipo de cliente y estado de fusión.
SELECT has_column('public', 'clients', 'kind', 'clients.kind exists');
SELECT has_column('public', 'clients', 'merged_into', 'clients.merged_into exists');
SELECT has_column('public', 'clients', 'merged_at', 'clients.merged_at exists');
SELECT col_is_fk('public', 'clients', 'merged_into',
    'merged_into references clients');
SELECT hasnt_column('public', 'clients', 'notes',
    'notes moved to client_notes rows');

-- Contactos por cliente.
SELECT has_table('public', 'client_contacts', 'client_contacts exists');
SELECT has_column('public', 'client_contacts', 'role_label',
    'contacts carry a role');
SELECT col_is_fk('public', 'client_contacts', 'client_id',
    'contacts reference the client');
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE oid = 'public.client_contacts'::regclass),
    'contacts row level security enabled');

-- Direcciones de obra.
SELECT has_table('public', 'client_addresses', 'client_addresses exists');
SELECT has_column('public', 'client_addresses', 'is_default',
    'addresses can mark a default');
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE oid = 'public.client_addresses'::regclass),
    'addresses row level security enabled');

-- Notas bitácora: una sola política FOR ALL; append-only viene de los
-- grants (authenticated no recibe UPDATE ni DELETE).
SELECT has_table('public', 'client_notes', 'client_notes exists');
SELECT policies_are('public', 'client_notes',
    ARRAY['client_notes_isolation'],
    'notes keep the single org isolation policy');
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE oid = 'public.client_notes'::regclass),
    'notes row level security enabled');
SELECT is(
    (SELECT COUNT(*)::int FROM information_schema.column_privileges
     WHERE table_schema='public' AND table_name='client_notes'
       AND grantee='authenticated' AND privilege_type='UPDATE'
       AND column_name<>'client_id'),
    0,
    'notes stay append-only — only client_id is repointable for merges');
SELECT is(
    (SELECT COUNT(*)::int FROM information_schema.role_table_grants
     WHERE table_schema='public' AND table_name='client_notes'
       AND grantee='authenticated' AND privilege_type='DELETE'),
    0,
    'notes cannot be deleted by authenticated');

-- Auditoría de fusión.
SELECT has_table('public', 'client_merges', 'client_merges exists');
SELECT has_column('public', 'client_merges', 'survivor_id',
    'merge records the survivor');
SELECT has_column('public', 'client_merges', 'actor_label',
    'merge records who did it');
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE oid = 'public.client_merges'::regclass),
    'merges row level security enabled');
SELECT is(
    (SELECT COUNT(*)::int FROM information_schema.role_table_grants
     WHERE table_schema='public' AND table_name='client_merges'
       AND grantee='authenticated'
       AND privilege_type IN ('UPDATE','DELETE')),
    0,
    'merge audit is append-only for authenticated');

-- Invitaciones de organización.
SELECT has_table('public', 'org_invitations', 'org_invitations exists');
SELECT has_column('public', 'org_invitations', 'status', 'invitation status exists');
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE oid = 'public.org_invitations'::regclass),
    'invitations row level security enabled');

-- Ajustes: 2FA por organización y umbral de descuento en reglas.
SELECT has_column('public', 'tenancy_organizations', 'require_totp',
    'org require_totp exists');
SELECT has_column('public', 'pricing_rules', 'discount_approval_threshold_pct',
    'discount approval threshold exists');

SELECT * FROM finish();
ROLLBACK;
