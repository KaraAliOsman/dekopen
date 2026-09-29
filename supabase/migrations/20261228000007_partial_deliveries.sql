-- Partial deliveries: an order may ship over several trips. Each trip is a
-- deliveries row carrying the manifest units it transports — NULL
-- unit_indexes keeps the pre-partial meaning "the whole order" — and each
-- guía de despacho seals only the unit subset it covers. At most one open
-- trip per order exists at a time: a second trip starts once the previous
-- resolves (DELIVERED/FAILED). The saldo stays pending in the order, never
-- inside a sealed document.
-- Append-only on top of 20261228000006_stock_spec_text.sql.

ALTER TABLE public.deliveries
    ADD COLUMN unit_indexes INTEGER[];

ALTER TABLE public.deliveries
    DROP CONSTRAINT deliveries_order_id_key;

CREATE UNIQUE INDEX deliveries_one_open_trip
    ON public.deliveries (order_id)
    WHERE status IN ('SCHEDULED', 'ON_ROUTE');
CREATE INDEX deliveries_order_idx
    ON public.deliveries (order_id);

ALTER TABLE public.dispatch_notes
    ADD COLUMN unit_indexes INTEGER[];

-- Coverage is computed by the service from non-voided notes, so one live
-- note per order no longer applies — a partial trip issues its own guía.
DROP INDEX public.uk_dispatch_note_live;
CREATE INDEX idx_dispatch_notes_order
    ON public.dispatch_notes (org_id, work_order_id);

-- A comprobante de entrega belongs to the trip it signs; order-level
-- uniqueness would forbid the second trip's POD.
ALTER TABLE public.delivery_confirmations
    DROP CONSTRAINT uk_confirmation_order;
