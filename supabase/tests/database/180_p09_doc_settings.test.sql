BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(9);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'doc_paper_size'
    ),
    'tenancy_organizations carries doc_paper_size'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'doc_terms'
    ),
    'tenancy_organizations carries doc_terms'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.tenancy_organizations'::regclass
          AND conname = 'doc_paper_size_values'
    ),
    'doc_paper_size is constrained to LETTER | LEGAL | A4'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.tenancy_organizations'::regclass
          AND conname = 'doc_terms_shape'
    ),
    'doc_terms shape is constrained'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.column_privileges
        WHERE table_schema = 'public' AND table_name = 'tenancy_organizations'
          AND column_name = 'doc_paper_size'
          AND grantee = 'documentary_backend' AND privilege_type = 'UPDATE'
    ),
    'documentary_backend can write doc_paper_size'
);

-- Functional shape checks against a scratch org row.
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('00000000-0000-0000-0000-00000000d091', 'Doc Terms Org', '76.000.091-0');

PREPARE set_valid AS
    UPDATE public.tenancy_organizations
    SET doc_terms = '{"plazo_entrega":"15 días hábiles","garantia":"2 años"}'::jsonb
    WHERE id = '00000000-0000-0000-0000-00000000d091';
SELECT lives_ok(
    'set_valid',
    'doc_terms accepts the declared legal keys'
);

PREPARE set_invalid_key AS
    UPDATE public.tenancy_organizations
    SET doc_terms = '{"otra_clave":"x"}'::jsonb
    WHERE id = '00000000-0000-0000-0000-00000000d091';
SELECT throws_ok(
    'set_invalid_key',
    '23514',
    NULL,
    'doc_terms rejects an undeclared key'
);

PREPARE set_invalid_paper AS
    UPDATE public.tenancy_organizations
    SET doc_paper_size = 'TABLOID'
    WHERE id = '00000000-0000-0000-0000-00000000d091';
SELECT throws_ok(
    'set_invalid_paper',
    '23514',
    NULL,
    'doc_paper_size rejects an unlisted size'
);

SELECT * FROM finish();
ROLLBACK;
