-- §3 durable conversations: contextual "ask" turns persist server-side so a
-- conversation survives SPA navigation, reload and returning later. Rows are
-- scoped (org, user, surface, refs) — the dock restores the thread for the
-- context the operator is looking at, never another project or user.

CREATE TABLE public.ai_ask_turns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    surface VARCHAR(40) NOT NULL,
    refs JSONB NOT NULL DEFAULT '{}',
    question TEXT NOT NULL,
    answer JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.ai_ask_turns ENABLE ROW LEVEL SECURITY;

-- Members read only their own turns inside their own org — a colleague's
-- questions stay private even though the context was shared.
CREATE POLICY ai_ask_turns_select ON public.ai_ask_turns
    FOR SELECT TO public
    USING (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );

-- Writes go through the backend role only: an answer row is committed
-- evidence of what the assistant said, so PostgREST clients never mint or
-- rewrite one directly. ai_backend is NOBYPASSRLS — the same org/user
-- scoping still binds the insert.
CREATE POLICY ai_ask_turns_insert ON public.ai_ask_turns
    FOR INSERT TO ai_backend
    WITH CHECK (
        org_id IN (SELECT private.current_user_org_ids())
        AND user_id = auth.uid()
    );

GRANT SELECT ON public.ai_ask_turns TO authenticated;
GRANT INSERT ON public.ai_ask_turns TO ai_backend;
REVOKE UPDATE, DELETE ON public.ai_ask_turns FROM authenticated, ai_backend;
-- Supabase default privileges mint INSERT on new tables for the caller roles;
-- an ask turn is committed evidence, so only ai_backend may write it.
REVOKE INSERT ON public.ai_ask_turns FROM anon, authenticated, service_role;

CREATE INDEX ai_ask_turns_thread_idx
    ON public.ai_ask_turns (org_id, user_id, surface, created_at);
