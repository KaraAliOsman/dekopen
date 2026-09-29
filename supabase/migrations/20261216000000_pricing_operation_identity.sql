-- Pricing operations carry the requester's email so approvers can audit who
-- asked, and a WITHDRAWN state lets a requester retract a pending request.

ALTER TABLE public.pricing_operations
  ADD COLUMN IF NOT EXISTS requested_by_email TEXT;

ALTER TABLE public.pricing_operations
  DROP CONSTRAINT pricing_operations_state_check;
ALTER TABLE public.pricing_operations
  ADD CONSTRAINT pricing_operations_state_check
  CHECK (state IN ('PREVIEW','PENDING','APPLIED','REJECTED','WITHDRAWN'));
