BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(9);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_jobs'
          AND column_name = 'operation_key'
    ),
    'ai_jobs carries operation_key for submit dedupe'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = 'ai_jobs'
          AND indexname = 'ai_jobs_operation_key_key'
    ),
    'ai_jobs operation_key partial unique index exists'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'ai_job_cancel_signals'
    ),
    'ai_job_cancel_signals exists'
);

SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE relnamespace = 'public'::regnamespace
       AND relname = 'ai_job_cancel_signals'),
    'ai_job_cancel_signals enforces RLS'
);

SELECT is(
    (SELECT count(*)::int FROM pg_policies
     WHERE schemaname = 'public' AND tablename = 'ai_job_cancel_signals'),
    3,
    'ai_job_cancel_signals has insert/select/delete policies'
);

SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'ai_job_cancel_signals'
          AND grantee = 'authenticated'
    ),
    'authenticated holds no grants on ai_job_cancel_signals'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'ai_job_cancel_signals'
          AND privilege_type = 'INSERT' AND grantee = 'ai_backend'
    ),
    'ai_backend can insert cancel signals'
);

-- QUEUED is a first-class, worker-claimable state.
SELECT ok(
    (SELECT pg_get_constraintdef(oid) FROM pg_constraint
     WHERE conrelid = 'public.ai_jobs'::regclass
       AND conname = 'ai_jobs_state_check') LIKE '%QUEUED%',
    'QUEUED is an accepted ai_jobs state'
);

-- The dedupe index only covers rows that carry a key — ai_jobs rows from
-- before the async path (operation_key NULL) never collide.
SELECT ok(
    (SELECT pg_get_indexdef(indexrelid) FROM pg_index
     WHERE indexrelid = 'public.ai_jobs_operation_key_key'::regclass)
      LIKE '%WHERE (operation_key IS NOT NULL)%',
    'operation_key uniqueness only applies to keyed rows'
);

SELECT * FROM finish();
ROLLBACK;
