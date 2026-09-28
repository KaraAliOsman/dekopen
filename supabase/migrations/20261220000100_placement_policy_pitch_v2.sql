-- Placement authority v2: sliding leaf origins resolve in
-- slot pitches (the bay's computed pitch), not a fixed millimetre
-- constant that only holds for one tuned demo width and fails to exist
-- for L3/L4 leaves. Policy rows are immutable, so the corrected
-- authority lands as a v2 row and the prep loader prefers the latest
-- version. x = x_mm + x_pitches * slot_pitch_mm.


INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/DEMO_60/V2'),
       s.id, NULL, 2, '{"schema_version":1,"policy_id":"DEMO_60_PLACEMENT_V2","version":2,"sliding_leaf_offsets":{"L1":{"x_mm":0.00,"y_mm":0.00,"x_pitches":0.00},"L2":{"x_mm":0.00,"y_mm":0.00,"x_pitches":1.00},"L3":{"x_mm":0.00,"y_mm":0.00,"x_pitches":2.00},"L4":{"x_mm":0.00,"y_mm":0.00,"x_pitches":3.00}},"sliding_infill_offsets":{"L1":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L2":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L3":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L4":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00}},"bead_offsets":{"TOP":{"x_mm":0.00,"y_mm":0.00},"RIGHT":{"x_mm":0.00,"y_mm":0.00},"BOTTOM":{"x_mm":0.00,"y_mm":0.00},"LEFT":{"x_mm":0.00,"y_mm":0.00}}}'::jsonb
FROM public.profile_systems s
WHERE s.code='DEMO_60' AND s.is_global=TRUE
  AND NOT EXISTS (
    SELECT 1 FROM public.manufacturing_placement_policies p
    WHERE p.system_id=s.id AND p.org_id IS NULL AND p.version=2)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/ALU_65/V2'),
       s.id, NULL, 2, '{"schema_version":1,"policy_id":"ALU_65_PLACEMENT_V2","version":2,"sliding_leaf_offsets":{"L1":{"x_mm":0.00,"y_mm":0.00,"x_pitches":0.00},"L2":{"x_mm":0.00,"y_mm":0.00,"x_pitches":1.00},"L3":{"x_mm":0.00,"y_mm":0.00,"x_pitches":2.00},"L4":{"x_mm":0.00,"y_mm":0.00,"x_pitches":3.00}},"sliding_infill_offsets":{"L1":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L2":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L3":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L4":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00}},"bead_offsets":{"TOP":{"x_mm":0.00,"y_mm":0.00},"RIGHT":{"x_mm":0.00,"y_mm":0.00},"BOTTOM":{"x_mm":0.00,"y_mm":0.00},"LEFT":{"x_mm":0.00,"y_mm":0.00}}}'::jsonb
FROM public.profile_systems s
WHERE s.code='ALU_65' AND s.is_global=TRUE
  AND NOT EXISTS (
    SELECT 1 FROM public.manufacturing_placement_policies p
    WHERE p.system_id=s.id AND p.org_id IS NULL AND p.version=2)
ON CONFLICT (id) DO NOTHING;

INSERT INTO public.manufacturing_placement_policies (id, system_id, org_id, version, authority)
SELECT uuid_generate_v5(uuid_ns_url(), 'https://dekopen.local/shot09/placement/GLASS_45/V2'),
       s.id, NULL, 2, '{"schema_version":1,"policy_id":"GLASS_45_PLACEMENT_V2","version":2,"sliding_leaf_offsets":{"L1":{"x_mm":0.00,"y_mm":0.00,"x_pitches":0.00},"L2":{"x_mm":0.00,"y_mm":0.00,"x_pitches":1.00},"L3":{"x_mm":0.00,"y_mm":0.00,"x_pitches":2.00},"L4":{"x_mm":0.00,"y_mm":0.00,"x_pitches":3.00}},"sliding_infill_offsets":{"L1":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L2":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L3":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00},"L4":{"x_mm":70.00,"y_mm":70.00,"x_pitches":0.00}},"bead_offsets":{"TOP":{"x_mm":0.00,"y_mm":0.00},"RIGHT":{"x_mm":0.00,"y_mm":0.00},"BOTTOM":{"x_mm":0.00,"y_mm":0.00},"LEFT":{"x_mm":0.00,"y_mm":0.00}}}'::jsonb
FROM public.profile_systems s
WHERE s.code='GLASS_45' AND s.is_global=TRUE
  AND NOT EXISTS (
    SELECT 1 FROM public.manufacturing_placement_policies p
    WHERE p.system_id=s.id AND p.org_id IS NULL AND p.version=2)
ON CONFLICT (id) DO NOTHING;
