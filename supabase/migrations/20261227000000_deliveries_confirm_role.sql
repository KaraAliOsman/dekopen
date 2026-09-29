-- Confirming a delivery seals a POD and may register a cobro en terreno —
-- a task ESTIMATOR legitimately performs. The deliveries UPDATE policy used
-- to exclude ESTIMATOR, so confirm_delivery's `SELECT ... FOR UPDATE`
-- returned zero rows and the API surfaced a misleading delivery_not_found
-- 404 for a role-scoped rejection. ESTIMATOR joins the update role set;
-- the endpoint's own role gate still decides who may confirm, and the
-- authenticated role has no UPDATE grant on the table, so PostgREST writes
-- remain closed.
DROP POLICY deliveries_member_update ON public.deliveries;
CREATE POLICY deliveries_member_update ON public.deliveries
    FOR UPDATE TO public
    USING (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'INSTALLER', 'ESTIMATOR']))
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'INSTALLER', 'ESTIMATOR']));
