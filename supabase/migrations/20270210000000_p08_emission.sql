-- P08 — Constructor de cotización y ciclo de vida del enlace.
--
-- 1) CHANGES_REQUESTED: el cliente pide ajustes sin rechazar la propuesta.
--    El enlace queda vivo para una decisión posterior (APPROVED/DECLINED) y
--    el pedido aterriza en "Hoy" + campana del estimador.
--    status era VARCHAR(10) — el nuevo estado necesita 17 caracteres.
ALTER TABLE public.customer_approvals
    ALTER COLUMN status TYPE VARCHAR(20);
ALTER TABLE public.customer_approvals
    DROP CONSTRAINT customer_approvals_status_check;
ALTER TABLE public.customer_approvals
    ADD CONSTRAINT customer_approvals_status_check
    CHECK (status IN ('PENDING', 'APPROVED', 'DECLINED', 'REVOKED', 'CHANGES_REQUESTED'));

-- 2) Plantillas comerciales de la organización: la clave 'pago' guarda el
--    calendario de pagos sugerido (no se imprime en el DOC-01 — alimenta el
--    prellenado de "Condiciones de pago" del constructor) y
--    doc_validity_days fija la vigencia sugerida de la cotización.
CREATE OR REPLACE FUNCTION public.doc_terms_is_valid(terms JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE WHEN jsonb_typeof(terms) IS DISTINCT FROM 'object' THEN FALSE
    ELSE NOT EXISTS (
        SELECT 1
        FROM jsonb_each(terms) AS entry(key, val)
        WHERE entry.key NOT IN (
            'plazo_entrega', 'instalacion', 'exclusiones',
            'garantia', 'jurisdiccion', 'pago'
        )
        OR jsonb_typeof(entry.val) <> 'string'
        OR length(entry.val #>> '{}') > 4000
    ) END
$$;

ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS doc_validity_days SMALLINT NOT NULL DEFAULT 15
        CONSTRAINT doc_validity_days_range
        CHECK (doc_validity_days BETWEEN 1 AND 365);

GRANT UPDATE (doc_validity_days)
    ON public.tenancy_organizations TO documentary_backend;

-- 3) Condiciones comerciales por cotización: el constructor precarga las
--    plantillas de la organización y el estimador puede editarlas por
--    cotización; el texto efectivo se congela dentro de la revisión
--    (organization.doc_terms del snapshot), así una edición posterior en
--    Ajustes nunca altera lo que el cliente firmó.
ALTER TABLE public.project_documentary_inputs
    ADD COLUMN IF NOT EXISTS doc_terms JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.project_documentary_inputs
    DROP CONSTRAINT IF EXISTS quote_doc_terms_shape,
    ADD CONSTRAINT quote_doc_terms_shape
        CHECK (public.doc_terms_is_valid(doc_terms));
