-- D03: per-system opening capabilities — which compositions of
-- movement × direction × leaf role × unit kind a series declares it can
-- fabricate, and whether the fixed-in-sash variant exists. The engine's
-- capability gate, the editor's typology offer and the AI's option
-- filter all read these rows; a system with no declared rows falls back
-- to its fabrication family's physical repertoire.

BEGIN;

CREATE TABLE public.system_opening_capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    -- How the leaf travels: the engine's OpeningMovement axis.
    movement TEXT NOT NULL
        CHECK (movement IN (
            'FIXED', 'TURN', 'TILT', 'TILT_TURN', 'TOP_HUNG',
            'BOTTOM_HUNG', 'SLIDE', 'LIFT_SLIDE', 'PARALLEL_SLIDE',
            'FOLD', 'PIVOT_V', 'PIVOT_H', 'VERTICAL_SLIDE')),
    -- Opening directions the composition admits, interior view.
    directions TEXT[] NOT NULL DEFAULT '{}'::text[]
        CHECK (directions <@ ARRAY['INWARD', 'OUTWARD']::text[]),
    -- Leaf roles admitted inside a multi-leaf composition.
    leaf_roles TEXT[] NOT NULL DEFAULT '{SINGLE}'::text[]
        CHECK (leaf_roles <@ ARRAY['SINGLE', 'ACTIVE', 'PASSIVE']::text[]),
    -- Which unit kinds (WINDOW / DOOR) may build this composition.
    unit_kinds TEXT[] NOT NULL DEFAULT '{WINDOW}'::text[]
        CHECK (unit_kinds <@ ARRAY['WINDOW', 'DOOR']::text[]),
    -- Maximum leaves in the composition (pairs need 2).
    max_leaves INT NOT NULL DEFAULT 1
        CHECK (max_leaves BETWEEN 1 AND 2),
    -- Whether a non-opening sash-fixed variant (fijo en hoja) exists.
    fixed_in_sash BOOLEAN NOT NULL DEFAULT FALSE,
    -- Which kit family the composition mounts, when the catalog names
    -- one; D04 refines per-leaf herraje resolution.
    hardware_group TEXT,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (
        system_id, org_id, movement, directions, leaf_roles,
        unit_kinds, max_leaves, fixed_in_sash
    ),
    UNIQUE (id, system_id)
);

ALTER TABLE public.system_opening_capabilities ENABLE ROW LEVEL SECURITY;

CREATE POLICY system_opening_capabilities_read
ON public.system_opening_capabilities FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));

CREATE POLICY system_opening_capabilities_backend_write
ON public.system_opening_capabilities FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

REVOKE ALL ON public.system_opening_capabilities FROM anon;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON public.system_opening_capabilities FROM authenticated;
GRANT SELECT ON public.system_opening_capabilities TO authenticated;
GRANT ALL ON public.system_opening_capabilities TO catalog_backend;
GRANT ALL ON public.system_opening_capabilities TO service_role;
-- The calculators and the AI read the declared offer under their own
-- roles: pricing/pricing-engine resolves what a quote may offer,
-- documentary freezes the position's typology evidence, AI filters
-- suggestions to the system's declared capability set.
GRANT SELECT ON public.system_opening_capabilities TO pricing_backend;
GRANT SELECT ON public.system_opening_capabilities TO documentary_backend;
GRANT SELECT ON public.system_opening_capabilities TO ai_backend;

COMMENT ON TABLE public.system_opening_capabilities IS
    'D03 declared opening repertoire per system: movement × directions × leaf roles × unit kinds × max leaves (+fijo en hoja). Engine capability gate + editor/AI offer read these rows; empty means the family fallback applies.';

-- Kit families that only exist on the Opening axis (D03): banderola (TILT),
-- abatimiento de bisagras abajo (BOTTOM_HUNG) and the passive-leaf falleba
-- (FALLEBA). Mirrors backend KIT_OPENING_TYPES.
ALTER TABLE public.hardware_kits DROP CONSTRAINT chk_kits_opening_type;
ALTER TABLE public.hardware_kits
    ADD CONSTRAINT chk_kits_opening_type CHECK (
        opening_type IN ('AWNING', 'BOTTOM_HUNG', 'DOOR', 'FALLEBA',
                         'SLIDING', 'TILT', 'TILT_TURN', 'TURN'));

COMMIT;
