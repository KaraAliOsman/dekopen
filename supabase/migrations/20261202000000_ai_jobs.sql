-- §07-B: durable AI job model. An agent run is a persisted job — goal, plan,
-- steps, tool calls (typed projections), artifacts, warnings, questions and
-- result — so the UI can show real work, resume settled jobs with follow-up
-- instructions, and keep evidence inspectable instead of buried in chat text.

CREATE TABLE public.ai_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    surface VARCHAR(40) NOT NULL,
    refs JSONB NOT NULL DEFAULT '{}',
    goal TEXT NOT NULL,
    state VARCHAR(24) NOT NULL CONSTRAINT ai_jobs_state_check CHECK (state IN (
        'QUEUED', 'PLANNING', 'RUNNING',
        'WAITING_FOR_USER', 'WAITING_FOR_APPROVAL',
        'FAILED_RETRYABLE', 'FAILED', 'SUCCEEDED', 'CANCELED'
    )),
    plan JSONB NOT NULL DEFAULT '[]',
    transcript JSONB NOT NULL DEFAULT '[]',
    artifacts JSONB NOT NULL DEFAULT '[]',
    warnings JSONB NOT NULL DEFAULT '[]',
    result JSONB,
    error_code VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

ALTER TABLE public.ai_jobs ENABLE ROW LEVEL SECURITY;

-- A job is the caller's work: org members read their own org's jobs only,
-- scoped further to the owning user. Writes happen under the same rule — a
-- user creates and resumes only their own jobs.
CREATE POLICY ai_jobs_select ON public.ai_jobs
    FOR SELECT TO public
    USING (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
CREATE POLICY ai_jobs_insert ON public.ai_jobs
    FOR INSERT TO public
    WITH CHECK (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );
CREATE POLICY ai_jobs_update ON public.ai_jobs
    FOR UPDATE TO public
    USING (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    )
    WITH CHECK (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );

GRANT SELECT, INSERT, UPDATE ON public.ai_jobs TO authenticated;
REVOKE DELETE ON public.ai_jobs FROM authenticated;

CREATE INDEX ai_jobs_org_user_idx ON public.ai_jobs (org_id, user_id, created_at DESC);
