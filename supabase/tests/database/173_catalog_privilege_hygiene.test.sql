BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(15);

-- TRUNCATE/TRIGGER/REFERENCES revoked on every catalog authority table.
SELECT ok(
  NOT has_table_privilege('authenticated', 'public.' || t, 'TRUNCATE'),
  format('authenticated cannot TRUNCATE %I (RLS-bypassing)', t)
) FROM (VALUES
  ('profile_systems'), ('profile_articles'), ('glazing_bead_matrix'),
  ('hardware_kits'), ('infill_articles')
) v(t);
SELECT ok(
  NOT has_table_privilege('authenticated', 'public.' || t, 'TRIGGER'),
  format('authenticated has no TRIGGER on %I', t)
) FROM (VALUES
  ('profile_systems'), ('profile_articles'), ('glazing_bead_matrix'),
  ('hardware_kits'), ('infill_articles')
) v(t);
SELECT ok(
  NOT has_table_privilege('authenticated', 'public.' || t, 'REFERENCES'),
  format('authenticated has no REFERENCES on %I', t)
) FROM (VALUES
  ('profile_systems'), ('profile_articles'), ('glazing_bead_matrix'),
  ('hardware_kits'), ('infill_articles')
) v(t);

SELECT finish();
ROLLBACK;
