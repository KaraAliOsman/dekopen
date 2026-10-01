-- Catalog-domain hostile review hardening (review-catalog.md).
--
-- CAT-01  Provenance columns were member-writable: the provenance triple is
--         the audit spine but any catalog-managing member could stamp it via
--         direct PostgREST writes. Postgres column privileges are additive —
--         excluding columns requires dropping the table-level INSERT/UPDATE
--         grants and re-granting column-wise over the member-writable set
--         (the catalog write serializers' fields). Backend writes that stamp
--         provenance run under the new `catalog_backend` role.
-- CAT-02  Re-open bookkeeping lived only in catalog service.update(); a
--         direct PostgREST technical edit of a reviewed row stayed "reviewed".
--         A BEFORE UPDATE trigger now performs the same bookkeeping for
--         member-side writes (the API's own writes keep doing it in service).
-- CAT-09b glazing_bead_matrix had no provenance columns at all — bead-width /
--         gasket edits never entered the review queue. The table gains the
--         same triple; guard_referenced_catalog's provenance exemption covers
--         it automatically (same strip-list).
-- CAT-11  catalog_imports_member_update let a member rewrite status/
--         candidates/result post-hoc — the audit record could lie about what
--         was confirmed. Members keep INSERT (upload) and SELECT only.
-- CAT-12  Postgres numeric/jsonb admit NaN: guard_manual_catalog's `qty <= 0`
--         check is NULL under NaN, and any NaN numeric column bricks
--         load_visible for the whole system at read time. Writes are now
--         rejected instead: NaN checks in the guard for jsonb payloads plus
--         `col = col` CHECK constraints on every numeric catalog column.
-- CAT-15  Unbound hardware kits (system_id IS NULL) had no uniqueness —
--         uk_kit_system_sku does not conflict on NULL. A partial index dedupes
--         them per org. opening_type/rail_type were free VARCHARs while
--         load_visible enum-coerces rail_type — a junk value made a system
--         unreadable; both are CHECK-constrained to the engine enums now.
--
-- Member-visible surface is unchanged: full SELECT, DELETE, and writes to the
-- same columns the UI could always write. The API's catalog service runs its
-- writes under catalog_backend so its provenance bookkeeping still works.

BEGIN;

-- ─── Role ─────────────────────────────────────────────────────────────────
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'catalog_backend') THEN
        CREATE ROLE catalog_backend NOLOGIN NOSUPERUSER NOBYPASSRLS
            NOCREATEDB NOCREATEROLE;
    END IF;
END $$;
GRANT catalog_backend TO postgres;
GRANT USAGE ON SCHEMA public TO catalog_backend;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.profile_systems, public.profile_articles, public.glazing_bead_matrix,
       public.hardware_kits, public.infill_articles
    TO catalog_backend;

-- The catalog write policies name TO authenticated explicitly — extend them to
-- the backend role so API writes (which run under catalog_backend) still pass
-- the same can_manage_catalog / org-membership predicates. The predicates read
-- request.jwt.claims, which is unchanged by SET LOCAL ROLE.
ALTER POLICY catalog_system_insert ON public.profile_systems
    TO authenticated, catalog_backend;
ALTER POLICY catalog_system_update ON public.profile_systems
    TO authenticated, catalog_backend;
ALTER POLICY catalog_system_delete ON public.profile_systems
    TO authenticated, catalog_backend;
ALTER POLICY profile_systems_select ON public.profile_systems
    TO authenticated, pricing_backend, documentary_backend, catalog_backend;
DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'profile_articles', 'glazing_bead_matrix', 'hardware_kits'
    ] LOOP
        EXECUTE format(
            'ALTER POLICY catalog_insert ON public.%I
             TO authenticated, catalog_backend', table_name);
        EXECUTE format(
            'ALTER POLICY catalog_update ON public.%I
             TO authenticated, catalog_backend', table_name);
        EXECUTE format(
            'ALTER POLICY catalog_delete ON public.%I
             TO authenticated, catalog_backend', table_name);
        EXECUTE format(
            'ALTER POLICY catalog_read ON public.%I
             TO authenticated, pricing_backend, documentary_backend,
                catalog_backend', table_name);
    END LOOP;
END $$;
ALTER POLICY infill_articles_select ON public.infill_articles
    TO authenticated, catalog_backend;

-- The policies' predicates call these helpers; catalog_backend must be able
-- to execute them while evaluating its own writes.
GRANT EXECUTE ON FUNCTION private.can_manage_catalog(UUID) TO catalog_backend;
GRANT EXECUTE ON FUNCTION private.current_user_org_ids() TO catalog_backend;

-- ─── CAT-09b: bead matrix provenance triple ────────────────────────────────
ALTER TABLE public.glazing_bead_matrix
    ADD COLUMN data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    ADD COLUMN technical_reviewed_at TIMESTAMPTZ,
    ADD COLUMN technical_reviewed_by UUID,
    ADD COLUMN review_pending BOOLEAN NOT NULL DEFAULT FALSE;

-- ─── CAT-01: provenance + audit columns are backend-only ───────────────────
REVOKE INSERT, UPDATE ON public.profile_systems FROM authenticated;
REVOKE INSERT, UPDATE ON public.profile_articles FROM authenticated;
REVOKE INSERT, UPDATE ON public.glazing_bead_matrix FROM authenticated;
REVOKE INSERT, UPDATE ON public.hardware_kits FROM authenticated;
REVOKE INSERT, UPDATE ON public.infill_articles FROM authenticated;

GRANT INSERT (id, org_id,
    applications, central_overlap_mm, chamber_clearance_mm, chamber_count, code,
    corner_bracket_loss_mm, depth_mm, door_bottom_clearance_mm,
    door_leaf_side_clearance_mm, door_threshold_mm, end_milling_overlap_mm,
    family, glass_clearance_foil_mm, glass_clearance_white_mm, hook_depth_mm,
    is_active, manufacturer, material, name, process_profile_id,
    pulley_height_mm, rail_type, rebate_depth_mm, sash_overlap_mm,
    sliding_end_add_mm, sliding_glazing_deduction_height_mm,
    sliding_glazing_deduction_width_mm, sliding_lateral_clearance_mm, version)
    ON public.profile_systems TO authenticated;
GRANT UPDATE (
    applications, central_overlap_mm, chamber_clearance_mm, chamber_count, code,
    corner_bracket_loss_mm, depth_mm, door_bottom_clearance_mm,
    door_leaf_side_clearance_mm, door_threshold_mm, end_milling_overlap_mm,
    family, glass_clearance_foil_mm, glass_clearance_white_mm, hook_depth_mm,
    is_active, manufacturer, material, name, process_profile_id,
    pulley_height_mm, rail_type, rebate_depth_mm, sash_overlap_mm,
    sliding_end_add_mm, sliding_glazing_deduction_height_mm,
    sliding_glazing_deduction_width_mm, sliding_lateral_clearance_mm, version)
    ON public.profile_systems TO authenticated;

GRANT INSERT (id, org_id,
    commercial_length_mm, face_width_mm, material, name, reinforcement_gap_mm,
    reinforcement_sku, role, section, sku, steel_weight_kg_m, system_id,
    weight_kg_m, welding_loss_mm)
    ON public.profile_articles TO authenticated;
GRANT UPDATE (
    commercial_length_mm, face_width_mm, material, name, reinforcement_gap_mm,
    reinforcement_sku, role, section, sku, steel_weight_kg_m, system_id,
    weight_kg_m, welding_loss_mm)
    ON public.profile_articles TO authenticated;

GRANT INSERT (id, org_id,
    bead_article_id, bead_width_mm, cut_add_mm, gasket_exterior_mm,
    gasket_interior_mm, glass_thickness_mm, is_active, system_id)
    ON public.glazing_bead_matrix TO authenticated;
GRANT UPDATE (
    bead_article_id, bead_width_mm, cut_add_mm, gasket_exterior_mm,
    gasket_interior_mm, glass_thickness_mm, is_active, system_id)
    ON public.glazing_bead_matrix TO authenticated;

GRANT INSERT (id, org_id,
    carriage_capacity_kg, carriages_qty, contents, is_active,
    max_leaf_height_mm, max_leaf_weight_kg, max_leaf_width_mm,
    min_leaf_height_mm, min_leaf_width_mm, name, opening_type, rail_type, sku,
    stay_arms_qty, system_id, weight_kg)
    ON public.hardware_kits TO authenticated;
GRANT UPDATE (
    carriage_capacity_kg, carriages_qty, contents, is_active,
    max_leaf_height_mm, max_leaf_weight_kg, max_leaf_width_mm,
    min_leaf_height_mm, min_leaf_width_mm, name, opening_type, rail_type, sku,
    stay_arms_qty, system_id, weight_kg)
    ON public.hardware_kits TO authenticated;

GRANT INSERT (id, org_id,
    sku, name, kind, thickness_mm, weight_kg_m2, is_active, system_id)
    ON public.infill_articles TO authenticated;
GRANT UPDATE (sku, name, kind, thickness_mm, weight_kg_m2, is_active, system_id)
    ON public.infill_articles TO authenticated;

-- ─── CAT-02: re-open bookkeeping on the direct-write path ──────────────────
CREATE OR REPLACE FUNCTION private.reopen_catalog_review() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
    -- Backend writes run under catalog_backend/postgres and do this
    -- bookkeeping themselves (catalogs.service stamps the same columns);
    -- this trigger covers member-side PostgREST writes only.
    IF current_user <> 'authenticated' THEN
        RETURN NEW;
    END IF;
    IF to_jsonb(NEW)
           - '{data_provenance,technical_reviewed_at,technical_reviewed_by,review_pending}'::TEXT[]
       IS NOT DISTINCT FROM
       to_jsonb(OLD)
           - '{data_provenance,technical_reviewed_at,technical_reviewed_by,review_pending}'::TEXT[]
    THEN
        RETURN NEW;
    END IF;
    IF OLD.technical_reviewed_at IS NOT NULL THEN
        NEW.technical_reviewed_at := NULL;
        NEW.technical_reviewed_by := NULL;
        NEW.review_pending := TRUE;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.reopen_catalog_review() FROM PUBLIC;

DO $$
DECLARE table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'profile_systems', 'profile_articles',
        'glazing_bead_matrix', 'hardware_kits', 'infill_articles'
    ] LOOP
        EXECUTE format(
            'CREATE TRIGGER catalog_review_reopen BEFORE UPDATE ON public.%I
             FOR EACH ROW EXECUTE FUNCTION private.reopen_catalog_review()',
            table_name
        );
    END LOOP;
END $$;

-- ─── CAT-12: NaN is rejected at write time, not discovered at read ──────────
-- guard_manual_catalog's qty check: NaN <= 0 evaluates NULL and passed.
-- A row guard + column CHECKs make NaN unwritable on every path.
CREATE OR REPLACE FUNCTION private.guard_manual_catalog()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    parent_org UUID;
    parent_global BOOLEAN;
    bead_org UUID;
    component JSONB;
    quantity NUMERIC;
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

    -- CAT-12: NUMERIC columns gain chk_*_no_nan CHECKs below; jsonb payloads
    -- can't carry a numeric NaN on this platform (raw JSON rejects the NaN
    -- token, to_jsonb stores it as a string) and the kit shape check already
    -- requires a number-typed qty, so the column CHECKs are the real gate.
    IF TG_TABLE_NAME = 'hardware_kits' THEN
        IF jsonb_typeof(NEW.contents) IS DISTINCT FROM 'array' THEN
            RAISE EXCEPTION 'catalog_contents_invalid' USING ERRCODE = '23514';
        END IF;
        FOR component IN SELECT value FROM jsonb_array_elements(NEW.contents)
        LOOP
            IF jsonb_typeof(component) IS DISTINCT FROM 'object' THEN
                RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
            END IF;
            IF NOT (component ?& ARRAY['sku', 'name', 'qty', 'unit'])
               OR component - ARRAY['sku', 'name', 'qty', 'unit'] <> '{}'::jsonb
               OR jsonb_typeof(component -> 'sku') IS DISTINCT FROM 'string'
               OR jsonb_typeof(component -> 'name') IS DISTINCT FROM 'string'
               OR jsonb_typeof(component -> 'unit') IS DISTINCT FROM 'string'
               OR jsonb_typeof(component -> 'qty') IS DISTINCT FROM 'number'
               OR btrim(component ->> 'sku') = ''
               OR btrim(component ->> 'name') = ''
               OR btrim(component ->> 'unit') = '' THEN
                RAISE EXCEPTION 'catalog_component_invalid' USING ERRCODE = '23514';
            END IF;
            quantity := (component ->> 'qty')::numeric;
            -- Numeric NaN compares equal to 'NaN'::numeric.
            IF quantity IS NULL OR quantity <= 0 OR quantity = 'NaN'::numeric THEN
                RAISE EXCEPTION 'catalog_quantity_invalid' USING ERRCODE = '23514';
            END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION private.guard_manual_catalog() FROM PUBLIC;

-- Numeric columns: Postgres NUMERIC treats NaN = NaN as TRUE, so the
-- rejection is col <> 'NaN' — false exactly when the stored value is NaN.
ALTER TABLE public.profile_systems ADD CONSTRAINT chk_systems_no_nan CHECK (
    (depth_mm IS NULL OR depth_mm <> 'NaN'::numeric)
    AND (chamber_clearance_mm IS NULL OR chamber_clearance_mm <> 'NaN'::numeric)
    AND (sash_overlap_mm IS NULL OR sash_overlap_mm <> 'NaN'::numeric)
    AND (glass_clearance_white_mm IS NULL OR glass_clearance_white_mm <> 'NaN'::numeric)
    AND (glass_clearance_foil_mm IS NULL OR glass_clearance_foil_mm <> 'NaN'::numeric)
    AND (pulley_height_mm IS NULL OR pulley_height_mm <> 'NaN'::numeric)
    AND (central_overlap_mm IS NULL OR central_overlap_mm <> 'NaN'::numeric)
    AND (sliding_lateral_clearance_mm IS NULL OR sliding_lateral_clearance_mm <> 'NaN'::numeric)
    AND (sliding_end_add_mm IS NULL OR sliding_end_add_mm <> 'NaN'::numeric)
    AND (sliding_glazing_deduction_width_mm IS NULL OR sliding_glazing_deduction_width_mm <> 'NaN'::numeric)
    AND (sliding_glazing_deduction_height_mm IS NULL OR sliding_glazing_deduction_height_mm <> 'NaN'::numeric)
    AND (corner_bracket_loss_mm IS NULL OR corner_bracket_loss_mm <> 'NaN'::numeric)
    AND (hook_depth_mm IS NULL OR hook_depth_mm <> 'NaN'::numeric)
    AND (door_threshold_mm IS NULL OR door_threshold_mm <> 'NaN'::numeric)
    AND (door_bottom_clearance_mm IS NULL OR door_bottom_clearance_mm <> 'NaN'::numeric)
    AND (door_leaf_side_clearance_mm IS NULL OR door_leaf_side_clearance_mm <> 'NaN'::numeric)
    AND (rebate_depth_mm IS NULL OR rebate_depth_mm <> 'NaN'::numeric)
    AND (end_milling_overlap_mm IS NULL OR end_milling_overlap_mm <> 'NaN'::numeric));
ALTER TABLE public.profile_articles ADD CONSTRAINT chk_articles_no_nan CHECK (
    face_width_mm <> 'NaN'::numeric
    AND (commercial_length_mm IS NULL OR commercial_length_mm <> 'NaN'::numeric)
    AND (welding_loss_mm IS NULL OR welding_loss_mm <> 'NaN'::numeric)
    AND (reinforcement_gap_mm IS NULL OR reinforcement_gap_mm <> 'NaN'::numeric)
    AND (weight_kg_m IS NULL OR weight_kg_m <> 'NaN'::numeric)
    AND (steel_weight_kg_m IS NULL OR steel_weight_kg_m <> 'NaN'::numeric));
ALTER TABLE public.glazing_bead_matrix ADD CONSTRAINT chk_beads_no_nan CHECK (
    glass_thickness_mm <> 'NaN'::numeric
    AND bead_width_mm <> 'NaN'::numeric
    AND (cut_add_mm IS NULL OR cut_add_mm <> 'NaN'::numeric)
    AND (gasket_interior_mm IS NULL OR gasket_interior_mm <> 'NaN'::numeric)
    AND (gasket_exterior_mm IS NULL OR gasket_exterior_mm <> 'NaN'::numeric));
ALTER TABLE public.hardware_kits ADD CONSTRAINT chk_kits_no_nan CHECK (
    min_leaf_width_mm <> 'NaN'::numeric
    AND max_leaf_width_mm <> 'NaN'::numeric
    AND min_leaf_height_mm <> 'NaN'::numeric
    AND max_leaf_height_mm <> 'NaN'::numeric
    AND max_leaf_weight_kg <> 'NaN'::numeric
    AND (weight_kg IS NULL OR weight_kg <> 'NaN'::numeric)
    AND (carriage_capacity_kg IS NULL OR carriage_capacity_kg <> 'NaN'::numeric));
ALTER TABLE public.infill_articles ADD CONSTRAINT chk_infills_no_nan CHECK (
    thickness_mm <> 'NaN'::numeric
    AND (weight_kg_m2 IS NULL OR weight_kg_m2 <> 'NaN'::numeric));

-- ─── CAT-11: the import ledger is append-only for members ───────────────────
REVOKE UPDATE, DELETE ON public.catalog_imports FROM authenticated;

-- ─── CAT-15: enum coherence + unbound-kit uniqueness ───────────────────────
ALTER TABLE public.hardware_kits
    ADD CONSTRAINT chk_kits_rail_type CHECK (rail_type IN ('dual', 'mono')),
    ADD CONSTRAINT chk_kits_opening_type CHECK (
        opening_type IN ('AWNING', 'DOOR', 'SLIDING', 'TILT_TURN', 'TURN'));
CREATE UNIQUE INDEX uk_kits_unbound_org_sku
    ON public.hardware_kits (org_id, sku) WHERE system_id IS NULL;

COMMIT;
