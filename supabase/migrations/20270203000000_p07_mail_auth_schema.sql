-- P07 — hallazgo QA: el aviso mail.pricing_decision fallaba con
-- "permission denied for schema auth" cuando la operación sí tenía
-- solicitante. El correo interno joinea auth.users bajo documentary_backend;
-- la migración p25_brand_mail intentó `GRANT USAGE ON SCHEMA auth` pero el
-- rol que ejecuta migraciones no puede otorgar objetos del schema auth
-- (emite "no privileges were granted" y la migración se registra igual) —
-- migración 20261212 ya documenta ese límite.
-- La lectura sale por funciones private.* SECURITY DEFINER (el owner sí
-- tiene USAGE sobre auth), con el límite de tenant dentro de la función:
-- las membresías activas del org llamante, nunca usuarios ajenos.

-- check_function_bodies=off: en el Postgres 16 vainilla del gate no existe
-- auth.users; sin esta directiva CREATE FUNCTION de LANGUAGE sql valida el
-- cuerpo y aborta (pg_dump usa el mismo mecanismo por el mismo motivo).
SET check_function_bodies = off;

CREATE FUNCTION private.org_member_emails(target_org UUID, allowed_roles TEXT[])
RETURNS SETOF TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT u.email::text
      FROM public.tenancy_memberships m
      JOIN auth.users u ON u.id = m.user_id
     WHERE m.org_id = target_org
       AND m.is_active
       AND m.role::text = ANY(allowed_roles)
     ORDER BY m.created_at
$$;

-- Email de un usuario concreto (etiqueta "quién decidió" en la notificación).
-- Sin filtro de org: la referencia ya viene de una fila del tenant; el rol
-- receptor nunca la consulta por id arbitrario — sólo los roles backend.
CREATE FUNCTION private.user_email(target_user UUID)
RETURNS TEXT
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
    SELECT email::text FROM auth.users WHERE id = target_user
$$;

REVOKE ALL ON FUNCTION private.org_member_emails(UUID, TEXT[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.user_email(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.org_member_emails(UUID, TEXT[])
    TO documentary_backend, portal_backend;
GRANT EXECUTE ON FUNCTION private.user_email(UUID)
    TO documentary_backend, portal_backend;
