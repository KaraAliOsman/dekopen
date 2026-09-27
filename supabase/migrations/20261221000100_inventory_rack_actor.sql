-- Workshop traceability: every stock movement can carry the physical rack it
-- touched and the human label of who did it. Without these, receiving tells
-- the shelf where material arrived but the ledger forgets, and a bodeguero
-- looking at a movement cannot answer "dónde está" or "quién lo hizo".
ALTER TABLE public.inventory_movements
    ADD COLUMN rack_location VARCHAR(50) NULL,
    ADD COLUMN actor_label VARCHAR(200) NULL;

COMMENT ON COLUMN public.inventory_movements.rack_location IS
    'Physical rack/bin the material went to or came from (free workshop code, e.g. R-03).';
COMMENT ON COLUMN public.inventory_movements.actor_label IS
    'Human label of the member who recorded the movement (their sign-in email).';
