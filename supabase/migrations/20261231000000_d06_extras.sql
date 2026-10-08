-- D06 — accesorios y servicios de verdad.
--
-- extra_articles is the catalogued accessory surface of a profile system:
-- vierteaguas/alféizar (cut length = bottom run + declared vuelos),
-- ensanches and tapajuntas (cut per declared exterior side), and counted
-- extras (mosquitero, aireador) emitted per operable leaf. The article
-- carries the sell price and cost — the engine derives quantity, subline,
-- BOM pieces and cuts; the catalog stores declared data only.
--
-- service_articles + project_service_selections are the project-level
-- services (instalación, sellado, retiro, andamio, flete): the article
-- declares the qty rule (per position, per m², per perimeter-ml, fixed)
-- and the price; the engine derives quantity off the quoted positions.
--
-- org_extra_templates / org_service_templates are the org defaults
-- preselected into new positions/projects (configurable in Ajustes).
-- tenancy_organizations.extras_display is the documentary policy:
-- whether position sublines print itemised or grouped.

BEGIN;

-- Cut-kind extras saw real members: the finishing roles the engine's
-- ProfileRole enum already names must exist on the catalog side too —
-- extra cuts carry them into the cut plan and the OT BOM.
ALTER TYPE public.profile_role ADD VALUE IF NOT EXISTS 'SILL';
ALTER TYPE public.profile_role ADD VALUE IF NOT EXISTS 'FRAME_EXTENSION';
ALTER TYPE public.profile_role ADD VALUE IF NOT EXISTS 'COVER_TRIM';
ALTER TYPE public.profile_role ADD VALUE IF NOT EXISTS 'SKIRT';

-- ─── position extras (catalog per system) ─────────────────────────────────

CREATE TABLE public.extra_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    kind TEXT NOT NULL,
    pricing_unit TEXT NOT NULL,
    unit_price NUMERIC(14, 2),
    unit_price_currency VARCHAR(3) NOT NULL DEFAULT 'CLP',
    unit_cost NUMERIC(14, 2),
    unit_cost_currency VARCHAR(3),
    -- Cut kinds only: the catalog profile the extra saws (enters the cut
    -- plan and OT BOM as an EXTRA piece).
    cut_profile_sku VARCHAR(100),
    cut_material TEXT,
    -- SILL only: reveal added at each end of an uninterrupted bottom run.
    vuelo_default_mm NUMERIC(10, 2),
    -- Applicability predicates: empty = compatible everywhere. Also the
    -- suggestion scope — an article with suggestion_reason is offered on
    -- every qualifying position that has not selected it.
    families TEXT[] NOT NULL DEFAULT '{}',
    unit_kinds TEXT[] NOT NULL DEFAULT '{}',
    suggestion_reason TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_extra_articles_kind CHECK (
        kind IN ('SILL', 'FRAME_EXTENSION', 'COVER_TRIM',
                 'MOSQUITO_SCREEN', 'VENTILATOR')),
    CONSTRAINT chk_extra_articles_unit CHECK (pricing_unit IN ('M', 'EA')),
    CONSTRAINT chk_extra_articles_kind_unit CHECK (
        (kind IN ('SILL', 'FRAME_EXTENSION', 'COVER_TRIM') AND pricing_unit = 'M')
        OR (kind IN ('MOSQUITO_SCREEN', 'VENTILATOR') AND pricing_unit = 'EA')),
    CONSTRAINT chk_extra_articles_cut CHECK (
        (kind IN ('SILL', 'FRAME_EXTENSION', 'COVER_TRIM')
            AND cut_profile_sku IS NOT NULL AND cut_material IS NOT NULL)
        OR (kind IN ('MOSQUITO_SCREEN', 'VENTILATOR')
            AND cut_profile_sku IS NULL AND cut_material IS NULL)),
    CONSTRAINT chk_extra_articles_vuelo CHECK (
        vuelo_default_mm IS NULL
        OR (kind = 'SILL' AND vuelo_default_mm >= 0.00)),
    CONSTRAINT chk_extra_articles_predicates CHECK (
        families <@ ARRAY['CASEMENT', 'SLIDING', 'LIFT_SLIDE', 'DOOR', 'FACADE_FIXED']::text[]
        AND unit_kinds <@ ARRAY['WINDOW', 'DOOR']::text[]),
    CONSTRAINT chk_extra_articles_fields CHECK (
        length(btrim(sku)) > 0 AND length(btrim(name)) > 0
        AND (unit_price IS NULL OR unit_price >= 0.00)
        AND (unit_cost IS NULL OR unit_cost >= 0.00)
        AND (unit_price_currency IS NULL OR length(btrim(unit_price_currency)) = 3)
        AND (unit_cost IS NULL OR unit_cost_currency IS NOT NULL)
        AND (suggestion_reason IS NULL OR length(btrim(suggestion_reason)) > 0)),
    CONSTRAINT chk_extra_articles_no_nan CHECK (
        (unit_price IS NULL OR unit_price <> 'NaN'::numeric)
        AND (unit_cost IS NULL OR unit_cost <> 'NaN'::numeric)
        AND (vuelo_default_mm IS NULL OR vuelo_default_mm <> 'NaN'::numeric)),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, sku),
    UNIQUE (id, system_id)
);

ALTER TABLE public.extra_articles ENABLE ROW LEVEL SECURITY;

CREATE POLICY extra_articles_read
ON public.extra_articles FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY extra_articles_backend_write
ON public.extra_articles FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

-- ─── project services (org catalog) ───────────────────────────────────────

CREATE TABLE public.service_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    kind TEXT NOT NULL,
    qty_rule TEXT NOT NULL,
    unit_price NUMERIC(14, 2),
    unit_price_currency VARCHAR(3) NOT NULL DEFAULT 'CLP',
    unit_cost NUMERIC(14, 2),
    unit_cost_currency VARCHAR(3),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_service_articles_kind CHECK (
        kind IN ('INSTALLATION', 'SEALING', 'REMOVAL', 'SCAFFOLDING', 'FREIGHT')),
    CONSTRAINT chk_service_articles_qty_rule CHECK (
        qty_rule IN ('PER_POSITION_UNIT', 'PER_M2', 'PER_LINEAR_METER', 'FIXED')),
    CONSTRAINT chk_service_articles_fields CHECK (
        length(btrim(code)) > 0 AND length(btrim(name)) > 0
        AND (unit_price IS NULL OR unit_price >= 0.00)
        AND (unit_cost IS NULL OR unit_cost >= 0.00)
        AND (unit_price_currency IS NULL OR length(btrim(unit_price_currency)) = 3)
        AND (unit_cost IS NULL OR unit_cost_currency IS NOT NULL)),
    CONSTRAINT chk_service_articles_no_nan CHECK (
        (unit_price IS NULL OR unit_price <> 'NaN'::numeric)
        AND (unit_cost IS NULL OR unit_cost <> 'NaN'::numeric)),
    UNIQUE NULLS NOT DISTINCT (org_id, code)
);

ALTER TABLE public.service_articles ENABLE ROW LEVEL SECURITY;

CREATE POLICY service_articles_read
ON public.service_articles FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY service_articles_backend_write
ON public.service_articles FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

-- ─── selections + org templates (tenant rows) ─────────────────────────────

CREATE TABLE public.project_service_selections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    service_article_id UUID NOT NULL REFERENCES public.service_articles(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, service_article_id)
);

ALTER TABLE public.project_service_selections ENABLE ROW LEVEL SECURITY;

-- Reads follow the project read surface (workshop sees the BOM); writes
-- stay with the estimators — the same split project_positions uses.
CREATE POLICY project_service_selections_read
ON public.project_service_selections FOR SELECT TO authenticated, documentary_backend
USING (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR','WORKSHOP_MANAGER']));
CREATE POLICY project_service_selections_write
ON public.project_service_selections FOR ALL TO authenticated
USING (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR']))
WITH CHECK (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR']));

CREATE TABLE public.org_extra_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    extra_article_id UUID NOT NULL REFERENCES public.extra_articles(id) ON DELETE CASCADE,
    sides TEXT[] NOT NULL DEFAULT '{}',
    qty INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_org_extra_templates_fields CHECK (
        sides <@ ARRAY['left', 'right', 'top', 'bottom']::text[]
        AND (qty IS NULL OR qty >= 1)),
    UNIQUE (org_id, extra_article_id)
);

ALTER TABLE public.org_extra_templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_extra_templates_read
ON public.org_extra_templates FOR SELECT TO authenticated
USING (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR','WORKSHOP_MANAGER']));
CREATE POLICY org_extra_templates_write
ON public.org_extra_templates FOR ALL TO authenticated
USING (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR']))
WITH CHECK (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR']));

CREATE TABLE public.org_service_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    service_article_id UUID NOT NULL REFERENCES public.service_articles(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, service_article_id)
);

ALTER TABLE public.org_service_templates ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_service_templates_read
ON public.org_service_templates FOR SELECT TO authenticated
USING (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR','WORKSHOP_MANAGER']));
CREATE POLICY org_service_templates_write
ON public.org_service_templates FOR ALL TO authenticated
USING (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR']))
WITH CHECK (private.pricing_role(org_id, ARRAY['OWNER','ESTIMATOR']));

-- ─── documentary policy on the org row ────────────────────────────────────

ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS extras_display TEXT NOT NULL DEFAULT 'DETAILED';

ALTER TABLE public.tenancy_organizations
    DROP CONSTRAINT IF EXISTS chk_tenancy_extras_display;
ALTER TABLE public.tenancy_organizations
    ADD CONSTRAINT chk_tenancy_extras_display
        CHECK (extras_display IN ('DETAILED', 'GROUPED'));

-- Same authority as the branding fields: the documentary backend writes
-- org display policy through the existing OWNER/ESTIMATOR update policy.
GRANT UPDATE (extras_display)
    ON public.tenancy_organizations TO documentary_backend;

-- ─── guards + grants ──────────────────────────────────────────────────────

-- extra_articles joins the catalog tables: manual-write coherence plus the
-- locked-catalog freeze authority (system_id NOT NULL keeps the shared
-- parent check meaningful).
DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['extra_articles']
    LOOP
        EXECUTE format(
            'CREATE TRIGGER catalog_guard BEFORE INSERT OR UPDATE ON public.%I
             FOR EACH ROW EXECUTE FUNCTION private.guard_manual_catalog()',
            table_name
        );
        EXECUTE format(
            'CREATE TRIGGER guard_referenced_catalog BEFORE INSERT OR UPDATE OR DELETE
             ON public.%I FOR EACH ROW EXECUTE FUNCTION private.guard_referenced_catalog()',
            table_name
        );
    END LOOP;
END;
$$;

-- service_articles is org data without a system parent — the catalog
-- freeze authority does not apply, only the read/write split.

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'extra_articles',
        'service_articles'
    ] LOOP
        EXECUTE format(
            'REVOKE ALL ON public.%I FROM anon', table_name);
        EXECUTE format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
            'ON public.%I FROM authenticated', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO authenticated', table_name);
        EXECUTE format(
            'GRANT ALL ON public.%I TO catalog_backend', table_name);
        EXECUTE format(
            'GRANT ALL ON public.%I TO service_role', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO pricing_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO documentary_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO ai_backend', table_name);
    END LOOP;
    FOREACH table_name IN ARRAY ARRAY[
        'project_service_selections',
        'org_extra_templates',
        'org_service_templates'
    ] LOOP
        EXECUTE format(
            'REVOKE ALL ON public.%I FROM anon', table_name);
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO authenticated', table_name);
        EXECUTE format(
            'GRANT ALL ON public.%I TO service_role', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO pricing_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO documentary_backend', table_name);
    END LOOP;
END;
$$;

COMMENT ON TABLE public.extra_articles IS
    'D06 catalogued position accessory per system: vierteaguas, ensanche, tapajunta, mosquitero, aireador — declared price/cost, cut profile and applicability predicates.';
COMMENT ON TABLE public.service_articles IS
    'D06 catalogued project service: instalación, sellado, retiro, andamio, flete — declared qty rule and price; engine derives quantity off quoted positions.';
COMMENT ON TABLE public.project_service_selections IS
    'D06 services selected on a project — ride the commercial totals undiscounted-but-taxed.';
COMMENT ON TABLE public.org_extra_templates IS
    'D06 org default extras preselected into every new position (e.g. instalación estándar).';
COMMENT ON TABLE public.org_service_templates IS
    'D06 org default services preselected into every new project.';
COMMENT ON COLUMN public.tenancy_organizations.extras_display IS
    'D06 documentary policy: DETAILED prints position sublines with prices, GROUPED folds them into the position price.';

COMMIT;
