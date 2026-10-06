-- P09 — Ajustes de documento de la organización: papel y textos legales
-- white-label. doc_paper_size fija el tamaño @page de todos los documentos
-- emitidos (Carta por defecto, Oficio y A4 opcionales). doc_terms guarda
-- los párrafos legales declarados por la organización (plazo, instalación,
-- exclusiones, garantía y jurisdicción) que la propuesta comercial imprime
-- textualmente en su bloque de condiciones — vacío = la línea se omite.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS doc_paper_size TEXT NOT NULL DEFAULT 'LETTER'
        CONSTRAINT doc_paper_size_values
        CHECK (doc_paper_size IN ('LETTER', 'LEGAL', 'A4')),
    ADD COLUMN IF NOT EXISTS doc_terms JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Solo las claves declaradas y textos acotados entran: un JSONB libre es un
-- canal para inyectar contenido arbitrario en documentos firmados.
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
            'garantia', 'jurisdiccion'
        )
        OR jsonb_typeof(entry.val) <> 'string'
        OR length(entry.val #>> '{}') > 4000
    ) END
$$;

ALTER TABLE public.tenancy_organizations
    ADD CONSTRAINT doc_terms_shape CHECK (public.doc_terms_is_valid(doc_terms));

-- Escritura en la misma superficie que el resto de la marca documental:
-- documentary_backend con columna-grant + la política de rol ya existente
-- cubre la fila completa del UPDATE (las políticas son por tabla, no por
-- columna — el grant es lo que acota el alcance).
GRANT UPDATE (doc_paper_size, doc_terms)
    ON public.tenancy_organizations TO documentary_backend;
