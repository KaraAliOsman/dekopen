-- Repair: policy authority JSONB stored numeric fields as strings.
--
-- `handle_requirement_policies`, `manufacturing_placement_policies` and
-- `reinforcement_cut_policies` payloads were seeded with numeric authority
-- values as JSON strings ("-10.00") instead of JSON numbers (-10.00). The
-- strict engine contract (EngineModel, strict=True) rejects string
-- decimals, so `design-options` answered 422 `technical_authority_required`
-- on every system whose policy was affected — the kit picker, handle
-- datum rules and readiness preview were unreachable.
--
-- Policy rows are immutable (immutable_authority trigger): the fix lands
-- as a NEW version per (system_id, org_id) pair, which is also how the
-- domain corrects authorities. Loaders already prefer the highest
-- version. The values are unchanged — only the JSON type is repaired —
-- scoped to each policy's own numeric field names so no string content
-- elsewhere is touched.

CREATE OR REPLACE FUNCTION private._authority_native_numerics(
    p_table text,
    p_fields text
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    EXECUTE format(
        'INSERT INTO public.%I (id, system_id, org_id, version, authority)
         SELECT uuid_generate_v5(
                    uuid_ns_url(),
                    ''https://dekopen.local/repair/native-numerics/%s/'' || s.id
                ),
                s.system_id, s.org_id, s.version + 1,
                (regexp_replace(
                    s.authority::text,
                    ''"(%s)"\s*:\s*"(-?[0-9]+(?:\.[0-9]+)?)"'',
                    ''"\1":\2'', ''g''
                )::jsonb || jsonb_build_object(''version'', s.version + 1))
         FROM (
             SELECT DISTINCT ON (system_id, org_id)
                    id, system_id, org_id, version, authority
             FROM public.%I
             ORDER BY system_id, org_id NULLS LAST, version DESC, id
         ) s
         WHERE s.authority::text ~
             ''"(%s)"\s*:\s*"-?[0-9]+(\.[0-9]+)?"''',
        p_table, p_table, p_fields, p_table, p_fields
    );
END;
$$;

SELECT private._authority_native_numerics(
    'handle_requirement_policies',
    'horizontal_offset_mm|mounting_min_from_leaf_top_mm|mounting_max_from_leaf_top_mm'
);
SELECT private._authority_native_numerics(
    'reinforcement_cut_policies',
    'profile_angle_left|profile_angle_right|reinforcement_angle_left|reinforcement_angle_right'
);
SELECT private._authority_native_numerics(
    'manufacturing_placement_policies',
    'x_mm|y_mm|x_pitches'
);

DROP FUNCTION private._authority_native_numerics(text, text);
