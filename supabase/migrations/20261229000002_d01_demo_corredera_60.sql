-- D01 (cont.): the DEMO_60 / DEMO_CORREDERA_60 split.
--
-- DEMO_60 was a casement system that also pretended to be a sliding one —
-- the same series cannot fabricate both families. The split gives the
-- sliding catalogue its own synthetic system (SLIDING family) and
-- repoints every saved sliding position from DEMO_60 to it. DEMO_60
-- keeps casement + door authority and gains the DOOR_SASH article its
-- door leaves actually use, plus its declared cut/reinforcement/limit
-- rules. All rows are SEED_SYNTHETIC: plausible values, never certified.

BEGIN;

DO $$
DECLARE
    demo60 UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60');
    corredera UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_CORREDERA_60');
BEGIN
    -- ------------------------------------------------------------------
    -- The sliding sibling system.
    -- ------------------------------------------------------------------
    INSERT INTO public.profile_systems (
        id, org_id, code, name, depth_mm, material, chamber_count,
        sash_overlap_mm, glass_clearance_white_mm, central_overlap_mm,
        sliding_end_add_mm, pulley_height_mm,
        sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
        door_leaf_side_clearance_mm, rebate_depth_mm, chamber_clearance_mm,
        system_family, is_global, is_demo, finishes, data_provenance
    )
    VALUES (
        corredera, NULL, 'DEMO_CORREDERA_60',
        'Sistema Demo Corredera 60mm PVC — referencia sintética',
        60.00, 'PVC', 3, 8.00, 5.00, 45.00, 6.00, 14.00,
        25.00, 25.00, 0.00, 20.00, 12.00,
        'SLIDING', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
        'SEED_SYNTHETIC'
    )
    ON CONFLICT (id) DO NOTHING;

    -- Inspector authority: the documentary freeze requires the fourteen
    -- rule configs and an explicit chamber clearance on every quotable
    -- system — same synthetic values as the other reference families.
    INSERT INTO public.inspector_rule_configs (id, system_id, org_id, rule_id, params)
    SELECT uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/shot07/config/' || corredera::text || '/' || cfg.rule_id),
        corredera, NULL, cfg.rule_id, cfg.params
    FROM (VALUES
        ('R01', '{}'::JSONB),
        ('R02', '{"min_ratio":"0.4000","max_ratio":"2.5000","suggested_ratio":"1.5000"}'::JSONB),
        ('R03', '{"min_width_mm":"350.00","max_width_mm":"1600.00","max_height_mm":"2400.00"}'::JSONB),
        ('R04', '{"monolithic_4_max_area_m2":"1.8000","dvh_4_any_4_max_area_m2":"2.6000"}'::JSONB),
        ('R05', '{"span_trigger_mm":"1800.00"}'::JSONB),
        ('R06', '{}'::JSONB),
        ('R07', '{"width_trigger_mm":"800.00","required_bottom_drains":3}'::JSONB),
        ('R08', '{"max_spacing_mm":"800.00"}'::JSONB),
        ('R09', '{"white_limit_mm":"4000.00","foiled_limit_mm":"3000.00"}'::JSONB),
        ('R10', '{"tolerance_mm":"1.50"}'::JSONB),
        ('R11', '{"expected_mm":"12.00","tolerance_mm":"1.50","suggested_sash_overlap_mm":"8.00"}'::JSONB),
        ('R12', '{"width_trigger_mm":"4500.00","minimum_ix_cm4":"45.0000"}'::JSONB),
        ('R13', '{"height_trigger_mm":"1200.00","required_stay_arms":2}'::JSONB),
        ('R14', '{"weight_trigger_kg":"150.00","required_carriages":4,"minimum_capacity_kg":"80.00"}'::JSONB)
    ) cfg(rule_id, params)
    ON CONFLICT (system_id, org_id, rule_id) DO NOTHING;

    -- Keep DEMO_60 honest: a casement series that also sells balcony/entry
    -- door leaves — CASEMENT family, sliding deductions retained because
    -- legacy positions may still read them, but it no longer fabricates
    -- sliding typologies.
    UPDATE public.profile_systems
        SET system_family = 'CASEMENT'
        WHERE id = demo60;

    -- ------------------------------------------------------------------
    -- Corredera articles (roles introduced by D01).
    -- ------------------------------------------------------------------
    INSERT INTO public.profile_articles (
        id, system_id, org_id, sku, name, role, material,
        face_width_mm, commercial_length_mm, welding_loss_mm,
        reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_CORREDERA_60/' || sku),
        corredera, NULL, sku, name, role::public.profile_role, 'PVC',
        face_width_mm, 6000.00, welding_loss_mm,
        15.00, weight_kg_m, 1.7000, 'SEED_SYNTHETIC'
    FROM (VALUES
        ('MARCO-CORR',      'Marco Corredera Demo 60',       'FRAME',        50.00, 6.00, 1.9000),
        ('RIEL-CORR',       'Riel Inferior Corredera Demo',  'RAIL',         52.00, 6.00, 2.0000),
        ('HOJA-CORR',       'Hoja Corredera Demo 60',        'SLIDING_SASH', 42.00, 6.00, 1.6000),
        ('ENCUENTRO-CORR',  'Encuentro Corredera Demo 60',   'INTERLOCK',    38.00, 6.00, 1.4500),
        ('POSTE-CORR-V',    'Poste Vertical Corredera Demo', 'MULLION_V',    60.00, 0.00, 1.7000),
        ('POSTE-CORR-H',    'Travesaño Corredera Demo',      'MULLION_H',    60.00, 0.00, 1.7000),
        ('JQ-CORR-24',      'Junquillo Corredera 24mm',      'GLAZING_BEAD', 24.00, 0.00, 0.3000),
        ('JQ-CORR-14',      'Junquillo Corredera 14mm',      'GLAZING_BEAD', 14.00, 0.00, 0.2500),
        ('JQ-CORR-10',      'Junquillo Corredera 10mm',      'GLAZING_BEAD', 10.00, 0.00, 0.2200),
        ('COPLE-CORR',      'Cople Corredera Demo',          'COUPLER',      30.00, 0.00, 0.4000)
    ) AS a(sku, name, role, face_width_mm, welding_loss_mm, weight_kg_m)
    ON CONFLICT (system_id, sku) DO NOTHING;


    -- ------------------------------------------------------------------
    -- Glazing beads for the corredera (same convention as DEMO_60: the
    -- bead article is chosen by infill thickness).
    -- ------------------------------------------------------------------
    INSERT INTO public.glazing_bead_matrix (
        id, system_id, org_id, glass_thickness_mm, bead_article_id,
        bead_width_mm, gasket_interior_mm, gasket_exterior_mm, cut_add_mm
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/DEMO_CORREDERA_60/bead/' || t || '/' || bead_sku),
        corredera, NULL, t,
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/DEMO_CORREDERA_60/' || bead_sku),
        bead_w, 3.00, 3.00, 9.00
    FROM (VALUES (4.00::numeric, 'JQ-CORR-24'::text, 24.00::numeric),
                 (20.00::numeric, 'JQ-CORR-14'::text, 14.00::numeric),
                 (24.00::numeric, 'JQ-CORR-10'::text, 10.00::numeric)) AS b(t, bead_sku, bead_w)
    ON CONFLICT (system_id, glass_thickness_mm) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Hardware kits: dual-rail plus its monorail sibling.
    -- ------------------------------------------------------------------
    INSERT INTO public.hardware_kits (
        id, org_id, system_id, sku, name, opening_type,
        min_leaf_width_mm, max_leaf_width_mm,
        min_leaf_height_mm, max_leaf_height_mm,
        max_leaf_weight_kg, rail_type, carriages_qty, stay_arms_qty,
        contents, weight_kg, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/DEMO_CORREDERA_60/' || sku),
        NULL, corredera, sku, name, 'SLIDING',
        400.00, 1500.00, 500.00, 2500.00, 120.00,
        rail, carriages, 0, contents::jsonb, weight, 'SEED_SYNTHETIC'
    FROM (VALUES
        ('KIT-SLIDING-CORR', 'Kit Corredera Demo Corredera 60', 'dual', 2,
         2.50, '[{"sku":"DEMO-CAR-DOBLE","name":"Carro doble corredera Demo","qty":2,"unit":"set","category":"ROLLER"},{"sku":"DEMO-MAN-CORR","name":"Cierre corredera Demo","qty":1,"unit":"set","category":"LOCK"}]'),
        ('KIT-SLIDING-CORR-MONO', 'Kit Corredera Mono Demo 60', 'mono', 1,
         2.10, '[{"sku":"DEMO-CAR-MONO","name":"Carro monorriel corredera Demo","qty":1,"unit":"set","category":"ROLLER"},{"sku":"DEMO-MAN-CORR","name":"Cierre corredera Demo","qty":1,"unit":"set","category":"LOCK"}]')
    ) AS k(sku, name, rail, carriages, weight, contents)
    ON CONFLICT (system_id, sku) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Declared cut rules (same values the engine fixture freezes).
    -- ------------------------------------------------------------------
    INSERT INTO public.profile_cut_rules (
        id, system_id, org_id, role, cut_angle_deg, welded_ends,
        interlock_deduction_mm, rounding_mm, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/cutrule/' || role),
        sys_id, NULL, role::public.profile_role, angle, welded, deduction, rounding,
        'SEED_SYNTHETIC'
    FROM (VALUES
        (corredera, 'DEMO_CORREDERA_60', 'FRAME',        45.00, 2, 0.00,  0.01),
        (corredera, 'DEMO_CORREDERA_60', 'RAIL',         45.00, 2, 0.00,  0.01),
        (corredera, 'DEMO_CORREDERA_60', 'SLIDING_SASH', 45.00, 2, 0.00,  0.01),
        (corredera, 'DEMO_CORREDERA_60', 'INTERLOCK',    45.00, 2, 18.00, 0.01),
        (corredera, 'DEMO_CORREDERA_60', 'MULLION_V',    90.00, 0, 0.00,  0.01),
        (corredera, 'DEMO_CORREDERA_60', 'MULLION_H',    90.00, 0, 0.00,  0.01),
        (corredera, 'DEMO_CORREDERA_60', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01)
    ) AS r(sys_id, sys_code, role, angle, welded, deduction, rounding)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- Reinforcement as data: WHITE members need steel from 1 m; foiled
    -- members are always reinforced (thermal expansion).
    -- ------------------------------------------------------------------
    INSERT INTO public.profile_reinforcement_rules (
        id, system_id, org_id, role, finish_class, min_length_mm,
        mandatory, screws_per_m, screw_sku, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/reinforce/' || role || '/' || finish || '/' || min_len),
        sys_id, NULL, role::public.profile_role, finish, min_len,
        TRUE, 4.00, 'TORNILLO-4X16', 'SEED_SYNTHETIC'
    FROM (
        SELECT corredera AS sys_id, 'DEMO_CORREDERA_60' AS sys_code,
               role, finish, min_len
        FROM (VALUES
            ('FRAME'), ('RAIL'), ('SLIDING_SASH'), ('INTERLOCK'),
            ('MULLION_V'), ('MULLION_H')
        ) AS roles(role)
        CROSS JOIN (VALUES
            ('WHITE'::text, 1000.00::numeric),
            ('NON_WHITE'::text, 0.00::numeric)
        ) AS classes(finish, min_len)
    ) AS rr(sys_id, sys_code, role, finish, min_len)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- Leaf dimensional limits per typology.
    -- ------------------------------------------------------------------
    INSERT INTO public.system_typology_limits (
        id, system_id, org_id, opening_type,
        min_leaf_width_mm, max_leaf_width_mm,
        min_leaf_height_mm, max_leaf_height_mm,
        max_leaf_weight_kg, max_aspect_ratio, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/limits/' || opening),
        sys_id, NULL, opening,
        min_w::numeric, max_w::numeric, min_h::numeric, max_h::numeric,
        max_kg::numeric, aspect::numeric,
        'SEED_SYNTHETIC'
    FROM (VALUES
        (corredera, 'DEMO_CORREDERA_60', 'SLIDING_2L',      400.00, 1500.00, 500.00, 2500.00, 120.00, NULL),
        (corredera, 'DEMO_CORREDERA_60', 'SLIDING_3L',      400.00, 1500.00, 500.00, 2500.00, 120.00, NULL),
        (corredera, 'DEMO_CORREDERA_60', 'SLIDING_4L',      400.00, 1500.00, 500.00, 2500.00, 120.00, NULL),
        (corredera, 'DEMO_CORREDERA_60', 'SLIDING',         400.00, 1500.00, 500.00, 2500.00, 120.00, NULL)
    ) AS l(sys_id, sys_code, opening, min_w, max_w, min_h, max_h, max_kg, aspect)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- DEMO_60 rows: only when the seeded system is actually present (a
    -- bare `supabase db reset` applies migrations before seed.sql — the
    -- same rows are shipped there for fresh clones).
    -- ------------------------------------------------------------------
    IF EXISTS (SELECT 1 FROM public.profile_systems WHERE id = demo60) THEN
        -- DEMO_60 door leaves ride on a dedicated door sash, like real
        -- casement series — SASH (75 mm) is the window leaf, DOOR_SASH
        -- (90 mm) is the door one.
        INSERT INTO public.profile_articles (
            id, system_id, org_id, sku, name, role, material,
            face_width_mm, commercial_length_mm, welding_loss_mm,
            reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m, data_provenance
        )
        VALUES (
            uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/HOJA-PUERTA'),
            demo60, NULL, 'HOJA-PUERTA', 'Hoja Puerta Demo 60', 'DOOR_SASH', 'PVC',
            90.00, 6000.00, 6.00, 15.00, 2.4000, 1.7000, 'SEED_SYNTHETIC'
        )
        ON CONFLICT (system_id, sku) DO NOTHING;

        INSERT INTO public.profile_cut_rules (
            id, system_id, org_id, role, cut_angle_deg, welded_ends,
            interlock_deduction_mm, rounding_mm, data_provenance
        )
        SELECT
            uuid_generate_v5(uuid_ns_url(),
                'https://dekopen.local/catalog/DEMO_60/cutrule/' || role),
            demo60, NULL, role::public.profile_role, angle, welded, deduction, rounding,
            'SEED_SYNTHETIC'
        FROM (VALUES
            ('FRAME',        45.00, 2, 0.00,  0.01),
            ('SASH',         45.00, 2, 0.00,  0.01),
            ('DOOR_SASH',    45.00, 2, 0.00,  0.01),
            ('MULLION_V',    90.00, 0, 0.00,  0.01),
            ('MULLION_H',    90.00, 0, 0.00,  0.01),
            ('GLAZING_BEAD', 45.00, NULL, 0.00, 0.01),
            ('THRESHOLD',    90.00, NULL, 0.00, 0.01)
        ) AS r(role, angle, welded, deduction, rounding)
        ON CONFLICT DO NOTHING;

        INSERT INTO public.profile_reinforcement_rules (
            id, system_id, org_id, role, finish_class, min_length_mm,
            mandatory, screws_per_m, screw_sku, data_provenance
        )
        SELECT
            uuid_generate_v5(uuid_ns_url(),
                'https://dekopen.local/catalog/DEMO_60/reinforce/' || role || '/' || finish || '/' || min_len),
            demo60, NULL, role::public.profile_role, finish, min_len,
            TRUE, 4.00, 'TORNILLO-4X16', 'SEED_SYNTHETIC'
        FROM (VALUES
            ('FRAME'), ('SASH'), ('DOOR_SASH'), ('MULLION_V'), ('MULLION_H')
        ) AS roles(role)
        CROSS JOIN (VALUES
            ('WHITE'::text, 1000.00::numeric),
            ('NON_WHITE'::text, 0.00::numeric)
        ) AS classes(finish, min_len)
        ON CONFLICT DO NOTHING;

        INSERT INTO public.system_typology_limits (
            id, system_id, org_id, opening_type,
            min_leaf_width_mm, max_leaf_width_mm,
            min_leaf_height_mm, max_leaf_height_mm,
            max_leaf_weight_kg, max_aspect_ratio, data_provenance
        )
        SELECT
            uuid_generate_v5(uuid_ns_url(),
                'https://dekopen.local/catalog/DEMO_60/limits/' || opening),
            demo60, NULL, opening,
            min_w::numeric, max_w::numeric, min_h::numeric, max_h::numeric,
            max_kg::numeric, aspect::numeric,
            'SEED_SYNTHETIC'
        FROM (VALUES
            ('TURN_LEFT',       350.00, 1400.00, 400.00, 2500.00, 100.00, 2.80),
            ('TILT_TURN_RIGHT', 450.00, 1600.00, 450.00, 2500.00, 130.00, NULL),
            ('AWNING',          400.00, 1800.00, 350.00, 1200.00, 45.00,  NULL),
            ('DOOR_ENTRY',      600.00, 1100.00, 1700.00, 2500.00, 120.00, NULL)
        ) AS l(opening, min_w, max_w, min_h, max_h, max_kg, aspect)
        ON CONFLICT DO NOTHING;

        -- --------------------------------------------------------------
        -- Manufacturing authorities for the corredera — copies of the demo
    -- placement/reinforcement policies plus the sliding-only subset of the
    -- handle policy (a corredera never mounts a casement handle).
    -- ------------------------------------------------------------------
    INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
    SELECT
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/DEMO_CORREDERA_60/V2'),
        corredera, NULL, version,
        jsonb_set(authority, '{policy_id}', '"DEMO_CORREDERA_60_PLACEMENT_V2"')
    FROM public.manufacturing_placement_policies
    WHERE system_id = demo60
    ORDER BY version DESC LIMIT 1
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.handle_requirement_policies (id, system_id, org_id, version, authority)
    SELECT
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/handles/DEMO_CORREDERA_60/V2'),
        corredera, NULL, version,
        jsonb_set(
            jsonb_set(authority, '{policy_id}', '"DEMO_CORREDERA_60_HANDLES_V2"'),
            '{slots}', (
                SELECT jsonb_agg(slot)
                FROM jsonb_array_elements(authority -> 'slots') AS slot
                WHERE slot ->> 'opening_type' LIKE 'SLIDING%'
            )
        )
    FROM public.handle_requirement_policies
    WHERE system_id = demo60
    ORDER BY version DESC LIMIT 1
    ON CONFLICT (id) DO NOTHING;

    -- Reinforcement-cut authorities are generated from each system's own
    -- declared reinforcement roles — a verbatim copy of DEMO_60's V1 would
    -- leave the sliding roles (SLIDING_SASH, INTERLOCK, RAIL) and the new
    -- DOOR_SASH without a rule, and the documentary freeze refuses members
    -- whose (role, angle_left, angle_right) has no authority. Welded
    -- members declare every 45°/90° combination the family can emit;
    -- sawn mullions and thresholds only meet square cuts.
    INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
    SELECT
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/DEMO_CORREDERA_60/V1'),
        corredera, NULL, 1,
        jsonb_build_object(
            'schema_version', 1,
            'policy_id', 'DEMO_CORREDERA_60_REINFORCEMENT_CUT_V1',
            'version', 1,
            'rules', gen.rules
        )
    FROM (SELECT corredera AS system_id) target
    CROSS JOIN LATERAL (
        SELECT jsonb_agg(jsonb_build_object(
            'role', rr.role,
            'profile_angle_left', c.angle_left,
            'profile_angle_right', c.angle_right,
            'reinforcement_angle_left', 90.0,
            'reinforcement_angle_right', 90.0,
            'length_authority', 'EXISTING_ENGINE',
            'compatible_with_existing_length', true
        ) ORDER BY rr.role, c.angle_left, c.angle_right) AS rules
        FROM (SELECT DISTINCT role::text AS role
              FROM public.profile_reinforcement_rules
              WHERE system_id = corredera) rr
        CROSS JOIN LATERAL (
            SELECT 90.00 AS angle_left, 90.00 AS angle_right
            WHERE rr.role IN ('MULLION_V','MULLION_H','THRESHOLD')
            UNION ALL
            SELECT v.al, v.ar FROM (VALUES
                (45.00,45.00),(45.00,90.00),(90.00,45.00),(90.00,90.00)
            ) AS v(al,ar)
            WHERE rr.role NOT IN ('MULLION_V','MULLION_H','THRESHOLD')
        ) c
    ) gen
    ON CONFLICT (id) DO NOTHING;

    -- DEMO_60 ships V2 with the D01 roles included: its V1 predates
    -- DOOR_SASH and authorities are immutable once issued.
    INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
    SELECT
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/DEMO_60/V2'),
        demo60, NULL, 2,
        jsonb_build_object(
            'schema_version', 1,
            'policy_id', 'DEMO_60_REINFORCEMENT_CUT_V2',
            'version', 2,
            'rules', gen.rules
        )
    FROM (SELECT demo60 AS system_id) target
    CROSS JOIN LATERAL (
        SELECT jsonb_agg(jsonb_build_object(
            'role', rr.role,
            'profile_angle_left', c.angle_left,
            'profile_angle_right', c.angle_right,
            'reinforcement_angle_left', 90.0,
            'reinforcement_angle_right', 90.0,
            'length_authority', 'EXISTING_ENGINE',
            'compatible_with_existing_length', true
        ) ORDER BY rr.role, c.angle_left, c.angle_right) AS rules
        FROM (SELECT DISTINCT role::text AS role
              FROM public.profile_reinforcement_rules
              WHERE system_id = demo60) rr
        CROSS JOIN LATERAL (
            SELECT 90.00 AS angle_left, 90.00 AS angle_right
            WHERE rr.role IN ('MULLION_V','MULLION_H','THRESHOLD')
            UNION ALL
            SELECT v.al, v.ar FROM (VALUES
                (45.00,45.00),(45.00,90.00),(90.00,45.00),(90.00,90.00)
            ) AS v(al,ar)
            WHERE rr.role NOT IN ('MULLION_V','MULLION_H','THRESHOLD')
        ) c
    ) gen
    ON CONFLICT (id) DO NOTHING;
    END IF;

    -- Purchase references and steel stock for every member the new systems
    -- can emit — readiness probes resolve them exactly like the
    -- long-standing DEMO_60 rows (NOT EXISTS keeps prior shot-07
    -- authorities untouched).
    INSERT INTO public.profile_purchase_mappings
        (id, profile_article_id, org_id, commercial_sku, manufacturer_name,
         supplier_name, purchase_unit, physical_stock_identity, stock_color,
         cutting_profile_id, binding_version)
    SELECT uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/shot07/purchase/' || article.id::text),
        article.id, NULL, 'COMPRA-' || article.sku, 'Referencia DEKOPEN',
        'Proveedor de referencia', 'BAR',
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/shot09/physical/profile/' || article.id::text),
        'WHITE',
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'),
        1
    FROM public.profile_articles article
    WHERE article.system_id IN (demo60, corredera) AND article.org_id IS NULL
      AND NOT EXISTS (
          SELECT 1 FROM public.profile_purchase_mappings m
          WHERE m.profile_article_id = article.id AND m.org_id IS NULL)
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.reinforcement_articles
        (id, system_id, org_id, parent_profile_article_id, sku,
         commercial_sku, name, manufacturer_name, supplier_name,
         stock_length_mm, purchase_unit, is_default,
         physical_stock_identity, stock_color, cutting_profile_id,
         binding_version)
    SELECT uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/shot07/steel/' || article.id::text),
        article.system_id, NULL, article.id, 'ACERO-' || article.sku,
        'COMPRA-ACERO-' || article.sku, 'Acero ' || article.name,
        'Referencia DEKOPEN', 'Proveedor de referencia', 6000.00, 'BAR',
        TRUE,
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/shot09/physical/steel/' || article.id::text),
        'WHITE',
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'),
        1
    FROM public.profile_articles article
    WHERE article.system_id IN (demo60, corredera) AND article.org_id IS NULL
      AND article.role NOT IN ('GLAZING_BEAD', 'THRESHOLD')
      AND NOT EXISTS (
          SELECT 1 FROM public.reinforcement_articles r
          WHERE r.parent_profile_article_id = article.id
            AND r.org_id IS NULL)
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.fitting_purchase_mappings
        (id, system_id, org_id, technical_sku, purchasing_sku,
         manufacturer_name, purchase_unit, version, provenance)
    SELECT uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/fitting/TORNILLO-4X16/V1'),
        sys_id, NULL, 'TORNILLO-4X16', 'COMPRA-TORNILLO-4X16',
        'Referencia DEKOPEN', 'EA', 1,
        '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
    FROM (VALUES (demo60, 'DEMO_60'), (corredera, 'DEMO_CORREDERA_60')) AS t(sys_id, sys_code)
    WHERE EXISTS (SELECT 1 FROM public.profile_systems s WHERE s.id = t.sys_id)
    ON CONFLICT (system_id, org_id, technical_sku, version) DO NOTHING;

    -- ------------------------------------------------------------------
    -- The split itself: saved sliding positions move to the sliding
    -- system. ON DELETE RESTRICT keeps the old row safe; we repoint, we
    -- never recompute the position (its bom_snapshot stays as-is and the
    -- editor recomputes on open).
    -- ------------------------------------------------------------------
    UPDATE public.project_positions
        SET system_id = corredera, updated_at = clock_timestamp()
        WHERE system_id = demo60
          AND typology IN ('SLIDING', 'SLIDING_2L', 'SLIDING_3L', 'SLIDING_4L');
END;
$$;

COMMIT;
