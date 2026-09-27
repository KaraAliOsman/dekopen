-- Repairs a regression in 20261221000000_order_sent_to.sql: adding `sent_to`
-- to the DRAFT→SENT whitelist rewrote guard_order_evidence without the
-- SENT→PARTIALLY_RECEIVED→FULFILLED clause (from 20260923140000) and without
-- the DRAFT/SENT→CANCELLED clause (from 20261219120000) — so receiving and
-- cancelling every threw order_evidence_immutable. This is the union of all
-- three legal transitions.
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
