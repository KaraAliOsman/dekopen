-- P10 — Portal de propuesta v2: alternativas declaradas, evidencia de
-- decisión y retorno de pago al portal.
--
-- 1) project_positions.is_option — una alternativa cotizada se dibuja y se
--    precifica como cualquier posición, pero NO suma al total del trato.
-- 2) customer_approval_events — cada decisión del cliente es un evento
--    append-only con su evidencia completa (nombre, RUT, IP, user agent,
--    texto de aceptación, revisión decidida y su huella, posiciones
--    marcadas). Un enlace puede ver varias (pedir cambios y luego aprobar);
--    los eventos jamás se reescriben.
-- 3) channel 'FOLLOW' — el enlace que el portal acuña cuando el cliente
--    sigue una cotización reemplazada hacia la vigente.
-- 4) project_payment_links.payer_return_url — el destino de retorno se
--    congela en el link: el portal vuelve al portal, no a una página
--    genérica.

ALTER TABLE public.project_positions
    ADD COLUMN IF NOT EXISTS is_option boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN public.project_positions.is_option IS
    'Posición alternativa: se precifica y se dibuja, pero queda fuera del '
    'total del trato ("no incluida en el precio").';

-- authenticated lee project_positions por columna (shot-08 revocó el grant
-- de tabla); el servicio documental escribe por columna también.
GRANT SELECT (is_option) ON public.project_positions TO authenticated;
GRANT UPDATE (is_option) ON public.project_positions TO documentary_backend;

-- portal_backend también necesita EXECUTE en el helper de membresías: las
-- policies de membresía en tablas hermanas lo invocan igual que en
-- project_payments (ya otorgado en 20261212000000_portal_backend_org_ids_grant).

-- ---- evidencia de decisión -------------------------------------------------

CREATE TABLE IF NOT EXISTS public.customer_approval_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL REFERENCES public.tenancy_organizations(id),
    approval_id uuid NOT NULL REFERENCES public.customer_approvals(id) ON DELETE CASCADE,
    project_id uuid NOT NULL REFERENCES public.projects(id),
    decision text NOT NULL
        CONSTRAINT customer_approval_events_decision_values
        CHECK (decision IN ('APPROVED', 'DECLINED', 'CHANGES_REQUESTED')),
    decided_by text NOT NULL,
    decided_rut varchar(32),
    decided_note text,
    decision_ip inet,
    decision_user_agent text,
    acceptance_text text,
    revision_code varchar(20),
    bom_hash text,
    positions jsonb
        CONSTRAINT customer_approval_events_positions_shape
        CHECK (positions IS NULL OR jsonb_typeof(positions) = 'array'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON TABLE public.customer_approval_events IS
    'Evidencia append-only de cada decisión del cliente sobre un enlace: '
    'quién, cuándo, desde dónde, sobre qué revisión y con qué texto.';
COMMENT ON COLUMN public.customer_approval_events.acceptance_text IS
    'Texto literal que el cliente marcó al aprobar (folio, revisión, total).';
COMMENT ON COLUMN public.customer_approval_events.bom_hash IS
    'Huella de la revisión decidida (bom_hash del snapshot sellado).';
COMMENT ON COLUMN public.customer_approval_events.positions IS
    'Alternativas marcadas por el cliente al decidir: '
    '[{position_id, position_index}].';

CREATE INDEX IF NOT EXISTS customer_approval_events_approval_idx
    ON public.customer_approval_events (approval_id, created_at);
CREATE INDEX IF NOT EXISTS customer_approval_events_project_idx
    ON public.customer_approval_events (org_id, project_id, created_at);

-- Append-only: la evidencia no se corrige ni se borra.
CREATE OR REPLACE FUNCTION private.guard_approval_events_immutable()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'approval_event_immutable' USING ERRCODE = '42501';
END;
$$;

REVOKE ALL ON FUNCTION private.guard_approval_events_immutable() FROM PUBLIC;

DROP TRIGGER IF EXISTS approval_events_immutable
    ON public.customer_approval_events;
CREATE TRIGGER approval_events_immutable
    BEFORE UPDATE OR DELETE ON public.customer_approval_events
    FOR EACH ROW EXECUTE FUNCTION private.guard_approval_events_immutable();

ALTER TABLE public.customer_approval_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY customer_approval_events_read ON public.customer_approval_events
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));

CREATE POLICY customer_approval_events_backend ON public.customer_approval_events
    FOR ALL TO documentary_backend
    USING (true) WITH CHECK (true);

-- El portal inserta los eventos de su propia decisión; los lee solo sobre el
-- enlace que resolvió (el GUC org del token + el approval_id de la fila).
CREATE POLICY customer_approval_events_portal_read ON public.customer_approval_events
    FOR SELECT TO portal_backend
    USING (org_id = NULLIF(current_setting('app.portal_org_id', true), '')::uuid);

CREATE POLICY customer_approval_events_portal_write ON public.customer_approval_events
    FOR INSERT TO portal_backend
    WITH CHECK (org_id = NULLIF(current_setting('app.portal_org_id', true), '')::uuid);

GRANT SELECT ON public.customer_approval_events TO authenticated;
GRANT SELECT, INSERT ON public.customer_approval_events TO portal_backend;
GRANT ALL ON public.customer_approval_events TO documentary_backend;
GRANT ALL ON public.customer_approval_events TO service_role;

REVOKE ALL ON public.customer_approval_events FROM anon;

-- Una decisión terminal es inmutable en el propio enlace: aprobada o
-- rechazada no se puede "des-decidir" ni reescribir su registro. Los enlaces
-- CHANGES_REQUESTED quedan abiertos por diseño (el cliente aún puede
-- aprobar); revocada jamás revive.
CREATE OR REPLACE FUNCTION private.guard_approval_decision_terminal()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF OLD.status IN ('APPROVED', 'DECLINED') THEN
        IF NEW.status IS DISTINCT FROM OLD.status
            OR NEW.decided_by IS DISTINCT FROM OLD.decided_by
            OR NEW.decided_at IS DISTINCT FROM OLD.decided_at
            OR NEW.decided_note IS DISTINCT FROM OLD.decided_note THEN
            RAISE EXCEPTION 'decision_evidence_immutable' USING ERRCODE = '42501';
        END IF;
    ELSIF OLD.status = 'REVOKED' AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'link_revoked_immutable' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.guard_approval_decision_terminal() FROM PUBLIC;

DROP TRIGGER IF EXISTS approval_decision_terminal ON public.customer_approvals;
CREATE TRIGGER approval_decision_terminal
    BEFORE UPDATE ON public.customer_approvals
    FOR EACH ROW EXECUTE FUNCTION private.guard_approval_decision_terminal();

-- El seguimiento por enlace reemplazado minta tokens propios: el canal los
-- distingue del correo enviado por el estimador.
ALTER TABLE public.customer_approvals
    DROP CONSTRAINT IF EXISTS customer_approvals_channel_values;
ALTER TABLE public.customer_approvals
    ADD CONSTRAINT customer_approvals_channel_values
    CHECK (channel IN ('EMAIL', 'DOCUMENT', 'FOLLOW'));

-- ---- retorno de pago por link ----------------------------------------------

ALTER TABLE public.project_payment_links
    ADD COLUMN IF NOT EXISTS payer_return_url text;

COMMENT ON COLUMN public.project_payment_links.payer_return_url IS
    'Destino del pagador tras decidir — sellado al acuñar el link (el portal '
    'vuelve a la cotización; el default sigue siendo la URL de la integración).';
