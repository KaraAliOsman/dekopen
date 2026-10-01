BEGIN;

-- AI-layer trust repair (hostile review AI-01 / AI-09):
-- 1) ai_audit_logs carried SELECT for every member role, so INSTALLER could
--    read the full privileged context projections the AI endpoints refuse
--    them. The select policy now mirrors _AGENT_CALLERS.
-- 2) ai_jobs was member-writable via PostgREST — a member could rewrite their
--    own job rows (state, transcript, artifacts, result). Writes now run
--    under a dedicated backend role (the API already executes inside the
--    caller's org/user policy, so the same policies apply to the role).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ai_backend') THEN
        CREATE ROLE ai_backend NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
END;
$$;
GRANT ai_backend TO postgres;
GRANT USAGE ON SCHEMA public, private, auth TO ai_backend;
GRANT EXECUTE ON FUNCTION private.current_user_org_ids() TO ai_backend;
GRANT EXECUTE ON FUNCTION auth.uid() TO ai_backend;
GRANT SELECT ON public.tenancy_memberships TO ai_backend;

-- ai_audit_logs: reads follow the AI-caller role set, not plain membership.
DROP POLICY ai_audit_logs_select ON public.ai_audit_logs;
CREATE POLICY ai_audit_logs_select ON public.ai_audit_logs
    FOR SELECT TO public
    USING (
        private.documentary_role(org_id, ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER'])
    );
DROP POLICY ai_audit_logs_insert ON public.ai_audit_logs;
CREATE POLICY ai_audit_logs_insert ON public.ai_audit_logs
    FOR INSERT TO ai_backend, billing_backend
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE INSERT ON public.ai_audit_logs FROM authenticated;
GRANT INSERT, SELECT ON public.ai_audit_logs TO ai_backend;
GRANT EXECUTE ON FUNCTION private.documentary_role(UUID, TEXT[]) TO ai_backend;
-- The select policy is TO public, so every backend role that reads
-- ai_audit_logs (billing settles wallet debits against it, pricing resolves
-- operations) must be able to evaluate documentary_role inside it.
GRANT EXECUTE ON FUNCTION private.documentary_role(UUID, TEXT[])
    TO billing_backend, pricing_backend, portal_backend;

-- ai_jobs: members keep reading their own job rows; only the backend role
-- may write them (the API's own upserts run under SET LOCAL ROLE ai_backend).
DROP POLICY ai_jobs_insert ON public.ai_jobs;
DROP POLICY ai_jobs_update ON public.ai_jobs;
CREATE POLICY ai_jobs_insert ON public.ai_jobs
    FOR INSERT TO ai_backend
    WITH CHECK (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
CREATE POLICY ai_jobs_update ON public.ai_jobs
    FOR UPDATE TO ai_backend
    USING (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    )
    WITH CHECK (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
REVOKE INSERT, UPDATE ON public.ai_jobs FROM authenticated;
GRANT SELECT, INSERT, UPDATE ON public.ai_jobs TO ai_backend;

COMMIT;
