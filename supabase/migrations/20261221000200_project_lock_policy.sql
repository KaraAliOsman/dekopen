-- confirm_delivery locks the project's concurrency point with SELECT … FOR
-- UPDATE before sealing the POD (+ optional cobro). Postgres evaluates FOR
-- UPDATE rows against the UPDATE policy and documentary_backend only held a
-- SELECT policy on projects — the lock silently matched zero rows and the
-- endpoint failed with project_not_found. A FOR UPDATE policy gates row
-- locking; the role still holds no UPDATE grant, so projects stay read-only.
CREATE POLICY project_documentary_backend_lock
ON public.projects FOR UPDATE TO documentary_backend
USING (private.documentary_role(org_id, ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER']))
WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER']));
