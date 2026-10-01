-- 040_shot_06 pins infill articles as member read-only: panels are imported
-- purchase/manufacturing authority, and every app mutation already escalates
-- through catalog_backend. catalog_integrity granted authenticated
-- column-level INSERT/UPDATE on infill_articles uniformly with the other
-- catalog tables; with no member write policy the grant only turned the
-- expected insufficient_privilege error into a silent no-op write. Revoke the
-- member write privileges on infill_articles only — the member-editable
-- column model on profile_systems/profile_articles/glazing_bead_matrix/
-- hardware_kits (156_catalog_integrity) is intentional and stays.
BEGIN;

REVOKE INSERT, UPDATE, DELETE ON public.infill_articles FROM authenticated;

COMMIT;
