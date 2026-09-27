-- Purchase retry + DOC-02 PDF: a cancelled order must release its requirement
-- claims so the same order type can be confirmed again, and DOC-02 is allowed
-- in both formats (the PDF renderer exists; the check predates it).

-- A cancelled order frees its requirement lines: the claim is per live line,
-- the cancelled order's rows stay as evidence with released_at stamped.
ALTER TABLE public.order_requirement_lines
    ADD COLUMN released_at timestamptz;
ALTER TABLE public.order_requirement_lines
    DROP CONSTRAINT order_requirement_lines_requirement_line_id_key;
CREATE UNIQUE INDEX order_requirement_lines_live_claim
    ON public.order_requirement_lines(requirement_line_id)
    WHERE released_at IS NULL;

-- released_at is the one mutable field on an order line: stamping it releases
-- the claim after cancellation. Every other column stays evidence — replace the
-- blanket immutability trigger with a guard that allows exactly that stamp.
CREATE OR REPLACE FUNCTION private.guard_order_line_release()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'documentary_evidence_immutable' USING ERRCODE = '42501';
    END IF;
    -- UPDATE is legal only when it stamps released_at on a still-live line and
    -- leaves every evidence column untouched.
    IF OLD.released_at IS NULL AND NEW.released_at IS NOT NULL
       AND (to_jsonb(NEW) - 'released_at') = (to_jsonb(OLD) - 'released_at') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'documentary_evidence_immutable' USING ERRCODE = '42501';
END;
$$;
REVOKE ALL ON FUNCTION private.guard_order_line_release() FROM PUBLIC;
DROP TRIGGER IF EXISTS immutable_evidence ON public.order_requirement_lines;
CREATE TRIGGER order_line_release
BEFORE UPDATE OR DELETE ON public.order_requirement_lines
FOR EACH ROW EXECUTE FUNCTION private.guard_order_line_release();
GRANT UPDATE (released_at) ON public.order_requirement_lines TO documentary_backend;

-- One supplier order per (version, order type, batch) among LIVE orders — a
-- cancelled order must not block re-ordering the same supplier, and a retry
-- attempt may legitimately address a supplier that already holds a live order
-- for other lines (a supplemental PO is normal).
ALTER TABLE public.orders
    DROP CONSTRAINT shot09_order_supplier_identity;
CREATE UNIQUE INDEX orders_supplier_identity_live
    ON public.orders(project_version_id, order_type, supplier_identity,
                     allocation_batch_id)
    WHERE status <> 'CANCELLED';

-- Claims already released by a cancellation before this migration shipped:
-- lines sitting on cancelled orders are free again.
UPDATE public.order_requirement_lines line
SET released_at = COALESCE(o.cancelled_at, now())
FROM public.orders o
WHERE line.order_id = o.id AND o.status = 'CANCELLED'
  AND line.released_at IS NULL;

-- Re-confirming after a cancel creates a new batch attempt for the same
-- (version, order type): allocation_hash is recomputed with the attempt so the
-- retry is its own auditable event.
ALTER TABLE public.order_allocation_batches
    ADD COLUMN attempt integer NOT NULL DEFAULT 1;
ALTER TABLE public.order_allocation_batches
    DROP CONSTRAINT order_allocation_batches_project_version_id_order_type_key;
ALTER TABLE public.order_allocation_batches
    ADD CONSTRAINT order_allocation_batches_version_type_attempt_key
    UNIQUE (project_version_id, order_type, attempt);

-- DOC-02 renders as PDF too.
ALTER TABLE public.document_artifacts
    DROP CONSTRAINT IF EXISTS document_artifacts_check2;
ALTER TABLE public.document_artifacts
    ADD CONSTRAINT document_artifacts_check2
    CHECK (
        (document_type = ANY (ARRAY['DOC-01'::text, 'DOC-03'::text,
            'DOC-05'::text, 'DOC-06'::text, 'DOC-07'::text]))
            AND format = 'PDF'::text
        OR document_type = 'DOC-02'::text
            AND format = ANY (ARRAY['PDF'::text, 'XLSX'::text])
        OR (document_type = ANY (ARRAY['DOC-04'::text, 'DOC-08'::text]))
            AND (format = ANY (ARRAY['PDF'::text, 'XLSX'::text]))
    );
