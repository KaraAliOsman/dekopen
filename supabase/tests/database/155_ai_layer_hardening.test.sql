BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(8);

-- Job rows are the API's truth: members read their own jobs but only the
-- dedicated backend role writes them (PostgREST can't fabricate runs).
SELECT ok(has_table_privilege('authenticated', 'public.ai_jobs', 'SELECT'),
    'members still read their own jobs');
SELECT ok(NOT has_table_privilege('authenticated', 'public.ai_jobs', 'INSERT'),
    'members cannot insert job rows via PostgREST');
SELECT ok(NOT has_table_privilege('authenticated', 'public.ai_jobs', 'UPDATE'),
    'members cannot rewrite job rows via PostgREST');
SELECT ok(has_table_privilege('ai_backend', 'public.ai_jobs', 'INSERT'),
    'the backend role writes job rows');
SELECT ok(has_table_privilege('ai_backend', 'public.ai_jobs', 'UPDATE'),
    'the backend role updates job rows');

-- The audit ledger is read under the AI-caller role set and written only by
-- backend roles — member roles the AI endpoints refuse cannot forge or
-- read the privileged projections it stores.
SELECT ok(NOT has_table_privilege('authenticated', 'public.ai_audit_logs', 'INSERT'),
    'members cannot forge audit rows');
SELECT ok(has_table_privilege('billing_backend', 'public.ai_audit_logs', 'INSERT'),
    'the billing role still writes audit rows');
SELECT ok(has_table_privilege('authenticated', 'public.ai_audit_logs', 'SELECT'),
    'member grant remains — the role-scoped policy does the gating');

SELECT * FROM finish();
ROLLBACK;
