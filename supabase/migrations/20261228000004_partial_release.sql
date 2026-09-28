-- order_requirement_lines.released_at was binary: a line either held its
-- whole claim or released all of it. Cancelling a PARTIALLY_RECEIVED order
-- must release only the unreceived remainder — release becomes
-- quantity-aware via released_qty.
ALTER TABLE public.order_requirement_lines
    ADD COLUMN IF NOT EXISTS released_qty NUMERIC NOT NULL DEFAULT 0;

-- The release guard still protects every evidence column; an UPDATE is now
-- legal only when it stamps released_at on a still-live line and may set
-- released_qty (0..quantity) alongside — nothing else may change.
CREATE OR REPLACE FUNCTION private.guard_order_line_release()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'documentary_evidence_immutable' USING ERRCODE = '42501';
    END IF;
    IF OLD.released_at IS NULL AND NEW.released_at IS NOT NULL
       AND NEW.released_qty >= 0 AND NEW.released_qty <= NEW.quantity
       AND (to_jsonb(NEW) - 'released_at' - 'released_qty')
           = (to_jsonb(OLD) - 'released_at' - 'released_qty') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'documentary_evidence_immutable' USING ERRCODE = '42501';
END;
$$;

GRANT UPDATE (released_qty) ON public.order_requirement_lines TO documentary_backend;

-- Rows released before this column existed released their full quantity.
ALTER TABLE public.order_requirement_lines DISABLE TRIGGER order_line_release;
UPDATE public.order_requirement_lines
SET released_qty = quantity
WHERE released_at IS NOT NULL;
ALTER TABLE public.order_requirement_lines ENABLE TRIGGER order_line_release;
