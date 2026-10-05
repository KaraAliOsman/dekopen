-- D04 — herrajes de verdad.
--
-- hardware_kits rows are the classes inside a (system × opening) family;
-- this migration gives each class its label and the declared restrictions
-- beyond the envelope (slenderness, minimum height for a stay), adds the
-- family catalogue (handle height rule + models + colours) and the sellable
-- options table. Component JSONB gains the declared rules: qty_rule,
-- cut_rule, unit mass/cost and machining declarations.
--
-- Honesty contract: the catalog stores declared data only. Resolved
-- quantities/cut lengths live in the engine's emitted BOM, never here.

BEGIN;

-- ─── kits = classes ────────────────────────────────────────────────────────

ALTER TABLE public.hardware_kits
    ADD COLUMN class_label TEXT,
    ADD COLUMN max_aspect_ratio NUMERIC(6, 3),
    ADD COLUMN min_stay_height_mm NUMERIC(10, 2);

ALTER TABLE public.hardware_kits
    ADD CONSTRAINT chk_kits_class_bounds CHECK (
        (class_label IS NULL OR length(btrim(class_label)) > 0)
        AND (max_aspect_ratio IS NULL OR max_aspect_ratio > 0.00)
        AND (min_stay_height_mm IS NULL OR min_stay_height_mm > 0.00)
        AND (max_aspect_ratio IS NULL OR max_aspect_ratio <> 'NaN'::numeric)
        AND (min_stay_height_mm IS NULL OR min_stay_height_mm <> 'NaN'::numeric)
    );

-- ─── family catalogue + sellable options ───────────────────────────────────

CREATE TABLE public.hardware_families (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    opening_type TEXT NOT NULL,
    handle_height_rule TEXT,
    handle_height_min_mm NUMERIC(10, 2),
    handle_height_max_mm NUMERIC(10, 2),
    handle_height_default_mm NUMERIC(10, 2),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_families_opening_type CHECK (
        opening_type IN ('AWNING', 'DOOR', 'SLIDING', 'TILT_TURN', 'TURN')),
    CONSTRAINT chk_families_height_rule CHECK (
        handle_height_rule IS NULL
        OR handle_height_rule IN ('CENTERED', 'FIXED_FROM_BASE', 'RANGE')),
    CONSTRAINT chk_families_height_range CHECK (
        ((handle_height_min_mm IS NULL) = (handle_height_max_mm IS NULL))
        AND (handle_height_min_mm IS NULL OR handle_height_min_mm > 0.00)
        AND (handle_height_max_mm IS NULL OR handle_height_max_mm > 0.00)
        AND (handle_height_min_mm IS NULL
             OR handle_height_min_mm <= handle_height_max_mm)
        AND (handle_height_default_mm IS NULL OR handle_height_default_mm > 0.00)
        AND (handle_height_rule IS DISTINCT FROM 'FIXED_FROM_BASE'
             OR handle_height_default_mm IS NOT NULL)),
    CONSTRAINT chk_families_no_nan CHECK (
        (handle_height_min_mm IS NULL OR handle_height_min_mm <> 'NaN'::numeric)
        AND (handle_height_max_mm IS NULL OR handle_height_max_mm <> 'NaN'::numeric)
        AND (handle_height_default_mm IS NULL OR handle_height_default_mm <> 'NaN'::numeric)),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, opening_type),
    UNIQUE (id, system_id)
);

CREATE TABLE public.hardware_handle_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    opening_type TEXT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    kind TEXT NOT NULL,
    price_delta_clp NUMERIC(12, 2),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_handle_models_opening_type CHECK (
        opening_type IN ('AWNING', 'DOOR', 'SLIDING', 'TILT_TURN', 'TURN')),
    CONSTRAINT chk_handle_models_kind CHECK (
        kind IN ('STANDARD', 'LOCKABLE', 'BUTTON', 'DOOR_ESCUTCHEON')),
    CONSTRAINT chk_handle_models_fields CHECK (
        length(btrim(sku)) > 0 AND length(btrim(name)) > 0
        AND (price_delta_clp IS NULL OR price_delta_clp >= 0.00)),
    CONSTRAINT chk_handle_models_no_nan CHECK (
        price_delta_clp IS NULL OR price_delta_clp <> 'NaN'::numeric),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, opening_type, sku),
    UNIQUE (id, system_id)
);

CREATE TABLE public.hardware_handle_colors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    opening_type TEXT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    price_delta_clp NUMERIC(12, 2),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_handle_colors_opening_type CHECK (
        opening_type IN ('AWNING', 'DOOR', 'SLIDING', 'TILT_TURN', 'TURN')),
    CONSTRAINT chk_handle_colors_fields CHECK (
        length(btrim(sku)) > 0 AND length(btrim(name)) > 0
        AND (price_delta_clp IS NULL OR price_delta_clp >= 0.00)),
    CONSTRAINT chk_handle_colors_no_nan CHECK (
        price_delta_clp IS NULL OR price_delta_clp <> 'NaN'::numeric),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, opening_type, sku),
    UNIQUE (id, system_id)
);

CREATE TABLE public.hardware_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    opening_type TEXT NOT NULL,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    kind TEXT NOT NULL,
    price_delta_clp NUMERIC(12, 2),
    components JSONB NOT NULL DEFAULT '[]'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_options_opening_type CHECK (
        opening_type IN ('AWNING', 'DOOR', 'SLIDING', 'TILT_TURN', 'TURN')),
    CONSTRAINT chk_options_kind CHECK (
        kind IN ('SECURITY', 'OPENING_LIMITER', 'MICROVENTILATION', 'CONCEALED_HINGES')),
    CONSTRAINT chk_options_fields CHECK (
        length(btrim(sku)) > 0 AND length(btrim(name)) > 0
        AND (price_delta_clp IS NULL OR price_delta_clp >= 0.00)),
    CONSTRAINT chk_options_no_nan CHECK (
        price_delta_clp IS NULL OR price_delta_clp <> 'NaN'::numeric),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, opening_type, sku),
    UNIQUE (id, system_id)
);

ALTER TABLE public.hardware_families ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hardware_handle_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hardware_handle_colors ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.hardware_options ENABLE ROW LEVEL SECURITY;

CREATE POLICY hardware_families_read
ON public.hardware_families FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY hardware_handle_models_read
ON public.hardware_handle_models FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY hardware_handle_colors_read
ON public.hardware_handle_colors FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY hardware_options_read
ON public.hardware_options FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));

CREATE POLICY hardware_families_backend_write
ON public.hardware_families FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY hardware_handle_models_backend_write
ON public.hardware_handle_models FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY hardware_handle_colors_backend_write
ON public.hardware_handle_colors FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY hardware_options_backend_write
ON public.hardware_options FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'hardware_families',
        'hardware_handle_models',
        'hardware_handle_colors',
        'hardware_options'
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
END;
$$;

-- ─── component JSONB authority ─────────────────────────────────────────────
--
-- One validator for kit contents and option components: a catalog line is
-- declared data — sku/name/unit plus either a fixed qty or a declared
-- qty_rule; optional cut_rule, unit mass/cost, category and machining
-- declarations. Resolved fields (length_mm, option_sku, emitted qty) are
-- NOT writable here — they belong to the engine's emitted BOM.

CREATE OR REPLACE FUNCTION private.validate_hardware_components(doc JSONB)
RETURNS VOID
LANGUAGE plpgsql
IMMUTABLE
SET search_path = ''
AS $$
DECLARE
    component JSONB;
    rule JSONB;
    machining JSONB;
    quantity NUMERIC;
BEGIN
    IF doc IS NULL THEN
        RETURN;
    END IF;
    IF jsonb_typeof(doc) IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'catalog_contents_invalid' USING ERRCODE = '23514';
    END IF;
    FOR component IN SELECT value FROM jsonb_array_elements(doc)
    LOOP
        IF jsonb_typeof(component) IS DISTINCT FROM 'object'
           OR NOT (component ?& ARRAY['sku', 'name', 'unit'])
           OR component - ARRAY[
               'sku', 'name', 'qty', 'unit', 'category',
               'qty_rule', 'cut_rule', 'weight_kg', 'cost_clp', 'machining'
           ] <> '{}'::jsonb
           OR jsonb_typeof(component -> 'sku') IS DISTINCT FROM 'string'
           OR jsonb_typeof(component -> 'name') IS DISTINCT FROM 'string'
           OR jsonb_typeof(component -> 'unit') IS DISTINCT FROM 'string'
           OR btrim(component ->> 'sku') = ''
           OR btrim(component ->> 'name') = ''
           OR btrim(component ->> 'unit') = ''
           OR NOT (component ? 'qty' OR component ? 'qty_rule') THEN
            RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
        END IF;
        IF component ? 'qty' THEN
            IF jsonb_typeof(component -> 'qty') IS DISTINCT FROM 'number' THEN
                RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
            END IF;
            quantity := (component ->> 'qty')::numeric;
            -- Numeric NaN compares equal to 'NaN'::numeric.
            IF quantity IS NULL OR quantity <= 0 OR quantity = 'NaN'::numeric THEN
                RAISE EXCEPTION 'catalog_quantity_invalid' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF component ? 'qty_rule' THEN
            rule := component -> 'qty_rule';
            IF jsonb_typeof(rule) IS DISTINCT FROM 'object'
               OR NOT (rule ?& ARRAY['kind', 'per_mm'])
               OR rule - ARRAY['kind', 'per_mm', 'min_qty', 'max_qty'] <> '{}'::jsonb
               OR (rule ->> 'kind') NOT IN ('PER_WIDTH', 'PER_HEIGHT')
               OR jsonb_typeof(rule -> 'per_mm') IS DISTINCT FROM 'number'
               OR (rule ->> 'per_mm')::numeric <= 0
               OR (rule ->> 'per_mm')::numeric = 'NaN'::numeric
               OR (rule ? 'min_qty'
                   AND (jsonb_typeof(rule -> 'min_qty') IS DISTINCT FROM 'number'
                        OR (rule ->> 'min_qty')::numeric < 1
                        OR (rule ->> 'min_qty')::numeric
                           <> floor((rule ->> 'min_qty')::numeric)))
               OR (rule ? 'max_qty'
                   AND (jsonb_typeof(rule -> 'max_qty') IS DISTINCT FROM 'number'
                        OR (rule ->> 'max_qty')::numeric < 1
                        OR (rule ->> 'max_qty')::numeric
                           <> floor((rule ->> 'max_qty')::numeric)))
               OR ((rule ? 'min_qty') AND (rule ? 'max_qty')
                   AND (rule ->> 'max_qty')::numeric < (rule ->> 'min_qty')::numeric) THEN
                RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF component ? 'cut_rule' THEN
            rule := component -> 'cut_rule';
            IF jsonb_typeof(rule) IS DISTINCT FROM 'object'
               OR NOT (rule ?& ARRAY['axis', 'minus_mm'])
               OR rule - ARRAY['axis', 'minus_mm'] <> '{}'::jsonb
               OR (rule ->> 'axis') NOT IN ('WIDTH', 'HEIGHT')
               OR jsonb_typeof(rule -> 'minus_mm') IS DISTINCT FROM 'number'
               OR (rule ->> 'minus_mm')::numeric < 0
               OR (rule ->> 'minus_mm')::numeric = 'NaN'::numeric THEN
                RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF component ? 'weight_kg'
           AND (jsonb_typeof(component -> 'weight_kg') IS DISTINCT FROM 'number'
                OR (component ->> 'weight_kg')::numeric < 0
                OR (component ->> 'weight_kg')::numeric = 'NaN'::numeric) THEN
            RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
        END IF;
        IF component ? 'cost_clp'
           AND (jsonb_typeof(component -> 'cost_clp') IS DISTINCT FROM 'number'
                OR (component ->> 'cost_clp')::numeric < 0
                OR (component ->> 'cost_clp')::numeric = 'NaN'::numeric) THEN
            RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
        END IF;
        IF component ? 'category'
           AND (component ->> 'category')
               NOT IN ('LOCK', 'HINGE', 'HANDLE', 'ROLLER', 'FITTING', 'OTHER') THEN
            RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
        END IF;
        IF component ? 'machining' THEN
            IF jsonb_typeof(component -> 'machining') IS DISTINCT FROM 'array' THEN
                RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
            END IF;
            FOR machining IN
                SELECT value FROM jsonb_array_elements(component -> 'machining')
            LOOP
                IF jsonb_typeof(machining) IS DISTINCT FROM 'object'
                   OR NOT (machining ? 'kind')
                   OR machining - ARRAY['kind', 'side', 'u_mm', 'y_mm', 'note']
                      <> '{}'::jsonb
                   OR (machining ->> 'kind') NOT IN (
                       'LOCK_PREP', 'HINGE_PREP', 'ESPAG_HOUSING',
                       'DRAINAGE', 'OTHER')
                   OR (machining ? 'u_mm'
                       AND (jsonb_typeof(machining -> 'u_mm') IS DISTINCT FROM 'number'
                            OR (machining ->> 'u_mm')::numeric < 0
                            OR (machining ->> 'u_mm')::numeric = 'NaN'::numeric))
                   OR (machining ? 'y_mm'
                       AND (jsonb_typeof(machining -> 'y_mm') IS DISTINCT FROM 'number'
                            OR (machining ->> 'y_mm')::numeric = 'NaN'::numeric)) THEN
                    RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
                END IF;
            END LOOP;
        END IF;
    END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION private.validate_hardware_components(JSONB) FROM PUBLIC;
-- The manual-write guard invokes it inside the trigger, so every role that
-- can write a guarded table needs EXECUTE; the shape error must surface as
-- 23514, not a nested 42501.
GRANT EXECUTE ON FUNCTION private.validate_hardware_components(JSONB)
    TO authenticated, catalog_backend, service_role;

-- The manual-write guard delegates kit contents and option components to
-- the shared validator; everything else keeps its existing checks.
CREATE OR REPLACE FUNCTION private.guard_manual_catalog()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    parent_org UUID;
    parent_global BOOLEAN;
    bead_org UUID;
BEGIN
    -- Privileged fixture/maintenance paths retain their existing authority.
    -- Every direct authenticated write, including PostgREST, passes here.
    IF current_user <> 'authenticated' THEN
        RETURN NEW;
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.id IS DISTINCT FROM OLD.id
           OR NEW.org_id IS DISTINCT FROM OLD.org_id THEN
            RAISE EXCEPTION 'catalog_identity_immutable' USING ERRCODE = '23514';
        END IF;
        IF TG_TABLE_NAME <> 'profile_systems' THEN
            IF NEW.system_id IS DISTINCT FROM OLD.system_id THEN
                RAISE EXCEPTION 'catalog_parent_immutable' USING ERRCODE = '23514';
            END IF;
        END IF;
    END IF;

    IF TG_TABLE_NAME = 'profile_systems' THEN
        RETURN NEW;
    END IF;

    IF NEW.system_id IS NOT NULL THEN
    SELECT org_id, is_global INTO parent_org, parent_global
    FROM public.profile_systems
    WHERE id = NEW.system_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'catalog_parent_invalid' USING ERRCODE = '23514';
    END IF;

    IF NOT (
        (parent_org IS NULL AND parent_global)
        OR (
            NEW.org_id IS NOT NULL
            AND parent_org IS NOT DISTINCT FROM NEW.org_id
        )
    ) THEN
        RAISE EXCEPTION 'catalog_parent_invalid' USING ERRCODE = '23514';
    END IF;
    -- Authenticated callers cannot edit global references. Lock only tenant
    -- references through the caller's existing UPDATE policy.
    IF parent_org IS NOT NULL THEN
        PERFORM id FROM public.profile_systems
        WHERE id = NEW.system_id AND org_id = NEW.org_id
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'catalog_parent_invalid' USING ERRCODE = '23514';
        END IF;
    END IF;
ELSIF TG_TABLE_NAME <> 'hardware_kits' THEN
    RAISE EXCEPTION 'catalog_parent_required' USING ERRCODE = '23514';
END IF;

    IF TG_TABLE_NAME = 'glazing_bead_matrix' THEN
    SELECT org_id INTO bead_org
    FROM public.profile_articles
    WHERE id = NEW.bead_article_id
      AND system_id = NEW.system_id
      AND role = 'GLAZING_BEAD'
      AND (
          org_id = NEW.org_id
          OR (
              org_id IS NULL
              AND parent_org IS NULL
              AND parent_global
          )
      );

    IF NOT FOUND THEN
        RAISE EXCEPTION 'catalog_bead_invalid' USING ERRCODE = '23514';
    END IF;
    IF bead_org IS NOT NULL THEN
        PERFORM id FROM public.profile_articles
        WHERE id = NEW.bead_article_id AND system_id = NEW.system_id
          AND org_id = NEW.org_id AND role = 'GLAZING_BEAD'
        FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'catalog_bead_invalid' USING ERRCODE = '23514';
        END IF;
    END IF;
END IF;

    IF TG_TABLE_NAME = 'profile_articles' AND TG_OP = 'UPDATE' THEN
        IF NEW.role <> 'GLAZING_BEAD' AND EXISTS (
            SELECT 1 FROM public.glazing_bead_matrix
            WHERE bead_article_id = NEW.id
        ) THEN
            RAISE EXCEPTION 'catalog_bead_in_use' USING ERRCODE = '23514';
        END IF;
    END IF;

    -- D04: kit contents and option components share the declared-component
    -- contract (qty or qty_rule, cut rules, masses, machining). Resolved
    -- fields stay unwritable — catalog stores declared data only.
    IF TG_TABLE_NAME = 'hardware_kits' THEN
        PERFORM private.validate_hardware_components(NEW.contents);
    ELSIF TG_TABLE_NAME = 'hardware_options' THEN
        PERFORM private.validate_hardware_components(NEW.components);
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.guard_manual_catalog() FROM PUBLIC;

-- Same guard coverage as the other catalog authority tables: manual-write
-- coherence plus the locked-catalog freeze authority.
DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'hardware_families', 'hardware_handle_models',
        'hardware_handle_colors', 'hardware_options'
    ]
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

COMMENT ON TABLE public.hardware_families IS
    'D04 hardware family per system x opening: declared handle-height rule and editable range.';
COMMENT ON TABLE public.hardware_handle_models IS
    'D04 sellable handle models per family (estandar, con llave, con boton, puerta con escudo).';
COMMENT ON TABLE public.hardware_handle_colors IS
    'D04 sellable handle colours per family, with declared price deltas.';
COMMENT ON TABLE public.hardware_options IS
    'D04 sellable hardware options per family (security, opening limiter, microventilation, concealed hinges) with price delta and component BOM.';

COMMIT;
