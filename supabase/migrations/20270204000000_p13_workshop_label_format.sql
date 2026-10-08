-- P13 — Formato de etiquetas de pieza por organización: la hoja de
-- etiquetas del pack de corte se imprime en grilla sobre el papel
-- documental de la org (LETTER/LEGAL/A4 vía doc_paper_size) o en rollo
-- térmico de 100×50 mm para etiquetadoras de taller.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS workshop_label_format TEXT NOT NULL DEFAULT 'GRID'
        CONSTRAINT workshop_label_format_values
        CHECK (workshop_label_format IN ('GRID', 'THERMAL_100X50'));

-- Misma superficie de escritura que doc_paper_size/doc_terms: columna-grant
-- al backend documental; la política de tabla ya cubre la fila.
GRANT UPDATE (workshop_label_format)
    ON public.tenancy_organizations TO documentary_backend;
