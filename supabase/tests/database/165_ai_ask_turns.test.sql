BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(6);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'ai_ask_turns'
    ),
    'ai_ask_turns exists'
);

SELECT ok(
    (SELECT relrowsecurity FROM pg_class
     WHERE relnamespace = 'public'::regnamespace
       AND relname = 'ai_ask_turns'),
    'ai_ask_turns enforces RLS'
);

SELECT is(
    (SELECT count(*)::int FROM pg_policies
     WHERE schemaname = 'public' AND tablename = 'ai_ask_turns'),
    2,
    'ai_ask_turns has select + backend-insert policies'
);

SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'ai_ask_turns'
          AND grantee = 'authenticated' AND privilege_type = 'INSERT'
    ),
    'authenticated cannot mint an ask turn — the answer row is committed evidence'
);

SELECT ok(
    NOT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'ai_ask_turns'
          AND grantee = 'authenticated' AND privilege_type IN ('UPDATE', 'DELETE')
    ),
    'authenticated cannot rewrite or erase an ask turn'
);

SELECT ok(
    EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'public' AND table_name = 'ai_ask_turns'
          AND grantee = 'ai_backend' AND privilege_type = 'INSERT'
    ),
    'ai_backend inserts ask turns under RLS'
);

SELECT * FROM finish();
ROLLBACK;
