-- Declared finish authority on the profile system: a series announces which
-- finishes it actually sells (WHITE, FOILED, ...). The estimator can only
-- pick a declared finish — the old hard-locked WHITE turns into catalog
-- authority, and every non-WHITE finish consumes the foil clearances the
-- system already declares (glass_clearance_foil_mm).
CREATE OR REPLACE FUNCTION public.is_nonempty_text_array(value JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT jsonb_typeof(value) = 'array'
       AND jsonb_array_length(value) > 0
       AND NOT EXISTS (
            SELECT 1
            FROM jsonb_array_elements(value) AS element
            WHERE jsonb_typeof(element.value) <> 'string'
               OR btrim(element.value #>> '{}') = ''
       )
$$;

ALTER TABLE public.profile_systems
    ADD COLUMN finishes JSONB NOT NULL DEFAULT '["WHITE"]'::jsonb;

ALTER TABLE public.profile_systems
    ADD CONSTRAINT profile_systems_finishes_shape
    CHECK (public.is_nonempty_text_array(finishes));

-- Demo reference system sells blanco + foliado — it already carries the
-- foil clearances, so declaring both is the honest authority. Locked
-- catalogs are skipped: a referenced system's finish list is frozen
-- authority (guard_referenced_system); seed.sql declares it on fresh setups.
UPDATE public.profile_systems
SET finishes = '["WHITE", "FOILED"]'::jsonb
WHERE code = 'DEMO_60' AND org_id IS NULL AND technical_locked IS NOT TRUE;
