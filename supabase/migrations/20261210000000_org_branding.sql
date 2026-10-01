-- White-label document branding: commercial identity shown on emitted
-- documents instead of the DEKOPEN masthead. brand_logo_key points at a
-- content-addressed storage object; brand_logo_sha256 pins its bytes so a
-- frozen document always renders the exact logo it was sealed with.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS commercial_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS giro VARCHAR(255),
    ADD COLUMN IF NOT EXISTS brand_address VARCHAR(255),
    ADD COLUMN IF NOT EXISTS brand_phone VARCHAR(64),
    ADD COLUMN IF NOT EXISTS brand_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS brand_logo_key VARCHAR(512),
    ADD COLUMN IF NOT EXISTS brand_logo_sha256 CHAR(64);

-- Branding writes run as documentary_backend inside the request transaction:
-- column-granted so the role can touch only the letterhead fields, and the
-- policy pins the row to the caller's org.
GRANT UPDATE (commercial_name, giro, brand_address, brand_phone,
    brand_email, brand_logo_key, brand_logo_sha256, updated_at)
    ON public.tenancy_organizations TO documentary_backend;
CREATE POLICY tenancy_organizations_branding_update
ON public.tenancy_organizations FOR UPDATE TO documentary_backend
USING (private.documentary_role(id, ARRAY['OWNER', 'ESTIMATOR']))
WITH CHECK (private.documentary_role(id, ARRAY['OWNER', 'ESTIMATOR']));
