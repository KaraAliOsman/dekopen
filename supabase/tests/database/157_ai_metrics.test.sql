BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(4);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_jobs'
          AND column_name = 'outcomes' AND data_type = 'jsonb'
    ),
    'ai_jobs carries an outcomes[] log'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'ai_jobs'
          AND column_name = 'outcomes' AND is_nullable = 'NO'
          AND column_default LIKE '%''[]''%'
    ),
    'outcomes is NOT NULL with a default for existing rows'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_jobs'
          AND policyname = 'ai_jobs_metrics_select'
          AND 'ai_backend' = ANY(roles)
    ),
    'ai_backend holds the org-wide metrics select policy'
);
SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_jobs'
          AND policyname = 'ai_jobs_metrics_select'
          AND 'authenticated' = ANY(roles)
    ),
    'members are NOT granted the metrics-wide read'
);

SELECT * FROM finish();
ROLLBACK;
