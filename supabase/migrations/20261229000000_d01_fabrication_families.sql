-- D01: fabrication families + cut/reinforcement/limit rule tables.
--
-- The profile_systems row stops pretending one parameter block fits every
-- fabrication family: `system_family` declares what the series physically
-- is (casement, sliding, lift-slide, door, fixed façade) and the engine
-- rejects typologies the family cannot build. Three new authority tables
-- carry, as data, the rules the engine executes deterministically:
--   * profile_cut_rules          — declared cut convention per role
--                                  (angle, welded ends, encuentro
--                                  deduction, cut quantum);
--   * profile_reinforcement_rules — steel requirement per role + finish
--                                  class + length (foiled/dark always
--                                  reinforced), with screw fastening for
--                                  the BOM;
--   * system_typology_limits      — leaf dimensional envelope per
--                                  opening type.
-- All three keep the catalog audit triple (data_provenance /
-- technical_reviewed_* / review_pending), org_id + RLS, and member read /
-- backend write grants.

BEGIN;

ALTER TYPE public.profile_role ADD VALUE 'SLIDING_SASH';
ALTER TYPE public.profile_role ADD VALUE 'INTERLOCK';
ALTER TYPE public.profile_role ADD VALUE 'RAIL';
ALTER TYPE public.profile_role ADD VALUE 'DOOR_SASH';
ALTER TYPE public.profile_role ADD VALUE 'FRAME_EXTENSION';
ALTER TYPE public.profile_role ADD VALUE 'SILL';
ALTER TYPE public.profile_role ADD VALUE 'COVER_TRIM';
ALTER TYPE public.profile_role ADD VALUE 'SKIRT';

ALTER TABLE public.profile_systems
    ADD COLUMN system_family TEXT NOT NULL DEFAULT 'CASEMENT'
        CHECK (system_family IN (
            'CASEMENT', 'SLIDING', 'LIFT_SLIDE', 'DOOR', 'FACADE_FIXED'));

COMMIT;
