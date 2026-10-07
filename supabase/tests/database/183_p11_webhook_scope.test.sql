BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(7);

-- P11 — el webhook público de pago resuelve su scope por identificador opaco
-- (id de link o token de proveedor) vía SECURITY DEFINER: sin JWT el RLS
-- org-scope es ciego y el settle no encuentra la fila.

SELECT has_function(
    'private', 'payment_link_public_scope', ARRAY['uuid', 'text'],
    'private.payment_link_public_scope existe'
);
SELECT ok(
    (SELECT procedure.prosecdef
       FROM pg_proc procedure
      WHERE procedure.pronamespace = 'private'::regnamespace
        AND procedure.proname = 'payment_link_public_scope'),
    'private.payment_link_public_scope es SECURITY DEFINER'
);
SELECT ok(
    has_function_privilege('documentary_backend', 'private.payment_link_public_scope(uuid, text)', 'EXECUTE'),
    'documentary_backend puede invocar el scope del webhook'
);
SELECT ok(
    NOT has_function_privilege('anon', 'private.payment_link_public_scope(uuid, text)', 'EXECUTE'),
    'el rol anónimo no puede invocar el scope (sólo lo usa el backend)'
);
SELECT ok(
    NOT has_function_privilege('authenticated', 'private.payment_link_public_scope(uuid, text)', 'EXECUTE'),
    'un miembro autenticado no puede invocar el scope directamente'
);

-- Resolución funcional: el scope devuelve la fila por id opaco o por token.
INSERT INTO auth.users (id, aud, role, email, email_confirmed_at, created_at, updated_at)
VALUES ('99999999-9999-4999-8999-999999999999', 'authenticated', 'authenticated',
        'pgtap-p11@dekopen.test', now(), now(), now());
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('99999999-9999-4999-8999-999999999998', 'pgTAP P11 scope', '76.999.999-9');
INSERT INTO public.tenancy_memberships (org_id, user_id, role)
VALUES ('99999999-9999-4999-8999-999999999998',
        '99999999-9999-4999-8999-999999999999', 'ESTIMATOR');
INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES ('99999999-9999-4999-8999-999999999997',
        '99999999-9999-4999-8999-999999999998', 'PG-1', 'pgTAP link',
        'Cliente pgTAP', '99999999-9999-4999-8999-999999999999');
INSERT INTO public.project_payment_links (
    id, org_id, project_id, operation_key, kind, amount, payer_email, subject,
    status, flow_token, environment, created_by
) VALUES (
    '99999999-9999-4999-8999-999999999996',
    '99999999-9999-4999-8999-999999999998',
    '99999999-9999-4999-8999-999999999997',
    'op-pgtap-scope', 'ANTICIPO', 1000, 'pgtap@test.cl', 'Cobro pgTAP',
    'PENDING', 'pgtap-tok', 'sandbox', '99999999-9999-4999-8999-999999999999'
);
SELECT is(
    (SELECT org_id::text FROM private.payment_link_public_scope(
        '99999999-9999-4999-8999-999999999996'::uuid, NULL::text)),
    '99999999-9999-4999-8999-999999999998',
    'el scope resuelve la fila por id de link'
);
SELECT is(
    (SELECT org_id::text FROM private.payment_link_public_scope(
        NULL::uuid, 'pgtap-tok')),
    '99999999-9999-4999-8999-999999999998',
    'el scope resuelve la fila por token del proveedor'
);

SELECT * FROM finish();
ROLLBACK;
