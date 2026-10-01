-- DocMission purchasing (PU11): CANCELLED existed in the order_status enum and
-- in every UI label, but nothing could ever set it — a wrong draft or a
-- supplier that never confirms could not be closed. This adds the operator
-- cancel path for orders with no arrivals yet.
--
-- It also repairs a regression introduced in
-- 20261219000000_purchase_order_expected_at.sql: that function replacement
-- dropped the SENT→PARTIALLY_RECEIVED→FULFILLED clause, so every receipt
-- after it threw order_evidence_immutable.
ALTER TABLE public.orders
    ADD COLUMN cancelled_by UUID,
    ADD COLUMN cancelled_at TIMESTAMPTZ;

COMMENT ON COLUMN public.orders.cancelled_by IS
  'Operator who cancelled the order; NULL while the order is live.';
COMMENT ON COLUMN public.orders.cancelled_at IS
  'When the order was cancelled; NULL while the order is live.';

ALTER TABLE public.orders
    DROP CONSTRAINT shot09_supplier_order_state;
ALTER TABLE public.orders
    ADD CONSTRAINT shot09_supplier_order_state CHECK (
        order_type = 'WORKSHOP_OT'::order_type
        OR status IN ('DRAFT'::order_status, 'SENT'::order_status,
                      'PARTIALLY_RECEIVED'::order_status, 'FULFILLED'::order_status,
                      'CANCELLED'::order_status)
    );

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
    IF OLD.status IN ('SENT', 'PARTIALLY_RECEIVED')
       AND NEW.status IN ('PARTIALLY_RECEIVED', 'FULFILLED')
       AND (to_jsonb(NEW) - ARRAY['status', 'updated_at'])
           = (to_jsonb(OLD) - ARRAY['status', 'updated_at']) THEN
        RETURN NEW;
    END IF;
    -- Cancellation is only honest while nothing arrived: once receipts exist
    -- the order is evidence of physical events and stays live forever.
    IF OLD.status IN ('DRAFT', 'SENT')
       AND NEW.status = 'CANCELLED'
       AND NEW.cancelled_by IS NOT NULL AND NEW.cancelled_at IS NOT NULL
       AND (to_jsonb(NEW) - ARRAY['status', 'cancelled_by', 'cancelled_at', 'updated_at'])
           = (to_jsonb(OLD) - ARRAY['status', 'cancelled_by', 'cancelled_at', 'updated_at']) THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'order_evidence_immutable' USING ERRCODE = '42501';
END;
$$;
REVOKE ALL ON FUNCTION private.guard_order_evidence() FROM PUBLIC;
