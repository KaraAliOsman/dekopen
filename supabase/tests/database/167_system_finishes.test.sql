BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path=public,extensions;
SELECT plan(4);

-- The system carries a declared finish list: the estimator's Acabado picker
-- is authority-driven, not hard-coded WHITE.
SELECT has_column('public', 'profile_systems', 'finishes',
                  'profile_systems declares finishes');

-- Existing rows get the WHITE-only default.
SELECT col_default_is('public', 'profile_systems', 'finishes', '["WHITE"]'::jsonb,
                      'finishes defaults to a WHITE-only list');

-- Shape guard: non-empty array of non-blank strings.
SELECT ok(
    is_nonempty_text_array('["WHITE","FOILED"]'::jsonb)
    AND NOT is_nonempty_text_array('[]'::jsonb)
    AND NOT is_nonempty_text_array('["WHITE", 5]'::jsonb)
    AND NOT is_nonempty_text_array('["WHITE", "  "]'::jsonb)
    AND NOT is_nonempty_text_array('"WHITE"'::jsonb),
    'is_nonempty_text_array rejects empty/mixed/non-array finishes'
);

-- Demo PVC series declares blanco + foliado (foil clearances exist for it).
SELECT ok(
    (SELECT finishes @> '"FOILED"'::jsonb
     FROM public.profile_systems WHERE code = 'DEMO_60' AND is_global),
    'DEMO_60 declares FOILED alongside WHITE'
);

SELECT * FROM finish();
ROLLBACK;
