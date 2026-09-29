BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap WITH SCHEMA extensions;
SET LOCAL search_path=public,extensions;
SELECT plan(5);

-- Release's `UPDATE projects SET status='IN_PRODUCTION'` runs under
-- documentary_backend: the column grant must cover both status and
-- updated_at (a missing grant was a live Emitir 500).
SELECT ok(
    has_column_privilege('documentary_backend', 'public.projects', 'updated_at', 'UPDATE'),
    'documentary_backend can stamp updated_at on the release transition'
);

-- …but never commercials or identity.
SELECT ok(
    NOT has_column_privilege('documentary_backend', 'public.projects', 'total_price_gross', 'UPDATE')
    AND NOT has_column_privilege('documentary_backend', 'public.projects', 'name', 'UPDATE'),
    'the grant stays lifecycle-only — no commercial or identity columns'
);

INSERT INTO tenancy_organizations(id,name,tax_id) VALUES
 ('88660000-0000-4000-8000-000000000001','Release Org','REL-1');
INSERT INTO tenancy_memberships(org_id,user_id,role) VALUES
 ('88660000-0000-4000-8000-000000000001','88661000-0000-4000-8000-000000000001','WORKSHOP_MANAGER');
INSERT INTO projects(id,org_id,code,name,client_name,status,current_revision,created_by) VALUES
 ('88662000-0000-4000-8000-000000000001','88660000-0000-4000-8000-000000000001','P-REL','Casa','Fixture','QUOTED','REV-A','88661000-0000-4000-8000-000000000001');

SET LOCAL ROLE documentary_backend;
SELECT set_config('request.jwt.claims',
                  '{"sub":"88661000-0000-4000-8000-000000000001"}', true);

-- sanctioned: status-only QUOTED → IN_PRODUCTION under the workshop role
UPDATE public.projects
SET status='IN_PRODUCTION', updated_at=clock_timestamp()
WHERE id='88662000-0000-4000-8000-000000000001';
SELECT ok(
    (SELECT status::text='IN_PRODUCTION' FROM public.projects
     WHERE id='88662000-0000-4000-8000-000000000001'),
    'documentary_backend transitions QUOTED → IN_PRODUCTION'
);

SELECT throws_matching(
    $$UPDATE public.projects SET name='X' WHERE id='88662000-0000-4000-8000-000000000001'::uuid$$,
    'permission denied',
    'any other column write under the role is still denied by the grant'
);

SELECT throws_matching(
    $$UPDATE public.projects SET status='DRAFT' WHERE id='88662000-0000-4000-8000-000000000001'::uuid$$,
    'documentary_project_update_forbidden',
    'a backward/lateral status move is rejected by the commercial guard'
);

SELECT * FROM finish();
ROLLBACK;
