-- work_centers are lazily seeded org config (production.service
-- _ensure_work_centers writes them on first production touch) — org-owned
-- operational rows, not an immutable audit chain. RESTRICT left org
-- teardown failing with 409 for any org that ever visited production
-- (and for the e2e fixture). Dependent production_steps keep their own
-- RESTRICT org FK, so an org with real production history still cannot
-- be deleted silently — this only unblocks orgs that never produced.
ALTER TABLE public.work_centers
    DROP CONSTRAINT work_centers_org_id_fkey,
    ADD CONSTRAINT work_centers_org_id_fkey
        FOREIGN KEY (org_id)
        REFERENCES public.tenancy_organizations(id)
        ON DELETE CASCADE;
