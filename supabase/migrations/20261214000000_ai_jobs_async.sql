-- Agent runs move off the request thread: the POST enqueues a durable job and
-- the worker claims the ai_jobs row. Two supporting changes live here.
--
-- 1) operation_key makes the submit idempotent — a retried POST replays to
--    the same ai_jobs row instead of queueing an orphan that never runs.
ALTER TABLE public.ai_jobs ADD COLUMN operation_key varchar(200);
CREATE UNIQUE INDEX ai_jobs_operation_key_key
    ON public.ai_jobs (org_id, user_id, operation_key)
    WHERE operation_key IS NOT NULL;

-- 2) Cooperative cancel: the worker holds the ai_jobs row lock for the whole
--    run, so a cancel UPDATE would wait out the provider call. The signal
--    lives in its own table — the worker checks it between rounds and aborts.
CREATE TABLE public.ai_job_cancel_signals (
    job_id       uuid PRIMARY KEY,
    org_id       uuid NOT NULL,
    user_id      uuid NOT NULL,
    requested_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.ai_job_cancel_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY ai_job_cancel_signals_insert ON public.ai_job_cancel_signals
    FOR INSERT TO ai_backend
    WITH CHECK (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
CREATE POLICY ai_job_cancel_signals_select ON public.ai_job_cancel_signals
    FOR SELECT TO ai_backend
    USING (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
CREATE POLICY ai_job_cancel_signals_delete ON public.ai_job_cancel_signals
    FOR DELETE TO ai_backend
    USING (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
REVOKE ALL ON public.ai_job_cancel_signals FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, DELETE ON public.ai_job_cancel_signals TO ai_backend;

COMMIT;
