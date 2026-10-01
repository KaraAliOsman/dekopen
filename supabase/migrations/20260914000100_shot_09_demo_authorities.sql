BEGIN;

INSERT INTO public.manufacturing_placement_policies (
    id, system_id, org_id, version, authority
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/DEMO_60/V1'),
    system.id,
    NULL,
    1,
    '{
      "schema_version": 1,
      "policy_id": "DEMO_60_PLACEMENT_V1",
      "version": 1,
      "sliding_leaf_offsets": {
        "L1": {"x_mm": "0.00", "y_mm": "0.00"},
        "L2": {"x_mm": "940.00", "y_mm": "0.00"}
      },
      "sliding_infill_offsets": {
        "L1": {"x_mm": "70.00", "y_mm": "70.00"},
        "L2": {"x_mm": "70.00", "y_mm": "70.00"}
      },
      "bead_offsets": {
        "TOP": {"x_mm": "0.00", "y_mm": "0.00"},
        "RIGHT": {"x_mm": "0.00", "y_mm": "0.00"},
        "BOTTOM": {"x_mm": "0.00", "y_mm": "0.00"},
        "LEFT": {"x_mm": "0.00", "y_mm": "0.00"}
      }
    }'::jsonb
FROM public.profile_systems AS system
WHERE system.code = 'DEMO_60' AND system.is_global
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.handle_requirement_policies (
    id, system_id, org_id, version, authority
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/handles/DEMO_60/V1'),
    system.id,
    NULL,
    1,
    '{
      "schema_version": 1,
      "policy_id": "DEMO_60_HANDLES_V1",
      "version": 1,
      "slots": [
        {"opening_type":"TURN_LEFT","leaf_slot":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"TURN_RIGHT","leaf_slot":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"TILT_TURN_LEFT","leaf_slot":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"TILT_TURN_RIGHT","leaf_slot":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"SLIDING_2L","leaf_slot":"L1","handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"SLIDING_2L","leaf_slot":"L2","handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"AWNING","leaf_slot":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"},
        {"opening_type":"DOOR_ENTRY","leaf_slot":null,"handle_domain_slot":"PRIMARY","host_member_side":"RIGHT","horizontal_reference":"HOST_MEMBER_AXIS","horizontal_offset_mm":"-10.00","permitted_vertical_references":["OUTER_TOP","OUTER_BOTTOM","LEAF_TOP","LEAF_BOTTOM"],"mounting_min_from_leaf_top_mm":"0.00","mounting_max_from_leaf_top_mm":"3000.00"}
      ]
    }'::jsonb
FROM public.profile_systems AS system
WHERE system.code = 'DEMO_60' AND system.is_global
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.reinforcement_cut_policies (
    id, system_id, org_id, version, authority
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/reinforcement-cuts/DEMO_60/V1'),
    system.id,
    NULL,
    1,
    '{
      "schema_version": 1,
      "policy_id": "DEMO_60_REINFORCEMENT_CUT_V1",
      "version": 1,
      "rules": [
        {"role":"FRAME","profile_angle_left":45.0,"profile_angle_right":45.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},
        {"role":"FRAME","profile_angle_left":45.0,"profile_angle_right":90.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},
        {"role":"SASH","profile_angle_left":45.0,"profile_angle_right":45.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},
        {"role":"MULLION_V","profile_angle_left":90.0,"profile_angle_right":90.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true},
        {"role":"MULLION_H","profile_angle_left":90.0,"profile_angle_right":90.0,"reinforcement_angle_left":90.0,"reinforcement_angle_right":90.0,"length_authority":"EXISTING_ENGINE","compatible_with_existing_length":true}
      ]
    }'::jsonb
FROM public.profile_systems AS system
WHERE system.code = 'DEMO_60' AND system.is_global
ON CONFLICT (id) DO NOTHING;

UPDATE public.profile_purchase_mappings AS mapping
SET physical_stock_identity = uuid_generate_v5(
        uuid_ns_url(), 'https://dekopen.local/shot09/physical/profile/' || mapping.profile_article_id
    ),
    stock_color = 'WHITE',
    cutting_profile_id = uuid_generate_v5(
        uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'
    ),
    binding_version = 1
FROM public.profile_articles AS article
JOIN public.profile_systems AS system ON system.id = article.system_id
WHERE mapping.profile_article_id = article.id
  AND system.code = 'DEMO_60' AND system.is_global
  AND mapping.org_id IS NULL;

UPDATE public.reinforcement_articles AS reinforcement
SET physical_stock_identity = uuid_generate_v5(
        uuid_ns_url(), 'https://dekopen.local/shot09/physical/steel/' || reinforcement.id
    ),
    stock_color = 'WHITE',
    cutting_profile_id = uuid_generate_v5(
        uuid_ns_url(), 'https://dekopen.local/shot07/cutting/DEMO'
    ),
    binding_version = 1
FROM public.profile_systems AS system
WHERE reinforcement.system_id = system.id
  AND system.code = 'DEMO_60' AND system.is_global
  AND reinforcement.org_id IS NULL;

INSERT INTO public.glass_purchase_mappings (
    id, system_id, org_id, technical_sku, purchasing_sku,
    manufacturer_name, purchase_unit, version, provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/glass/DEMO_60/GLASS-BASE/V1'),
    system.id,
    NULL,
    'GLASS-BASE',
    'DEMO-GLASS-FINISHED-UNIT',
    'DEMO_60 SYNTHETIC FIXTURE',
    'EA',
    1,
    '{"source":"DEMO_60 SYNTHETIC FIXTURE","certified":"false"}'::jsonb
FROM public.profile_systems AS system
WHERE system.code = 'DEMO_60' AND system.is_global
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.hardware_purchase_mappings (
    id, hardware_kit_id, org_id, purchasing_sku,
    manufacturer_name, purchase_unit, version, provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/hardware/' || kit.id || '/V1'),
    kit.id,
    NULL,
    'DEMO-BUY-' || kit.sku,
    'DEMO_60 SYNTHETIC FIXTURE',
    'KIT',
    1,
    '{"source":"DEMO_60 SYNTHETIC FIXTURE","mode":"KIT_ONLY"}'::jsonb
FROM public.hardware_kits AS kit
JOIN public.profile_systems AS system ON system.id = kit.system_id
WHERE system.code = 'DEMO_60' AND system.is_global AND kit.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.panel_purchase_authorities (
    id, infill_article_id, org_id, purchasing_sku, manufacturer_name,
    supply_form, purchase_unit, version, provenance
)
SELECT
    uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/panel/' || panel.id || '/V1'),
    panel.id,
    NULL,
    'DEMO-BUY-' || panel.sku,
    'DEMO_60 SYNTHETIC FIXTURE',
    'CUT_TO_SIZE',
    'EA',
    1,
    '{"source":"DEMO_60 SYNTHETIC FIXTURE","certified":"false"}'::jsonb
FROM public.infill_articles AS panel
JOIN public.profile_systems AS system ON system.id = panel.system_id
WHERE system.code = 'DEMO_60' AND system.is_global AND panel.org_id IS NULL
ON CONFLICT (id) DO NOTHING;

COMMIT;
