-- P14: richer machine authority (type, axes, work envelope) and the audit
-- trail of every change to org-declared machine/tool authority. A verdict is
-- only honest when the authority it checked against is recorded — this table
-- is who changed what, when, and from which value to which.

ALTER TABLE public.cnc_machines
    ADD COLUMN machine_type TEXT NOT NULL DEFAULT 'MACHINING_CENTER'
        CHECK (machine_type IN (
            'MACHINING_CENTER', 'ROUTER', 'SAW_DRILL_LINE', 'COPY_ROUTER',
            'OTHER'
        )),
    ADD COLUMN axes_count SMALLINT CHECK (
        axes_count IS NULL OR (axes_count >= 2 AND axes_count <= 6)
    ),
    ADD COLUMN travel_x_mm NUMERIC CHECK (
        travel_x_mm IS NULL OR travel_x_mm > 0
    ),
    ADD COLUMN travel_y_mm NUMERIC CHECK (
        travel_y_mm IS NULL OR travel_y_mm > 0
    ),
    ADD COLUMN travel_z_mm NUMERIC CHECK (
        travel_z_mm IS NULL OR travel_z_mm > 0
    );

-- "Reemplazado" needs a target: the program this one was replaced by's
-- successor. On re-optimization the prior program flips to SUPERSEDED and
-- this column points to the CURRENT program that took its place.
ALTER TABLE public.cnc_programs
    ADD COLUMN superseded_by UUID REFERENCES public.cnc_programs(id)
        ON DELETE SET NULL;
CREATE INDEX cnc_programs_superseded_by_idx
    ON public.cnc_programs (superseded_by)
    WHERE superseded_by IS NOT NULL;

CREATE TABLE public.cnc_authority_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    entity TEXT NOT NULL CHECK (entity IN ('machine', 'tool')),
    entity_id UUID NOT NULL,
    entity_code TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN ('created', 'updated', 'deactivated', 'reactivated')
    ),
    actor_id UUID,
    -- {field: {"from": old, "to": new}} — the declared value before and
    -- after, so the trail shows WHAT changed, not only that it did.
    changed JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(changed) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX cnc_authority_events_org_idx
    ON public.cnc_authority_events (org_id, created_at DESC);

ALTER TABLE public.cnc_authority_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY cnc_authority_events_isolation ON public.cnc_authority_events
FOR ALL
USING (org_id IN (SELECT private.current_user_org_ids()))
WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

REVOKE ALL ON public.cnc_authority_events FROM anon, authenticated;
GRANT SELECT ON public.cnc_authority_events TO authenticated;
GRANT SELECT, INSERT ON public.cnc_authority_events TO documentary_backend;
GRANT ALL ON public.cnc_authority_events TO service_role;
-- The audit trail is append-only: no role rewrites or deletes history.
