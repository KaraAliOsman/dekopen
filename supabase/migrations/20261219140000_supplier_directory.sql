-- F12: org-scoped supplier directory — one master record per tax id so
-- eligibility rows stop re-typing supplier identity freehand, and expired
-- evidence can be surfaced/enforced consistently.
CREATE TABLE public.suppliers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    tax_id TEXT NOT NULL CHECK (length(btrim(tax_id)) > 0),
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    details JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (org_id, tax_id)
);
ALTER TABLE public.suppliers ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.suppliers FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.suppliers TO documentary_backend;
GRANT ALL ON public.suppliers TO service_role;

CREATE POLICY suppliers_backend
ON public.suppliers FOR ALL TO documentary_backend
USING (private.documentary_role(org_id, ARRAY['OWNER', 'ESTIMATOR', 'WORKSHOP_MANAGER']))
WITH CHECK (private.documentary_role(org_id, ARRAY['OWNER', 'WORKSHOP_MANAGER']));
