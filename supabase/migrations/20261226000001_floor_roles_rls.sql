-- Floor roles (OPERATOR on stations, INSTALLER on delivery) act on work
-- orders through the API. The API admits them (_READERS /
-- _WORKSHOP_STEP_ACTORS / _STEP_ACTORS) but several documentary_backend
-- policies still gate on [OWNER, ESTIMATOR, WORKSHOP_MANAGER], so every
-- order detail read returned zero rows (work_order_not_found) and every
-- step transition hit an empty FOR UPDATE set (production_step_not_found).
-- RLS here enforces tenancy + coarse write authority — the HTTP layer
-- remains the authority on WHO may do WHAT.

-- Order detail resolves the sealed snapshot through documentary_backend;
-- members already read both tables as `authenticated`.
CREATE POLICY projects_member_read
ON public.projects FOR SELECT TO documentary_backend
USING (org_id IN (SELECT private.current_user_org_ids()));

CREATE POLICY project_versions_member_read
ON public.project_versions FOR SELECT TO documentary_backend
USING (org_id IN (SELECT private.current_user_org_ids()));

-- Step transitions: OPERATOR drives station steps, INSTALLER drives
-- delivery steps; both write the step row + the append-only event.
DROP POLICY production_steps_member_update ON public.production_steps;
CREATE POLICY production_steps_member_update ON public.production_steps
    FOR UPDATE TO public
    USING (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR', 'INSTALLER']))
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR', 'INSTALLER']));

DROP POLICY production_step_events_member_insert ON public.production_step_events;
CREATE POLICY production_step_events_member_insert ON public.production_step_events
    FOR INSERT TO public
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR', 'INSTALLER']));

-- Step completion writes the stock ledger (consumption) and registers or
-- liquidates remnants; delivery steps update the delivery row.
DROP POLICY inventory_movements_member_insert ON public.inventory_movements;
CREATE POLICY inventory_movements_member_insert ON public.inventory_movements
    FOR INSERT TO public
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR', 'INSTALLER']));

DROP POLICY inventory_remnants_member_insert ON public.inventory_remnants;
CREATE POLICY inventory_remnants_member_insert ON public.inventory_remnants
    FOR INSERT TO public
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR']));

DROP POLICY inventory_remnants_member_update ON public.inventory_remnants;
CREATE POLICY inventory_remnants_member_update ON public.inventory_remnants
    FOR UPDATE TO public
    USING (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR']))
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'OPERATOR']));

DROP POLICY deliveries_member_update ON public.deliveries;
CREATE POLICY deliveries_member_update ON public.deliveries
    FOR UPDATE TO public
    USING (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'INSTALLER']))
    WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER', 'INSTALLER']));
