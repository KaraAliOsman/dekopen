-- suppliers is an org-owned directory row, not an immutable audit chain —
-- the tenant teardown (and the e2e fixture) deletes tenancy_organizations
-- and was blocked by the RESTRICT FK. Align with the other org-owned
-- catalog/operational tables: org delete cascades its supplier rows.
ALTER TABLE public.suppliers
    DROP CONSTRAINT suppliers_org_id_fkey,
    ADD CONSTRAINT suppliers_org_id_fkey
        FOREIGN KEY (org_id)
        REFERENCES public.tenancy_organizations(id)
        ON DELETE CASCADE;
