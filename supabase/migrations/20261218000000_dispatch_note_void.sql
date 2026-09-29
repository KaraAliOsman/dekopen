-- Guía de despacho void: a mis-emitted note (wrong address, cancelled
-- shipment, wrong receiver) must be voidable BEFORE it becomes fiscal
-- evidence. Void marks the sealed row — the emitted PDF stays evidence of
-- what was issued — and only the three void fields may ever be written.
-- Re-dispatch issues a fresh note: the uniqueness contract moves to a
-- partial index over live notes.

ALTER TABLE public.production_step_events
    DROP CONSTRAINT production_step_events_event_check;
ALTER TABLE public.production_step_events
    ADD CONSTRAINT production_step_events_event_check
    CHECK (event IN (
        'WO_RELEASED', 'STEP_STARTED', 'STEP_COMPLETED', 'STEP_BLOCKED',
        'STEP_UNBLOCKED', 'NOTE', 'WO_COMPLETED', 'WO_HOLD', 'WO_OPTIMIZED',
        'QC_FAILED', 'WO_REMADE', 'WO_CNC_EXPORTED', 'WO_DXF_EXPORTED',
        'WO_PACKED', 'WO_DISPATCHED', 'WO_INSTALLED',
        'WO_DELIVERY_SCHEDULED', 'WO_DELIVERY_ON_ROUTE',
        'WO_DELIVERY_DELIVERED', 'WO_DELIVERY_FAILED', 'WO_DELIVERY_CONFIRMED',
        'WO_REMNANTS_SETTLED', 'WO_OPS_EXPORTED', 'WO_STOCK_CONSUMED',
        'WO_DISPATCH_VOIDED'
    ));

ALTER TABLE public.dispatch_notes
    ADD COLUMN voided_at TIMESTAMPTZ,
    ADD COLUMN voided_by UUID,
    ADD COLUMN voided_reason TEXT;

ALTER TABLE public.dispatch_notes
    DROP CONSTRAINT uk_dispatch_note;
CREATE UNIQUE INDEX uk_dispatch_note_live
    ON public.dispatch_notes (work_order_id)
    WHERE voided_at IS NULL;

-- The backend role may only ever touch the void columns — the sealed
-- payload, hash and code remain insert-only.
GRANT UPDATE (voided_at, voided_by, voided_reason)
    ON public.dispatch_notes TO documentary_backend;
