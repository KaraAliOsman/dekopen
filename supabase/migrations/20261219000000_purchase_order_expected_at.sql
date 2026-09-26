-- Purchasing review (PU6): an order carries no time dimension at all.
-- `expected_at` is the supplier-promised delivery date the buyer types at
-- send time — captured authority, never synthesized. Nullable: a supplier
-- that gives no date stays unknown rather than fabricated.
ALTER TABLE public.orders ADD COLUMN expected_at DATE;

COMMENT ON COLUMN public.orders.expected_at IS
  'Supplier-promised delivery date entered when the order is sent; NULL when the supplier gave no date.';

-- The evidence guard whitelists exactly the columns a DRAFT→SENT transition
-- may touch; expected_at joins that list or every send is rejected.
CREATE OR REPLACE FUNCTION private.guard_order_evidence()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF OLD.order_type = 'WORKSHOP_OT' THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'order_evidence_immutable' USING ERRCODE = '42501';
    END IF;
    IF OLD.status = 'DRAFT' AND NEW.status = 'SENT'
       AND NEW.sent_by IS NOT NULL AND NEW.sent_at IS NOT NULL
       AND (to_jsonb(NEW) - ARRAY['status', 'sent_by', 'sent_at', 'expected_at', 'updated_at'])
           = (to_jsonb(OLD) - ARRAY['status', 'sent_by', 'sent_at', 'expected_at', 'updated_at']) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'order_evidence_immutable' USING ERRCODE = '42501';
END;
$$;
REVOKE ALL ON FUNCTION private.guard_order_evidence() FROM PUBLIC;
