-- D02: structured glass — supplier products, surcharges, safety rules and
-- dimensional limits as org-editable data, plus the resolved composition
-- snapshot on each position. No normative table text is invented here: the
-- seeded rows are synthetic examples pending technical review (D01 ingest
-- carries the official tables when the owner uploads them).

BEGIN;

CREATE TABLE public.glass_products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    -- NULL = the product is offered on every system; a system-scoped row
    -- overrides the cross-system row for the same SKU (DISTINCT ON +
    -- system_id NULLS LAST, same resolution as the purchase mappings).
    system_id UUID REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    sku TEXT NOT NULL CHECK (length(btrim(sku)) > 0),
    commercial_name TEXT NOT NULL CHECK (length(btrim(commercial_name)) > 0),
    -- Canonical round-trip notation (engine formatter output); the
    -- composition JSONB is the parsed layer stack, exterior → interior.
    notation TEXT NOT NULL CHECK (length(btrim(notation)) > 0),
    -- NULL composition = UNKNOWN product (notation never parsed): stays
    -- selectable, every derived number reports unknown, review_pending=TRUE.
    composition JSONB CHECK (
        composition IS NULL OR jsonb_typeof(composition) = 'object'),
    total_thickness_mm NUMERIC(8, 2) CHECK (total_thickness_mm IS NULL OR total_thickness_mm > 0.00),
    -- Supplier-declared data only — never computed. NULL stays NULL.
    safety_class TEXT CHECK (safety_class IS NULL OR safety_class IN ('A', 'B', 'C')),
    ug_w_m2k NUMERIC(6, 3) CHECK (ug_w_m2k IS NULL OR ug_w_m2k > 0),
    g_value NUMERIC(4, 3) CHECK (g_value IS NULL OR (g_value >= 0.000 AND g_value <= 1.000)),
    light_transmission_pct NUMERIC(5, 2)
        CHECK (light_transmission_pct IS NULL
               OR (light_transmission_pct >= 0.00 AND light_transmission_pct <= 100.00)),
    weight_kg_m2 NUMERIC(8, 3) CHECK (weight_kg_m2 IS NULL OR weight_kg_m2 > 0),
    min_billable_area_m2 NUMERIC(10, 4)
        CHECK (min_billable_area_m2 IS NULL OR min_billable_area_m2 >= 0),
    -- Declared relative-price band (1 cheapest … 5 most expensive) for the
    -- selector's comparability signal. Declared catalog data — the real
    -- money never leaves the cost lists. NULL = not declared.
    price_tier SMALLINT CHECK (price_tier IS NULL OR (price_tier >= 1 AND price_tier <= 5)),
    supplier_name TEXT,
    supplier_sku TEXT,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id, system_id, sku)
);
COMMENT ON TABLE public.glass_products IS
    'D02 supplier glass product: structured composition + declared specs. '
    'Money stays in the pricing cost lists — this table carries product data '
    'only (price_tier is a declared relative band, not a rate).';

CREATE TABLE public.glass_product_surcharges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_id UUID NOT NULL REFERENCES public.glass_products(id) ON DELETE CASCADE,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    kind TEXT NOT NULL CHECK (kind IN ('TEMPERED', 'EDGE_POLISH', 'DRILL', 'PALILLAJE')),
    unit TEXT NOT NULL CHECK (unit IN ('M2', 'M', 'EA', 'CROSS')),
    unit_cost NUMERIC(14, 4) NOT NULL CHECK (unit_cost >= 0),
    currency public.currency_code NOT NULL DEFAULT 'CLP',
    label TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id, product_id, kind, unit)
);
COMMENT ON TABLE public.glass_product_surcharges IS
    'D02 priced extras a glass product supports (tempering, polished edges, '
    'drills, georgian-bar grids). The piece declares the selection; the rate '
    'lives here.';

CREATE TABLE public.glass_safety_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code TEXT NOT NULL CHECK (length(btrim(code)) > 0),
    title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
    message TEXT,
    applies_openings TEXT[] CHECK (applies_openings IS NULL OR cardinality(applies_openings) > 0),
    sill_below_mm NUMERIC(8, 2) CHECK (sill_below_mm IS NULL OR sill_below_mm >= 0),
    min_area_m2 NUMERIC(10, 4) CHECK (min_area_m2 IS NULL OR min_area_m2 >= 0),
    requires_door BOOLEAN,
    requires_adjacent_door BOOLEAN,
    required_safety TEXT NOT NULL
        CHECK (required_safety IN ('TEMPERED', 'LAMINATED', 'SAFETY_GLASS',
                                   'SAFETY_CLASS_A', 'SAFETY_CLASS_B', 'SAFETY_CLASS_C')),
    severity TEXT NOT NULL DEFAULT 'WARNING' CHECK (severity IN ('WARNING', 'MANDATORY')),
    source_ref TEXT,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id, code)
);
COMMENT ON TABLE public.glass_safety_rules IS
    'D02 situational glazing-safety rules (NCh 135/2 family): WARNING advises, '
    'MANDATORY only if the org sets it. Normative table text is loaded via '
    'catalog ingest, not invented.';

CREATE TABLE public.glass_type_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code TEXT NOT NULL CHECK (length(btrim(code)) > 0),
    lamina_kind TEXT NOT NULL DEFAULT 'ANY'
        CHECK (lamina_kind IN ('ANY', 'FLOAT', 'TINTED', 'TEMPERED',
                               'HEAT_STRENGTHENED', 'LAMINATED', 'LOW_E',
                               'SOLAR_CONTROL', 'REFLECTIVE', 'MIRROR',
                               'SATIN', 'PRINTED')),
    thickness_min_mm NUMERIC(8, 2) CHECK (thickness_min_mm IS NULL OR thickness_min_mm > 0),
    thickness_max_mm NUMERIC(8, 2) CHECK (thickness_max_mm IS NULL OR thickness_max_mm > 0),
    min_side_mm NUMERIC(8, 2) CHECK (min_side_mm IS NULL OR min_side_mm > 0),
    max_side_mm NUMERIC(8, 2) CHECK (max_side_mm IS NULL OR max_side_mm > 0),
    min_area_m2 NUMERIC(10, 4) CHECK (min_area_m2 IS NULL OR min_area_m2 >= 0),
    max_area_m2 NUMERIC(10, 4) CHECK (max_area_m2 IS NULL OR max_area_m2 > 0),
    max_aspect_ratio NUMERIC(8, 3) CHECK (max_aspect_ratio IS NULL OR max_aspect_ratio > 0),
    -- Tempered glass is never trimmed on site: the order asks for the exact
    -- cut measure the engine derived.
    requires_exact_cut BOOLEAN NOT NULL DEFAULT FALSE,
    severity TEXT NOT NULL DEFAULT 'WARNING' CHECK (severity IN ('WARNING', 'MANDATORY')),
    source_ref TEXT,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (thickness_min_mm IS NULL OR thickness_max_mm IS NULL
           OR thickness_min_mm <= thickness_max_mm),
    CHECK (min_side_mm IS NULL OR max_side_mm IS NULL
           OR min_side_mm <= max_side_mm),
    CHECK (min_area_m2 IS NULL OR max_area_m2 IS NULL
           OR min_area_m2 <= max_area_m2),
    UNIQUE NULLS NOT DISTINCT (org_id, code)
);
COMMENT ON TABLE public.glass_type_limits IS
    'D02 manufacturing bounds per lamina kind + thickness band (supplier '
    'data): side/area/aspect envelopes and the exact-cut flag.';

ALTER TABLE public.glass_products ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.glass_product_surcharges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.glass_safety_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.glass_type_limits ENABLE ROW LEVEL SECURITY;

CREATE POLICY glass_products_read
ON public.glass_products FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY glass_product_surcharges_read
ON public.glass_product_surcharges FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY glass_safety_rules_read
ON public.glass_safety_rules FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY glass_type_limits_read
ON public.glass_type_limits FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));

CREATE POLICY glass_products_backend_write
ON public.glass_products FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY glass_product_surcharges_backend_write
ON public.glass_product_surcharges FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY glass_safety_rules_backend_write
ON public.glass_safety_rules FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY glass_type_limits_backend_write
ON public.glass_type_limits FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'glass_products',
        'glass_product_surcharges',
        'glass_safety_rules',
        'glass_type_limits'
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
        -- Backend calculators read the declared data under their own
        -- roles: pricing resolves surcharges/min-area, documentary freezes
        -- product evidence, the AI layer reads the same catalog.
        EXECUTE format(
            'GRANT SELECT ON public.%I TO pricing_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO documentary_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO ai_backend', table_name);
    END LOOP;
END;
$$;

-- Resolved composition snapshot + review flag on each position. Every
-- pre-D02 row declares a free-text spec the parser may not honour, so the
-- migration marks them pending: the first evaluation through the engine
-- writes the structured composition back and clears the flag (parseable)
-- or leaves it set with a `{"status": "UNKNOWN"}` payload (not parseable).
ALTER TABLE public.project_positions
    ADD COLUMN glass_composition JSONB
        CHECK (glass_composition IS NULL OR jsonb_typeof(glass_composition) = 'object'),
    ADD COLUMN glass_review_pending BOOLEAN NOT NULL DEFAULT FALSE;
COMMENT ON COLUMN public.project_positions.glass_composition IS
    'D02 map "bay:leaf" → engine-resolved composition dict; unparseable '
    'declared specs keep {"status":"UNKNOWN","spec":<text>}.';
COMMENT ON COLUMN public.project_positions.glass_review_pending IS
    'D02 set when any declared glass_spec has no structured composition yet '
    '(parser could not resolve it or the row predates the model).';
UPDATE public.project_positions
SET glass_review_pending = TRUE
WHERE glass_spec IS NOT NULL AND btrim(glass_spec) <> '';

COMMIT;
