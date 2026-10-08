-- D08 — Tipologías avanzadas: familias de fabricación y sistemas DEMO.
--
-- El dominio `system_family` gana las cuatro familias que D03 ya declara en
-- el motor (PARALLEL_SLIDE, FOLDING, PIVOT, VERTICAL_SLIDE); las capacidades
-- admiten composiciones de más de un par (plegable 3+0 … n+m, hasta 8 hojas
-- como el motor). Seis sistemas sintéticos cubren el repertorio del encargo —
-- elevable (HST), osciloparalela (PSK), plegable, pivotante, guillotina y
-- puerta corredera — cada uno con artículos, junquillos, kits, reglas de
-- corte/refuerzo, límites de tipología, capacidades declaradas y las catorce
-- configs de inspector que el congelado documental exige. Todo es
-- SEED_SYNTHETIC: valores plausibles de referencia, nunca certificados.

BEGIN;

-- ------------------------------------------------------------------
-- Dominio de familia extendido.
-- ------------------------------------------------------------------
ALTER TABLE public.profile_systems
    DROP CONSTRAINT IF EXISTS profile_systems_system_family_check;
ALTER TABLE public.profile_systems
    ADD CONSTRAINT profile_systems_system_family_check
        CHECK (system_family IN (
            'CASEMENT', 'SLIDING', 'LIFT_SLIDE', 'DOOR', 'FACADE_FIXED',
            'PARALLEL_SLIDE', 'FOLDING', 'PIVOT', 'VERTICAL_SLIDE'));

-- Una composición plegable cabe en más de dos hojas (el motor admite 8).
ALTER TABLE public.system_opening_capabilities
    DROP CONSTRAINT IF EXISTS system_opening_capabilities_max_leaves_check;
ALTER TABLE public.system_opening_capabilities
    ADD CONSTRAINT system_opening_capabilities_max_leaves_check
        CHECK (max_leaves BETWEEN 1 AND 8);

-- Familias de kit D08: elevable, osciloparalela, plegable (carros+guías
-- del paquete), pivote, guillotina y la hoja corredera de puerta.
ALTER TABLE public.hardware_kits DROP CONSTRAINT chk_kits_opening_type;
ALTER TABLE public.hardware_kits
    ADD CONSTRAINT chk_kits_opening_type CHECK (
        opening_type IN ('AWNING', 'BOTTOM_HUNG', 'DOOR', 'FALLEBA',
                         'SLIDING', 'TILT', 'TILT_TURN', 'TURN',
                         'LIFT_SLIDE', 'PARALLEL_SLIDE', 'FOLD', 'PIVOT',
                         'VERTICAL_SLIDE', 'DOOR_SLIDING'));

DO $$
DECLARE
    elev UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_ELEVACION_90');
    psk UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_PSK_90');
    fold UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_PLEGABLE_70');
    piv UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_PIVOTANTE_120');
    gui UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_GUILLOTINA_60');
    pcorr UUID := uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_PUERTA_CORREDERA_70');
BEGIN
    -- ------------------------------------------------------------------
    -- Sistemas: una serie sintética por familia de fabricación.
    -- ------------------------------------------------------------------
    INSERT INTO public.profile_systems (
        id, org_id, code, name, depth_mm, material, chamber_count,
        sash_overlap_mm, glass_clearance_white_mm, central_overlap_mm,
        sliding_end_add_mm, pulley_height_mm,
        sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
        door_leaf_side_clearance_mm, rebate_depth_mm, end_milling_overlap_mm,
        chamber_clearance_mm,
        system_family, is_global, is_demo, finishes, data_provenance
    )
    VALUES
        (elev, NULL, 'DEMO_ELEVACION_90',
         'Sistema Demo Elevable HST 90mm PVC — referencia sintética',
         90.00, 'PVC', 4, 8.00, 5.00, 55.00, 8.00, 20.00,
         28.00, 28.00, 6.00, 20.00, 0.00, 12.00,
         'LIFT_SLIDE', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
         'SEED_SYNTHETIC'),
        (psk, NULL, 'DEMO_PSK_90',
         'Sistema Demo Osciloparalela PSK 90mm PVC — referencia sintética',
         90.00, 'PVC', 4, 8.00, 5.00, 42.00, 6.00, 16.00,
         26.00, 26.00, 6.00, 20.00, 0.00, 12.00,
         'PARALLEL_SLIDE', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
         'SEED_SYNTHETIC'),
        (fold, NULL, 'DEMO_PLEGABLE_70',
         'Sistema Demo Plegable 70mm PVC — referencia sintética',
         70.00, 'PVC', 3, 8.00, 5.00, 40.00, 6.00, 12.00,
         22.00, 22.00, 6.00, 20.00, 0.00, 12.00,
         'FOLDING', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
         'SEED_SYNTHETIC'),
        (piv, NULL, 'DEMO_PIVOTANTE_120',
         'Sistema Demo Pivotante 120mm PVC — referencia sintética',
         120.00, 'PVC', 5, 8.00, 5.00, 40.00, 6.00, 12.00,
         24.00, 24.00, 6.00, 20.00, 0.00, 12.00,
         'PIVOT', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
         'SEED_SYNTHETIC'),
        (gui, NULL, 'DEMO_GUILLOTINA_60',
         'Sistema Demo Guillotina 60mm PVC — referencia sintética',
         60.00, 'PVC', 3, 8.00, 5.00, 30.00, 6.00, 14.00,
         20.00, 20.00, 0.00, 20.00, 0.00, 12.00,
         'VERTICAL_SLIDE', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
         'SEED_SYNTHETIC'),
        (pcorr, NULL, 'DEMO_PUERTA_CORREDERA_70',
         'Sistema Demo Puerta Corredera 70mm PVC — referencia sintética',
         90.00, 'PVC', 4, 8.00, 5.00, 55.00, 8.00, 20.00,
         28.00, 28.00, 6.00, 20.00, 0.00, 12.00,
         'SLIDING', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb,
         'SEED_SYNTHETIC')
    ON CONFLICT (id) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Autoridad del inspector: las catorce configs que un sistema
    -- cotizable debe declarar (mismos valores sintéticos de las demás
    -- familias de referencia).
    -- ------------------------------------------------------------------
    INSERT INTO public.inspector_rule_configs (id, system_id, org_id, rule_id, params)
    SELECT uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/shot07/config/' || sys_id::text || '/' || cfg.rule_id),
        sys_id, NULL, cfg.rule_id, cfg.params
    FROM (VALUES (elev), (psk), (fold), (piv), (gui), (pcorr)) AS systems(sys_id)
    CROSS JOIN (VALUES
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

    -- ------------------------------------------------------------------
    -- Artículos de perfil por sistema.
    -- ------------------------------------------------------------------
    INSERT INTO public.profile_articles (
        id, system_id, org_id, sku, name, role, material,
        face_width_mm, commercial_length_mm, welding_loss_mm,
        reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/' || sku),
        sys_id, NULL, sku, name, role::public.profile_role, 'PVC',
        face_width_mm, 6000.00, welding_loss_mm,
        gap_mm, 1.2000, 1.7000, 'SEED_SYNTHETIC'
    FROM (VALUES
        -- Elevable HST: marco + riel + hoja corredera + encuentro + umbral.
        (elev, 'DEMO_ELEVACION_90', 'MARCO-ELEV',     'Marco Elevación Demo 90',        'FRAME',        58.00, 6.00, 15.00),
        (elev, 'DEMO_ELEVACION_90', 'RIEL-ELEV',      'Riel Inferior Elevación Demo',   'RAIL',         42.00, 6.00, 15.00),
        (elev, 'DEMO_ELEVACION_90', 'HOJA-ELEV',      'Hoja Elevable Demo 90',          'SLIDING_SASH', 52.00, 6.00, 15.00),
        (elev, 'DEMO_ELEVACION_90', 'ENC-ELEV',       'Encuentro Elevación Demo',       'INTERLOCK',    40.00, 6.00, 15.00),
        (elev, 'DEMO_ELEVACION_90', 'UMBRAL-ELEV',    'Umbral Elevable Demo',           'THRESHOLD',    25.00, 0.00, 0.00),
        (elev, 'DEMO_ELEVACION_90', 'POSTE-ELEV-V',   'Poste Vertical Elevación Demo',  'MULLION_V',    70.00, 0.00, 5.00),
        (elev, 'DEMO_ELEVACION_90', 'POSTE-ELEV-H',   'Travesaño Elevación Demo',       'MULLION_H',    70.00, 0.00, 5.00),
        (elev, 'DEMO_ELEVACION_90', 'JQ-ELEV-24',     'Junquillo Elevación 24mm',       'GLAZING_BEAD', 24.00, 0.00, 15.00),
        (elev, 'DEMO_ELEVACION_90', 'JQ-ELEV-10',     'Junquillo Elevación 10mm',       'GLAZING_BEAD', 10.00, 0.00, 15.00),
        -- Osciloparalela PSK.
        (psk, 'DEMO_PSK_90', 'MARCO-PSK',   'Marco Osciloparalela Demo 90',      'FRAME',        52.00, 6.00, 15.00),
        (psk, 'DEMO_PSK_90', 'RIEL-PSK',    'Riel Osciloparalela Demo',          'RAIL',         45.00, 6.00, 15.00),
        (psk, 'DEMO_PSK_90', 'HOJA-PSK',    'Hoja Osciloparalela Demo 90',       'SLIDING_SASH', 46.00, 6.00, 15.00),
        (psk, 'DEMO_PSK_90', 'ENC-PSK',     'Encuentro Osciloparalela Demo',     'INTERLOCK',    36.00, 6.00, 15.00),
        (psk, 'DEMO_PSK_90', 'POSTE-PSK-V', 'Poste Vertical Osciloparalela Demo','MULLION_V',    66.00, 0.00, 5.00),
        (psk, 'DEMO_PSK_90', 'POSTE-PSK-H', 'Travesaño Osciloparalela Demo',     'MULLION_H',    66.00, 0.00, 5.00),
        (psk, 'DEMO_PSK_90', 'JQ-PSK-24',   'Junquillo PSK 24mm',                'GLAZING_BEAD', 24.00, 0.00, 15.00),
        (psk, 'DEMO_PSK_90', 'JQ-PSK-10',   'Junquillo PSK 10mm',                'GLAZING_BEAD', 10.00, 0.00, 15.00),
        -- Plegable: marco + guía inferior + hoja plegable (perfil SASH).
        (fold, 'DEMO_PLEGABLE_70', 'MARCO-FOLD',   'Marco Plegable Demo 70',        'FRAME',        60.00, 6.00, 15.00),
        (fold, 'DEMO_PLEGABLE_70', 'GUIA-FOLD',    'Guía Inferior Plegable Demo',   'RAIL',         45.00, 6.00, 15.00),
        (fold, 'DEMO_PLEGABLE_70', 'HOJA-FOLD',    'Hoja Plegable Demo 70',         'SASH',         55.00, 6.00, 15.00),
        (fold, 'DEMO_PLEGABLE_70', 'POSTE-FOLD-V', 'Poste Vertical Plegable Demo',  'MULLION_V',    70.00, 0.00, 5.00),
        (fold, 'DEMO_PLEGABLE_70', 'POSTE-FOLD-H', 'Travesaño Plegable Demo',       'MULLION_H',    70.00, 0.00, 5.00),
        (fold, 'DEMO_PLEGABLE_70', 'JQ-FOLD-24',   'Junquillo Plegable 24mm',       'GLAZING_BEAD', 24.00, 0.00, 15.00),
        (fold, 'DEMO_PLEGABLE_70', 'JQ-FOLD-10',   'Junquillo Plegable 10mm',       'GLAZING_BEAD', 10.00, 0.00, 15.00),
        -- Pivotante: marco + hoja ventana + hoja puerta + umbral.
        (piv, 'DEMO_PIVOTANTE_120', 'MARCO-PIV',    'Marco Pivotante Demo 120',      'FRAME',        75.00, 6.00, 15.00),
        (piv, 'DEMO_PIVOTANTE_120', 'HOJA-PIV-V',   'Hoja Pivotante Ventana Demo',   'SASH',         70.00, 6.00, 15.00),
        (piv, 'DEMO_PIVOTANTE_120', 'HOJA-PIV',     'Hoja Pivotante Puerta Demo',    'DOOR_SASH',    95.00, 6.00, 15.00),
        (piv, 'DEMO_PIVOTANTE_120', 'UMBRAL-PIV',   'Umbral Pivotante Demo',         'THRESHOLD',    25.00, 0.00, 0.00),
        (piv, 'DEMO_PIVOTANTE_120', 'POSTE-PIV-V',  'Poste Vertical Pivotante Demo', 'MULLION_V',    80.00, 0.00, 5.00),
        (piv, 'DEMO_PIVOTANTE_120', 'POSTE-PIV-H',  'Travesaño Pivotante Demo',      'MULLION_H',    80.00, 0.00, 5.00),
        (piv, 'DEMO_PIVOTANTE_120', 'JQ-PIV-24',    'Junquillo Pivotante 24mm',      'GLAZING_BEAD', 24.00, 0.00, 15.00),
        (piv, 'DEMO_PIVOTANTE_120', 'JQ-PIV-10',    'Junquillo Pivotante 10mm',      'GLAZING_BEAD', 10.00, 0.00, 15.00),
        -- Guillotina: marco con correderas en jamba + hoja corredera + travesaño
        -- de encuentro entre hojas apiladas.
        (gui, 'DEMO_GUILLOTINA_60', 'MARCO-GUI',    'Marco Guillotina Demo 60',      'FRAME',        50.00, 6.00, 15.00),
        (gui, 'DEMO_GUILLOTINA_60', 'HOJA-GUI',     'Hoja Guillotina Demo 60',       'SLIDING_SASH', 38.00, 6.00, 15.00),
        (gui, 'DEMO_GUILLOTINA_60', 'TRAVES-GUI',   'Travesaño Encuentro Guillotina','INTERLOCK',    34.00, 6.00, 15.00),
        (gui, 'DEMO_GUILLOTINA_60', 'POSTE-GUI-V',  'Poste Vertical Guillotina Demo','MULLION_V',    60.00, 0.00, 5.00),
        (gui, 'DEMO_GUILLOTINA_60', 'POSTE-GUI-H',  'Travesaño Guillotina Demo',     'MULLION_H',    60.00, 0.00, 5.00),
        (gui, 'DEMO_GUILLOTINA_60', 'JQ-GUI-24',    'Junquillo Guillotina 24mm',     'GLAZING_BEAD', 24.00, 0.00, 15.00),
        (gui, 'DEMO_GUILLOTINA_60', 'JQ-GUI-10',    'Junquillo Guillotina 10mm',     'GLAZING_BEAD', 10.00, 0.00, 15.00),
        -- Puerta corredera: misma geometría de serie corredera con umbral.
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'MARCO-PCORR',   'Marco Puerta Corredera Demo',     'FRAME',        58.00, 6.00, 15.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'RIEL-PCORR',    'Riel Puerta Corredera Demo',      'RAIL',         42.00, 6.00, 15.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'HOJA-PCORR',    'Hoja Puerta Corredera Demo',      'SLIDING_SASH', 52.00, 6.00, 15.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'ENC-PCORR',     'Encuentro Puerta Corredera Demo', 'INTERLOCK',    40.00, 6.00, 15.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'UMBRAL-PCORR',  'Umbral Puerta Corredera Demo',    'THRESHOLD',    25.00, 0.00, 0.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'POSTE-PCORR-V', 'Poste Vertical Pta Corredera',    'MULLION_V',    70.00, 0.00, 5.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'POSTE-PCORR-H', 'Travesaño Pta Corredera',         'MULLION_H',    70.00, 0.00, 5.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'JQ-PCORR-24',   'Junquillo Pta Corredera 24mm',    'GLAZING_BEAD', 24.00, 0.00, 15.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'JQ-PCORR-10',   'Junquillo Pta Corredera 10mm',    'GLAZING_BEAD', 10.00, 0.00, 15.00)
    ) AS a(sys_id, sys_code, sku, name, role, face_width_mm, welding_loss_mm, gap_mm)
    ON CONFLICT (system_id, sku) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Matriz de junquillos (por espesor de acristalamiento).
    -- ------------------------------------------------------------------
    INSERT INTO public.glazing_bead_matrix (
        id, system_id, org_id, glass_thickness_mm, bead_article_id,
        bead_width_mm, gasket_interior_mm, gasket_exterior_mm, cut_add_mm
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/bead/' || t || '/' || bead_sku),
        sys_id, NULL, t,
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/' || bead_sku),
        bead_w, 3.00, 3.00, 9.00
    FROM (VALUES
        (elev, 'DEMO_ELEVACION_90', 4.00::numeric, 'JQ-ELEV-24'::text, 24.00::numeric),
        (elev, 'DEMO_ELEVACION_90', 24.00, 'JQ-ELEV-10', 10.00),
        (psk, 'DEMO_PSK_90', 4.00, 'JQ-PSK-24', 24.00),
        (psk, 'DEMO_PSK_90', 24.00, 'JQ-PSK-10', 10.00),
        (fold, 'DEMO_PLEGABLE_70', 4.00, 'JQ-FOLD-24', 24.00),
        (fold, 'DEMO_PLEGABLE_70', 24.00, 'JQ-FOLD-10', 10.00),
        (piv, 'DEMO_PIVOTANTE_120', 4.00, 'JQ-PIV-24', 24.00),
        (piv, 'DEMO_PIVOTANTE_120', 24.00, 'JQ-PIV-10', 10.00),
        (gui, 'DEMO_GUILLOTINA_60', 4.00, 'JQ-GUI-24', 24.00),
        (gui, 'DEMO_GUILLOTINA_60', 24.00, 'JQ-GUI-10', 10.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 4.00, 'JQ-PCORR-24', 24.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 24.00, 'JQ-PCORR-10', 10.00)
    ) AS b(sys_id, sys_code, t, bead_sku, bead_w)
    ON CONFLICT (system_id, glass_thickness_mm) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Kits de herraje: cada familia D08 declara sus clases por peso; la
    -- puerta corredera monta el kit DOOR_SLIDING (carros + cerradura de
    -- patio) y la hoja de paso plegable resuelve TURN/DOOR como una hoja
    -- practicable.
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
            'https://dekopen.local/catalog/' || sys_code || '/' || sku),
        NULL, sys_id, sku, name, opening,
        min_w, max_w, min_h, max_h, max_kg,
        'dual', carriages, stays, contents::jsonb, weight, 'SEED_SYNTHETIC'
    FROM (VALUES
        -- HST: carros elevadores por clase de peso + manilla de elevación.
        (elev, 'DEMO_ELEVACION_90', 'KIT-HST-200', 'Kit Elevable HST 200kg Demo', 'LIFT_SLIDE',
         700.00, 3200.00, 800.00, 2800.00, 200.00, 2, 0, 4.80,
         '[{"sku":"DEMO-CAR-HST-200","name":"Carretilla elevadora 200kg Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-MANILLA-ELEV","name":"Manilla de elevación Demo","qty":1,"unit":"unit","category":"HANDLE"},{"sku":"DEMO-CIERRE-ELEV","name":"Cierre elevable Demo","qty":1,"unit":"unit","category":"LOCK"}]'),
        (elev, 'DEMO_ELEVACION_90', 'KIT-HST-400', 'Kit Elevable HST 400kg Reforzado Demo', 'LIFT_SLIDE',
         700.00, 3200.00, 800.00, 2800.00, 400.00, 4, 0, 7.20,
         '[{"sku":"DEMO-CAR-HST-400","name":"Carretilla elevadora reforzada 400kg Demo","qty":4,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-MANILLA-ELEV","name":"Manilla de elevación Demo","qty":1,"unit":"unit","category":"HANDLE"},{"sku":"DEMO-CIERRE-ELEV","name":"Cierre elevable Demo","qty":1,"unit":"unit","category":"LOCK"}]'),
        -- La serie elevable también fabrica la corredera estándar y la
        -- puerta corredera sobre el mismo riel.
        (elev, 'DEMO_ELEVACION_90', 'KIT-SLIDING-ELEV', 'Kit Corredera estándar Elevación 90', 'SLIDING',
         400.00, 1500.00, 500.00, 2500.00, 120.00, 2, 0, 2.50, '[]'),
        (elev, 'DEMO_ELEVACION_90', 'KIT-PTA-CORR-ELEV', 'Kit Puerta Corredera Elevación 90 Demo', 'DOOR_SLIDING',
         700.00, 1800.00, 1700.00, 2600.00, 160.00, 2, 0, 3.40,
         '[{"sku":"DEMO-CAR-PTA-ELEV","name":"Carretilla puerta corredera Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-CERR-PATIO","name":"Cerradura patio corredera Demo","qty":1,"unit":"unit","category":"LOCK"}]'),
        -- PSK: herraje basculante+paralelo por peso.
        (psk, 'DEMO_PSK_90', 'KIT-PSK-130', 'Kit Osciloparalela PSK 130kg Demo', 'PARALLEL_SLIDE',
         650.00, 1600.00, 600.00, 2400.00, 130.00, 2, 0, 3.60,
         '[{"sku":"DEMO-BOGIE-PSK","name":"Bogie osciloparalelo Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-BASC-PSK","name":"Brazo basculante PSK Demo","qty":2,"unit":"unit","category":"FITTING"},{"sku":"DEMO-MANILLA-PSK","name":"Manilla PSK Demo","qty":1,"unit":"unit","category":"HANDLE"}]'),
        (psk, 'DEMO_PSK_90', 'KIT-PSK-200', 'Kit Osciloparalela PSK 200kg Reforzado Demo', 'PARALLEL_SLIDE',
         650.00, 2000.00, 600.00, 2400.00, 200.00, 2, 0, 4.40,
         '[{"sku":"DEMO-BOGIE-PSK-R","name":"Bogie osciloparalelo reforzado Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-BASC-PSK","name":"Brazo basculante PSK Demo","qty":2,"unit":"unit","category":"FITTING"},{"sku":"DEMO-MANILLA-PSK","name":"Manilla PSK Demo","qty":1,"unit":"unit","category":"HANDLE"}]'),
        -- Plegable: carros de guía por hoja; la hoja de paso monta el kit
        -- de hoja practicable (TURN en ventana, DOOR en puerta).
        (fold, 'DEMO_PLEGABLE_70', 'KIT-FOLD-80', 'Kit Plegable 80kg Demo', 'FOLD',
         400.00, 1000.00, 800.00, 2600.00, 80.00, 2, 0, 3.10,
         '[{"sku":"DEMO-CAR-FOLD","name":"Carretilla de guía plegable Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-BISAGRA-FOLD","name":"Bisagra intermedia plegable Demo","qty":3,"unit":"unit","category":"HINGE"}]'),
        (fold, 'DEMO_PLEGABLE_70', 'KIT-FOLD-100', 'Kit Plegable 100kg Reforzado Demo', 'FOLD',
         400.00, 1000.00, 800.00, 2600.00, 100.00, 2, 0, 3.60,
         '[{"sku":"DEMO-CAR-FOLD-R","name":"Carretilla de guía plegable reforzada Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-BISAGRA-FOLD","name":"Bisagra intermedia plegable Demo","qty":3,"unit":"unit","category":"HINGE"}]'),
        (fold, 'DEMO_PLEGABLE_70', 'KIT-FOLD-PASO', 'Kit Hoja de Paso Plegable Demo', 'TURN',
         400.00, 1000.00, 800.00, 2600.00, 100.00, 0, 0, 1.80,
         '[{"sku":"DEMO-CIERRE-PASO","name":"Cierre hoja de paso Demo","qty":1,"unit":"unit","category":"LOCK"},{"sku":"DEMO-MANILLA-PASO","name":"Manilla hoja de paso Demo","qty":1,"unit":"unit","category":"HANDLE"}]'),
        (fold, 'DEMO_PLEGABLE_70', 'KIT-FOLD-PASO-DOOR', 'Kit Hoja de Paso Plegable Puerta Demo', 'DOOR',
         600.00, 1000.00, 1700.00, 2600.00, 120.00, 0, 0, 2.20,
         '[{"sku":"DEMO-CERR-PASO-PTA","name":"Cerradura hoja de paso puerta Demo","qty":1,"unit":"unit","category":"LOCK"},{"sku":"DEMO-MANILLA-PASO","name":"Manilla hoja de paso Demo","qty":1,"unit":"unit","category":"HANDLE"}]'),
        -- Pivotante: pivotes por clase (puerta 300 kg, ventana 80 kg).
        (piv, 'DEMO_PIVOTANTE_120', 'KIT-PIV-300', 'Kit Pivotante Puerta 300kg Demo', 'PIVOT',
         900.00, 2000.00, 1900.00, 3000.00, 300.00, 0, 0, 6.50,
         '[{"sku":"DEMO-PIVOT-INF","name":"Pivote inferior 300kg Demo","qty":1,"unit":"unit","category":"FITTING"},{"sku":"DEMO-PIVOT-SUP","name":"Pivote superior guía Demo","qty":1,"unit":"unit","category":"FITTING"},{"sku":"DEMO-TIRADOR-PIV","name":"Tirador pivotante Demo","qty":1,"unit":"unit","category":"HANDLE"}]'),
        (piv, 'DEMO_PIVOTANTE_120', 'KIT-PIV-80', 'Kit Pivotante Ventana 80kg Demo', 'PIVOT',
         500.00, 1400.00, 500.00, 1900.00, 80.00, 0, 0, 2.10,
         '[{"sku":"DEMO-PIVOT-V-80","name":"Pivote ventana 80kg Demo","qty":2,"unit":"unit","category":"FITTING"}]'),
        -- Guillotina: contrapesos o balances espirales según el peso.
        (gui, 'DEMO_GUILLOTINA_60', 'KIT-GUI-CONTRAPESO', 'Kit Guillotina Contrapeso 60kg Demo', 'VERTICAL_SLIDE',
         400.00, 1400.00, 300.00, 1400.00, 60.00, 0, 0, 5.80,
         '[{"sku":"DEMO-CONTRAPESO-GUI","name":"Contrapeso guillotina Demo","qty":2,"unit":"unit","category":"FITTING"},{"sku":"DEMO-CORDON-GUI","name":"Cordón/polea guillotina Demo","qty":2,"unit":"unit","category":"FITTING"}]'),
        (gui, 'DEMO_GUILLOTINA_60', 'KIT-GUI-MUELLES', 'Kit Guillotina Muelles 40kg Demo', 'VERTICAL_SLIDE',
         400.00, 1200.00, 300.00, 1200.00, 40.00, 0, 0, 2.40,
         '[{"sku":"DEMO-ESPIRAL-GUI","name":"Balance espiral guillotina Demo","qty":2,"unit":"unit","category":"FITTING"}]'),
        -- Puerta corredera: corredera estándar + la hoja de puerta con su
        -- cerradura de patio.
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'KIT-SLIDING-PCORR', 'Kit Corredera Puerta 70 Demo', 'SLIDING',
         400.00, 1500.00, 500.00, 2500.00, 120.00, 2, 0, 2.50, '[]'),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'KIT-PTA-CORR', 'Kit Puerta Corredera 70 Demo', 'DOOR_SLIDING',
         700.00, 1800.00, 1700.00, 2600.00, 160.00, 2, 0, 3.40,
         '[{"sku":"DEMO-CAR-PTA-ELEV","name":"Carretilla puerta corredera Demo","qty":2,"unit":"unit","category":"ROLLER"},{"sku":"DEMO-CERR-PATIO","name":"Cerradura patio corredera Demo","qty":1,"unit":"unit","category":"LOCK"}]')
    ) AS k(sys_id, sys_code, sku, name, opening, min_w, max_w, min_h, max_h,
           max_kg, carriages, stays, weight, contents)
    ON CONFLICT (system_id, sku) DO NOTHING;

    -- ------------------------------------------------------------------
    -- Reglas de corte declaradas (mismas que el fixture del motor congela).
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
        (elev, 'DEMO_ELEVACION_90', 'FRAME', 45.00, 2, 0.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'RAIL', 45.00, 2, 0.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'SLIDING_SASH', 45.00, 2, 0.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'INTERLOCK', 45.00, 2, 18.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'THRESHOLD', 45.00, 0, 0.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'MULLION_V', 90.00, 0, 0.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'MULLION_H', 90.00, 0, 0.00, 0.01),
        (elev, 'DEMO_ELEVACION_90', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01),
        (psk, 'DEMO_PSK_90', 'FRAME', 45.00, 2, 0.00, 0.01),
        (psk, 'DEMO_PSK_90', 'RAIL', 45.00, 2, 0.00, 0.01),
        (psk, 'DEMO_PSK_90', 'SLIDING_SASH', 45.00, 2, 0.00, 0.01),
        (psk, 'DEMO_PSK_90', 'INTERLOCK', 45.00, 2, 18.00, 0.01),
        (psk, 'DEMO_PSK_90', 'MULLION_V', 90.00, 0, 0.00, 0.01),
        (psk, 'DEMO_PSK_90', 'MULLION_H', 90.00, 0, 0.00, 0.01),
        (psk, 'DEMO_PSK_90', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01),
        (fold, 'DEMO_PLEGABLE_70', 'FRAME', 45.00, 2, 0.00, 0.01),
        (fold, 'DEMO_PLEGABLE_70', 'RAIL', 45.00, 2, 0.00, 0.01),
        (fold, 'DEMO_PLEGABLE_70', 'SASH', 45.00, 2, 0.00, 0.01),
        (fold, 'DEMO_PLEGABLE_70', 'MULLION_V', 90.00, 0, 0.00, 0.01),
        (fold, 'DEMO_PLEGABLE_70', 'MULLION_H', 90.00, 0, 0.00, 0.01),
        (fold, 'DEMO_PLEGABLE_70', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'FRAME', 45.00, 2, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'SASH', 45.00, 2, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'DOOR_SASH', 45.00, 2, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'THRESHOLD', 45.00, 0, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'MULLION_V', 90.00, 0, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'MULLION_H', 90.00, 0, 0.00, 0.01),
        (piv, 'DEMO_PIVOTANTE_120', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01),
        (gui, 'DEMO_GUILLOTINA_60', 'FRAME', 45.00, 2, 0.00, 0.01),
        (gui, 'DEMO_GUILLOTINA_60', 'SLIDING_SASH', 45.00, 2, 0.00, 0.01),
        (gui, 'DEMO_GUILLOTINA_60', 'INTERLOCK', 45.00, 2, 18.00, 0.01),
        (gui, 'DEMO_GUILLOTINA_60', 'MULLION_V', 90.00, 0, 0.00, 0.01),
        (gui, 'DEMO_GUILLOTINA_60', 'MULLION_H', 90.00, 0, 0.00, 0.01),
        (gui, 'DEMO_GUILLOTINA_60', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'FRAME', 45.00, 2, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'RAIL', 45.00, 2, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'SLIDING_SASH', 45.00, 2, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'INTERLOCK', 45.00, 2, 18.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'THRESHOLD', 45.00, 0, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'MULLION_V', 90.00, 0, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'MULLION_H', 90.00, 0, 0.00, 0.01),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'GLAZING_BEAD', 45.00, NULL, 0.00, 0.01)
    ) AS r(sys_id, sys_code, role, angle, welded, deduction, rounding)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- Refuerzo declarado: WHITE desde 1 m; laminado siempre.
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
        SELECT sys_id, sys_code, role, finish, min_len
        FROM (VALUES
            (elev, 'DEMO_ELEVACION_90', 'FRAME'),
            (elev, 'DEMO_ELEVACION_90', 'RAIL'),
            (elev, 'DEMO_ELEVACION_90', 'SLIDING_SASH'),
            (elev, 'DEMO_ELEVACION_90', 'INTERLOCK'),
            (elev, 'DEMO_ELEVACION_90', 'MULLION_V'),
            (elev, 'DEMO_ELEVACION_90', 'MULLION_H'),
            (psk, 'DEMO_PSK_90', 'FRAME'),
            (psk, 'DEMO_PSK_90', 'RAIL'),
            (psk, 'DEMO_PSK_90', 'SLIDING_SASH'),
            (psk, 'DEMO_PSK_90', 'INTERLOCK'),
            (psk, 'DEMO_PSK_90', 'MULLION_V'),
            (psk, 'DEMO_PSK_90', 'MULLION_H'),
            (fold, 'DEMO_PLEGABLE_70', 'FRAME'),
            (fold, 'DEMO_PLEGABLE_70', 'RAIL'),
            (fold, 'DEMO_PLEGABLE_70', 'SASH'),
            (fold, 'DEMO_PLEGABLE_70', 'MULLION_V'),
            (fold, 'DEMO_PLEGABLE_70', 'MULLION_H'),
            (piv, 'DEMO_PIVOTANTE_120', 'FRAME'),
            (piv, 'DEMO_PIVOTANTE_120', 'SASH'),
            (piv, 'DEMO_PIVOTANTE_120', 'DOOR_SASH'),
            (piv, 'DEMO_PIVOTANTE_120', 'MULLION_V'),
            (piv, 'DEMO_PIVOTANTE_120', 'MULLION_H'),
            (gui, 'DEMO_GUILLOTINA_60', 'FRAME'),
            (gui, 'DEMO_GUILLOTINA_60', 'SLIDING_SASH'),
            (gui, 'DEMO_GUILLOTINA_60', 'INTERLOCK'),
            (gui, 'DEMO_GUILLOTINA_60', 'MULLION_V'),
            (gui, 'DEMO_GUILLOTINA_60', 'MULLION_H'),
            (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'FRAME'),
            (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'RAIL'),
            (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'SLIDING_SASH'),
            (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'INTERLOCK'),
            (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'MULLION_V'),
            (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'MULLION_H')
        ) AS roles(sys_id, sys_code, role)
        CROSS JOIN (VALUES
            ('WHITE'::text, 1000.00::numeric),
            ('NON_WHITE'::text, 0.00::numeric)
        ) AS classes(finish, min_len)
    ) AS rr(sys_id, sys_code, role, finish, min_len)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- Límites dimensionales por tipología.
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
        max_kg::numeric, NULL,
        'SEED_SYNTHETIC'
    FROM (VALUES
        -- Elevable: esquemas correderos heredados + la hoja elevable.
        (elev, 'DEMO_ELEVACION_90', 'SLIDING_2L', 400.00, 1500.00, 500.00, 2500.00, 120.00),
        (elev, 'DEMO_ELEVACION_90', 'SLIDING_3L', 400.00, 1500.00, 500.00, 2500.00, 120.00),
        (elev, 'DEMO_ELEVACION_90', 'SLIDING_4L', 400.00, 1500.00, 500.00, 2500.00, 120.00),
        (elev, 'DEMO_ELEVACION_90', 'SLIDING', 400.00, 1500.00, 500.00, 2500.00, 120.00),
        (elev, 'DEMO_ELEVACION_90', 'LIFT_SLIDE', 700.00, 3200.00, 800.00, 2800.00, 400.00),
        (elev, 'DEMO_ELEVACION_90', 'DOOR:LIFT_SLIDE', 700.00, 1800.00, 1700.00, 2600.00, 400.00),
        (elev, 'DEMO_ELEVACION_90', 'SLIDE', 400.00, 1500.00, 500.00, 2500.00, 160.00),
        (elev, 'DEMO_ELEVACION_90', 'DOOR:SLIDE', 700.00, 1800.00, 1700.00, 2600.00, 160.00),
        -- PSK.
        (psk, 'DEMO_PSK_90', 'PARALLEL_SLIDE', 650.00, 2000.00, 600.00, 2400.00, 200.00),
        (psk, 'DEMO_PSK_90', 'DOOR:PARALLEL_SLIDE', 700.00, 1400.00, 1700.00, 2400.00, 200.00),
        -- Plegable: el límite por hoja del paquete y la hoja de paso.
        (fold, 'DEMO_PLEGABLE_70', 'FOLD', 400.00, 1000.00, 800.00, 2600.00, 100.00),
        (fold, 'DEMO_PLEGABLE_70', 'DOOR:FOLD', 600.00, 1000.00, 1700.00, 2600.00, 120.00),
        (fold, 'DEMO_PLEGABLE_70', 'DOOR:FOLD:LEFT:OUTWARD:ACTIVE', 600.00, 1000.00, 1700.00, 2600.00, 120.00),
        -- Pivotante.
        (piv, 'DEMO_PIVOTANTE_120', 'PIVOT_V', 500.00, 1400.00, 500.00, 1900.00, 80.00),
        (piv, 'DEMO_PIVOTANTE_120', 'PIVOT_H', 500.00, 1400.00, 500.00, 1900.00, 80.00),
        (piv, 'DEMO_PIVOTANTE_120', 'DOOR:PIVOT_V', 900.00, 2000.00, 1900.00, 3000.00, 300.00),
        -- Guillotina.
        (gui, 'DEMO_GUILLOTINA_60', 'VERTICAL_SLIDE', 400.00, 1400.00, 300.00, 1400.00, 60.00),
        -- Puerta corredera.
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'SLIDING_2L', 400.00, 1500.00, 500.00, 2500.00, 120.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'SLIDING', 400.00, 1500.00, 500.00, 2500.00, 120.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'SLIDE', 400.00, 1500.00, 500.00, 2500.00, 160.00),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'DOOR:SLIDE', 700.00, 1800.00, 1700.00, 2600.00, 160.00)
    ) AS l(sys_id, sys_code, opening, min_w, max_w, min_h, max_h, max_kg)
    ON CONFLICT DO NOTHING;

    -- ------------------------------------------------------------------
    -- Capacidades declaradas: lo que cada sistema ofrece en el editor.
    -- La puerta corredera es una unidad DOOR sobre familia SLIDING; la
    -- elevable declara además la corredera estándar y la puerta corredera
    -- (mismo riel); el plegable declara hasta 4 hojas con hoja de paso.
    -- ------------------------------------------------------------------
    INSERT INTO public.system_opening_capabilities (
        id, system_id, org_id, movement, directions, leaf_roles,
        unit_kinds, max_leaves, fixed_in_sash, hardware_group, data_provenance
    )
    SELECT
        uuid_generate_v5(uuid_ns_url(),
            'https://dekopen.local/catalog/' || sys_code || '/capability/' || cap_key),
        sys_id, NULL, movement, directions::text[], roles::text[],
        units::text[], max_leaves, sash, NULL, 'SEED_SYNTHETIC'
    FROM (VALUES
        (elev, 'DEMO_ELEVACION_90', 'FIXED', 'cap-fixed', '{}', '{SINGLE}', '{WINDOW,DOOR}', 2, TRUE),
        (elev, 'DEMO_ELEVACION_90', 'SLIDE', 'cap-slide', '{}', '{SINGLE}', '{WINDOW,DOOR}', 1, FALSE),
        (elev, 'DEMO_ELEVACION_90', 'LIFT_SLIDE', 'cap-lift', '{}', '{SINGLE}', '{WINDOW,DOOR}', 1, FALSE),
        (psk, 'DEMO_PSK_90', 'FIXED', 'cap-fixed', '{}', '{SINGLE}', '{WINDOW}', 2, TRUE),
        (psk, 'DEMO_PSK_90', 'PARALLEL_SLIDE', 'cap-psk', '{}', '{SINGLE}', '{WINDOW,DOOR}', 1, FALSE),
        (fold, 'DEMO_PLEGABLE_70', 'FIXED', 'cap-fixed', '{}', '{SINGLE}', '{WINDOW,DOOR}', 2, TRUE),
        (fold, 'DEMO_PLEGABLE_70', 'FOLD', 'cap-fold', '{INWARD,OUTWARD}', '{ACTIVE,PASSIVE}', '{WINDOW,DOOR}', 4, FALSE),
        (piv, 'DEMO_PIVOTANTE_120', 'FIXED', 'cap-fixed', '{}', '{SINGLE}', '{WINDOW,DOOR}', 2, TRUE),
        (piv, 'DEMO_PIVOTANTE_120', 'PIVOT_V', 'cap-pivv', '{}', '{SINGLE}', '{DOOR}', 1, FALSE),
        (piv, 'DEMO_PIVOTANTE_120', 'PIVOT_H', 'cap-pivh', '{}', '{SINGLE}', '{WINDOW,DOOR}', 1, FALSE),
        (gui, 'DEMO_GUILLOTINA_60', 'FIXED', 'cap-fixed', '{}', '{SINGLE}', '{WINDOW}', 2, TRUE),
        (gui, 'DEMO_GUILLOTINA_60', 'VERTICAL_SLIDE', 'cap-gui', '{}', '{SINGLE}', '{WINDOW}', 2, FALSE),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'FIXED', 'cap-fixed', '{}', '{SINGLE}', '{WINDOW,DOOR}', 2, TRUE),
        (pcorr, 'DEMO_PUERTA_CORREDERA_70', 'SLIDE', 'cap-slide', '{}', '{SINGLE}', '{WINDOW,DOOR}', 1, FALSE)
    ) AS cap(sys_id, sys_code, movement, cap_key, directions, roles, units, max_leaves, sash)
    ON CONFLICT DO NOTHING;
END $$;

COMMIT;
