-- D01 (cont.): singleton coverage for the resolved roles and the three
-- rule authority tables. Lives in its own migration because the new
-- profile_role literals cannot be referenced in the transaction that adds
-- them.

BEGIN;

-- The new enum literals cannot be referenced inside this transaction by
-- constraint expressions that evaluate rows, so the singleton list lives
-- in the trigger + indexes only (they only pattern-match text values when
-- rows are written, which happens in later transactions). COUPLER stays
-- multi-valued: an assembly may reference several coupler SKUs.
DROP INDEX IF EXISTS uk_tenant_system_singleton_profile_role;
DROP INDEX IF EXISTS uk_global_system_singleton_profile_role;

CREATE UNIQUE INDEX uk_tenant_system_singleton_profile_role
ON public.profile_articles(system_id,org_id,role)
WHERE org_id IS NOT NULL
  AND role IN ('FRAME','SASH','SLIDING_SASH','DOOR_SASH','MULLION_V','MULLION_H',
               'INVERSOR','ADDITIONAL','THRESHOLD','INTERLOCK','RAIL',
               'FRAME_EXTENSION','SILL','COVER_TRIM','SKIRT');

CREATE UNIQUE INDEX uk_global_system_singleton_profile_role
ON public.profile_articles(system_id,role)
WHERE org_id IS NULL
  AND role IN ('FRAME','SASH','SLIDING_SASH','DOOR_SASH','MULLION_V','MULLION_H',
               'INVERSOR','ADDITIONAL','THRESHOLD','INTERLOCK','RAIL',
               'FRAME_EXTENSION','SILL','COVER_TRIM','SKIRT');

CREATE OR REPLACE FUNCTION private.guard_singleton_profile_role() RETURNS TRIGGER
LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
    IF NEW.role IN ('FRAME','SASH','SLIDING_SASH','DOOR_SASH','MULLION_V','MULLION_H',
                    'INVERSOR','ADDITIONAL','THRESHOLD','INTERLOCK','RAIL',
                    'FRAME_EXTENSION','SILL','COVER_TRIM','SKIRT') THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(NEW.system_id::text || ':' || NEW.role::text, 0));
        IF EXISTS(
            SELECT 1
            FROM public.profile_articles AS other
            WHERE other.system_id = NEW.system_id
              AND other.role = NEW.role
              AND other.id IS DISTINCT FROM NEW.id
              AND (other.org_id IS NULL OR NEW.org_id IS NULL OR other.org_id = NEW.org_id)
        ) THEN
            RAISE EXCEPTION 'catalog_singleton_role_conflict' USING ERRCODE = '23505';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.guard_singleton_profile_role() FROM PUBLIC;

CREATE TABLE public.profile_cut_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    role public.profile_role NOT NULL,
    cut_angle_deg NUMERIC(5, 2) NOT NULL DEFAULT 45.00,
    welded_ends INT CHECK (welded_ends IS NULL OR welded_ends IN (0, 1, 2)),
    interlock_deduction_mm NUMERIC(10, 2) NOT NULL DEFAULT 0.00,
    rounding_mm NUMERIC(10, 2) NOT NULL DEFAULT 0.01
        CHECK (rounding_mm >= 0.01),
    reinforcement_sku VARCHAR(100),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, role),
    UNIQUE (id, system_id)
);

CREATE TABLE public.profile_reinforcement_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    role public.profile_role NOT NULL,
    finish_class TEXT NOT NULL DEFAULT 'ALL'
        CHECK (finish_class IN ('ALL', 'WHITE', 'NON_WHITE')),
    min_length_mm NUMERIC(10, 2) NOT NULL DEFAULT 0.00
        CHECK (min_length_mm >= 0.00),
    mandatory BOOLEAN NOT NULL DEFAULT TRUE,
    reinforcement_sku VARCHAR(100),
    cut_deduction_mm NUMERIC(10, 2) NOT NULL DEFAULT 0.00
        CHECK (cut_deduction_mm >= 0.00),
    screws_per_m NUMERIC(6, 2) CHECK (screws_per_m IS NULL OR screws_per_m >= 0.00),
    screw_sku VARCHAR(100),
    CHECK (screws_per_m IS NULL OR screw_sku IS NOT NULL),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, role, finish_class, min_length_mm),
    UNIQUE (id, system_id)
);

CREATE TABLE public.system_typology_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    opening_type TEXT NOT NULL,
    min_leaf_width_mm NUMERIC(10, 2),
    max_leaf_width_mm NUMERIC(10, 2),
    min_leaf_height_mm NUMERIC(10, 2),
    max_leaf_height_mm NUMERIC(10, 2),
    max_leaf_weight_kg NUMERIC(8, 2),
    max_aspect_ratio NUMERIC(6, 3),
    CHECK (min_leaf_width_mm IS NULL OR min_leaf_width_mm > 0.00),
    CHECK (max_leaf_width_mm IS NULL OR max_leaf_width_mm > 0.00),
    CHECK (min_leaf_height_mm IS NULL OR min_leaf_height_mm > 0.00),
    CHECK (max_leaf_height_mm IS NULL OR max_leaf_height_mm > 0.00),
    CHECK (max_leaf_weight_kg IS NULL OR max_leaf_weight_kg > 0.00),
    CHECK (max_aspect_ratio IS NULL OR max_aspect_ratio > 0.00),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, opening_type),
    UNIQUE (id, system_id)
);

ALTER TABLE public.profile_cut_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profile_reinforcement_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_typology_limits ENABLE ROW LEVEL SECURITY;

CREATE POLICY profile_cut_rules_read
ON public.profile_cut_rules FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY profile_reinforcement_rules_read
ON public.profile_reinforcement_rules FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY system_typology_limits_read
ON public.system_typology_limits FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));

CREATE POLICY profile_cut_rules_backend_write
ON public.profile_cut_rules FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY profile_reinforcement_rules_backend_write
ON public.profile_reinforcement_rules FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY system_typology_limits_backend_write
ON public.system_typology_limits FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'profile_cut_rules',
        'profile_reinforcement_rules',
        'system_typology_limits'
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
        -- Backend calculators read the declared conventions under their
        -- own roles: pricing resolves BOM costs, documentary freezes the
        -- position rows' limit evidence, the AI layer reasons over the
        -- same catalog. Write stays catalog-scoped.
        EXECUTE format(
            'GRANT SELECT ON public.%I TO pricing_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO documentary_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO ai_backend', table_name);
    END LOOP;
END;
$$;

-- Row-level evidence can attest these authorities like any other.
COMMENT ON TABLE public.profile_cut_rules IS
    'D01 declared cut convention per profile role (angle, welded ends, encuentro deduction, cut quantum).';
COMMENT ON TABLE public.profile_reinforcement_rules IS
    'D01 steel reinforcement requirement as data: role + finish class + member length decide.';
COMMENT ON TABLE public.system_typology_limits IS
    'D01 leaf dimensional envelope per system and opening typology; engine enforces, UI displays.';

COMMIT;
