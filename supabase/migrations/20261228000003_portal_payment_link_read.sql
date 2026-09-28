-- §07: the customer proposal must surface the minted payment link's URL.
-- project_payment_links only carried the auth.uid()-scoped isolation
-- policy, which is empty for portal_backend (the share token carries no
-- JWT). Grant the portal role the same org-scoped read posture as
-- project_payments (20261207000000_portal_payments.sql).

GRANT SELECT ON public.project_payment_links TO portal_backend;

CREATE POLICY project_payment_links_portal_read ON public.project_payment_links
    FOR SELECT TO portal_backend
    USING (org_id = NULLIF(current_setting('app.portal_org_id', true), '')::uuid);
