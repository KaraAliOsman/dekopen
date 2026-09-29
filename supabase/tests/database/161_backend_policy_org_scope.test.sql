BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(3);

-- §12-7: backend-role policies must carry an org predicate — Python's
-- org filter can no longer be the only tenant wall on these tables.
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'document_imports'
          AND policyname = 'document_imports_backend'
          AND qual LIKE '%current_user_org_ids%'
    ),
    'document_imports backend policy is org-scoped'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'catalog_imports'
          AND policyname = 'catalog_imports_backend'
          AND qual LIKE '%current_user_org_ids%'
    ),
    'catalog_imports backend policy is org-scoped'
);
SELECT ok(
    EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public' AND tablename = 'ai_audit_provenance'
          AND policyname = 'ai_audit_provenance_backend'
          AND qual LIKE '%ai_audit_logs%'
          AND qual LIKE '%current_user_org_ids%'
    ),
    'ai_audit_provenance backend policy scopes through the parent audit org'
);

SELECT * FROM finish();
ROLLBACK;
