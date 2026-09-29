-- Phase-04: parameter evidence registry.
--
-- Every catalog authority row already carries the provenance triple
-- (data_provenance / technical_reviewed_* / review_pending). What it lacks
-- is WHERE the number came from: the datasheet, the page, the scope and the
-- applicability condition the mandate requires reviewers to see.
--
-- This table is per-parameter evidence: one row binds (authority_table,
-- row_id, field_name) to a source document+page, a declared value+unit as
-- stated in the source, a scope and a review state. Members may DECLARE
-- evidence (that's documentation, not approval) — review_state transitions
-- are stamped server-side only and writes route through the catalog API,
-- which runs under catalog_backend.

BEGIN;

CREATE TABLE public.catalog_parameter_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    -- The catalog row this evidence attests (no FK: it points at several
    -- authority tables; existence is enforced by the API layer).
    authority_table TEXT NOT NULL CHECK (authority_table IN (
        'profile_systems', 'profile_articles', 'glazing_bead_matrix',
        'hardware_kits', 'infill_articles',
        'manufacturing_placement_policies', 'handle_requirement_policies',
        'reinforcement_cut_policies', 'glass_purchase_mappings',
        'fitting_purchase_mappings', 'catalog_imports')),
    row_id UUID NOT NULL,
    field_name TEXT NOT NULL,
    -- The value exactly as the source states it (may differ in unit from the
    -- stored canonical value — that's the point of recording it).
    value_text TEXT,
    unit TEXT CHECK (unit IS NULL OR unit IN (
        'mm', 'mm2', 'm', 'kg', 'kg/m', 'kg/m2',
        'unit', 'set', 'percent', 'currency', 'text')),
    scope TEXT NOT NULL DEFAULT 'SYSTEM'
        CHECK (scope IN ('SYSTEM', 'SERIES', 'GLOBAL', 'ORG')),
    -- Applicability condition in words ("solo vidrio ≤ 24 mm", "hojas
    -- practicables"). Never machine-enforced — shown to reviewers.
    applicability TEXT,
    source_document TEXT NOT NULL,
    source_page INTEGER CHECK (source_page IS NULL OR source_page > 0),
    -- Display-only reference. The backend never fetches arbitrary URLs from
    -- documents; this field exists so a reviewer can consult the original.
    source_url TEXT CHECK (source_url IS NULL OR source_url ~* '^https?://'),
    declared_by UUID NOT NULL,
    declared_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    review_state TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (review_state IN ('PENDING', 'REVIEWED', 'REJECTED')),
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    -- A review stamp must carry both reviewer and timestamp; a pending row
    -- must carry neither (no half-stamps).
    CHECK ((review_state = 'PENDING') = (reviewed_by IS NULL AND reviewed_at IS NULL))
);

-- One attestation per (row, field, source page) — re-importing the same
-- document re-declares nothing.
CREATE UNIQUE INDEX catalog_parameter_evidence_dedupe
    ON public.catalog_parameter_evidence
    (authority_table, row_id, field_name, source_document,
     COALESCE(source_page, 0));

CREATE INDEX idx_catalog_parameter_evidence_row
    ON public.catalog_parameter_evidence (authority_table, row_id);
CREATE INDEX idx_catalog_parameter_evidence_org
    ON public.catalog_parameter_evidence (org_id);

ALTER TABLE public.catalog_parameter_evidence ENABLE ROW LEVEL SECURITY;

-- Members read their org's evidence plus platform-global rows.
CREATE POLICY catalog_parameter_evidence_select ON public.catalog_parameter_evidence
    FOR SELECT TO authenticated
    USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

-- No member-side writes at all: declaration, edit and review happen through
-- the catalog API (catalog_backend), which stamps actor identity itself.
CREATE POLICY catalog_parameter_evidence_backend_write ON public.catalog_parameter_evidence
    FOR ALL TO catalog_backend
    USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
    WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

REVOKE ALL ON public.catalog_parameter_evidence FROM anon;
-- Supabase default privileges hand authenticated every DML on new tables;
-- peel them back so SELECT is the only member grant.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.catalog_parameter_evidence FROM authenticated;
GRANT SELECT ON public.catalog_parameter_evidence TO authenticated;
GRANT ALL ON public.catalog_parameter_evidence TO catalog_backend;
GRANT ALL ON public.catalog_parameter_evidence TO service_role;

COMMIT;
