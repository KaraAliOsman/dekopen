-- Purchasing hostile-review A4: "Enviar orden" flipped a status but recorded
-- nothing about where the order actually went. `sent_to` captures the
-- destination the buyer used (supplier email/phone), so the SENT state is
-- honest evidence of a real communication — never a fabricated send.
ALTER TABLE public.orders ADD COLUMN sent_to VARCHAR(200);

COMMENT ON COLUMN public.orders.sent_to IS
  'Destination the buyer sent the order to (email/phone), entered at send time; NULL when not recorded.';

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
    RAISE EXCEPTION 'order_evidence_immutable' USING ERRCODE = '42501';
END;
$$;
REVOKE ALL ON FUNCTION private.guard_order_evidence() FROM PUBLIC;
