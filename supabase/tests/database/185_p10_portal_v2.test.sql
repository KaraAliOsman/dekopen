BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(12);

-- P10 — portal v2: is_option en posiciones, eventos append-only de
-- evidencia, canal FOLLOW y retorno de pago por link.

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'project_positions'
          AND column_name = 'is_option' AND is_nullable = 'NO'
    ),
    'project_positions.is_option existe NOT NULL'
);
SELECT ok(
    has_column_privilege('authenticated', 'public.project_positions',
        'is_option', 'SELECT')
    AND has_column_privilege('documentary_backend', 'public.project_positions',
        'is_option', 'UPDATE'),
    'is_option: lectura de miembros, escritura documental'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'customer_approval_events'
    ),
    'customer_approval_events existe'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'customer_approval_events'
          AND policyname = 'customer_approval_events_portal_write'
          AND cmd = 'INSERT' AND 'portal_backend' = ANY (roles)
    ),
    'portal_backend inserta la evidencia de la decisión'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'approval_events_immutable'
    ),
    'customer_approval_events es append-only (trigger UPDATE/DELETE)'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'approval_decision_terminal'
    ),
    'customer_approvals: decisión terminal inmutable'
);

INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('00000000-0000-0000-0000-00000000d0a1', 'P10 Org', '76.000.010-0');
INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES (
    '00000000-0000-0000-0000-00000000d0a2',
    '00000000-0000-0000-0000-00000000d0a1',
    'PT10', 'P10 evidencia', 'Cliente',
    '00000000-0000-0000-0000-00000000d0a1'
);
INSERT INTO public.pricing_operations
    (id, org_id, project_id, requested_by, request, input_snapshot, result,
     source_revision, state, reason)
VALUES (
    '00000000-0000-0000-0000-00000000d0a4',
    '00000000-0000-0000-0000-00000000d0a1',
    '00000000-0000-0000-0000-00000000d0a2',
    '00000000-0000-0000-0000-00000000d0a1',
    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
    'BASE', 'APPLIED', 'fixture'
);
INSERT INTO public.project_versions
    (id, org_id, project_id, revision_code, snapshot_json, emitted_by,
     pricing_operation_id, canonical_version, bom_hash, snapshot_sha256,
     production_allowed, documentary_complete)
VALUES (
    '00000000-0000-0000-0000-00000000d0a3',
    '00000000-0000-0000-0000-00000000d0a1',
    '00000000-0000-0000-0000-00000000d0a2',
    'REV-A', '{}'::jsonb,
    '00000000-0000-0000-0000-00000000d0a1',
    '00000000-0000-0000-0000-00000000d0a4',
    'DOCUMENTARY_CANONICAL_V1',
    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    TRUE, TRUE
);
INSERT INTO public.customer_approvals (
    id, org_id, project_id, project_version_id, token_hash, expires_at,
    created_by, channel
) VALUES (
    '00000000-0000-0000-0000-00000000d0a5',
    '00000000-0000-0000-0000-00000000d0a1',
    '00000000-0000-0000-0000-00000000d0a2',
    '00000000-0000-0000-0000-00000000d0a3',
    'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee',
    now() + interval '7 days',
    '00000000-0000-0000-0000-00000000d0a1', 'FOLLOW'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM public.customer_approvals
        WHERE id = '00000000-0000-0000-0000-00000000d0a5'
          AND channel = 'FOLLOW'
    ),
    'customer_approvals accepts the FOLLOW channel'
);

-- La evidencia: inserta completa y jamás se reescribe.
PREPARE insert_event AS
    INSERT INTO public.customer_approval_events (
        org_id, approval_id, project_id, decision, decided_by, decided_rut,
        decided_note, decision_ip, decision_user_agent, acceptance_text,
        revision_code, bom_hash, positions
    ) VALUES (
        '00000000-0000-0000-0000-00000000d0a1',
        '00000000-0000-0000-0000-00000000d0a5',
        '00000000-0000-0000-0000-00000000d0a2',
        'APPROVED', 'Cliente pgTAP', '11.222.333-9',
        NULL, '190.54.10.20'::inet, 'pgTAP/1.0',
        'Acepto la propuesta COT-PT10-REV-A por $1.000.000 IVA incluido y sus condiciones.',
        'REV-A',
        'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        '[{"position_id":"p1","position_index":12}]'::jsonb
    );
SELECT lives_ok(
    'insert_event',
    'la evidencia completa de la decisión se persiste'
);

PREPARE rewrite_event AS
    UPDATE public.customer_approval_events
    SET decided_rut = '1.111.111-1'
    WHERE approval_id = '00000000-0000-0000-0000-00000000d0a5';
SELECT throws_ok(
    'rewrite_event',
    '42501',
    NULL,
    'la evidencia de decisión no se reescribe (append-only)'
);

PREPARE delete_event AS
    DELETE FROM public.customer_approval_events
    WHERE approval_id = '00000000-0000-0000-0000-00000000d0a5';
SELECT throws_ok(
    'delete_event',
    '42501',
    NULL,
    'la evidencia de decisión no se borra (append-only)'
);

-- Decisión terminal: un enlace aprobado no se "des-aprueba".
UPDATE public.customer_approvals
SET status = 'APPROVED', decided_by = 'Cliente pgTAP', decided_at = now()
WHERE id = '00000000-0000-0000-0000-00000000d0a5';

PREPARE redecide AS
    UPDATE public.customer_approvals
    SET status = 'DECLINED'
    WHERE id = '00000000-0000-0000-0000-00000000d0a5';
SELECT throws_ok(
    'redecide',
    '42501',
    NULL,
    'una decisión terminal no se reescribe en el enlace'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'project_payment_links'
          AND column_name = 'payer_return_url'
    ),
    'project_payment_links.payer_return_url existe'
);

SELECT * FROM finish();
ROLLBACK;
