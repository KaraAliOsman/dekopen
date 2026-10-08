-- D05 — colores y acabados de verdad.
--
-- `profile_systems.finishes` stays the declared domain of finish codes a
-- series sells; this migration adds the real color catalog those codes
-- point at (`system_color_options`) and the per-system bicolor
-- capability (`profile_systems.bicolor_allowed`).
--
-- Honesty contract: each row is declared catalog data — manufacturer
-- code, kind, faces, finish class, linear render color/texture and a
-- declared sell surcharge. Resolved quantities (BOM metres, position
-- area) and combination validation live in the engine, never here.

BEGIN;

ALTER TABLE public.profile_systems
    ADD COLUMN bicolor_allowed BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN public.profile_systems.bicolor_allowed IS
    'D05: whether the series sells bars finished differently on the '
    'interior and exterior faces (foil/coextruded/powder pairs).';

CREATE TABLE public.system_color_options (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    -- Keys `profile_systems.finishes` — the declared pickable domain.
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    -- Manufacturing process of the finish.
    kind TEXT NOT NULL,
    -- Manufacturer reference (RAL code, film ref, anodizing class).
    manufacturer_code VARCHAR(100),
    -- MATE / SATINADO / BRILLANTE for powder or anodized finishes.
    gloss VARCHAR(30),
    -- Linear sRGB hex '#RRGGBB' — NULL means the render stays approximate.
    render_color VARCHAR(7),
    -- Declared render texture ('WOOD_GRAIN'); NULL renders flat.
    render_texture VARCHAR(30),
    -- Machining finish domain for reinforcement rules (D01 connect).
    finish_class TEXT NOT NULL DEFAULT 'WHITE',
    -- The finish films the glazing rebate → foil clearance applies.
    film_clearance BOOLEAN NOT NULL DEFAULT FALSE,
    -- Declared per-finish glazing clearance override (mm).
    glass_clearance_mm NUMERIC(10, 2),
    -- Heat-loaded face — dark finishes shrink the admissible envelope.
    dark BOOLEAN NOT NULL DEFAULT FALSE,
    -- Faces the finish is manufactured on.
    faces TEXT NOT NULL DEFAULT 'BOTH',
    -- Required finish code on the opposite face (coextruded over a base).
    pair_code VARCHAR(50),
    -- Leaf-envelope multiplier for this finish (<= 1).
    size_factor NUMERIC(4, 3),
    -- Declared sell surcharge: per profile metre / per m² / fixed per
    -- position / % of materials.
    surcharge_kind TEXT,
    surcharge_amount NUMERIC(12, 4),
    surcharge_currency VARCHAR(3),
    surcharge_label VARCHAR(255),
    sort_order INTEGER NOT NULL DEFAULT 0,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_color_options_code CHECK (
        length(btrim(code)) > 0 AND code !~ '/'),
    CONSTRAINT chk_color_options_name CHECK (length(btrim(name)) > 0),
    CONSTRAINT chk_color_options_kind CHECK (
        kind IN ('MASS', 'FOIL', 'COEXTRUDED', 'POWDER', 'ANODIZED', 'WOOD_EFFECT')),
    CONSTRAINT chk_color_options_render_color CHECK (
        render_color IS NULL OR render_color ~ '^#[0-9A-Fa-f]{6}$'),
    CONSTRAINT chk_color_options_finish_class CHECK (
        finish_class IN ('WHITE', 'NON_WHITE')),
    CONSTRAINT chk_color_options_faces CHECK (
        faces IN ('BOTH', 'EXTERIOR_ONLY', 'INTERIOR_ONLY')),
    CONSTRAINT chk_color_options_pair CHECK (
        pair_code IS NULL OR (length(btrim(pair_code)) > 0 AND pair_code <> code)),
    CONSTRAINT chk_color_options_clearance CHECK (
        glass_clearance_mm IS NULL
        OR (glass_clearance_mm > 0.00 AND glass_clearance_mm <> 'NaN'::numeric)),
    CONSTRAINT chk_color_options_size_factor CHECK (
        size_factor IS NULL
        OR (size_factor > 0.000 AND size_factor <= 1.000
            AND size_factor <> 'NaN'::numeric)),
    CONSTRAINT chk_color_options_surcharge CHECK (
        ((surcharge_kind IS NULL) = (surcharge_amount IS NULL))
        AND (surcharge_kind IS NULL OR surcharge_kind IN
             ('PER_PROFILE_METER', 'PER_M2', 'FIXED_PER_POSITION', 'PCT_OF_MATERIALS'))
        AND (surcharge_amount IS NULL
             OR (surcharge_amount >= 0.0000 AND surcharge_amount <> 'NaN'::numeric))
        AND (surcharge_kind IS DISTINCT FROM 'PCT_OF_MATERIALS'
             OR surcharge_amount <= 1.0000)),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, code),
    UNIQUE (id, system_id)
);

ALTER TABLE public.system_color_options ENABLE ROW LEVEL SECURITY;

CREATE POLICY system_color_options_read
ON public.system_color_options FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));

CREATE POLICY system_color_options_backend_write
ON public.system_color_options FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

DO $$
BEGIN
    EXECUTE format(
        'REVOKE ALL ON public.%I FROM anon', 'system_color_options');
    EXECUTE format(
        'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
        'ON public.%I FROM authenticated', 'system_color_options');
    EXECUTE format(
        'GRANT SELECT ON public.%I TO authenticated', 'system_color_options');
    EXECUTE format(
        'GRANT ALL ON public.%I TO catalog_backend', 'system_color_options');
    EXECUTE format(
        'GRANT ALL ON public.%I TO service_role', 'system_color_options');
    EXECUTE format(
        'GRANT SELECT ON public.%I TO pricing_backend', 'system_color_options');
    EXECUTE format(
        'GRANT SELECT ON public.%I TO documentary_backend', 'system_color_options');
    EXECUTE format(
        'GRANT SELECT ON public.%I TO ai_backend', 'system_color_options');
END;
$$;

-- Same guard coverage as the other catalog authority tables: manual-write
-- coherence plus the locked-catalog freeze authority.
DO $$
BEGIN
    EXECUTE format(
        'CREATE TRIGGER catalog_guard BEFORE INSERT OR UPDATE ON public.%I
         FOR EACH ROW EXECUTE FUNCTION private.guard_manual_catalog()',
        'system_color_options'
    );
    EXECUTE format(
        'CREATE TRIGGER guard_referenced_catalog BEFORE INSERT OR UPDATE OR DELETE
         ON public.%I FOR EACH ROW EXECUTE FUNCTION private.guard_referenced_catalog()',
        'system_color_options'
    );
END;
$$;

COMMENT ON TABLE public.system_color_options IS
    'D05 real color catalog per system: manufacturer code, kind, faces, '
    'finish class, render color/texture and declared sell surcharge per '
    'finish code declared in profile_systems.finishes.';

COMMIT;
