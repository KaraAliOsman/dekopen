-- Partial deliveries follow-up: a guía belongs to the trip that carried it.
-- The link lets coverage exclude units whose trip FAILED — a failed delivery
-- frees its units so a new trip can carry them under a fresh guía, while
-- DELIVERED / in-transit units stay committed.
ALTER TABLE public.dispatch_notes
    ADD COLUMN delivery_id UUID REFERENCES public.deliveries (id);

CREATE INDEX idx_dispatch_notes_delivery
    ON public.dispatch_notes (delivery_id)
    WHERE delivery_id IS NOT NULL;
