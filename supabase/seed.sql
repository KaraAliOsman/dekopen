-- Deterministic global catalog required by the SHOT-02 gate.

INSERT INTO public.profile_systems (
    id,
    org_id,
    code,
    name,
    depth_mm,
    material,
    chamber_count,
    sash_overlap_mm,
    glass_clearance_white_mm,
    central_overlap_mm,
    sliding_end_add_mm,
    sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm,
    is_global,
    is_demo,
    finishes
)
VALUES (
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
    NULL,
    'DEMO_60',
    'Sistema Demo 60mm PVC — referencia sintética',
    60.00,
    'PVC',
    3,
    8.00,
    5.00,
    40.00,
    6.00,
    20.00,
    20.00,
    7.00,
    TRUE,
    TRUE,
    '["WHITE", "FOILED"]'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
    org_id = EXCLUDED.org_id,
    code = EXCLUDED.code,
    name = EXCLUDED.name,
    depth_mm = EXCLUDED.depth_mm,
    material = EXCLUDED.material,
    chamber_count = EXCLUDED.chamber_count,
    sash_overlap_mm = EXCLUDED.sash_overlap_mm,
    glass_clearance_white_mm = EXCLUDED.glass_clearance_white_mm,
    central_overlap_mm = EXCLUDED.central_overlap_mm,
    sliding_end_add_mm = EXCLUDED.sliding_end_add_mm,
    sliding_glazing_deduction_width_mm = EXCLUDED.sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm = EXCLUDED.sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm = EXCLUDED.door_leaf_side_clearance_mm,
    is_global = EXCLUDED.is_global,
    is_demo = EXCLUDED.is_demo,
    finishes = EXCLUDED.finishes;

INSERT INTO public.profile_articles (
    id,
    system_id,
    org_id,
    sku,
    name,
    role,
    face_width_mm,
    commercial_length_mm,
    welding_loss_mm,
    reinforcement_gap_mm
)
VALUES
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/MARCO'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'MARCO',
        'Marco Demo 60',
        'FRAME',
        60.00,
        6000.00,
        6.00,
        15.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/HOJA'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'HOJA',
        'Hoja Demo 60',
        'SASH',
        75.00,
        6000.00,
        6.00,
        15.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/POSTE-V'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'POSTE-V',
        'Poste Vertical Demo 60',
        'MULLION_V',
        80.00,
        6000.00,
        0.00,
        5.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/POSTE-H'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'POSTE-H',
        'Travesaño Horizontal Demo 60',
        'MULLION_H',
        80.00,
        6000.00,
        0.00,
        5.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-24'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'JQ-24',
        'Junquillo Demo 60 24mm',
        'GLAZING_BEAD',
        24.00,
        6000.00,
        0.00,
        15.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-14'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'JQ-14',
        'Junquillo Demo 60 14mm',
        'GLAZING_BEAD',
        14.00,
        6000.00,
        0.00,
        15.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-10'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        'JQ-10',
        'Junquillo Demo 60 10mm',
        'GLAZING_BEAD',
        10.00,
        6000.00,
        0.00,
        15.00
    )
ON CONFLICT (id) DO UPDATE SET
    system_id = EXCLUDED.system_id,
    org_id = EXCLUDED.org_id,
    sku = EXCLUDED.sku,
    name = EXCLUDED.name,
    role = EXCLUDED.role,
    face_width_mm = EXCLUDED.face_width_mm,
    commercial_length_mm = EXCLUDED.commercial_length_mm,
    welding_loss_mm = EXCLUDED.welding_loss_mm,
    reinforcement_gap_mm = EXCLUDED.reinforcement_gap_mm;

-- §15: declared simplified sections for the demo frame and sash. The polygon
-- is the profile cross-section (x = face width, y = depth, exterior at y=0);
-- source POLYGON marks a catalog-declared simplified shape, not a
-- manufacturer-drawing extraction. The schema-upgrade drills replay this seed
-- against pre-§15 schemas, where the column does not exist — the statement is
-- planned only when the schema carries it.
DO $seed_sections$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public'
                 AND table_name = 'profile_articles'
                 AND column_name = 'section') THEN
        UPDATE public.profile_articles AS article
        SET section = shapes.section::jsonb
        FROM (VALUES
    ('MARCO', '{
        "source": "POLYGON",
        "polygon": [
            {"x_mm": 0, "y_mm": 0}, {"x_mm": 60, "y_mm": 0},
            {"x_mm": 60, "y_mm": 24}, {"x_mm": 40, "y_mm": 24},
            {"x_mm": 40, "y_mm": 44}, {"x_mm": 60, "y_mm": 44},
            {"x_mm": 60, "y_mm": 60}, {"x_mm": 0, "y_mm": 60}
        ],
        "depth_mm": 60,
        "orientation": "EXTERIOR_DOWN",
        "local_origin": "TOP_LEFT",
        "axes": [
            {"name": "GLAZING", "y_mm": 24},
            {"name": "WEB", "y_mm": 34}
        ]
    }'::text),
    ('HOJA', '{
        "source": "POLYGON",
        "polygon": [
            {"x_mm": 0, "y_mm": 0}, {"x_mm": 75, "y_mm": 0},
            {"x_mm": 75, "y_mm": 30}, {"x_mm": 50, "y_mm": 30},
            {"x_mm": 50, "y_mm": 52}, {"x_mm": 75, "y_mm": 52},
            {"x_mm": 75, "y_mm": 75}, {"x_mm": 0, "y_mm": 75}
        ],
        "depth_mm": 75,
        "orientation": "EXTERIOR_DOWN",
        "local_origin": "TOP_LEFT",
        "axes": [
            {"name": "GLAZING", "y_mm": 30},
            {"name": "WEB", "y_mm": 41}
        ]
    }'::text)
) AS shapes(sku, section)
        WHERE article.sku = shapes.sku
          AND article.system_id = uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60')
          AND article.org_id IS NULL;
    END IF;
END;
$seed_sections$;

INSERT INTO public.hardware_kits (
    id,
    org_id,
    system_id,
    sku,
    name,
    opening_type,
    min_leaf_width_mm,
    max_leaf_width_mm,
    min_leaf_height_mm,
    max_leaf_height_mm,
    max_leaf_weight_kg,
    carriages_qty,
    stay_arms_qty
)
VALUES
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/KIT-TURN'),
        NULL,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        'KIT-TURN',
        'Kit Practicable Demo 60',
        'TURN',
        400.00,
        1200.00,
        500.00,
        2400.00,
        80.00,
        0,
        0
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/KIT-TILT-TURN'),
        NULL,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        'KIT-TILT-TURN',
        'Kit Vorne OB 100kg',
        'TILT_TURN',
        450.00,
        1400.00,
        600.00,
        2400.00,
        100.00,
        0,
        1
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/KIT-SLIDING'),
        NULL,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        'KIT-SLIDING',
        'Kit Corredera Demo 60',
        'SLIDING',
        400.00,
        1500.00,
        500.00,
        2500.00,
        120.00,
        2,
        0
    )
ON CONFLICT (id) DO UPDATE SET
    org_id = EXCLUDED.org_id,
    system_id = EXCLUDED.system_id,
    sku = EXCLUDED.sku,
    name = EXCLUDED.name,
    opening_type = EXCLUDED.opening_type,
    min_leaf_width_mm = EXCLUDED.min_leaf_width_mm,
    max_leaf_width_mm = EXCLUDED.max_leaf_width_mm,
    min_leaf_height_mm = EXCLUDED.min_leaf_height_mm,
    max_leaf_height_mm = EXCLUDED.max_leaf_height_mm,
    max_leaf_weight_kg = EXCLUDED.max_leaf_weight_kg,
    carriages_qty = EXCLUDED.carriages_qty,
    stay_arms_qty = EXCLUDED.stay_arms_qty;

INSERT INTO public.glazing_bead_matrix (
    id,
    system_id,
    org_id,
    glass_thickness_mm,
    bead_article_id,
    bead_width_mm,
    gasket_interior_mm,
    gasket_exterior_mm,
    cut_add_mm
)
VALUES
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/GLASS-4'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        4.00,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-24'),
        24.00,
        3.00,
        3.00,
        9.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/GLASS-5'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        5.00,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-24'),
        24.00,
        2.50,
        2.50,
        9.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/GLASS-6'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        6.00,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-24'),
        24.00,
        2.00,
        2.00,
        9.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/GLASS-20'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        20.00,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-14'),
        14.00,
        3.00,
        3.00,
        9.00
    ),
    (
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/GLASS-24'),
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60'),
        NULL,
        24.00,
        uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/JQ-10'),
        10.00,
        3.00,
        3.00,
        9.00
    )
ON CONFLICT (id) DO UPDATE SET
    system_id = EXCLUDED.system_id,
    org_id = EXCLUDED.org_id,
    glass_thickness_mm = EXCLUDED.glass_thickness_mm,
    bead_article_id = EXCLUDED.bead_article_id,
    bead_width_mm = EXCLUDED.bead_width_mm,
    gasket_interior_mm = EXCLUDED.gasket_interior_mm,
    gasket_exterior_mm = EXCLUDED.gasket_exterior_mm,
    cut_add_mm = EXCLUDED.cut_add_mm;

BEGIN;

-- Synthetic DEMO_60 fixtures, not manufacturer specifications.
UPDATE public.hardware_kits AS kit
SET weight_kg = 2.50,
    name = CASE WHEN kit.sku = 'KIT-TILT-TURN' THEN 'Kit Vorne OB 100kg' ELSE kit.name END
FROM public.profile_systems AS system
WHERE kit.system_id = system.id AND system.code = 'DEMO_60' AND system.is_global = TRUE
  AND kit.sku IN ('KIT-TURN', 'KIT-TILT-TURN', 'KIT-SLIDING');

-- Categorized kit contents: the visual renderer and readiness reads bind
-- handle/hinge/lock counts to these declared lines instead of heuristics.
-- Quantities are synthetic fixture data, not a manufacturer bill of parts.
UPDATE public.hardware_kits AS kit
SET contents = CASE kit.sku
    WHEN 'KIT-TURN' THEN '[
        {"sku":"DEMO-BIS-60","name":"Bisagra practicable Demo 60","qty":3,"unit":"unit","category":"HINGE"},
        {"sku":"DEMO-MAN-PRACT","name":"Manilla roseta practicable Demo","qty":1,"unit":"unit","category":"HANDLE"},
        {"sku":"DEMO-CREM-60","name":"Cremona + ganchos Demo 60","qty":1,"unit":"set","category":"LOCK"}
      ]'::JSONB
    WHEN 'KIT-TILT-TURN' THEN '[
        {"sku":"DEMO-BIS-OB","name":"Bisagra oscilobatiente Demo (tijera+esquina)","qty":4,"unit":"unit","category":"HINGE"},
        {"sku":"DEMO-MAN-OB","name":"Manilla oscilobatiente Demo","qty":1,"unit":"unit","category":"HANDLE"},
        {"sku":"DEMO-CREM-OB","name":"Cremona multipunto Demo","qty":1,"unit":"set","category":"LOCK"}
      ]'::JSONB
    WHEN 'KIT-SLIDING' THEN '[
        {"sku":"DEMO-CARR-60","name":"Carro doble rueda corredera Demo","qty":2,"unit":"unit","category":"ROLLER"},
        {"sku":"DEMO-UNERO-60","name":"Uñero embutido corredera Demo","qty":1,"unit":"unit","category":"HANDLE"},
        {"sku":"DEMO-CIERRE-60","name":"Cierre embutido corredera Demo","qty":1,"unit":"unit","category":"LOCK"}
      ]'::JSONB
    ELSE kit.contents
  END
FROM public.profile_systems AS system
WHERE kit.system_id = system.id AND system.code = 'DEMO_60' AND system.is_global = TRUE
  AND kit.sku IN ('KIT-TURN', 'KIT-TILT-TURN', 'KIT-SLIDING');

INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material,
    face_width_mm, commercial_length_mm, welding_loss_mm, reinforcement_gap_mm,
    reinforcement_sku
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/UMBRAL-ALU'),
    system.id, NULL, 'UMBRAL-ALU', 'Umbral Aluminio Demo 60', 'THRESHOLD', 'ALUMINIUM',
    30.00, 6000.00, 0.00, 0.00, NULL
FROM public.profile_systems AS system
WHERE system.code = 'DEMO_60' AND system.is_global = TRUE
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, role = EXCLUDED.role, material = EXCLUDED.material,
    face_width_mm = EXCLUDED.face_width_mm,
    commercial_length_mm = EXCLUDED.commercial_length_mm,
    welding_loss_mm = EXCLUDED.welding_loss_mm,
    reinforcement_gap_mm = EXCLUDED.reinforcement_gap_mm,
    reinforcement_sku = EXCLUDED.reinforcement_sku;

INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material,
    face_width_mm, commercial_length_mm, welding_loss_mm, reinforcement_gap_mm,
    weight_kg_m, steel_weight_kg_m
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/' || coupler.sku),
    system.id, NULL, coupler.sku, coupler.name, 'COUPLER', 'PVC',
    coupler.face_mm, 6000.00, 6.00, 15.00, coupler.weight, 1.7000
FROM public.profile_systems AS system
CROSS JOIN (VALUES
    ('COPLE-60', 'Acoplador Angular Demo 60/30', 30.00::numeric, 0.9000::numeric),
    ('COPLE-90', 'Acoplador Angular Demo 60/34', 34.00::numeric, 1.1000::numeric),
    ('CANAL-U', 'Canal U vidrio sin marco 60/24', 24.00::numeric, 0.7000::numeric)
) AS coupler(sku, name, face_mm, weight)
WHERE system.code = 'DEMO_60' AND system.is_global = TRUE
ON CONFLICT (system_id, sku) DO UPDATE SET
    name = EXCLUDED.name, role = EXCLUDED.role, material = EXCLUDED.material,
    face_width_mm = EXCLUDED.face_width_mm,
    commercial_length_mm = EXCLUDED.commercial_length_mm,
    welding_loss_mm = EXCLUDED.welding_loss_mm,
    reinforcement_gap_mm = EXCLUDED.reinforcement_gap_mm,
    weight_kg_m = EXCLUDED.weight_kg_m,
    steel_weight_kg_m = EXCLUDED.steel_weight_kg_m;

INSERT INTO public.infill_articles (
    id, system_id, org_id, sku, name, kind, thickness_mm, weight_kg_m2
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/PANEL-SANDWICH-DEMO-24'),
    system.id, NULL, 'PANEL-SANDWICH-DEMO-24', 'Panel Sándwich Demo 24mm',
    'SANDWICH_PANEL', 24.00, 10.0000
FROM public.profile_systems AS system
WHERE system.code = 'DEMO_60' AND system.is_global = TRUE
ON CONFLICT (system_id, sku) DO UPDATE SET
    name = EXCLUDED.name, kind = EXCLUDED.kind,
    thickness_mm = EXCLUDED.thickness_mm, weight_kg_m2 = EXCLUDED.weight_kg_m2;

INSERT INTO public.hardware_kits (
    id, system_id, org_id, sku, name, opening_type,
    min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,
    max_leaf_weight_kg, rail_type, carriages_qty, stay_arms_qty, weight_kg, contents
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/' || fixture.sku),
    system.id, NULL, fixture.sku, fixture.name, fixture.opening_type,
    fixture.min_w, fixture.max_w, fixture.min_h, fixture.max_h, fixture.max_weight,
    'dual', 0, fixture.stays, 2.50, fixture.contents
FROM public.profile_systems AS system
CROSS JOIN (VALUES
    ('KIT-AWNING-16', 'Kit Proyectante Compás 16" 45kg', 'AWNING',
     400.00, 1200.00, 400.00, 1000.00, 45.00, 2,
     '[{"sku":"DEMO-STAY-16","name":"Compás a fricción 16\"","qty":2,"unit":"unit","category":"FITTING"},
       {"sku":"DEMO-MAN-PROY","name":"Manilla central proyectante Demo","qty":1,"unit":"unit","category":"HANDLE"}]'::JSONB),
    ('KIT-DOOR-MULTIPOINT', 'Kit Puerta Entrada Multipunto Demo 60', 'DOOR',
     700.00, 1200.00, 1800.00, 2400.00, 120.00, 0,
     '[{"sku":"DEMO-LOCK-MULTIPOINT","name":"Cerradura multipunto Demo","qty":1,"unit":"unit","category":"LOCK"},
       {"sku":"DEMO-BIS-PUERTA","name":"Bisagra puerta reforzada Demo","qty":3,"unit":"unit","category":"HINGE"},
       {"sku":"DEMO-MAN-PUERTA","name":"Par manilla puerta + cilindro Demo","qty":1,"unit":"set","category":"HANDLE"}]'::JSONB)
) AS fixture(sku, name, opening_type, min_w, max_w, min_h, max_h, max_weight, stays, contents)
WHERE system.code = 'DEMO_60' AND system.is_global = TRUE
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, opening_type = EXCLUDED.opening_type,
    min_leaf_width_mm = EXCLUDED.min_leaf_width_mm,
    max_leaf_width_mm = EXCLUDED.max_leaf_width_mm,
    min_leaf_height_mm = EXCLUDED.min_leaf_height_mm,
    max_leaf_height_mm = EXCLUDED.max_leaf_height_mm,
    max_leaf_weight_kg = EXCLUDED.max_leaf_weight_kg,
    rail_type = EXCLUDED.rail_type, carriages_qty = EXCLUDED.carriages_qty,
    stay_arms_qty = EXCLUDED.stay_arms_qty, weight_kg = EXCLUDED.weight_kg,
    contents = EXCLUDED.contents;

-- DEMO_60 SYNTHETIC FIXTURE. No manufacturer certification or new mass authority.
UPDATE public.profile_systems SET chamber_clearance_mm=12.00
 WHERE code='DEMO_60' AND is_global=TRUE;
INSERT INTO public.cutting_profiles
 (id, org_id, code, name, kerf_mm, head_trim_mm, tail_trim_mm, is_default, is_active)
VALUES (uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot07/cutting/DEMO'),
 NULL,'DEMO','Catálogo de demostración',4.00,15.00,15.00,TRUE,TRUE)
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.profile_purchase_mappings
 (id,profile_article_id,org_id,commercial_sku,manufacturer_name,supplier_name,purchase_unit)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot07/purchase/'||article.id),
 article.id,NULL,'COMPRA-'||article.sku,'Catálogo de demostración','Proveedor de referencia','BAR'
FROM public.profile_articles article JOIN public.profile_systems system ON system.id=article.system_id
WHERE system.code='DEMO_60' AND system.is_global=TRUE AND article.org_id IS NULL
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.reinforcement_articles
 (id,system_id,org_id,parent_profile_article_id,sku,commercial_sku,name,
 manufacturer_name,supplier_name,stock_length_mm,purchase_unit,is_default)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot07/steel/'||article.id),
 system.id,NULL,article.id,'ACERO-'||article.sku,'COMPRA-ACERO-'||article.sku,
 'Catálogo de demostración','Catálogo de demostración','Proveedor de referencia',6000.00,'BAR',TRUE
FROM public.profile_articles article JOIN public.profile_systems system ON system.id=article.system_id
WHERE system.code='DEMO_60' AND system.is_global=TRUE AND article.org_id IS NULL
 AND article.role NOT IN ('GLAZING_BEAD','THRESHOLD')
ON CONFLICT (id) DO NOTHING;
INSERT INTO public.inspector_rule_configs (id,system_id,org_id,rule_id,params)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot07/config/'||system.id||'/'||cfg.rule_id),
 system.id,NULL,cfg.rule_id,cfg.params
FROM public.profile_systems system CROSS JOIN (VALUES
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
) cfg(rule_id,params)
WHERE system.code='DEMO_60' AND system.is_global=TRUE
ON CONFLICT (system_id,org_id,rule_id) DO NOTHING;

DO $shot09$
BEGIN
IF to_regclass('public.manufacturing_placement_policies') IS NOT NULL THEN
UPDATE public.profile_purchase_mappings AS mapping
SET physical_stock_identity=uuid_generate_v5(
     uuid_ns_url(),'https://dekopen.local/shot09/physical/profile/'||mapping.profile_article_id),
    stock_color='WHITE',
    cutting_profile_id=uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot07/cutting/DEMO'),
    binding_version=1
FROM public.profile_articles article JOIN public.profile_systems system ON system.id=article.system_id
WHERE mapping.profile_article_id=article.id AND system.code='DEMO_60' AND system.is_global=TRUE
 AND mapping.org_id IS NULL;
UPDATE public.reinforcement_articles AS reinforcement
SET physical_stock_identity=uuid_generate_v5(
     uuid_ns_url(),'https://dekopen.local/shot09/physical/steel/'||reinforcement.id),
    stock_color='WHITE',
    cutting_profile_id=uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot07/cutting/DEMO'),
    binding_version=1
FROM public.profile_systems system
WHERE reinforcement.system_id=system.id AND system.code='DEMO_60' AND system.is_global=TRUE
 AND reinforcement.org_id IS NULL;

INSERT INTO public.manufacturing_placement_policies (id,system_id,org_id,version,authority)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot09/placement/DEMO_60/V2'),
 system.id,NULL,2,'{"schema_version":1,"policy_id":"DEMO_60_PLACEMENT_V2","version":2,"sliding_leaf_offsets":{"L1":{"x_mm":0.00,"y_mm":0.00,"x_pitches":0.00},"L2":{"x_mm":0.00,"y_mm":0.00,"x_pitches":1.00},"L3":{"x_mm":0.00,"y_mm":0.00,"x_pitches":2.00},"L4":{"x_mm":0.00,"y_mm":0.00,"x_pitches":3.00}},"sliding_infill_offsets":{"L1":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L2":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L3":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L4":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00}},"bead_offsets":{"TOP":{"x_mm":0.00,"y_mm":0.00},"RIGHT":{"x_mm":0.00,"y_mm":0.00},"BOTTOM":{"x_mm":0.00,"y_mm":0.00},"LEFT":{"x_mm":0.00,"y_mm":0.00}}}'::jsonb
FROM public.profile_systems system
WHERE system.code='DEMO_60' AND system.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.handle_requirement_policies (id,system_id,org_id,version,authority)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot09/handles/DEMO_60/V2'),
 system.id,NULL,2,'{"schema_version":1,"policy_id":"DEMO_60_HANDLES_V2","version":2,"slots":[{"opening_type":"TURN_LEFT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TURN_RIGHT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TILT_TURN_LEFT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TILT_TURN_RIGHT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_2L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_2L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L4","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L4","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"AWNING","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"BOTTOM","horizontal_reference":"HOST_MEMBER_CENTER","horizontal_offset_mm":0.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"DOOR_ENTRY","leaf_slot":null,"leaf_handedness":"LEFT","handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"DOOR_ENTRY","leaf_slot":null,"leaf_handedness":"RIGHT","handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00}]}'::jsonb
FROM public.profile_systems system
WHERE system.code='DEMO_60' AND system.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.reinforcement_cut_policies (id,system_id,org_id,version,authority)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot09/reinforcement-cuts/DEMO_60/V1'),
 system.id,NULL,1,'{"schema_version":1,"policy_id":"DEMO_60_REINFORCEMENT_CUT_V1","version":1,"rules":[{"role":"FRAME","profile_angle_left":45.0,"profile_angle_right":45.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},{"role":"FRAME","profile_angle_left":45.0,"profile_angle_right":90.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},{"role":"SASH","profile_angle_left":45.0,"profile_angle_right":45.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},{"role":"MULLION_V","profile_angle_left":90.0,"profile_angle_right":90.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},{"role":"MULLION_H","profile_angle_left":90.0,"profile_angle_right":90.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true}]}'::jsonb
FROM public.profile_systems system
WHERE system.code='DEMO_60' AND system.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.glass_purchase_mappings
 (id,system_id,org_id,technical_sku,purchasing_sku,manufacturer_name,purchase_unit,version,provenance,glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot09/glass/DEMO_60/GLASS-BASE/V1'),
 system.id,NULL,'VIDRIO-BASE','VIDRIO-TERMINADO','Catálogo de demostración','EA',1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb,'4 Float Incoloro'
FROM public.profile_systems system
WHERE system.code='DEMO_60' AND system.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

-- Fitting purchase authority for the declared fastening SKUs — the same
-- fixture convention as the hardware mappings.
INSERT INTO public.fitting_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name,
  purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/catalog/' || s.code || '/fitting/TORNILLO-4X16/V1'),
 s.id, NULL, 'TORNILLO-4X16', 'COMPRA-TORNILLO-4X16', 'Referencia DEKOPEN',
 'EA', 1, '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
FROM public.profile_systems s
WHERE s.code IN ('DEMO_60','DEMO_70','DEMO_CORREDERA_60')
  AND s.is_global = TRUE
ON CONFLICT (system_id, org_id, technical_sku, version) DO NOTHING;

INSERT INTO public.hardware_purchase_mappings
 (id,hardware_kit_id,org_id,purchasing_sku,manufacturer_name,purchase_unit,version,provenance)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot09/hardware/'||kit.id||'/V1'),
 kit.id,NULL,'COMPRA-'||kit.sku,'Catálogo de demostración','KIT',1,
 '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
FROM public.hardware_kits kit JOIN public.profile_systems system ON system.id=kit.system_id
WHERE system.code='DEMO_60' AND system.is_global=TRUE AND kit.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.panel_purchase_authorities
 (id,infill_article_id,org_id,purchasing_sku,manufacturer_name,supply_form,purchase_unit,version,provenance)
SELECT uuid_generate_v5(uuid_ns_url(),'https://dekopen.local/shot09/panel/'||panel.id||'/V1'),
 panel.id,NULL,'COMPRA-'||panel.sku,'Catálogo de demostración','CUT_TO_SIZE','EA',1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb
FROM public.infill_articles panel JOIN public.profile_systems system ON system.id=panel.system_id
WHERE system.code='DEMO_60' AND system.is_global=TRUE AND panel.org_id IS NULL
ON CONFLICT (id) DO NOTHING;
END IF;
END;
$shot09$;

COMMIT;
-- Reference families ALU_65 + GLASS_45 — SYNTHETIC TEST DATA, not manufacturer
-- specifications. Seeded so the editor, engine, inspector and documentary flow
-- can run a PVC, an aluminium and a glass-dominant family end to end.
BEGIN;

INSERT INTO public.profile_systems (
    id, org_id, code, name, depth_mm, material, chamber_count, sash_overlap_mm,
    glass_clearance_white_mm, glass_clearance_foil_mm, pulley_height_mm,
    central_overlap_mm, sliding_lateral_clearance_mm, sliding_end_add_mm,
    corner_bracket_loss_mm, hook_depth_mm, door_threshold_mm,
    door_bottom_clearance_mm, rail_type, sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm, door_leaf_side_clearance_mm,
    chamber_clearance_mm, is_global, is_demo
) VALUES (uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_65'), NULL, 'ALU_65', 'Línea Aluminio 65 — referencia sintética', 65.00,'ALUMINIUM',1,6.00,4.00,4.00,10.00,25.00,3.00,5.00,2.00,8.00,25.00,18.00,'dual',15.00,15.00,5.00,8.00, TRUE, TRUE)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, depth_mm = EXCLUDED.depth_mm, material = EXCLUDED.material,
    chamber_count = EXCLUDED.chamber_count, sash_overlap_mm = EXCLUDED.sash_overlap_mm,
    glass_clearance_white_mm = EXCLUDED.glass_clearance_white_mm,
    glass_clearance_foil_mm = EXCLUDED.glass_clearance_foil_mm,
    pulley_height_mm = EXCLUDED.pulley_height_mm,
    central_overlap_mm = EXCLUDED.central_overlap_mm,
    sliding_lateral_clearance_mm = EXCLUDED.sliding_lateral_clearance_mm,
    sliding_end_add_mm = EXCLUDED.sliding_end_add_mm,
    corner_bracket_loss_mm = EXCLUDED.corner_bracket_loss_mm,
    hook_depth_mm = EXCLUDED.hook_depth_mm, door_threshold_mm = EXCLUDED.door_threshold_mm,
    door_bottom_clearance_mm = EXCLUDED.door_bottom_clearance_mm, rail_type = EXCLUDED.rail_type,
    sliding_glazing_deduction_width_mm = EXCLUDED.sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm = EXCLUDED.sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm = EXCLUDED.door_leaf_side_clearance_mm,
    chamber_clearance_mm = EXCLUDED.chamber_clearance_mm,
    is_global = EXCLUDED.is_global, is_demo = EXCLUDED.is_demo;

INSERT INTO public.profile_systems (
    id, org_id, code, name, depth_mm, material, chamber_count, sash_overlap_mm,
    glass_clearance_white_mm, glass_clearance_foil_mm, pulley_height_mm,
    central_overlap_mm, sliding_lateral_clearance_mm, sliding_end_add_mm,
    corner_bracket_loss_mm, hook_depth_mm, door_threshold_mm,
    door_bottom_clearance_mm, rail_type, sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm, door_leaf_side_clearance_mm,
    chamber_clearance_mm, is_global, is_demo
) VALUES (uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/GLASS_45'), NULL, 'GLASS_45', 'Vidrio-dominante 45 (aluminio) — referencia sintética', 45.00,'ALUMINIUM',1,4.00,3.00,3.00,8.00,18.00,2.00,4.00,1.50,6.00,12.00,12.00,'dual',10.00,10.00,3.00,6.00, TRUE, TRUE)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, depth_mm = EXCLUDED.depth_mm, material = EXCLUDED.material,
    chamber_count = EXCLUDED.chamber_count, sash_overlap_mm = EXCLUDED.sash_overlap_mm,
    glass_clearance_white_mm = EXCLUDED.glass_clearance_white_mm,
    glass_clearance_foil_mm = EXCLUDED.glass_clearance_foil_mm,
    pulley_height_mm = EXCLUDED.pulley_height_mm,
    central_overlap_mm = EXCLUDED.central_overlap_mm,
    sliding_lateral_clearance_mm = EXCLUDED.sliding_lateral_clearance_mm,
    sliding_end_add_mm = EXCLUDED.sliding_end_add_mm,
    corner_bracket_loss_mm = EXCLUDED.corner_bracket_loss_mm,
    hook_depth_mm = EXCLUDED.hook_depth_mm, door_threshold_mm = EXCLUDED.door_threshold_mm,
    door_bottom_clearance_mm = EXCLUDED.door_bottom_clearance_mm, rail_type = EXCLUDED.rail_type,
    sliding_glazing_deduction_width_mm = EXCLUDED.sliding_glazing_deduction_width_mm,
    sliding_glazing_deduction_height_mm = EXCLUDED.sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm = EXCLUDED.door_leaf_side_clearance_mm,
    chamber_clearance_mm = EXCLUDED.chamber_clearance_mm,
    is_global = EXCLUDED.is_global, is_demo = EXCLUDED.is_demo;

INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material, face_width_mm,
    commercial_length_mm, welding_loss_mm, reinforcement_gap_mm, weight_kg_m
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_65/' || a.sku), s.id, NULL,
 a.sku, a.name, a.role::public.profile_role, 'ALUMINIUM'::public.material_type,
 a.face_mm, 6000.00, 0.00, 0.00, a.weight
FROM public.profile_systems s CROSS JOIN (VALUES
    ('MARCO-A','Marco Aluminio 65','FRAME',55.00,1.4000),
    ('HOJA-A','Hoja Aluminio 65','SASH',62.00,1.5500),
    ('POSTE-A-V','Poste vertical Aluminio 65','MULLION_V',70.00,1.7000),
    ('POSTE-A-H','Travesaño Aluminio 65','MULLION_H',70.00,1.7000),
    ('JQ-A-24','Junquillo Aluminio 24','GLAZING_BEAD',24.00,0.3500),
    ('JQ-A-16','Junquillo Aluminio 16','GLAZING_BEAD',16.00,0.2800),
    ('JQ-A-8','Junquillo Aluminio 8','GLAZING_BEAD',8.00,0.2000),
    ('UMBRAL-A','Umbral Aluminio 65','THRESHOLD',28.00,0.9000),
    ('COPLE-A-30','Acoplador Aluminio 30','COUPLER',30.00,0.8500),
    ('COPLE-A-90','Acoplador Aluminio 90','COUPLER',34.00,1.0000),
    ('CANAL-A-U','Canal U vidrio sin marco Aluminio 26','COUPLER',26.00,0.7200)
) AS a(sku, name, role, face_mm, weight)
WHERE s.code = 'ALU_65' AND s.is_global = TRUE
ON CONFLICT (system_id, sku) DO UPDATE SET
    name = EXCLUDED.name, role = EXCLUDED.role, material = EXCLUDED.material,
    face_width_mm = EXCLUDED.face_width_mm, welding_loss_mm = EXCLUDED.welding_loss_mm,
    reinforcement_gap_mm = EXCLUDED.reinforcement_gap_mm, weight_kg_m = EXCLUDED.weight_kg_m;

INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material, face_width_mm,
    commercial_length_mm, welding_loss_mm, reinforcement_gap_mm, weight_kg_m
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/GLASS_45/' || a.sku), s.id, NULL,
 a.sku, a.name, a.role::public.profile_role, 'ALUMINIUM'::public.material_type,
 a.face_mm, 6000.00, 0.00, 0.00, a.weight
FROM public.profile_systems s CROSS JOIN (VALUES
    ('MARCO-G','Marco Vidrio 45','FRAME',34.00,0.9500),
    ('HOJA-G','Hoja Vidrio 45','SASH',42.00,1.1500),
    ('POSTE-G-V','Poste vertical Vidrio 45','MULLION_V',38.00,1.2500),
    ('POSTE-G-H','Travesaño Vidrio 45','MULLION_H',38.00,1.2500),
    ('JQ-G-10','Junquillo Vidrio 10','GLAZING_BEAD',10.00,0.2200),
    ('JQ-G-6','Junquillo Vidrio 6','GLAZING_BEAD',6.00,0.1800),
    ('UMBRAL-G','Umbral Vidrio 45','THRESHOLD',18.00,0.6000),
    ('COPLE-G-30','Acoplador Vidrio 30','COUPLER',26.00,0.7000),
    ('COPLE-G-90','Acoplador Vidrio 90','COUPLER',28.00,0.7800),
    ('REMATE-G','Remate estructural Vidrio 45','COUPLER',20.00,0.5500),
    ('CANAL-G-U','Canal U estructural Vidrio 45/24','COUPLER',24.00,0.6400)
) AS a(sku, name, role, face_mm, weight)
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE
ON CONFLICT (system_id, sku) DO UPDATE SET
    name = EXCLUDED.name, role = EXCLUDED.role, material = EXCLUDED.material,
    face_width_mm = EXCLUDED.face_width_mm, welding_loss_mm = EXCLUDED.welding_loss_mm,
    reinforcement_gap_mm = EXCLUDED.reinforcement_gap_mm, weight_kg_m = EXCLUDED.weight_kg_m;

INSERT INTO public.glazing_bead_matrix (
    id, system_id, org_id, glass_thickness_mm, bead_article_id, bead_width_mm,
    gasket_interior_mm, gasket_exterior_mm, cut_add_mm
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_65/BEAD-' || matrix.thick),
 s.id, NULL, matrix.thick::numeric, p.id, matrix.bead_w::numeric, matrix.gi::numeric,
 matrix.ge::numeric, 7.00
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('5','JQ-A-24',24.00,3.00,3.00),
    ('24','JQ-A-8',8.00,3.50,3.50),
    ('20','JQ-A-16',16.00,3.00,3.00),
    ('28','JQ-A-8',8.00,3.50,3.50)
) AS matrix(thick, bead_sku, bead_w, gi, ge)
JOIN public.profile_articles p ON p.system_id = s.id AND p.sku = matrix.bead_sku
WHERE s.code = 'ALU_65' AND s.is_global = TRUE
ON CONFLICT (id) DO UPDATE SET
    glass_thickness_mm = EXCLUDED.glass_thickness_mm, bead_article_id = EXCLUDED.bead_article_id,
    bead_width_mm = EXCLUDED.bead_width_mm, gasket_interior_mm = EXCLUDED.gasket_interior_mm,
    gasket_exterior_mm = EXCLUDED.gasket_exterior_mm, cut_add_mm = EXCLUDED.cut_add_mm;

INSERT INTO public.glazing_bead_matrix (
    id, system_id, org_id, glass_thickness_mm, bead_article_id, bead_width_mm,
    gasket_interior_mm, gasket_exterior_mm, cut_add_mm
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/GLASS_45/BEAD-' || matrix.thick),
 s.id, NULL, matrix.thick::numeric, p.id, matrix.bead_w::numeric, matrix.gi::numeric,
 matrix.ge::numeric, 7.00
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('24','JQ-G-10',10.00,2.00,2.00),
    ('28','JQ-G-6',6.00,2.50,2.50),
    ('32','JQ-G-6',6.00,3.00,3.00)
) AS matrix(thick, bead_sku, bead_w, gi, ge)
JOIN public.profile_articles p ON p.system_id = s.id AND p.sku = matrix.bead_sku
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE
ON CONFLICT (id) DO UPDATE SET
    glass_thickness_mm = EXCLUDED.glass_thickness_mm, bead_article_id = EXCLUDED.bead_article_id,
    bead_width_mm = EXCLUDED.bead_width_mm, gasket_interior_mm = EXCLUDED.gasket_interior_mm,
    gasket_exterior_mm = EXCLUDED.gasket_exterior_mm, cut_add_mm = EXCLUDED.cut_add_mm;

INSERT INTO public.hardware_kits (
    id, system_id, org_id, sku, name, opening_type,
    min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,
    max_leaf_weight_kg, rail_type, carriages_qty, stay_arms_qty, weight_kg, contents
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_65/' || kit.sku), s.id, NULL,
 kit.sku, kit.name, kit.opening_type, kit.min_w, kit.max_w, kit.min_h, kit.max_h,
 kit.max_weight, kit.rail, kit.carriages, kit.stays, 2.50, kit.contents
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('KIT-A-TURN','Kit practicable Aluminio 65','TURN',400,1100,500,2200,60,'dual',0,0,
     '[{"sku":"ALU-BIS-65","name":"Bisagra practicable Aluminio 65","qty":3,"unit":"unit","category":"HINGE"},
       {"sku":"ALU-MAN-PRACT","name":"Manilla roseta Aluminio","qty":1,"unit":"unit","category":"HANDLE"},
       {"sku":"ALU-CREM-65","name":"Cremona multipunto Aluminio 65","qty":1,"unit":"set","category":"LOCK"}]'::JSONB),
    ('KIT-A-TILT-TURN','Kit oscilobatiente Aluminio 65','TILT_TURN',450,1300,600,2200,90,'dual',0,1,
     '[{"sku":"ALU-BIS-OB","name":"Bisagra oscilobatiente Aluminio 65","qty":4,"unit":"unit","category":"HINGE"},
       {"sku":"ALU-MAN-OB","name":"Manilla oscilobatiente Aluminio","qty":1,"unit":"unit","category":"HANDLE"},
       {"sku":"ALU-CREM-OB","name":"Cremona multipunto Aluminio 65","qty":1,"unit":"set","category":"LOCK"}]'::JSONB),
    ('KIT-A-SLIDING','Kit corredera Aluminio 65','SLIDING',500,1800,600,2400,100,'dual',2,0,
     '[{"sku":"ALU-CARR-65","name":"Carro doble rueda corredera Aluminio","qty":2,"unit":"unit","category":"ROLLER"},
       {"sku":"ALU-TIRADOR-65","name":"Tirador superficial corredera Aluminio","qty":1,"unit":"unit","category":"HANDLE"},
       {"sku":"ALU-CIERRE-65","name":"Cierre corredera Aluminio","qty":1,"unit":"unit","category":"LOCK"}]'::JSONB),
    ('KIT-A-AWNING','Kit proyectante Aluminio 65','AWNING',450,1400,400,1200,50,'dual',0,2,
     '[{"sku":"ALU-STAY-65","name":"Compás a fricción Aluminio 65","qty":2,"unit":"unit","category":"FITTING"},
       {"sku":"ALU-MAN-PROY","name":"Manilla central proyectante Aluminio","qty":1,"unit":"unit","category":"HANDLE"}]'::JSONB),
    ('KIT-A-DOOR','Kit puerta multipunto Aluminio 65','DOOR',750,1200,1900,2400,90,'dual',0,0,
     '[{"sku":"ALU-BIS-PUERTA","name":"Bisagra puerta Aluminio 65","qty":3,"unit":"unit","category":"HINGE"},
       {"sku":"ALU-LOCK-PUERTA","name":"Cerradura multipunto Aluminio","qty":1,"unit":"unit","category":"LOCK"},
       {"sku":"ALU-MAN-PUERTA","name":"Par manilla puerta + cilindro Aluminio","qty":1,"unit":"set","category":"HANDLE"}]'::JSONB)
) AS kit(sku, name, opening_type, min_w, max_w, min_h, max_h, max_weight, rail, carriages, stays, contents)
WHERE s.code = 'ALU_65' AND s.is_global = TRUE
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, opening_type = EXCLUDED.opening_type,
    min_leaf_width_mm = EXCLUDED.min_leaf_width_mm, max_leaf_width_mm = EXCLUDED.max_leaf_width_mm,
    min_leaf_height_mm = EXCLUDED.min_leaf_height_mm, max_leaf_height_mm = EXCLUDED.max_leaf_height_mm,
    max_leaf_weight_kg = EXCLUDED.max_leaf_weight_kg, rail_type = EXCLUDED.rail_type,
    carriages_qty = EXCLUDED.carriages_qty, stay_arms_qty = EXCLUDED.stay_arms_qty,
    weight_kg = EXCLUDED.weight_kg, contents = EXCLUDED.contents;

INSERT INTO public.hardware_kits (
    id, system_id, org_id, sku, name, opening_type,
    min_leaf_width_mm, max_leaf_width_mm, min_leaf_height_mm, max_leaf_height_mm,
    max_leaf_weight_kg, rail_type, carriages_qty, stay_arms_qty, weight_kg, contents
)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/GLASS_45/' || kit.sku), s.id, NULL,
 kit.sku, kit.name, kit.opening_type, kit.min_w, kit.max_w, kit.min_h, kit.max_h,
 kit.max_weight, kit.rail, kit.carriages, kit.stays, 2.50, kit.contents
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('KIT-G-TURN','Kit practicable Vidrio 45','TURN',400,1000,500,2100,50,'dual',0,0,
     '[{"sku":"GLASS-BIS-45","name":"Bisagra vidrio-perfil 45","qty":3,"unit":"unit","category":"HINGE"},
       {"sku":"GLASS-MAN-45","name":"Manilla acero pulido vidrio 45","qty":1,"unit":"unit","category":"HANDLE"},
       {"sku":"GLASS-CIERRE-45","name":"Cierre magnético vidrio 45","qty":1,"unit":"unit","category":"LOCK"}]'::JSONB),
    ('KIT-G-TILT-TURN','Kit oscilobatiente Vidrio 45','TILT_TURN',450,1200,600,2100,70,'dual',0,1,
     '[{"sku":"GLASS-BIS-OB","name":"Bisagra oscilobatiente vidrio 45","qty":4,"unit":"unit","category":"HINGE"},
       {"sku":"GLASS-MAN-OB","name":"Manilla oscilobatiente vidrio 45","qty":1,"unit":"unit","category":"HANDLE"},
       {"sku":"GLASS-CIERRE-OB","name":"Cierre magnético vidrio 45","qty":1,"unit":"unit","category":"LOCK"}]'::JSONB),
    ('KIT-G-SLIDING','Kit corredera Vidrio 45','SLIDING',600,1600,700,2300,80,'dual',2,0,
     '[{"sku":"GLASS-CARR-45","name":"Carro corredera vidrio 45","qty":2,"unit":"unit","category":"ROLLER"},
       {"sku":"GLASS-TIRADOR-45","name":"Tirador barra vidrio 45","qty":1,"unit":"unit","category":"HANDLE"},
       {"sku":"GLASS-LOCK-45","name":"Cerradura corredera vidrio 45","qty":1,"unit":"unit","category":"LOCK"}]'::JSONB),
    ('KIT-G-AWNING','Kit proyectante Vidrio 45','AWNING',500,1600,400,1100,45,'dual',0,2,
     '[{"sku":"GLASS-STAY-45","name":"Compás proyectante vidrio 45","qty":2,"unit":"unit","category":"FITTING"},
       {"sku":"GLASS-MAN-PROY","name":"Manilla central vidrio 45","qty":1,"unit":"unit","category":"HANDLE"}]'::JSONB),
    ('KIT-G-DOOR','Kit puerta Vidrio 45','DOOR',800,1100,1950,2300,70,'dual',0,0,
     '[{"sku":"GLASS-BIS-PUERTA","name":"Bisagra puerta vidrio 45","qty":3,"unit":"unit","category":"HINGE"},
       {"sku":"GLASS-LOCK-PUERTA","name":"Cerradura puerta vidrio 45","qty":1,"unit":"unit","category":"LOCK"},
       {"sku":"GLASS-MAN-PUERTA","name":"Par manilla puerta vidrio + cilindro","qty":1,"unit":"set","category":"HANDLE"}]'::JSONB)
) AS kit(sku, name, opening_type, min_w, max_w, min_h, max_h, max_weight, rail, carriages, stays, contents)
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name, opening_type = EXCLUDED.opening_type,
    min_leaf_width_mm = EXCLUDED.min_leaf_width_mm, max_leaf_width_mm = EXCLUDED.max_leaf_width_mm,
    min_leaf_height_mm = EXCLUDED.min_leaf_height_mm, max_leaf_height_mm = EXCLUDED.max_leaf_height_mm,
    max_leaf_weight_kg = EXCLUDED.max_leaf_weight_kg, rail_type = EXCLUDED.rail_type,
    carriages_qty = EXCLUDED.carriages_qty, stay_arms_qty = EXCLUDED.stay_arms_qty,
    weight_kg = EXCLUDED.weight_kg, contents = EXCLUDED.contents;

INSERT INTO public.infill_articles (id, system_id, org_id, sku, name, kind, thickness_mm, weight_kg_m2)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_65/PANEL-SANDWICH-ALU-24'), s.id, NULL,
 'PANEL-SANDWICH-ALU-24', 'Panel sándwich Aluminio 24', 'SANDWICH_PANEL', 24.00, 9.5000
FROM public.profile_systems s WHERE s.code='ALU_65' AND s.is_global=TRUE
ON CONFLICT (system_id, sku) DO UPDATE SET
    name = EXCLUDED.name, kind = EXCLUDED.kind, thickness_mm = EXCLUDED.thickness_mm,
    weight_kg_m2 = EXCLUDED.weight_kg_m2;

INSERT INTO public.infill_articles (id, system_id, org_id, sku, name, kind, thickness_mm, weight_kg_m2)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/GLASS_45/PANEL-SANDWICH-GLASS-24'), s.id, NULL,
 'PANEL-SANDWICH-GLASS-24', 'Panel sándwich Vidrio 24', 'SANDWICH_PANEL', 24.00, 9.5000
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (system_id, sku) DO UPDATE SET
    name = EXCLUDED.name, kind = EXCLUDED.kind, thickness_mm = EXCLUDED.thickness_mm,
    weight_kg_m2 = EXCLUDED.weight_kg_m2;

INSERT INTO public.inspector_rule_configs (id, system_id, org_id, rule_id, params)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/config/' || s.id::text || '/' || cfg.rule_id),
 s.id, NULL, cfg.rule_id, cfg.params
FROM public.profile_systems s CROSS JOIN (VALUES
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
WHERE s.code = 'ALU_65' AND s.is_global = TRUE
ON CONFLICT (system_id, org_id, rule_id) DO NOTHING;

INSERT INTO public.inspector_rule_configs (id, system_id, org_id, rule_id, params)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/config/' || s.id::text || '/' || cfg.rule_id),
 s.id, NULL, cfg.rule_id, cfg.params
FROM public.profile_systems s CROSS JOIN (VALUES
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
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE
ON CONFLICT (system_id, org_id, rule_id) DO NOTHING;

-- The purchase-authority tail targets the post-shot-09 schema (physical
-- stock identity, provenance, glass_spec). The pre-pricing upgrade drill
-- replays this seed on a shot-07 schema; the tail is planned only when the
-- column family exists.
DO $post09$
BEGIN
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'glass_purchase_mappings'
             AND column_name = 'glass_spec') THEN
INSERT INTO public.profile_purchase_mappings
 (id, profile_article_id, org_id, commercial_sku, manufacturer_name, supplier_name,
  purchase_unit, physical_stock_identity, stock_color, cutting_profile_id, binding_version)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/purchase/' || article.id::text),
 article.id, NULL, 'COMPRA-' || article.sku, 'Referencia DEKOPEN', 'Proveedor de referencia', 'BAR',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/physical/profile/' || article.id::text),
 'WHITE',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'),
 1
FROM public.profile_articles article
JOIN public.profile_systems s ON s.id = article.system_id
WHERE s.code = 'ALU_65' AND s.is_global = TRUE AND article.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.profile_purchase_mappings
 (id, profile_article_id, org_id, commercial_sku, manufacturer_name, supplier_name,
  purchase_unit, physical_stock_identity, stock_color, cutting_profile_id, binding_version)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/purchase/' || article.id::text),
 article.id, NULL, 'COMPRA-' || article.sku, 'Referencia DEKOPEN', 'Proveedor de referencia', 'BAR',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/physical/profile/' || article.id::text),
 'WHITE',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'),
 1
FROM public.profile_articles article
JOIN public.profile_systems s ON s.id = article.system_id
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE AND article.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.hardware_purchase_mappings
 (id, hardware_kit_id, org_id, purchasing_sku, manufacturer_name, purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/hardware/' || kit.id::text || '/V1'),
 kit.id, NULL, 'COMPRA-' || kit.sku, 'Referencia DEKOPEN', 'KIT', 1,
 '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
FROM public.hardware_kits kit
JOIN public.profile_systems s ON s.id = kit.system_id
WHERE s.code = 'ALU_65' AND s.is_global = TRUE AND kit.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name, purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/glass/ALU_65/DVH-24/V1'), s.id, NULL,
 'DVH-24', 'TEST-BUY-DVH-24', 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, '4-16-4'
FROM public.profile_systems s WHERE s.code='ALU_65' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name, purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/glass/ALU_65/MONO-5/V1'), s.id, NULL,
 'MONO-5', 'TEST-BUY-MONO-5', 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, '5'
FROM public.profile_systems s WHERE s.code='ALU_65' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.panel_purchase_authorities
 (id, infill_article_id, org_id, purchasing_sku, manufacturer_name, supply_form, purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/panel/' || panel.id::text || '/V1'),
 panel.id, NULL, 'COMPRA-' || panel.sku, 'Referencia DEKOPEN', 'CUT_TO_SIZE', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb
FROM public.infill_articles panel
JOIN public.profile_systems s ON s.id = panel.system_id
WHERE s.code = 'ALU_65' AND s.is_global = TRUE AND panel.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.hardware_purchase_mappings
 (id, hardware_kit_id, org_id, purchasing_sku, manufacturer_name, purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/hardware/' || kit.id::text || '/V1'),
 kit.id, NULL, 'COMPRA-' || kit.sku, 'Referencia DEKOPEN', 'KIT', 1,
 '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
FROM public.hardware_kits kit
JOIN public.profile_systems s ON s.id = kit.system_id
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE AND kit.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name, purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/glass/GLASS_45/DVH-28/V1'), s.id, NULL,
 'DVH-28', 'TEST-BUY-DVH-28', 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, '4-20-4'
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name, purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/glass/GLASS_45/DVH-32/V1'), s.id, NULL,
 'DVH-32', 'TEST-BUY-DVH-32', 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, '4-24-4'
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name, purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/glass/GLASS_45/MONO-8/V1'), s.id, NULL,
 'MONO-8', 'TEST-BUY-MONO-8', 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, '8'
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.panel_purchase_authorities
 (id, infill_article_id, org_id, purchasing_sku, manufacturer_name, supply_form, purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/panel/' || panel.id::text || '/V1'),
 panel.id, NULL, 'COMPRA-' || panel.sku, 'Referencia DEKOPEN', 'CUT_TO_SIZE', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb
FROM public.infill_articles panel
JOIN public.profile_systems s ON s.id = panel.system_id
WHERE s.code = 'GLASS_45' AND s.is_global = TRUE AND panel.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/ALU_65/V2'), s.id, NULL,2,
 '{"schema_version":1,"policy_id":"ALU_65_PLACEMENT_V2","version":2,"sliding_leaf_offsets":{"L1":{"x_mm":0.00,"y_mm":0.00,"x_pitches":0.00},"L2":{"x_mm":0.00,"y_mm":0.00,"x_pitches":1.00},"L3":{"x_mm":0.00,"y_mm":0.00,"x_pitches":2.00},"L4":{"x_mm":0.00,"y_mm":0.00,"x_pitches":3.00}},"sliding_infill_offsets":{"L1":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L2":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L3":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L4":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00}},"bead_offsets":{"TOP":{"x_mm":0.00,"y_mm":0.00},"RIGHT":{"x_mm":0.00,"y_mm":0.00},"BOTTOM":{"x_mm":0.00,"y_mm":0.00},"LEFT":{"x_mm":0.00,"y_mm":0.00}}}'::jsonb
FROM public.profile_systems s WHERE s.code='ALU_65' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.handle_requirement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/handles/ALU_65/V2'), s.id, NULL, 2,
 '{"schema_version":1,"policy_id":"ALU_65_HANDLES_V2","version":2,"slots":[{"opening_type":"TURN_LEFT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TURN_RIGHT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TILT_TURN_LEFT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TILT_TURN_RIGHT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_2L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_2L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L4","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L4","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"AWNING","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"BOTTOM","horizontal_reference":"HOST_MEMBER_CENTER","horizontal_offset_mm":0.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"DOOR_ENTRY","leaf_slot":null,"leaf_handedness":"LEFT","handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"DOOR_ENTRY","leaf_slot":null,"leaf_handedness":"RIGHT","handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00}]}'::jsonb
FROM public.profile_systems s WHERE s.code='ALU_65' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/ALU_65/V1'), s.id, NULL, 1,
 '{"schema_version": 1, "policy_id": "ALU_65_REINFORCEMENT_CUT_V1", "version": 1, "rules": [{"role": "FRAME", "profile_angle_left":45.0, "profile_angle_right":45.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "FRAME", "profile_angle_left":45.0, "profile_angle_right":90.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "SASH", "profile_angle_left":45.0, "profile_angle_right":45.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "MULLION_V", "profile_angle_left":90.0, "profile_angle_right":90.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "MULLION_H", "profile_angle_left":90.0, "profile_angle_right":90.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}]}'::jsonb
FROM public.profile_systems s WHERE s.code='ALU_65' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/GLASS_45/V2'), s.id, NULL,2,
 '{"schema_version":1,"policy_id":"GLASS_45_PLACEMENT_V2","version":2,"sliding_leaf_offsets":{"L1":{"x_mm":0.00,"y_mm":0.00,"x_pitches":0.00},"L2":{"x_mm":0.00,"y_mm":0.00,"x_pitches":1.00},"L3":{"x_mm":0.00,"y_mm":0.00,"x_pitches":2.00},"L4":{"x_mm":0.00,"y_mm":0.00,"x_pitches":3.00}},"sliding_infill_offsets":{"L1":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L2":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L3":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L4":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00}},"bead_offsets":{"TOP":{"x_mm":0.00,"y_mm":0.00},"RIGHT":{"x_mm":0.00,"y_mm":0.00},"BOTTOM":{"x_mm":0.00,"y_mm":0.00},"LEFT":{"x_mm":0.00,"y_mm":0.00}}}'::jsonb
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.handle_requirement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/handles/GLASS_45/V2'), s.id, NULL, 2,
 '{"schema_version":1,"policy_id":"GLASS_45_HANDLES_V2","version":2,"slots":[{"opening_type":"TURN_LEFT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TURN_RIGHT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TILT_TURN_LEFT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"TILT_TURN_RIGHT","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_2L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_2L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_3L","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING_4L","leaf_slot":"L4","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L1","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L2","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L3","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"SLIDING","leaf_slot":"L4","leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"AWNING","leaf_slot":null,"leaf_handedness":null,"handle_domain_slot":"PRIMARY","host_member_side":"BOTTOM","horizontal_reference":"HOST_MEMBER_CENTER","horizontal_offset_mm":0.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"DOOR_ENTRY","leaf_slot":null,"leaf_handedness":"LEFT","handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":-10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00},{"opening_type":"DOOR_ENTRY","leaf_slot":null,"leaf_handedness":"RIGHT","handle_domain_slot":"PRIMARY","host_member_side":"LEFT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":10.00,"permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":0.00,"mounting_max_from_leaf_top_mm":3000.00}]}'::jsonb
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/GLASS_45/V1'), s.id, NULL, 1,
 '{"schema_version": 1, "policy_id": "GLASS_45_REINFORCEMENT_CUT_V1", "version": 1, "rules": [{"role": "FRAME", "profile_angle_left":45.0, "profile_angle_right":45.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "FRAME", "profile_angle_left":45.0, "profile_angle_right":90.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "SASH", "profile_angle_left":45.0, "profile_angle_right":45.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "MULLION_V", "profile_angle_left":90.0, "profile_angle_right":90.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}, {"role": "MULLION_H", "profile_angle_left":90.0, "profile_angle_right":90.0, "reinforcement_angle_left":90.0, "reinforcement_angle_right":90.0, "length_authority": "EXISTING_ENGINE", "compatible_with_existing_length": true}]}'::jsonb
FROM public.profile_systems s WHERE s.code='GLASS_45' AND s.is_global=TRUE
ON CONFLICT (id) DO NOTHING;

-- §2 fabrication authority: the values the engine once invented as hard-coded
-- constants are now catalog columns; the synthetic reference families declare
-- their own and carry the fixture provenance label. Guarded on the column so
-- the shot-07 upgrade drill skips it on the old schema.
IF EXISTS (SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = 'profile_systems'
             AND column_name = 'data_provenance') THEN
UPDATE public.profile_systems SET
    rebate_depth_mm = CASE code
        WHEN 'DEMO_60' THEN 20.00
        WHEN 'ALU_65' THEN 7.00
        WHEN 'GLASS_45' THEN 5.00
    END,
    end_milling_overlap_mm = CASE code
        WHEN 'DEMO_60' THEN 0.00
        WHEN 'ALU_65' THEN 3.00
        WHEN 'GLASS_45' THEN 2.00
    END,
    data_provenance = 'SEED_SYNTHETIC'
WHERE is_global = TRUE AND org_id IS NULL
  AND code IN ('DEMO_60', 'ALU_65', 'GLASS_45');
UPDATE public.profile_articles a SET data_provenance = 'SEED_SYNTHETIC'
FROM public.profile_systems s
WHERE a.system_id = s.id AND s.code IN ('DEMO_60', 'ALU_65', 'GLASS_45')
  AND a.org_id IS NULL;
UPDATE public.infill_articles a SET data_provenance = 'SEED_SYNTHETIC'
FROM public.profile_systems s
WHERE a.system_id = s.id AND s.code IN ('DEMO_60', 'ALU_65', 'GLASS_45')
  AND a.org_id IS NULL;
UPDATE public.hardware_kits k SET data_provenance = 'SEED_SYNTHETIC'
FROM public.profile_systems s
WHERE k.system_id = s.id AND s.code IN ('DEMO_60', 'ALU_65', 'GLASS_45')
  AND k.org_id IS NULL;
-- Per-article masses used to arrive through engine fallbacks (1.20 / 1.70
-- kg·m⁻¹); since §2 they are catalog authority. The synthetic reference
-- family declares the same values the canonical engine fixture carries so
-- leaf weight — and therefore hardware certification — is decidable.
UPDATE public.profile_articles a SET
    weight_kg_m = 1.2000,
    steel_weight_kg_m = 1.7000
FROM public.profile_systems s
WHERE a.system_id = s.id AND s.code = 'DEMO_60'
  AND a.org_id IS NULL AND a.weight_kg_m IS NULL;
END IF;

END IF;
END;
$post09$;

COMMIT;
-- ---------------------------------------------------------------------------
-- D01: the DEMO catalogue grows real fabrication families.
--   DEMO_60 stays a casement+door PVC series; DEMO_CORREDERA_60 carries the
--   sliding family; DEMO_70 is the deeper casement sibling and
--   ALU_CORREDERA_70 the aluminium slider. Everything here is SEED_SYNTHETIC
--   demonstration data — plausible values, a fixed deterministic seed, never
--   manufacturer-certified. Guarded on the D01 column so older-schema
--   replays (the shot-07 upgrade drill) skip the block untouched.
-- ---------------------------------------------------------------------------
DO $d01$
BEGIN
IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'profile_systems'
      AND column_name = 'system_family'
) THEN
    RETURN;
END IF;

-- The corredera sibling itself lives in migration
-- 20261229000002_d01_demo_corredera_60, which also owns DEMO_60's D01 rows
-- when the seeded system already exists (existing databases). On a fresh
-- reset the migration runs before this seed, so the block below repeats
-- the DEMO_60 rows idempotently — ON CONFLICT keeps both paths safe.

-- DEMO_70 — PVC casement, deeper chamber, heavier door leaf.
INSERT INTO public.profile_systems (
    id, org_id, code, name, depth_mm, material, chamber_count,
    sash_overlap_mm, glass_clearance_white_mm, central_overlap_mm,
    sliding_end_add_mm, pulley_height_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm, rebate_depth_mm, end_milling_overlap_mm,
    chamber_clearance_mm,
    system_family, is_global, is_demo, finishes, data_provenance
)
VALUES (
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_70'),
    NULL, 'DEMO_70',
    'Sistema Demo 70mm PVC — referencia sintética',
    70.00, 'PVC', 4, 8.00, 5.00, 40.00, 6.00, 12.00,
    20.00, 20.00, 7.00, 22.00, 0.00, 12.00,
    'CASEMENT', TRUE, TRUE, '["WHITE", "FOILED"]'::jsonb, 'SEED_SYNTHETIC'
)
ON CONFLICT (id) DO NOTHING;

-- ALU_CORREDERA_70 — mechanically jointed aluminium slider.
INSERT INTO public.profile_systems (
    id, org_id, code, name, depth_mm, material, chamber_count,
    sash_overlap_mm, glass_clearance_white_mm, central_overlap_mm,
    sliding_end_add_mm, pulley_height_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm, rebate_depth_mm, end_milling_overlap_mm,
    corner_bracket_loss_mm, chamber_clearance_mm,
    system_family, is_global, is_demo, finishes, data_provenance
)
VALUES (
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_CORREDERA_70'),
    NULL, 'ALU_CORREDERA_70',
    'Corredera Demo Aluminio 70mm — referencia sintética',
    70.00, 'ALUMINIUM', 1, 6.00, 4.00, 42.00, 5.00, 10.00,
    15.00, 15.00, 0.00, 18.00, 0.00, 2.00, 8.00,
    'SLIDING', TRUE, TRUE, '["NATURAL", "PINTADO"]'::jsonb, 'SEED_SYNTHETIC'
)
ON CONFLICT (id) DO NOTHING;

-- DEMO_70 articles (PVC casement set + dedicated door sash + threshold).
INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material,
    face_width_mm, commercial_length_mm, welding_loss_mm,
    reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_70/' || a.sku),
    s.id, NULL, a.sku, a.name, role::public.profile_role, 'PVC',
    face, 6000.00, weld, gap, weight, 1.7000, 'SEED_SYNTHETIC'
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('MARCO-70',      'Marco Demo 70',            'FRAME',        65.00, 6.00, 15.00, 2.2000),
    ('HOJA-70',       'Hoja Demo 70',             'SASH',         85.00, 6.00, 15.00, 2.6000),
    ('HOJA-PUERTA-70','Hoja Puerta Demo 70',      'DOOR_SASH',    95.00, 6.00, 15.00, 2.8000),
    ('POSTE-70-V',    'Poste Vertical Demo 70',   'MULLION_V',    85.00, 0.00, 5.00,  2.4000),
    ('POSTE-70-H',    'Travesaño Demo 70',        'MULLION_H',    85.00, 0.00, 5.00,  2.4000),
    ('JQ-70-24',      'Junquillo Demo 70 24mm',   'GLAZING_BEAD', 24.00, 0.00, 15.00, 0.3000),
    ('JQ-70-14',      'Junquillo Demo 70 14mm',   'GLAZING_BEAD', 14.00, 0.00, 15.00, 0.2500),
    ('UMBRAL-70-ALU', 'Umbral Aluminio Demo 70',  'THRESHOLD',    32.00, 0.00, 0.00,  0.9000)
) AS a(sku, name, role, face, weld, gap, weight)
WHERE s.code = 'DEMO_70' AND s.is_global = TRUE
ON CONFLICT (system_id, sku) DO NOTHING;

-- ALU_CORREDERA_70 articles (sawn, mechanically jointed — no welding).
INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material,
    face_width_mm, commercial_length_mm, welding_loss_mm,
    reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/ALU_CORREDERA_70/' || a.sku),
    s.id, NULL, a.sku, a.name, role::public.profile_role, 'ALUMINIUM',
    face, 6500.00, 0.00, 0.00, weight, 0.0000, 'SEED_SYNTHETIC'
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('MARCO-AC',      'Marco Corredera Aluminio 70',      'FRAME',        45.00, 1.2500),
    ('RIEL-AC',       'Riel Corredera Aluminio 70',       'RAIL',         50.00, 1.4500),
    ('HOJA-AC',       'Hoja Corredera Aluminio 70',       'SLIDING_SASH', 35.00, 1.1000),
    ('ENCUENTRO-AC',  'Encuentro Corredera Aluminio 70',  'INTERLOCK',    30.00, 0.9500),
    ('POSTE-AC-V',    'Poste Vertical Aluminio 70',       'MULLION_V',    55.00, 1.3000),
    ('POSTE-AC-H',    'Travesaño Aluminio 70',            'MULLION_H',    55.00, 1.3000),
    ('JQ-AC-10',      'Junquillo Aluminio Corredera 10',  'GLAZING_BEAD', 10.00, 0.2000)
) AS a(sku, name, role, face, weight)
WHERE s.code = 'ALU_CORREDERA_70' AND s.is_global = TRUE
ON CONFLICT (system_id, sku) DO NOTHING;

-- Glazing beads for the new families.
INSERT INTO public.glazing_bead_matrix (
    id, system_id, org_id, glass_thickness_mm, bead_article_id,
    bead_width_mm, gasket_interior_mm, gasket_exterior_mm, cut_add_mm
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/bead/' || t),
    s.id, NULL, t,
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/' || bead_sku),
    bead_w, 3.00, 3.00, cut_add
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('DEMO_70',        24.00::numeric, 'JQ-70-24'::text, 24.00::numeric, 9.00::numeric),
    ('DEMO_70',        20.00::numeric, 'JQ-70-14'::text, 14.00::numeric, 9.00::numeric),
    ('ALU_CORREDERA_70', 20.00::numeric, 'JQ-AC-10'::text, 10.00::numeric, 7.00::numeric)
) AS b(sys_code, t, bead_sku, bead_w, cut_add)
WHERE s.code = b.sys_code AND s.is_global = TRUE
ON CONFLICT (system_id, glass_thickness_mm) DO NOTHING;

-- Hardware kits: casement + door for DEMO_70, dual/mono rails for the ALU slider.
INSERT INTO public.hardware_kits (
    id, org_id, system_id, sku, name, opening_type,
    min_leaf_width_mm, max_leaf_width_mm,
    min_leaf_height_mm, max_leaf_height_mm,
    max_leaf_weight_kg, rail_type, carriages_qty, stay_arms_qty,
    contents, weight_kg, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/' || k.sku),
    NULL, s.id, k.sku, k.name, k.opening,
    k.min_w, k.max_w, k.min_h, k.max_h, k.max_kg,
    k.rail, k.carriages, k.stays, k.contents::jsonb, k.weight, 'SEED_SYNTHETIC'
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('DEMO_70', 'KIT-TURN-70',       'Kit Practicable Demo 70',           'TURN',      400.00, 1300.00, 500.00, 2400.00, 90.00,  'dual', 0, 0,
     2.80, '[{"sku":"DEMO-BIS-70","name":"Bisagra demo 70","qty":3,"unit":"unit","category":"HINGE"},{"sku":"DEMO-MAN-70","name":"Manilla demo 70","qty":1,"unit":"unit","category":"HANDLE"}]'),
    ('DEMO_70', 'KIT-TILT-TURN-70',  'Kit Oscilobatiente Demo 70',        'TILT_TURN', 450.00, 1600.00, 500.00, 2400.00, 130.00, 'dual', 0, 1,
     3.40, '[{"sku":"DEMO-TT-70","name":"Mecanismo oscilobatiente demo 70","qty":1,"unit":"set","category":"LOCK"},{"sku":"DEMO-MAN-70","name":"Manilla demo 70","qty":1,"unit":"unit","category":"HANDLE"}]'),
    ('DEMO_70', 'KIT-DOOR-70',       'Kit Puerta Multipunto Demo 70',     'DOOR',      700.00, 1200.00, 1800.00, 2400.00, 130.00, 'dual', 0, 0,
     4.10, '[{"sku":"DEMO-LOCK-70","name":"Cerradura multipunto demo 70","qty":1,"unit":"unit","category":"LOCK"},{"sku":"DEMO-BIS-70","name":"Bisagra puerta reforzada demo 70","qty":3,"unit":"unit","category":"HINGE"}]'),
    ('DEMO_70', 'KIT-AWNING-70',     'Kit Proyectante Demo 70',           'AWNING',    400.00, 1400.00, 400.00, 1200.00, 50.00,  'dual', 0, 2,
     2.10, '[{"sku":"DEMO-STAY-70","name":"Compás a fricción demo 70","qty":2,"unit":"unit","category":"FITTING"},{"sku":"DEMO-MAN-70","name":"Manilla demo 70","qty":1,"unit":"unit","category":"HANDLE"}]'),
    ('ALU_CORREDERA_70', 'KIT-A-SLIDING-70',      'Kit Corredera Aluminio 70',      'SLIDING', 450.00, 1800.00, 600.00, 2400.00, 100.00, 'dual', 2, 0,
     2.60, '[{"sku":"ALU-CAR-70","name":"Carro doble corredera aluminio","qty":2,"unit":"set","category":"ROLLER"},{"sku":"ALU-CIERRE-70","name":"Cierre corredera aluminio","qty":1,"unit":"set","category":"LOCK"}]'),
    ('ALU_CORREDERA_70', 'KIT-A-SLIDING-70-MONO', 'Kit Corredera Aluminio 70 Mono', 'SLIDING', 450.00, 1800.00, 600.00, 2400.00, 100.00, 'mono', 1, 0,
     2.20, '[{"sku":"ALU-CAR-70M","name":"Carro monorriel aluminio","qty":1,"unit":"set","category":"ROLLER"},{"sku":"ALU-CIERRE-70","name":"Cierre corredera aluminio","qty":1,"unit":"set","category":"LOCK"}]')
) AS k(sys_code, sku, name, opening, min_w, max_w, min_h, max_h, max_kg, rail, carriages, stays, weight, contents)
WHERE s.code = k.sys_code AND s.is_global = TRUE
ON CONFLICT (system_id, sku) DO NOTHING;

-- DEMO_60's dedicated door sash (its door leaves ride DOOR_SASH, not SASH).
INSERT INTO public.profile_articles (
    id, system_id, org_id, sku, name, role, material,
    face_width_mm, commercial_length_mm, welding_loss_mm,
    reinforcement_gap_mm, weight_kg_m, steel_weight_kg_m, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/DEMO_60/HOJA-PUERTA'),
    s.id, NULL, 'HOJA-PUERTA', 'Hoja Puerta Demo 60', 'DOOR_SASH', 'PVC',
    90.00, 6000.00, 6.00, 15.00, 2.4000, 1.7000, 'SEED_SYNTHETIC'
FROM public.profile_systems s
WHERE s.code = 'DEMO_60' AND s.is_global = TRUE
ON CONFLICT (system_id, sku) DO NOTHING;

-- Declared cut rules: PVC welds at 45°, aluminium is sawn mechanical.
INSERT INTO public.profile_cut_rules (
    id, system_id, org_id, role, cut_angle_deg, welded_ends,
    interlock_deduction_mm, rounding_mm, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/cutrule/' || role),
    s.id, NULL, role::public.profile_role, angle, welded, deduction, rounding, 'SEED_SYNTHETIC'
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('DEMO_60',        'FRAME',        45.00, 2,    0.00,  0.01),
    ('DEMO_60',        'SASH',         45.00, 2,    0.00,  0.01),
    ('DEMO_60',        'DOOR_SASH',    45.00, 2,    0.00,  0.01),
    ('DEMO_60',        'MULLION_V',    90.00, 0,    0.00,  0.01),
    ('DEMO_60',        'MULLION_H',    90.00, 0,    0.00,  0.01),
    ('DEMO_60',        'GLAZING_BEAD', 45.00, NULL, 0.00,  0.01),
    ('DEMO_60',        'THRESHOLD',    90.00, NULL, 0.00,  0.01),
    ('DEMO_70',        'FRAME',        45.00, 2,    0.00,  0.01),
    ('DEMO_70',        'SASH',         45.00, 2,    0.00,  0.01),
    ('DEMO_70',        'DOOR_SASH',    45.00, 2,    0.00,  0.01),
    ('DEMO_70',        'MULLION_V',    90.00, 0,    0.00,  0.01),
    ('DEMO_70',        'MULLION_H',    90.00, 0,    0.00,  0.01),
    ('DEMO_70',        'GLAZING_BEAD', 45.00, NULL, 0.00,  0.01),
    ('DEMO_70',        'THRESHOLD',    90.00, NULL, 0.00,  0.01),
    ('ALU_CORREDERA_70','FRAME',        45.00, NULL, 0.00,  0.01),
    ('ALU_CORREDERA_70','RAIL',         45.00, NULL, 0.00,  0.01),
    ('ALU_CORREDERA_70','SLIDING_SASH', 45.00, NULL, 0.00,  0.01),
    ('ALU_CORREDERA_70','INTERLOCK',    45.00, NULL, 12.00, 0.01),
    ('ALU_CORREDERA_70','MULLION_V',    90.00, NULL, 0.00,  0.01),
    ('ALU_CORREDERA_70','MULLION_H',    90.00, NULL, 0.00,  0.01),
    ('ALU_CORREDERA_70','GLAZING_BEAD', 45.00, NULL, 0.00,  0.01),
    ('ALU_65',          'FRAME',        45.00, NULL, 0.00,  0.01),
    ('ALU_65',          'SASH',         45.00, NULL, 0.00,  0.01),
    ('ALU_65',          'DOOR_SASH',    45.00, NULL, 0.00,  0.01),
    ('ALU_65',          'MULLION_V',    90.00, NULL, 0.00,  0.01),
    ('ALU_65',          'MULLION_H',    90.00, NULL, 0.00,  0.01),
    ('ALU_65',          'GLAZING_BEAD', 45.00, NULL, 0.00,  0.01),
    ('ALU_65',          'THRESHOLD',    90.00, NULL, 0.00,  0.01)
) AS r(sys_code, role, angle, welded, deduction, rounding)
WHERE s.code = r.sys_code AND s.is_global = TRUE
ON CONFLICT DO NOTHING;

-- Reinforcement rules: PVC families declare steel policy; aluminium systems
-- declare none (mechanical joints are never steel-reinforced — absence is a
-- declaration, not a gap).
INSERT INTO public.profile_reinforcement_rules (
    id, system_id, org_id, role, finish_class, min_length_mm,
    mandatory, screws_per_m, screw_sku, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/catalog/' || s.code || '/reinforce/' || role || '/' || finish || '/' || min_len),
    s.id, NULL, role::public.profile_role, finish, min_len,
    TRUE, 4.00, 'TORNILLO-4X16', 'SEED_SYNTHETIC'
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('FRAME'), ('SASH'), ('DOOR_SASH'), ('MULLION_V'), ('MULLION_H')
) AS roles(role)
CROSS JOIN (VALUES
    ('WHITE'::text, 1000.00::numeric),
    ('NON_WHITE'::text, 0.00::numeric)
) AS classes(finish, min_len)
WHERE s.code IN ('DEMO_60', 'DEMO_70') AND s.is_global = TRUE
ON CONFLICT DO NOTHING;

-- Leaf dimensional limits.
INSERT INTO public.system_typology_limits (
    id, system_id, org_id, opening_type,
    min_leaf_width_mm, max_leaf_width_mm,
    min_leaf_height_mm, max_leaf_height_mm,
    max_leaf_weight_kg, max_aspect_ratio, data_provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/limits/' || opening),
    s.id, NULL, opening, min_w::numeric, max_w::numeric, min_h::numeric,
    max_h::numeric, max_kg::numeric, aspect::numeric, 'SEED_SYNTHETIC'
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('DEMO_60',        'TURN_LEFT',       350.00, 1400.00, 400.00, 2500.00, 100.00, 2.80),
    ('DEMO_60',        'TILT_TURN_RIGHT', 450.00, 1600.00, 450.00, 2500.00, 130.00, NULL),
    ('DEMO_60',        'AWNING',          400.00, 1800.00, 350.00, 1200.00, 45.00,  NULL),
    ('DEMO_60',        'DOOR_ENTRY',      600.00, 1100.00, 1700.00, 2500.00, 120.00, NULL),
    ('DEMO_70',        'TURN_LEFT',       350.00, 1500.00, 400.00, 2500.00, 110.00, 2.80),
    ('DEMO_70',        'TILT_TURN_RIGHT', 450.00, 1600.00, 450.00, 2500.00, 130.00, NULL),
    ('DEMO_70',        'AWNING',          400.00, 1800.00, 350.00, 1200.00, 50.00,  NULL),
    ('DEMO_70',        'DOOR_ENTRY',      600.00, 1150.00, 1700.00, 2500.00, 130.00, NULL),
    ('ALU_CORREDERA_70','SLIDING_2L',      450.00, 1800.00, 600.00, 2400.00, 100.00, NULL),
    ('ALU_CORREDERA_70','SLIDING_3L',      450.00, 1800.00, 600.00, 2400.00, 100.00, NULL),
    ('ALU_CORREDERA_70','SLIDING_4L',      450.00, 1800.00, 600.00, 2400.00, 100.00, NULL),
    ('ALU_CORREDERA_70','SLIDING',         450.00, 1800.00, 600.00, 2400.00, 100.00, NULL),
    ('ALU_65',          'TURN_LEFT',       350.00, 1000.00, 400.00, 2200.00, 60.00,  NULL),
    ('ALU_65',          'TILT_TURN_RIGHT', 450.00, 1200.00, 450.00, 2200.00, 90.00,  NULL),
    ('ALU_65',          'DOOR_ENTRY',      600.00, 1100.00, 1700.00, 2500.00, 100.00, NULL)
) AS l(sys_code, opening, min_w, max_w, min_h, max_h, max_kg, aspect)
WHERE s.code = l.sys_code AND s.is_global = TRUE
ON CONFLICT DO NOTHING;

-- Purchase coverage: pricing flows through the fixture cost list, which
-- maps every purchase SKU. Seed the mappings for the new demo articles.
INSERT INTO public.profile_purchase_mappings
 (id, profile_article_id, org_id, commercial_sku, manufacturer_name, supplier_name,
  purchase_unit, physical_stock_identity, stock_color, cutting_profile_id, binding_version)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/purchase/' || article.id::text),
 article.id, NULL, 'COMPRA-' || article.sku, 'Referencia DEKOPEN', 'Proveedor de referencia', 'BAR',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/physical/profile/' || article.id::text),
 'WHITE',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'),
 1
FROM public.profile_articles article
JOIN public.profile_systems s ON s.id = article.system_id
WHERE s.code IN ('DEMO_60','DEMO_70','DEMO_CORREDERA_60','ALU_CORREDERA_70')
  AND s.is_global = TRUE AND article.org_id IS NULL
  AND EXISTS (SELECT 1 FROM information_schema.columns
              WHERE table_schema='public' AND table_name='profile_purchase_mappings'
                AND column_name='physical_stock_identity')
ON CONFLICT (id) DO NOTHING;

-- Steel reinforcement stock for every welded PVC member — DEMO_60's
-- original articles already carry theirs from the shot-07 block; NOT
-- EXISTS adds only the newcomers (HOJA-PUERTA and the new systems).
INSERT INTO public.reinforcement_articles
 (id, system_id, org_id, parent_profile_article_id, sku, commercial_sku, name,
  manufacturer_name, supplier_name, stock_length_mm, purchase_unit, is_default,
  physical_stock_identity, stock_color, cutting_profile_id, binding_version)
SELECT uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/shot07/steel/' || article.id::text),
 s.id, NULL, article.id, 'ACERO-' || article.sku, 'COMPRA-ACERO-' || article.sku,
 'Acero ' || article.name, 'Referencia DEKOPEN', 'Proveedor de referencia',
 6000.00, 'BAR', TRUE,
 uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/shot09/physical/steel/' || article.id::text),
 'WHITE',
 uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'),
 1
FROM public.profile_articles article
JOIN public.profile_systems s ON s.id = article.system_id
WHERE s.code IN ('DEMO_60','DEMO_70','DEMO_CORREDERA_60')
  AND s.is_global = TRUE AND article.org_id IS NULL
  AND article.role NOT IN ('GLAZING_BEAD','THRESHOLD')
  AND NOT EXISTS (SELECT 1 FROM public.reinforcement_articles r
                  WHERE r.parent_profile_article_id = article.id
                    AND r.org_id IS NULL)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.hardware_purchase_mappings
 (id, hardware_kit_id, org_id, purchasing_sku, manufacturer_name, purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/hardware/' || kit.id::text || '/V1'),
 kit.id, NULL, 'COMPRA-' || kit.sku, 'Referencia DEKOPEN', 'KIT', 1,
 '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
FROM public.hardware_kits kit
JOIN public.profile_systems s ON s.id = kit.system_id
WHERE s.code IN ('DEMO_70','DEMO_CORREDERA_60','ALU_CORREDERA_70')
  AND s.is_global = TRUE AND kit.org_id IS NULL
  AND EXISTS (SELECT 1 FROM information_schema.tables
              WHERE table_schema='public' AND table_name='hardware_purchase_mappings')
ON CONFLICT (id) DO NOTHING;

-- Glass purchase authorities for the new demo systems: one technical SKU per
-- supported glazing, matching each system's bead matrix. They feed both the
-- estimator's glass options and the documentary freeze.
INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name,
  purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/shot09/glass/' || s.code || '/' || m.technical_sku || '/V1'),
 s.id, NULL, m.technical_sku, m.purchasing_sku, 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, m.glass_spec
FROM public.profile_systems s
JOIN (VALUES
    ('DEMO_70',           'VIDRIO-BASE', 'VIDRIO-TERMINADO',  '4-16-4 Float Incoloro'),
    ('DEMO_70',           'DVH-20',      'COMPRA-DVH-20',     '4-12-4 Float Incoloro'),
    ('DEMO_CORREDERA_60', 'VIDRIO-BASE', 'VIDRIO-TERMINADO',  '4-16-4 Float Incoloro'),
    ('DEMO_CORREDERA_60', 'DVH-20',      'COMPRA-DVH-20',     '4-12-4 Float Incoloro'),
    ('DEMO_CORREDERA_60', 'MONO-4',      'COMPRA-MONO-4',     '4 Float Incoloro'),
    ('ALU_CORREDERA_70',  'VIDRIO-BASE', 'VIDRIO-TERMINADO',  '4-12-4 Float Incoloro')
) AS m(sys_code, technical_sku, purchasing_sku, glass_spec) ON m.sys_code = s.code
WHERE s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

-- Fastening purchase authority for DEMO_70 (PVC, reinforced — the engine
-- emits TORNILLO-4X16 fittings per reinforced member).
INSERT INTO public.fitting_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name,
  purchase_unit, version, provenance)
SELECT uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/catalog/' || s.code || '/fitting/TORNILLO-4X16/V1'),
 s.id, NULL, 'TORNILLO-4X16', 'COMPRA-TORNILLO-4X16', 'Referencia DEKOPEN',
 'EA', 1, '{"source":"Referencia DEKOPEN","mode":"KIT_ONLY"}'::jsonb
FROM public.profile_systems s
WHERE s.code = 'DEMO_70' AND s.is_global = TRUE
ON CONFLICT (system_id, org_id, technical_sku, version) DO NOTHING;

-- Manufacturing authorities for the new demo systems (placement, handles,
-- reinforcement-cut) — copies of the demo V2 conventions scoped to each code.
INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/' || s.code || '/V2'),
 s.id, NULL, p.version, jsonb_set(p.authority, '{policy_id}', to_jsonb(s.code || '_PLACEMENT_V2'))
FROM public.manufacturing_placement_policies p
JOIN public.profile_systems src ON src.id = p.system_id AND src.code = 'DEMO_60'
CROSS JOIN public.profile_systems s
WHERE s.code IN ('DEMO_70','ALU_CORREDERA_70','DEMO_CORREDERA_60') AND s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.handle_requirement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/handles/' || s.code || '/V2'),
 s.id, NULL, p.version,
 jsonb_set(
   jsonb_set(p.authority, '{policy_id}', to_jsonb(s.code || '_HANDLES_V2')),
   '{slots}', CASE WHEN s.code IN ('ALU_CORREDERA_70','DEMO_CORREDERA_60') THEN (
        SELECT jsonb_agg(slot) FROM jsonb_array_elements(p.authority -> 'slots') AS slot
        WHERE slot ->> 'opening_type' LIKE 'SLIDING%')
      ELSE p.authority -> 'slots' END)
FROM public.handle_requirement_policies p
JOIN public.profile_systems src ON src.id = p.system_id AND src.code = 'DEMO_60'
CROSS JOIN public.profile_systems s
WHERE s.code IN ('DEMO_70','ALU_CORREDERA_70','DEMO_CORREDERA_60') AND s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

-- Aluminium declares no steel reinforcement: the verbatim V1 copy stands
-- as the placeholder authority (its rules are never consulted — no member
-- of the family is marked for steel).
INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/' || s.code || '/V1'),
 s.id, NULL, p.version, jsonb_set(p.authority, '{policy_id}', to_jsonb(s.code || '_REINFORCEMENT_CUT_V1'))
FROM public.reinforcement_cut_policies p
JOIN public.profile_systems src ON src.id = p.system_id AND src.code = 'DEMO_60'
CROSS JOIN public.profile_systems s
WHERE s.code IN ('ALU_CORREDERA_70') AND s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

-- PVC systems generate their cut authorities from their own declared
-- reinforcement roles — a verbatim copy would leave sliding roles
-- (SLIDING_SASH, INTERLOCK, RAIL) and the new DOOR_SASH without a rule,
-- and the documentary freeze refuses members whose (role, angle_left,
-- angle_right) has no authority. Welded members declare every 45°/90°
-- combination the family can emit; sawn mullions and thresholds only
-- meet square cuts.
INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/' || s.code || '/V1'),
    s.id, NULL, 1,
    jsonb_build_object(
        'schema_version', 1,
        'policy_id', s.code || '_REINFORCEMENT_CUT_V1',
        'version', 1,
        'rules', gen.rules
    )
FROM public.profile_systems s
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
          WHERE system_id = s.id) rr
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
WHERE s.code IN ('DEMO_70','DEMO_CORREDERA_60') AND s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

-- DEMO_60 ships V2 with the D01 roles included: its V1 predates
-- DOOR_SASH and authorities are immutable once issued.
INSERT INTO public.reinforcement_cut_policies (id, system_id, org_id, version, authority)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/DEMO_60/V2'),
    s.id, NULL, 2,
    jsonb_build_object(
        'schema_version', 1,
        'policy_id', 'DEMO_60_REINFORCEMENT_CUT_V2',
        'version', 2,
        'rules', gen.rules
    )
FROM public.profile_systems s
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
          WHERE system_id = s.id) rr
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
WHERE s.code = 'DEMO_60' AND s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

-- Inspector authority for the new reference families: the documentary
-- freeze refuses systems without the fourteen rule configs (the chamber
-- clearance lives on the profile_systems insert).
INSERT INTO public.inspector_rule_configs (id, system_id, org_id, rule_id, params)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot07/config/' || s.id::text || '/' || cfg.rule_id),
 s.id, NULL, cfg.rule_id, cfg.params
FROM public.profile_systems s CROSS JOIN (VALUES
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
WHERE s.code IN ('DEMO_70','ALU_CORREDERA_70','DEMO_CORREDERA_60') AND s.is_global = TRUE
ON CONFLICT (system_id, org_id, rule_id) DO NOTHING;

END;
$d01$;

COMMIT;

BEGIN;

-- ------------------------------------------------------------------------
-- D02 — Vidrios de verdad: catálogo demo de productos estructurados,
-- reglas de seguridad y límites SINTÉTICOS (pendientes de revisión técnica;
-- la norma oficial entra por la ingesta de catálogo, no se inventa aquí).
-- ------------------------------------------------------------------------

-- Junquillos para el laminado 3+3 (6,38 mm): el paño real usa la misma
-- familia de junquillo del vidrio delgado de cada sistema.
INSERT INTO public.glazing_bead_matrix (
    id, system_id, org_id, glass_thickness_mm, bead_article_id,
    bead_width_mm, gasket_interior_mm, gasket_exterior_mm, cut_add_mm
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/bead/6.38/' || bead_sku),
    s.id, NULL, 6.38,
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/catalog/' || s.code || '/' || bead_sku),
    bead_w, 3.00, 3.00, cut_add
FROM public.profile_systems s
CROSS JOIN (VALUES
    ('DEMO_60',           'JQ-24'::text,      24.00::numeric, 9.00::numeric),
    ('DEMO_CORREDERA_60', 'JQ-CORR-24'::text, 24.00::numeric, 9.00::numeric)
) AS b(sys_code, bead_sku, bead_w, cut_add)
WHERE s.code = b.sys_code AND s.is_global = TRUE
ON CONFLICT (system_id, glass_thickness_mm) DO NOTHING;

-- Autoridades de compra para los nuevos SKU técnicos de vidrio.
INSERT INTO public.glass_purchase_mappings
 (id, system_id, org_id, technical_sku, purchasing_sku, manufacturer_name,
  purchase_unit, version, provenance, glass_spec)
SELECT uuid_generate_v5(uuid_ns_url(),
        'https://dekopen.local/shot09/glass/' || s.code || '/' || m.technical_sku || '/V1'),
 s.id, NULL, m.technical_sku, m.purchasing_sku, 'Referencia DEKOPEN', 'EA', 1,
 '{"source":"Referencia DEKOPEN","certified":"false"}'::jsonb, m.glass_spec
FROM public.profile_systems s
JOIN (VALUES
    ('DEMO_60', 'DVH-20', 'COMPRA-DVH-20', '4-12-4 Float Incoloro'),
    ('DEMO_60', 'VIDRIO-LOWE-24', 'COMPRA-TP-LOWE-24', '4 / 16 Ar / 4 Low-E (c3)'),
    ('DEMO_60', 'VIDRIO-TEMP-6', 'COMPRA-TEMP-6', '6 templado'),
    ('DEMO_60', 'VIDRIO-LAM-638', 'COMPRA-LAM-638', '3+3 PVB 0,38'),
    ('DEMO_70', 'VIDRIO-LOWE-24', 'COMPRA-TP-LOWE-24', '4 / 16 Ar / 4 Low-E (c3)'),
    ('DEMO_70', 'VIDRIO-TEMP-24', 'COMPRA-TP-TEMP-24', '4 templado / 16 aire / 4'),
    ('DEMO_CORREDERA_60', 'VIDRIO-LAM-638', 'COMPRA-LAM-638', '3+3 PVB 0,38'),
    ('ALU_CORREDERA_70', 'VIDRIO-LOWE-20', 'COMPRA-TP-LOWE-20', '4 / 12 Ar / 4 Low-E (c3)')
    ) AS m(sys_code, technical_sku, purchasing_sku, glass_spec) ON m.sys_code = s.code
WHERE s.is_global = TRUE
ON CONFLICT (id) DO NOTHING;

-- Catálogo demo de productos de vidrio: composición estructurada generada
-- por el propio parser del motor. Los datos de proveedor (Ug, g, TL,
-- clase de seguridad) son SINTÉTICOS y quedan pendientes de revisión.
INSERT INTO public.glass_products (
    id, org_id, system_id, sku, commercial_name, notation, composition,
    total_thickness_mm, safety_class, ug_w_m2k, g_value,
    light_transmission_pct, weight_kg_m2, min_billable_area_m2, price_tier,
    supplier_name, supplier_sku, data_provenance, review_pending
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/d02/glass/' || s.code || '/' || p.sku),
    NULL, s.id, p.sku, p.commercial_name, p.notation, p.composition::jsonb,
    p.total_thickness_mm, p.safety_class, p.ug_w_m2k, p.g_value,
    p.light_transmission_pct, p.weight_kg_m2, p.min_billable_area_m2, p.price_tier,
    'Vidriería DEMO (sintético)', p.sku, 'SEED_SYNTHETIC', p.review_pending
FROM public.profile_systems s
JOIN (VALUES
    ('DEMO_60'::text, 'VIDRIO-BASE'::text, 'Termopanel incoloro 4·16·4'::text, '4-16-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '24'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('DEMO_60'::text, 'DVH-20'::text, 'Termopanel incoloro 4·12·4'::text, '4-12-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"12","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '20'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('DEMO_60'::text, 'VIDRIO-LOWE-24'::text, 'Termopanel Low-E 4·16·4'::text, '4 / 16 Ar / 4 Low-E (c3)'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"ARGON","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":"LOW_E","coating_face":3,"supplier_sku":null}]}'::text, '24'::numeric, NULL::text, 1.400, 0.630, 80.00,
     '20.00'::numeric, '0.30'::numeric, 4::smallint, TRUE::boolean),
    ('DEMO_60'::text, 'VIDRIO-TEMP-6'::text, 'Templado incoloro 6 mm'::text, '6 templado'::text,
     '{"layers":[{"type":"lamina","panes":["6"],"interlayer":null,"tint":"CLEAR","treatment":"TEMPERED","coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '6'::numeric, 'B'::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '15.00'::numeric, '0.30'::numeric, 3::smallint, TRUE::boolean),
    ('DEMO_60'::text, 'VIDRIO-LAM-638'::text, 'Laminado seguridad 3+3'::text, '3+3 PVB 0,38'::text,
     '{"layers":[{"type":"lamina","panes":["3","3"],"interlayer":"PVB_038","tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '6.38'::numeric, 'A'::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '15.4066'::numeric, '0.30'::numeric, 4::smallint, TRUE::boolean),
    ('DEMO_70'::text, 'VIDRIO-BASE'::text, 'Termopanel incoloro 4·16·4'::text, '4-16-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '24'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('DEMO_70'::text, 'DVH-20'::text, 'Termopanel incoloro 4·12·4'::text, '4-12-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"12","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '20'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('DEMO_70'::text, 'VIDRIO-LOWE-24'::text, 'Termopanel Low-E 4·16·4'::text, '4 / 16 Ar / 4 Low-E (c3)'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"ARGON","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":"LOW_E","coating_face":3,"supplier_sku":null}]}'::text, '24'::numeric, NULL::text, 1.400, 0.630, 80.00,
     '20.00'::numeric, '0.30'::numeric, 4::smallint, TRUE::boolean),
    ('DEMO_70'::text, 'VIDRIO-TEMP-24'::text, 'Termopanel templado 4·16·4'::text, '4 templado / 16 aire / 4'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":"TEMPERED","coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '24'::numeric, 'B'::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 4::smallint, TRUE::boolean),
    ('DEMO_CORREDERA_60'::text, 'VIDRIO-BASE'::text, 'Termopanel incoloro 4·16·4'::text, '4-16-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '24'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('DEMO_CORREDERA_60'::text, 'DVH-20'::text, 'Termopanel incoloro 4·12·4'::text, '4-12-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"12","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '20'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('DEMO_CORREDERA_60'::text, 'MONO-4'::text, 'Monolítico incoloro 4 mm'::text, '4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '4'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '10.00'::numeric, '0.30'::numeric, 1::smallint, FALSE::boolean),
    ('DEMO_CORREDERA_60'::text, 'VIDRIO-LAM-638'::text, 'Laminado seguridad 3+3'::text, '3+3 PVB 0,38'::text,
     '{"layers":[{"type":"lamina","panes":["3","3"],"interlayer":"PVB_038","tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '6.38'::numeric, 'A'::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '15.4066'::numeric, '0.30'::numeric, 4::smallint, TRUE::boolean),
    ('ALU_CORREDERA_70'::text, 'VIDRIO-BASE'::text, 'Termopanel incoloro 4·12·4'::text, '4-12-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"12","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '20'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('ALU_CORREDERA_70'::text, 'VIDRIO-LOWE-20'::text, 'Termopanel Low-E 4·12·4'::text, '4 / 12 Ar / 4 Low-E (c3)'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"12","gas":"ARGON","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":"LOW_E","coating_face":3,"supplier_sku":null}]}'::text, '20'::numeric, NULL::text, 1.400, 0.630, 80.00,
     '20.00'::numeric, '0.30'::numeric, 4::smallint, TRUE::boolean),
    ('ALU_65'::text, 'DVH-24'::text, 'Termopanel incoloro 4·16·4'::text, '4-16-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"16","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '24'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('ALU_65'::text, 'MONO-5'::text, 'Monolítico incoloro 5 mm'::text, '5 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["5"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '5'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '12.50'::numeric, '0.30'::numeric, 1::smallint, FALSE::boolean),
    ('GLASS_45'::text, 'DVH-28'::text, 'Termopanel incoloro 4·20·4'::text, '4-20-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"20","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '28'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('GLASS_45'::text, 'DVH-32'::text, 'Termopanel incoloro 4·24·4'::text, '4-24-4 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null},{"type":"chamber","width_mm":"24","gas":"AIR","spacer":"ALUMINIUM","sealant":null},{"type":"lamina","panes":["4"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '32'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 2::smallint, FALSE::boolean),
    ('GLASS_45'::text, 'MONO-8'::text, 'Monolítico incoloro 8 mm'::text, '8 Float Incoloro'::text,
     '{"layers":[{"type":"lamina","panes":["8"],"interlayer":null,"tint":"CLEAR","treatment":null,"coating":null,"coating_face":null,"supplier_sku":null}]}'::text, '8'::numeric, NULL::text, NULL::numeric, NULL::numeric, NULL::numeric,
     '20.00'::numeric, '0.30'::numeric, 1::smallint, FALSE::boolean)
    ) AS p(sys_code, sku, commercial_name, notation, composition, total_thickness_mm,
            safety_class, ug_w_m2k, g_value, light_transmission_pct, weight_kg_m2,
            min_billable_area_m2, price_tier, review_pending)
    ON p.sys_code = s.code
WHERE s.is_global = TRUE
ON CONFLICT DO NOTHING;

-- Recargos demo por producto (CLP sintéticos).
INSERT INTO public.glass_product_surcharges (
    id, product_id, org_id, kind, unit, unit_cost, currency, label,
    data_provenance, review_pending
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/d02/glass-surcharge/' || gp.id::text || '/' || r.kind),
    gp.id, NULL, r.kind, r.unit, r.unit_cost, 'CLP', r.label,
    'SEED_SYNTHETIC', TRUE
FROM public.glass_products gp
JOIN (VALUES
    ('VIDRIO-LOWE-24'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text),
    ('VIDRIO-LOWE-24'::text, 'DRILL'::text, 'EA'::text, '3500'::numeric, 'Perforación'::text),
    ('VIDRIO-TEMP-24'::text, 'TEMPERED'::text, 'M2'::text, '5500'::numeric, 'Recargo templado'::text),
    ('VIDRIO-TEMP-24'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text),
    ('VIDRIO-TEMP-6'::text, 'TEMPERED'::text, 'M2'::text, '5500'::numeric, 'Recargo templado'::text),
    ('VIDRIO-TEMP-6'::text, 'EDGE_POLISH'::text, 'M'::text, '1200'::numeric, 'Canto pulido'::text),
    ('VIDRIO-LAM-638'::text, 'EDGE_POLISH'::text, 'M'::text, '1200'::numeric, 'Canto pulido'::text),
    ('VIDRIO-LOWE-20'::text, 'DRILL'::text, 'EA'::text, '3500'::numeric, 'Perforación'::text),
    ('VIDRIO-BASE'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text),
    ('VIDRIO-BASE'::text, 'DRILL'::text, 'EA'::text, '3500'::numeric, 'Perforación'::text),
    ('DVH-20'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text),
    ('DVH-24'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text),
    ('DVH-28'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text),
    ('DVH-32'::text, 'PALILLAJE'::text, 'CROSS'::text, '1500'::numeric, 'Palillaje interior — por cruce'::text)
    ) AS r(sku, kind, unit, unit_cost, label)
    ON r.sku = gp.sku
WHERE gp.org_id IS NULL
ON CONFLICT DO NOTHING;

-- Reglas de seguridad demo (familia NCh 135/2): avisos, no bloqueos. El
-- texto es sintético y queda pendiente de la norma oficial vía ingesta.
INSERT INTO public.glass_safety_rules (
    id, org_id, code, title, message, applies_openings, sill_below_mm,
    min_area_m2, requires_door, requires_adjacent_door, required_safety,
    severity, source_ref, data_provenance, review_pending
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/d02/glass-rule/' || r.code),
    NULL, r.code, r.title, r.message, r.applies_openings, r.sill_below_mm,
    r.min_area_m2, r.requires_door, r.requires_adjacent_door, r.required_safety,
    r.severity, 'NCh 135/2 — referencia sintética pendiente de norma oficial',
    'SEED_SYNTHETIC', TRUE
FROM (VALUES
    ('GLASS-SAFETY-DOOR'::text, 'Paño vidriado en puerta'::text, 'El paño de una puerta vidriada debería llevar vidrio de seguridad (templado o laminado).'::text,
     NULL::text[], NULL::numeric, NULL, 'True'::boolean, NULL, 'SAFETY_GLASS'::text, 'WARNING'::text),
    ('GLASS-SAFETY-ADJ-DOOR'::text, 'Paño lateral junto a puerta'::text, 'El paño lateral de una puerta debería llevar vidrio de seguridad.'::text,
     NULL::text[], NULL, NULL, NULL, 'True'::boolean, 'SAFETY_GLASS'::text, 'WARNING'::text),
    -- Ninguna regla de antepecho: la distancia del vidrio al piso no la
    -- sabe el modelo (la base de la unidad no es el piso). Una regla
    -- sill_below_mm dispararía en falso en toda ventana normal; las reglas
    -- de piso llegan con la norma oficial y contexto de instalación.
    ('GLASS-SAFETY-LARGE-PANE'::text, 'Gran paño vidriado'::text, 'Un paño de 4 m² o más expone una superficie grande: se recomienda vidrio de seguridad.'::text,
     NULL::text[], NULL, '4.0'::numeric, NULL, NULL, 'SAFETY_GLASS'::text, 'WARNING'::text)
    ) AS r(code, title, message, applies_openings, sill_below_mm, min_area_m2,
            requires_door, requires_adjacent_door, required_safety, severity)
ON CONFLICT DO NOTHING;

-- Límites dimensionales demo (sintéticos; el templado exige medida exacta).
INSERT INTO public.glass_type_limits (
    id, org_id, code, lamina_kind, thickness_min_mm, thickness_max_mm,
    min_side_mm, max_side_mm, min_area_m2, max_area_m2, max_aspect_ratio,
    requires_exact_cut, severity, source_ref, data_provenance, review_pending
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/d02/glass-limit/' || r.code),
    NULL, r.code, r.lamina_kind, r.thickness_min_mm, r.thickness_max_mm,
    r.min_side_mm, r.max_side_mm, r.min_area_m2, r.max_area_m2,
    r.max_aspect_ratio, r.requires_exact_cut, r.severity, r.source_ref,
    'SEED_SYNTHETIC', TRUE
FROM (VALUES
    ('GLASS-LIMIT-TEMPERED-EXACT-CUT'::text, 'TEMPERED'::text, NULL, NULL, NULL, NULL,
     NULL::numeric, NULL, NULL, TRUE::boolean, 'WARNING'::text, 'Práctica vidriera — el templado no se recorta'::text),
    ('GLASS-LIMIT-FLOAT-4'::text, 'FLOAT'::text, '4'::numeric, '4'::numeric, NULL, NULL,
     NULL, '4.5'::numeric, NULL, FALSE::boolean, 'WARNING'::text, 'Referencia sintética — revisar con proveedor'::text),
    ('GLASS-LIMIT-TEMPERED-SIDE'::text, 'TEMPERED'::text, NULL, NULL, NULL, '3200'::numeric,
     NULL, NULL, NULL, FALSE::boolean, 'WARNING'::text, 'Referencia sintética — revisar con proveedor'::text),
    ('GLASS-LIMIT-MONO-SIDE'::text, 'FLOAT'::text, NULL, NULL, '250'::numeric, NULL,
     NULL, NULL, '12.0'::numeric, FALSE::boolean, 'WARNING'::text, 'Referencia sintética — relación de aspecto ≤ 12'::text)
    ) AS r(code, lamina_kind, thickness_min_mm, thickness_max_mm, min_side_mm,
            max_side_mm, min_area_m2, max_area_m2, max_aspect_ratio,
            requires_exact_cut, severity, source_ref)
ON CONFLICT DO NOTHING;

COMMIT;
