BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(6);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_jobs'
          AND column_name = 'org_id'
    ),
    'ai_jobs is org-scoped'
);
SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE relnamespace = 'public'::regnamespace AND relname = 'ai_jobs'),
    'ai_jobs enforces RLS'
);
SELECT is(
    (SELECT count(*)::int FROM pg_policies
     WHERE schemaname = 'public' AND tablename = 'ai_jobs'
       AND policyname LIKE 'ai_jobs_%'),
    4,
    'ai_jobs has select/insert/update/metrics-select policies (no delete)'
);
SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_jobs'
          AND cmd = 'DELETE'
    ),
    'ai_jobs records are never deleted'
);
SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'ai_jobs'
          AND privilege_type = 'DELETE' AND grantee = 'authenticated'
    ),
    'authenticated holds no DELETE grant on ai_jobs'
);
SELECT throws_ok(
    $$INSERT INTO public.ai_jobs (org_id, user_id, surface, goal, state)
      VALUES (uuid_generate_v4(), uuid_generate_v4(), 'dashboard', 'x', 'DONE')$$,
    '23514',
    NULL,
    'invalid job state is rejected by the check constraint'
);

SELECT * FROM finish();
ROLLBACK;
