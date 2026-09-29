-- §09: the proposal surface shows the customer their payment state.
-- The portal role reads the project's cobranza ledger scoped to the
-- approval's organization — the same org scope every other portal
-- policy binds via the app.portal_org_id GUC.
GRANT SELECT ON public.project_payments TO portal_backend;

CREATE POLICY project_payments_portal_read ON public.project_payments
    FOR SELECT TO portal_backend
    USING (org_id = NULLIF(current_setting('app.portal_org_id', true), '')::uuid);
