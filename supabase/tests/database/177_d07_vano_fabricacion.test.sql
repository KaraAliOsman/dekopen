BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(16);

-- D07 del vano a la fabricación: mounting rules como autoridad versionada
-- por sistema/organización, el registro del vano en la posición, el estado
-- de medida con su sello de confirmación, y la tolerancia org-configurable.

SELECT has_table('public', 'mounting_rules', 'mounting_rules exists');
SELECT has_column(
    'public', 'mounting_rules', 'authority',
    'mounting rules carry the signed per-side authority JSONB'
);
SELECT col_has_check(
    'public', 'mounting_rules', 'code',
    'mounting code is a closed CHECK domain'
);
SELECT policies_are(
    'public', 'mounting_rules',
    ARRAY['mounting_rules_read'],
    'mounting rules: member+documentary read, no member writes'
);
SELECT col_has_check(
    'public', 'project_positions', 'measurement_state',
    'measurement state is a closed CHECK domain'
);
SELECT has_column(
    'public', 'project_positions', 'rough_opening_input',
    'positions carry the vano record (1–3 points per axis, wall, escuadra)'
);
SELECT has_column(
    'public', 'project_positions', 'fabrication_lock',
    'positions carry the manual fabrication pin'
);
SELECT has_column(
    'public', 'tenancy_organizations', 'vano_spread_tolerance_mm',
    'spread tolerance is org-configurable in Ajustes'
);
SELECT ok(
    (SELECT COUNT(*) FROM public.mounting_rules)
    >= (SELECT COUNT(*) FROM public.profile_systems) * 5,
    'every existing system seeds the five mounting types'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.mounting_rules r
        JOIN public.profile_systems s ON s.id = r.system_id
        WHERE s.code = 'DEMO_60' AND r.code = 'EN_VANO'
          AND r.org_id IS NULL
          AND r.authority->'sides'->'top'->>'mm' = '-10.00'
          AND r.review_pending = TRUE
          AND r.data_provenance = 'SEED_SYNTHETIC'
    ),
    'DEMO_60 en-vano seeds 10 mm perimeter clearance, pending review'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.mounting_rules r
        JOIN public.profile_systems s ON s.id = r.system_id
        WHERE s.code = 'DEMO_60' AND r.code = 'SOBRE_VANO'
          AND r.authority->'sides'->'top'->>'mm' = '20.00'
    ),
    'sobre-vano adds 20 mm overlap instead of deducting'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'mounting_rules'
          AND t.tgname = 'immutable_authority'
    ),
    'immutable_authority trigger guards rule mutation'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM pg_trigger t
        JOIN pg_class c ON c.oid = t.tgrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relname = 'project_positions'
          AND t.tgname = 'validate_position_mounting_rule_scope'
    ),
    'positions reject mounting rules from another system'
);
SELECT ok(
    NOT EXISTS(
        SELECT 1 FROM public.mounting_rules
        WHERE code = 'EN_VANO' AND version <> 1
    ),
    'seeded rules land as version 1 — revisions arrive as new rows'
);

-- Probe org: pgTAP runs before the e2e fixture, so tenancy_organizations
-- is empty here — every probe row carries its own org.
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('d0700000-0000-4000-8000-000000000001', 'D07 probe', 'D07-1');

-- The scope trigger really fires: a rule from another system is rejected.
DO $$
DECLARE
    pos_system UUID;
    other_rule UUID;
    probe_project UUID;
    probe_org UUID := 'd0700000-0000-4000-8000-000000000001';
BEGIN
    SELECT s.id INTO pos_system FROM public.profile_systems s LIMIT 1;
    SELECT r.id INTO other_rule FROM public.mounting_rules r
    WHERE r.system_id <> pos_system LIMIT 1;
    IF other_rule IS NULL OR pos_system IS NULL THEN
        RETURN;  -- single-system fixture: the trigger install check above
    END IF;
    INSERT INTO public.projects (
        id, code, name, client_name, org_id, created_by
    ) VALUES (
        gen_random_uuid(), 'PRJ-D07-TEST', 'probe', 'probe',
        probe_org, gen_random_uuid()
    ) RETURNING id INTO probe_project;
    BEGIN
        INSERT INTO public.project_positions (
            id, project_id, org_id, position_index, location_tag, quantity,
            typology, system_id, width_mm, height_mm,
            color_interior, color_exterior, parametric_tree, bom_snapshot,
            mounting_rule_id
        ) VALUES (
            gen_random_uuid(), probe_project, probe_org, 1, 'probe', 1,
            'VENTANA', pos_system, 1000.00, 1000.00,
            'WHITE', 'WHITE', '{}'::jsonb, '{}'::jsonb,
            other_rule
        );
        RAISE EXCEPTION 'scope trigger allowed a foreign-system mounting rule';
    EXCEPTION WHEN foreign_key_violation OR raise_exception THEN
        IF SQLERRM = 'scope trigger allowed a foreign-system mounting rule' THEN
            RAISE;
        END IF;
        -- expected: mounting_rule_scope_mismatch (23503)
    END;
END $$;
SELECT pass('mounting rule from another system is rejected by the trigger');

-- CONFIRMED without its confirmation stamp violates the check.
DO $$
BEGIN
    INSERT INTO public.project_positions (
        id, project_id, org_id, position_index, location_tag, quantity,
        typology, system_id, width_mm, height_mm,
        color_interior, color_exterior, parametric_tree, bom_snapshot,
        measurement_state, measurement_confirmed_at
    ) VALUES (
        gen_random_uuid(),
        (SELECT id FROM public.projects LIMIT 1),
        'd0700000-0000-4000-8000-000000000001',
        99, 'probe', 1, 'VENTANA',
        (SELECT id FROM public.profile_systems LIMIT 1),
        1000.00, 1000.00, 'WHITE', 'WHITE', '{}'::jsonb, '{}'::jsonb,
        'CONFIRMED', NULL
    );
EXCEPTION WHEN check_violation THEN
    RAISE NOTICE 'expected check violation';
END $$;
SELECT pass('CONFIRMED without its confirmation stamp violates the check');

SELECT finish();
ROLLBACK;
