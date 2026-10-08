BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(19);

-- D01 fabricación families: profile_systems declares its family and the
-- catalog carries cut/reinforcement/limit rules as auditable data.

SELECT has_column(
    'public', 'profile_systems', 'system_family',
    'profile_systems declares its fabrication family'
);
SELECT col_has_check(
    'public', 'profile_systems', 'system_family',
    'system_family is a closed CHECK domain'
);
SELECT enum_has_labels(
    'public', 'profile_role',
    ARRAY[
        'FRAME','SASH','MULLION_V','MULLION_H','INVERSOR','GLAZING_BEAD',
        'COUPLER','ADDITIONAL','THRESHOLD',
        'SLIDING_SASH','INTERLOCK','RAIL','DOOR_SASH',
        'FRAME_EXTENSION','SILL','COVER_TRIM','SKIRT'
    ],
    'profile_role carries the D01 resolved roles'
);
SELECT has_table('public', 'profile_cut_rules', 'profile_cut_rules exists');
SELECT has_table('public', 'profile_reinforcement_rules', 'profile_reinforcement_rules exists');
SELECT has_table('public', 'system_typology_limits', 'system_typology_limits exists');
SELECT col_is_fk(
    'public', 'profile_cut_rules', 'system_id',
    'cut rules reference their system'
);
SELECT policies_are(
    'public', 'profile_cut_rules',
    ARRAY['profile_cut_rules_read','profile_cut_rules_backend_write'],
    'cut rules: member read + backend write only'
);
SELECT policies_are(
    'public', 'system_typology_limits',
    ARRAY['system_typology_limits_read','system_typology_limits_backend_write'],
    'typology limits: member read + backend write only'
);

-- The DEMO_60 / DEMO_CORREDERA_60 split.
SELECT results_eq(
    $$ SELECT system_family FROM public.profile_systems
        WHERE code = 'DEMO_60' AND is_global $$,
    $$ VALUES ('CASEMENT'::text) $$,
    'DEMO_60 is a casement family'
);
SELECT results_eq(
    $$ SELECT system_family FROM public.profile_systems
        WHERE code = 'DEMO_CORREDERA_60' AND is_global $$,
    $$ VALUES ('SLIDING'::text) $$,
    'DEMO_CORREDERA_60 is the sliding family'
);
SELECT is_empty(
    $$ SELECT p.id FROM public.project_positions p
        JOIN public.profile_systems s ON s.id = p.system_id
        WHERE s.code = 'DEMO_60'
          AND p.typology IN ('SLIDING','SLIDING_2L','SLIDING_3L','SLIDING_4L') $$,
    'no saved sliding position still points at DEMO_60'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_articles a
        JOIN public.profile_systems s ON s.id = a.system_id
        WHERE s.code = 'DEMO_CORREDERA_60' AND a.role = 'RAIL'
    ),
    'the corredera declares a bottom RAIL article'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_articles a
        JOIN public.profile_systems s ON s.id = a.system_id
        WHERE s.code = 'DEMO_CORREDERA_60' AND a.role = 'INTERLOCK'
    ),
    'the corredera declares an INTERLOCK (encuentro) article'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_articles a
        JOIN public.profile_systems s ON s.id = a.system_id
        WHERE s.code = 'DEMO_60' AND a.role = 'DOOR_SASH'
    ),
    'DEMO_60 declares its dedicated door sash'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_reinforcement_rules r
        JOIN public.profile_systems s ON s.id = r.system_id
        WHERE s.code = 'DEMO_60' AND r.role = 'SASH'
          AND r.finish_class = 'NON_WHITE' AND r.min_length_mm = 0
    ),
    'foiled sash members are always reinforced (NON_WHITE, min 0)'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_cut_rules r
        JOIN public.profile_systems s ON s.id = r.system_id
        WHERE s.code = 'DEMO_CORREDERA_60' AND r.role = 'INTERLOCK'
          AND r.interlock_deduction_mm = 18.00
    ),
    'the encuentro cut rule carries its 18 mm deduction'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.system_typology_limits l
        JOIN public.profile_systems s ON s.id = l.system_id
        WHERE s.code = 'DEMO_60' AND l.opening_type = 'TURN_LEFT'
          AND l.max_leaf_width_mm = 1400.00
    ),
    'DEMO_60 declares the TURN_LEFT leaf envelope'
);

-- Singleton coverage now includes the resolved leaf/frame roles.
PREPARE dup AS
    INSERT INTO public.profile_articles (
        system_id, org_id, sku, name, role, material, face_width_mm
    )
    SELECT a.system_id, a.org_id, 'DUP-INTERLOCK', 'Duplicado', 'INTERLOCK',
           a.material, a.face_width_mm
    FROM public.profile_articles a
    JOIN public.profile_systems s ON s.id = a.system_id
    WHERE s.code = 'DEMO_CORREDERA_60' AND a.role = 'INTERLOCK'
    LIMIT 1;
SELECT throws_matching(
    'dup', 'catalog_singleton_role_conflict',
    'a second INTERLOCK on the same system is rejected'
);

SELECT * FROM finish();
ROLLBACK;
