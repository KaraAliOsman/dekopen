BEGIN;

-- P25 (marca): color primario white-label de la org, el pie
-- "Generado con DEKOPEN" opt-in en documentos del cliente, y la
-- bandeja de salida persistente de correos transaccionales.

-- 1) Identidad white-label: el color primario de la marca del fabricante
--    se valida #RRGGBB aquí; el contraste AA contra papel se evalúa en
--    backend/renderers (fallback teal-800). doc_dekopen_credit deja la
--    atribución oculta por defecto — el fabricante vende con su marca.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS brand_color VARCHAR(7)
        CONSTRAINT brand_color_hex
        CHECK (brand_color IS NULL OR brand_color ~ '^#[0-9A-Fa-f]{6}$'),
    ADD COLUMN IF NOT EXISTS doc_dekopen_credit BOOLEAN NOT NULL DEFAULT FALSE;

-- La política tenancy_organizations_branding_update ya acota el UPDATE al
-- org del llamante (OWNER/ESTIMATOR); solo faltan las columnas en el grant.
GRANT UPDATE (brand_color, doc_dekopen_credit)
    ON public.tenancy_organizations TO documentary_backend;

-- 2) Outbox transaccional: cada correo se materializa ANTES de enviarse —
--    la fila es la evidencia de qué salió, a quién y con qué resultado.
--    El proveedor por defecto es sandbox (registra sin entregar); SMTP se
--    activa por configuración (docs/ACTIVACION.md).
CREATE TABLE public.mail_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    audience VARCHAR(8) NOT NULL
        CONSTRAINT mail_messages_audience_check
        CHECK (audience IN ('CLIENT', 'INTERNAL')),
    template VARCHAR(48) NOT NULL,
    to_email VARCHAR(255) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    html_body TEXT NOT NULL,
    text_body TEXT NOT NULL,
    status VARCHAR(8) NOT NULL DEFAULT 'QUEUED'
        CONSTRAINT mail_messages_status_check
        CHECK (status IN ('QUEUED', 'SENT', 'FAILED', 'SKIPPED')),
    provider VARCHAR(40),
    provider_ref VARCHAR(255),
    error TEXT,
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    attempts INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX mail_messages_org_created
    ON public.mail_messages (org_id, created_at DESC);
ALTER TABLE public.mail_messages ENABLE ROW LEVEL SECURITY;

-- Miembros con rol comercial leen la bandeja de su org (trazabilidad de
-- qué salió al cliente); nadie más la ve.
CREATE POLICY mail_messages_select ON public.mail_messages
    FOR SELECT TO public
    USING (
        private.documentary_role(org_id, ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER'])
    );

-- Solo los roles backend escriben: el enqueue ocurre dentro de la
-- transacción del caso de uso (compartir cotización, decidir, cobrar,
-- bloquear paso) bajo el mismo org del llamante.
CREATE POLICY mail_messages_insert ON public.mail_messages
    FOR INSERT TO documentary_backend, portal_backend
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY mail_messages_update ON public.mail_messages
    FOR UPDATE TO documentary_backend, portal_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

GRANT SELECT, INSERT, UPDATE ON public.mail_messages
    TO documentary_backend, portal_backend;
GRANT SELECT ON public.mail_messages TO authenticated;

-- El correo interno a propietarios/estimadores necesita el email de
-- inicio de sesión: se lee vía join con membresías del propio org
-- (nunca a usuarios ajenos), por eso el grant es a los roles que ya
-- sirven esos casos de uso, no a authenticated.
-- El schema auth sólo existe en el stack Supabase; en la puerta de replay
-- sobre Postgres 16 vanilla estos grants se omiten (allí no hay auth.users).
DO $$
BEGIN
    IF to_regclass('auth.users') IS NOT NULL THEN
        EXECUTE 'GRANT USAGE ON SCHEMA auth TO portal_backend';
        EXECUTE 'GRANT SELECT ON auth.users TO documentary_backend, portal_backend';
    END IF;
END $$;

COMMIT;
