-- Customer approval links become revocable: a share sent to the wrong person
-- must have an off switch before its 30-day expiry. REVOKED joins the status
-- enum; the portal path treats a revoked token as dead.

ALTER TABLE public.customer_approvals
    DROP CONSTRAINT customer_approvals_status_check;
ALTER TABLE public.customer_approvals
    ADD CONSTRAINT customer_approvals_status_check
    CHECK (status IN ('PENDING', 'APPROVED', 'DECLINED', 'REVOKED'));

ALTER TABLE public.customer_approvals
    ADD COLUMN revoked_at TIMESTAMPTZ,
    ADD COLUMN revoked_by UUID;
