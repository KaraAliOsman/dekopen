-- Catalog table privilege hygiene.
--
-- The catalog authority tables intentionally allow member INSERT/UPDATE/
-- DELETE under `authenticated`: the app's catalog endpoints run under the
-- authenticated role and RLS policies (`can_manage_catalog`, not-global,
-- not-demo) gate which rows a member may touch. Review-stamp columns are
-- additionally excluded via column-level grants.
--
-- But Supabase's default privileges also granted REFERENCES, TRIGGER and
-- TRUNCATE on these tables. No application path uses them, and TRUNCATE is
-- the dangerous one: it does not consult RLS, so an `authenticated` SQL
-- session (or any defect that executes raw SQL under that role) could wipe
-- every tenant's catalog plus the platform-global rows in one statement.
-- PostgREST cannot issue TRUNCATE over REST, but the grant should not rely
-- on that accident — privileges follow the need, nothing more.
--
-- DELETE stays: `catalogs.service.delete` runs under authenticated context.
-- SELECT stays. REFERENCES/TRIGGER/TRUNCATE go.

REVOKE REFERENCES, TRIGGER, TRUNCATE
  ON public.profile_systems,
     public.profile_articles,
     public.glazing_bead_matrix,
     public.hardware_kits,
     public.infill_articles,
     public.manufacturing_placement_policies,
     public.handle_requirement_policies,
     public.reinforcement_cut_policies,
     public.glass_purchase_mappings,
     public.fitting_purchase_mappings,
     public.catalog_parameter_evidence,
     public.catalog_imports
  FROM authenticated;
