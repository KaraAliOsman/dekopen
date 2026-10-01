-- §08 measurement: record what users did with a job's proposed actions, and
-- let the AI backend read org-wide aggregates for the metrics surface.
--
-- outcomes[] entries: {turn_index, step_index, action, ops, recorded_by,
-- recorded_at} — the client's report that a step's ops were applied or
-- declined. Member writes still go through the API (ai_backend UPDATE holds
-- the org+user policy; authenticated lost UPDATE rights in the hardening
-- migration), so an outcome row can only land under the owning user.
ALTER TABLE public.ai_jobs ADD COLUMN outcomes JSONB NOT NULL DEFAULT '[]';

-- Metrics aggregate across the org's jobs, but the TO public select policy
-- binds rows to auth.uid(). This extra permissive policy exists only for
-- ai_backend (the API role) — permissive policies union, so under member
-- claims ai_backend reads the org's jobs for aggregation while PostgREST
-- reads (authenticated) remain user-scoped.
CREATE POLICY ai_jobs_metrics_select ON public.ai_jobs
    FOR SELECT TO ai_backend
    USING (org_id IN (SELECT private.current_user_org_ids()));
