BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(2);

-- P11 — _seal_repr escribe repr_storage_object_key/repr_file_sha256 tras
-- subir el PDF tributario; sin GRANT UPDATE la emisión 409a (42501).

SELECT ok(
    has_column_privilege('documentary_backend', 'public.project_dtes',
        'repr_storage_object_key', 'UPDATE'),
    'documentary_backend puede sellar repr_storage_object_key'
);
SELECT ok(
    has_column_privilege('documentary_backend', 'public.project_dtes',
        'repr_file_sha256', 'UPDATE'),
    'documentary_backend puede sellar repr_file_sha256'
);

SELECT * FROM finish();
ROLLBACK;
