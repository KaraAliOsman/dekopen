-- Step events carry a human actor label so the order history reads
-- "WELD completado — operario@taller.cl" instead of a bare UUID.
-- Mirrors inventory_movements.actor_label (20261221000100), but filled by a
-- trigger from the verified JWT claims every request already propagates as
-- request.jwt.claims — every INSERT site is covered, present and future.
ALTER TABLE public.production_step_events
    ADD COLUMN actor_label VARCHAR(200) NULL;

COMMENT ON COLUMN public.production_step_events.actor_label IS
    'Human label of the member who caused the event (their sign-in email).';

CREATE OR REPLACE FUNCTION public.step_event_actor_label()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.actor_label IS NULL THEN
        NEW.actor_label := NULLIF(
            current_setting('request.jwt.claims', true)::jsonb ->> 'email', '');
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER production_step_events_actor_label
    BEFORE INSERT ON public.production_step_events
    FOR EACH ROW EXECUTE FUNCTION public.step_event_actor_label();
