-- The order-level evidence guard only allowed DRAFT/SENT -> CANCELLED. With
-- quantity-aware line release (20261228000004) a PARTIALLY_RECEIVED order may
-- also cancel: its received lines keep covering the requirement through
-- released_qty, so the order itself is allowed to close while its receipts
-- remain intact as evidence.
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
       AND (to_jsonb(NEW) - ARRAY['status', 'sent_by', 'sent_at', 'sent_to', 'expected_at', 'updated_at'])
           = (to_jsonb(OLD) - ARRAY['status', 'sent_by', 'sent_at', 'sent_to', 'expected_at', 'updated_at']) THEN
        RETURN NEW;
    END IF;
    IF OLD.status IN ('SENT', 'PARTIALLY_RECEIVED')
       AND NEW.status IN ('PARTIALLY_RECEIVED', 'FULFILLED')
       AND (to_jsonb(NEW) - ARRAY['status', 'updated_at'])
           = (to_jsonb(OLD) - ARRAY['status', 'updated_at']) THEN
        RETURN NEW;
    END IF;
    -- Cancellation is allowed until the order is fully received: received
    -- quantities stay as evidence on the order lines and keep covering the
    -- requirement; only the unreceived remainder is released back.
    IF OLD.status IN ('DRAFT', 'SENT', 'PARTIALLY_RECEIVED')
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
