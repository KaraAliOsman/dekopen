BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(11);

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

-- Canal del enlace de aprobación: EMAIL rota por share, DOCUMENT vive en
-- el QR sellado del PDF (la evidencia inmutable sigue resolviendo).
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'customer_approvals'
          AND column_name = 'channel' AND column_default LIKE '%EMAIL%'
    ),
    'customer_approvals carries channel defaulting to EMAIL'
);

INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES (
    '00000000-0000-0000-0000-00000000d092',
    '00000000-0000-0000-0000-00000000d091',
    'PTY-DOC-091', 'Doc Channel', 'Cliente',
    '00000000-0000-0000-0000-00000000d091'
);
INSERT INTO public.pricing_operations
    (id, org_id, project_id, requested_by, request, input_snapshot, result,
     source_revision, state, reason)
VALUES (
    '00000000-0000-0000-0000-00000000d094',
    '00000000-0000-0000-0000-00000000d091',
    '00000000-0000-0000-0000-00000000d092',
    '00000000-0000-0000-0000-00000000d091',
    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
    'BASE', 'APPLIED', 'fixture'
);
INSERT INTO public.project_versions
    (id, org_id, project_id, revision_code, snapshot_json, emitted_by,
     pricing_operation_id, canonical_version, bom_hash, snapshot_sha256,
     production_allowed, documentary_complete)
VALUES (
    '00000000-0000-0000-0000-00000000d093',
    '00000000-0000-0000-0000-00000000d091',
    '00000000-0000-0000-0000-00000000d092',
    'REV-A', '{}'::jsonb,
    '00000000-0000-0000-0000-00000000d091',
    '00000000-0000-0000-0000-00000000d094',
    'DOCUMENTARY_CANONICAL_V1',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    TRUE, TRUE
);

PREPARE set_document_channel AS
    INSERT INTO public.customer_approvals (
        org_id, project_id, project_version_id, token_hash, expires_at,
        created_by, channel
    ) VALUES (
        '00000000-0000-0000-0000-00000000d091',
        '00000000-0000-0000-0000-00000000d092',
        '00000000-0000-0000-0000-00000000d093',
        'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc',
        now() + interval '7 days',
        '00000000-0000-0000-0000-00000000d091', 'DOCUMENT'
    );
SELECT lives_ok(
    'set_document_channel',
    'customer_approvals accepts the DOCUMENT channel'
);

PREPARE set_bad_channel AS
    INSERT INTO public.customer_approvals (
        org_id, project_id, project_version_id, token_hash, expires_at,
        created_by, channel
    ) VALUES (
        '00000000-0000-0000-0000-00000000d091',
        '00000000-0000-0000-0000-00000000d092',
        '00000000-0000-0000-0000-00000000d093',
        'dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd',
        now() + interval '7 days',
        '00000000-0000-0000-0000-00000000d091', 'CARRIER_PIGEON'
    );
SELECT throws_ok(
    'set_bad_channel',
    '23514',
    NULL,
    'customer_approvals rejects an unlisted channel'
);

SELECT * FROM finish();
ROLLBACK;
