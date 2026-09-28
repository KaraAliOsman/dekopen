BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(9);

-- Policy authority JSONB must store numerics as JSON numbers, not strings:
-- the strict engine contract rejects string decimals and the field-level
-- parsers refuse them. History rows may legitimately keep the defect —
-- the invariant is that the LATEST version per (system_id, org_id) scope,
-- which is what every loader resolves, carries numeric-native payloads.

SELECT is(
  (SELECT count(*)::int FROM (
     SELECT DISTINCT ON (system_id, org_id) authority
     FROM handle_requirement_policies
     ORDER BY system_id, org_id NULLS LAST, version DESC, id) s
   WHERE s.authority::text ~
     '"(horizontal_offset_mm|mounting_min_from_leaf_top_mm|mounting_max_from_leaf_top_mm)"\s*:\s*"-?[0-9]+(\.[0-9]+)?"'),
  0,
  'handle_requirement_policies latest: no string-typed numeric fields');

SELECT is(
  (SELECT count(*)::int FROM (
     SELECT DISTINCT ON (system_id, org_id) authority
     FROM reinforcement_cut_policies
     ORDER BY system_id, org_id NULLS LAST, version DESC, id) s
   WHERE s.authority::text ~
     '"(profile_angle_left|profile_angle_right|reinforcement_angle_left|reinforcement_angle_right)"\s*:\s*"-?[0-9]+(\.[0-9]+)?"'),
  0,
  'reinforcement_cut_policies latest: no string-typed numeric fields');

SELECT is(
  (SELECT count(*)::int FROM (
     SELECT DISTINCT ON (system_id, org_id) authority
     FROM manufacturing_placement_policies
     ORDER BY system_id, org_id NULLS LAST, version DESC, id) s
   WHERE s.authority::text ~
     '"(x_mm|y_mm|x_pitches)"\s*:\s*"-?[0-9]+(\.[0-9]+)?"'),
  0,
  'manufacturing_placement_policies latest: no string-typed numeric fields');

-- The embedded policy version matches the row version at latest revision.
SELECT is(
  (SELECT count(*)::int FROM (
     SELECT DISTINCT ON (system_id, org_id) id, version,
            (authority->>'version')::int AS authority_version
     FROM handle_requirement_policies
     ORDER BY system_id, org_id NULLS LAST, version DESC, id) s
   WHERE authority_version IS DISTINCT FROM version),
  0,
  'handle policies: embedded authority.version matches row version');

SELECT is(
  (SELECT count(*)::int FROM (
     SELECT DISTINCT ON (system_id, org_id) id, version,
            (authority->>'version')::int AS authority_version
     FROM manufacturing_placement_policies
     ORDER BY system_id, org_id NULLS LAST, version DESC, id) s
   WHERE authority_version IS DISTINCT FROM version),
  0,
  'placement policies: embedded authority.version matches row version');

SELECT is(
  (SELECT count(*)::int FROM (
     SELECT DISTINCT ON (system_id, org_id) id, version,
            (authority->>'version')::int AS authority_version
     FROM reinforcement_cut_policies
     ORDER BY system_id, org_id NULLS LAST, version DESC, id) s
   WHERE authority_version IS DISTINCT FROM version),
  0,
  'reinforcement policies: embedded authority.version matches row version');

-- Spot: declared numeric fields are JSON numbers at latest revision.
SELECT ok(
  NOT EXISTS (
    SELECT 1 FROM (
      SELECT DISTINCT ON (system_id, org_id) authority
      FROM handle_requirement_policies
      ORDER BY system_id, org_id NULLS LAST, version DESC, id) h
    WHERE jsonb_typeof(h.authority->'slots'->0->'horizontal_offset_mm') IS DISTINCT FROM 'number'
      AND h.authority->'slots'->0->'horizontal_offset_mm' IS NOT NULL
  ),
  'handle slot horizontal_offset_mm is a JSON number');

SELECT ok(
  NOT EXISTS (
    SELECT 1 FROM (
      SELECT DISTINCT ON (system_id, org_id) authority
      FROM manufacturing_placement_policies
      ORDER BY system_id, org_id NULLS LAST, version DESC, id) p
    WHERE jsonb_typeof(p.authority->'bead_offsets'->'TOP'->'x_mm') IS DISTINCT FROM 'number'
      AND p.authority->'bead_offsets'->'TOP'->'x_mm' IS NOT NULL
  ),
  'placement bead_offsets.TOP.x_mm is a JSON number');

SELECT ok(
  NOT EXISTS (
    SELECT 1 FROM (
      SELECT DISTINCT ON (system_id, org_id) authority
      FROM reinforcement_cut_policies
      ORDER BY system_id, org_id NULLS LAST, version DESC, id) r
    WHERE jsonb_typeof(r.authority->'rules'->0->'profile_angle_left') IS DISTINCT FROM 'number'
      AND r.authority->'rules'->0->'profile_angle_left' IS NOT NULL
  ),
  'reinforcement rule profile_angle_left is a JSON number');

SELECT finish();
ROLLBACK;
