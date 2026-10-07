-- P22 — clientes, empresa y ajustes.
--
-- Clientes deja de ser una ficha plana: tipo persona/empresa, contactos con
-- rol, direcciones de obra múltiples, notas con autor y fecha (apéndice — la
-- columna suelta `clients.notes` migra a la primera nota y desaparece) y
-- fusión auditada de duplicados por RUT.
--
-- Empresa gana razón social/RUT editables y un interruptor de 2FA obligatorio
-- por org; Usuarios y roles lee membresías con correo y estado 2FA vía una
-- función SECURITY DEFINER que filtra por la org del llamante (nunca entrega
-- una org ajena), e invita por `org_invitations`.
--
-- Todo corre bajo RLS por org_id como cualquier tabla de tenant.


SET check_function_bodies = off;

-- ---------------------------------------------------------------------------
-- Clientes: tipo + marca de fusión. La duplicación que `uk_org_client_rut`
-- detecta se resuelve por `merge_clients` (backend) y queda en
-- `client_merges` + `merged_into`.
ALTER TABLE public.clients
    ADD COLUMN kind TEXT NOT NULL DEFAULT 'COMPANY'
        CONSTRAINT clients_kind_check CHECK (kind IN ('PERSON', 'COMPANY')),
    ADD COLUMN merged_into UUID
        REFERENCES public.clients(id) ON DELETE SET NULL,
    ADD COLUMN merged_at TIMESTAMPTZ;

-- ---------------------------------------------------------------------------
-- Contactos: varios por cliente, cada uno con rol; `is_primary` marca el
-- primero del listado (el encargo no pide unicidad — quien guarda decide).
CREATE TABLE public.client_contacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    client_id UUID NOT NULL
        REFERENCES public.clients(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    role_label VARCHAR(80),
    email VARCHAR(255),
    phone VARCHAR(50),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_client_contacts_client
    ON public.client_contacts(client_id, is_primary DESC, created_at);

-- Direcciones de obra: varias, una puede ser `is_default` para precargar la
-- dirección de despacho de un proyecto nuevo.
CREATE TABLE public.client_addresses (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    client_id UUID NOT NULL
        REFERENCES public.clients(id) ON DELETE CASCADE,
    label VARCHAR(120) NOT NULL,
    address TEXT NOT NULL,
    comuna VARCHAR(60),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_client_addresses_client
    ON public.client_addresses(client_id, is_default DESC, created_at);

-- Notas de la ficha: apéndice con autor y fecha, sin UPDATE/DELETE — una nota
-- escrita queda escrita (auditoría de la relación comercial).
CREATE TABLE public.client_notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    client_id UUID NOT NULL
        REFERENCES public.clients(id) ON DELETE CASCADE,
    author_id UUID NOT NULL,
    author_label VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_client_notes_client
    ON public.client_notes(client_id, created_at DESC);

-- Fusión auditada: quién juntó qué con qué y cuántas filas movió.
CREATE TABLE public.client_merges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    survivor_id UUID NOT NULL
        REFERENCES public.clients(id) ON DELETE RESTRICT,
    merged_client_id UUID NOT NULL
        REFERENCES public.clients(id) ON DELETE RESTRICT,
    actor_id UUID NOT NULL,
    actor_label VARCHAR(255) NOT NULL,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Invitaciones a la org: correo + rol + estado. Si el correo ya es usuario,
-- el backend crea la membresía directo y marca la invitación aceptada; si
-- no, queda pendiente hasta que se acepte o se revoque.
CREATE TABLE public.org_invitations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    role public.org_role NOT NULL,
    status VARCHAR(12) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACCEPTED', 'REVOKED')),
    invited_by UUID NOT NULL,
    invited_label VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    responded_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uk_org_invitation_pending
    ON public.org_invitations(org_id, email) WHERE status = 'PENDING';

-- La nota suelta de `clients` entra a la ficha como primera nota (con el
-- correo del autor cuando lo tiene, "Migración" como autor registrado) y la
-- columna desaparece: dos fuentes de verdad para lo mismo quedan prohibidas.
-- auth.users sólo existe en Supabase: en el Postgres vainilla del gate el
-- backfill corre igual pero el autor queda "—".
DO $backfill$
BEGIN
    IF to_regclass('auth.users') IS NULL THEN
        INSERT INTO public.client_notes
            (org_id, client_id, author_id, author_label, body, created_at)
        SELECT c.org_id, c.id, c.created_by, '—', c.notes, c.created_at
        FROM public.clients c
        WHERE c.notes IS NOT NULL AND btrim(c.notes) <> '';
    ELSE
        INSERT INTO public.client_notes
            (org_id, client_id, author_id, author_label, body, created_at)
        SELECT c.org_id,
               c.id,
               c.created_by,
               COALESCE((SELECT u.email::text FROM auth.users u WHERE u.id = c.created_by), '—'),
               c.notes,
               c.created_at
        FROM public.clients c
        WHERE c.notes IS NOT NULL AND btrim(c.notes) <> '';
    END IF;
END
$backfill$;

ALTER TABLE public.clients DROP COLUMN notes;

-- ---------------------------------------------------------------------------
-- Empresa: razón social (name), RUT legal (tax_id), moneda y 2FA obligatorio.
-- Los grants siguen el mismo camino de `tenancy_organizations_branding_update`
-- (OWNER/ESTIMATOR escriben bajo documentary_backend); `currency` es
-- comercial pero vive en la fila de org.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS require_totp BOOLEAN NOT NULL DEFAULT FALSE;

GRANT UPDATE (name, tax_id, currency, require_totp)
    ON public.tenancy_organizations TO documentary_backend;

-- Umbral de descuento con aprobación: por debajo aplica directo; por encima
-- queda pendiente de aprobación del dueño (misma máquina de estados que ya
-- usa pricing; el valor era constante 10 % en el motor — ahora es dato de
-- la org, default conservado).
ALTER TABLE public.pricing_rules
    ADD COLUMN discount_approval_threshold_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.1000
        CONSTRAINT pricing_rules_discount_threshold_check
        CHECK (discount_approval_threshold_pct > 0 AND discount_approval_threshold_pct <= 1);

GRANT SELECT (discount_approval_threshold_pct)
    ON public.pricing_rules TO pricing_backend;
-- Ajustes > Comercial escribe las reglas comerciales (IVA, banda de margen,
-- umbral de descuento) via pricing_backend: grants de columna + políticas de
-- escritura acotadas a OWNER/ESTIMATOR (los roles que escriben ajustes).
GRANT UPDATE (tax_rate_pct, default_margin_pct, margin_min_pct,
    margin_max_pct, discount_approval_threshold_pct)
    ON public.pricing_rules TO pricing_backend;
-- INSERT a nivel tabla: una org nueva sin fila de reglas crea la suya al
-- guardar Comercial por primera vez (el UPDATE de arriba sigue por columna).
GRANT INSERT ON public.pricing_rules TO pricing_backend;

CREATE POLICY pricing_rules_settings_write ON public.pricing_rules
    FOR UPDATE TO pricing_backend
    USING (org_id IN (SELECT private.current_user_org_ids())
           AND private.pricing_role(org_id, ARRAY['OWNER', 'ESTIMATOR']))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids())
           AND private.pricing_role(org_id, ARRAY['OWNER', 'ESTIMATOR']));
CREATE POLICY pricing_rules_settings_insert ON public.pricing_rules
    FOR INSERT TO pricing_backend
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids())
           AND private.pricing_role(org_id, ARRAY['OWNER', 'ESTIMATOR']));

-- ---------------------------------------------------------------------------
-- RLS — misma forma que `clients_isolation` (FOR ALL por org).
ALTER TABLE public.client_contacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_addresses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.client_merges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.org_invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY client_contacts_isolation ON public.client_contacts FOR ALL
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY client_addresses_isolation ON public.client_addresses FOR ALL
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY client_notes_isolation ON public.client_notes FOR ALL
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY client_merges_isolation ON public.client_merges FOR ALL
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY org_invitations_isolation ON public.org_invitations FOR ALL
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

-- authenticated maneja contactos/direcciones completos; las notas sólo se
-- leen y se escriben (apéndice); las fusiones sólo se leen y se crean.
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.client_contacts, public.client_addresses TO authenticated;
GRANT SELECT, INSERT ON public.client_notes TO authenticated;
GRANT SELECT, INSERT ON public.client_merges TO authenticated;
-- El default de Supabase concede ALL a authenticated: notas y auditoría de
-- fusión son append-only (se corrige revocando lo que excede SELECT/INSERT).
REVOKE UPDATE, DELETE ON public.client_notes FROM authenticated;
REVOKE UPDATE, DELETE ON public.client_merges FROM authenticated;
-- Única excepción: la fusión repunta notas con UPDATE a nivel columna
-- (client_id); el cuerpo de la nota sigue siendo append-only.
GRANT UPDATE (client_id) ON public.client_notes TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.org_invitations TO authenticated;

-- La ficha y los agregados de saldo leen via documentary_backend.
GRANT SELECT
    ON public.client_contacts, public.client_addresses,
       public.client_notes, public.client_merges
    TO documentary_backend;

-- ---------------------------------------------------------------------------
-- Usuarios y roles: membresías con correo (auth.users) y estado 2FA, y
-- resolución de correo a user_id para invitar. SECURITY DEFINER para leer
-- auth.users; ambas filtran por la org del llamante — sin bypass cross-tenant.
CREATE OR REPLACE FUNCTION private.org_members(target_org UUID)
RETURNS TABLE (
    membership_id UUID,
    user_id UUID,
    email TEXT,
    role public.org_role,
    is_active BOOLEAN,
    totp_enabled BOOLEAN,
    created_at TIMESTAMPTZ
)
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = ''
AS $func$
    SELECT m.id, m.user_id, u.email::text, m.role, m.is_active, m.totp_enabled, m.created_at
    FROM public.tenancy_memberships m
    JOIN auth.users u ON u.id = m.user_id
    WHERE m.org_id = target_org
      AND target_org IN (SELECT private.current_user_org_ids())
    ORDER BY m.created_at, m.id
$func$;

REVOKE ALL ON FUNCTION private.org_members(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.org_members(UUID) TO authenticated;

CREATE OR REPLACE FUNCTION private.user_id_by_email(target_email TEXT)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
STABLE
SET search_path = ''
AS $func$
    SELECT u.id FROM auth.users u WHERE lower(u.email) = lower(target_email) LIMIT 1
$func$;

REVOKE ALL ON FUNCTION private.user_id_by_email(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.user_id_by_email(TEXT) TO authenticated;

-- Escribir membresías: sólo por funciones SECURITY DEFINER que filtran por
-- la org del llamante (el rol `authenticated` no toca tenancy_memberships).
-- El OWNER que llama invita/cambia roles/desactiva; la protección de "no
-- dejar la org sin dueño" vive en el servicio, que cuenta activos antes.
CREATE OR REPLACE FUNCTION private.set_membership(
    target_org UUID,
    target_membership UUID,
    new_role public.org_role,
    new_is_active BOOLEAN
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $func$
BEGIN
    IF target_org NOT IN (SELECT private.current_user_org_ids()) THEN
        RAISE EXCEPTION 'set_membership: organización fuera del contexto';
    END IF;
    UPDATE public.tenancy_memberships
    SET role = new_role,
        is_active = new_is_active,
        updated_at = clock_timestamp()
    WHERE id = target_membership AND org_id = target_org;
END
$func$;

REVOKE ALL ON FUNCTION private.set_membership(UUID, UUID, public.org_role, BOOLEAN) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.set_membership(UUID, UUID, public.org_role, BOOLEAN)
    TO authenticated;

-- Reclamo de invitaciones: para el correo verificado del llamante (su propio
-- login) o para un usuario existente invitado por el OWNER de la org — en
-- ambos casos la fila `org_invitations` fue escrita bajo RLS por un miembro
-- de esa org, así que otorgar la membresía que declara es seguro. Una
-- membresía existente se reactiva con el rol invitado.
CREATE OR REPLACE FUNCTION private.claim_org_invitations(target_email TEXT, target_user UUID)
RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $func$
DECLARE
    v_invitation RECORD;
    v_count INTEGER := 0;
BEGIN
    FOR v_invitation IN
        SELECT id, org_id, role FROM public.org_invitations
        WHERE status = 'PENDING' AND lower(email) = lower(target_email)
          -- Sin esta guarda cualquiera reclamaría la invitación de un correo
          -- ajeno a un user_id arbitrario. Vale reclamar la propia (login) o
          -- dentro de las orgs del llamante (un OWNER invita a quien ya es
          -- usuario).
          AND (target_user = auth.uid()
              OR org_id IN (SELECT private.current_user_org_ids()))
    LOOP
        INSERT INTO public.tenancy_memberships (org_id, user_id, role, is_active)
        VALUES (v_invitation.org_id, target_user, v_invitation.role, TRUE)
        ON CONFLICT (org_id, user_id)
        DO UPDATE SET role = EXCLUDED.role, is_active = TRUE, updated_at = clock_timestamp();
        UPDATE public.org_invitations
        SET status = 'ACCEPTED', responded_at = clock_timestamp()
        WHERE id = v_invitation.id;
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END
$func$;

REVOKE ALL ON FUNCTION private.claim_org_invitations(TEXT, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.claim_org_invitations(TEXT, UUID) TO authenticated;
