-- CNC subsystem: org-declared machines, tool library, generated programs.
-- Machines/tools are manufacturing AUTHORITY the org declares — writes flow
-- through documentary_backend (API role checks decide who may edit). Programs
-- are generated artifacts: insert-once rows that flip CURRENT → SUPERSEDED on
-- replan, never updated in place.

CREATE TABLE public.cnc_tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code TEXT NOT NULL CHECK (length(btrim(code)) > 0),
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    kind TEXT NOT NULL CHECK (kind IN (
        'SAW_BLADE', 'DRILL_BIT', 'END_MILL', 'ROUTER_BIT', 'PUNCH',
        'MARKING', 'CUSTOM'
    )),
    diameter_mm NUMERIC CHECK (diameter_mm IS NULL OR diameter_mm > 0),
    working_length_mm NUMERIC CHECK (working_length_mm IS NULL OR working_length_mm > 0),
    max_depth_mm NUMERIC CHECK (max_depth_mm IS NULL OR max_depth_mm > 0),
    -- NULL = unrestricted; otherwise the operation kinds this tool may run.
    compatible_kinds TEXT[] CHECK (
        compatible_kinds IS NULL
        OR compatible_kinds <@ ARRAY[
            'SAW_CUT', 'DRILL', 'SLOT', 'DRAINAGE', 'VENTILATION',
            'HANDLE_PREP', 'LOCK_PREP', 'HINGE_PREP', 'CORNER_CONNECTOR',
            'T_CONNECTOR', 'MILLING', 'END_MACHINING', 'ROUTING',
            'GASKET_MARK', 'CUSTOM'
        ]::text[]
    ),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, code)
);
CREATE INDEX cnc_tools_org_idx ON public.cnc_tools (org_id);

CREATE TABLE public.cnc_machines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code TEXT NOT NULL CHECK (length(btrim(code)) > 0),
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    manufacturer TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    controller_family TEXT NOT NULL DEFAULT 'NEUTRAL',
    coordinate_systems TEXT[] NOT NULL DEFAULT '{BAR_AXIS,MEMBER_PLAN,SHEET_PLAN}',
    -- NULL = the machine runs every declared kind / face; a set is a real limit.
    supported_kinds TEXT[] CHECK (
        supported_kinds IS NULL
        OR supported_kinds <@ ARRAY[
            'SAW_CUT', 'DRILL', 'SLOT', 'DRAINAGE', 'VENTILATION',
            'HANDLE_PREP', 'LOCK_PREP', 'HINGE_PREP', 'CORNER_CONNECTOR',
            'T_CONNECTOR', 'MILLING', 'END_MACHINING', 'ROUTING',
            'GASKET_MARK', 'CUSTOM'
        ]::text[]
    ),
    supported_faces TEXT[] CHECK (
        supported_faces IS NULL
        OR supported_faces <@ ARRAY[
            'OUTSIDE_FACE', 'INSIDE_FACE', 'TOP_EDGE', 'BOTTOM_EDGE',
            'START_EDGE', 'END_EDGE'
        ]::text[]
    ),
    max_member_length_mm NUMERIC CHECK (max_member_length_mm IS NULL OR max_member_length_mm > 0),
    safe_margin_mm NUMERIC CHECK (safe_margin_mm IS NULL OR safe_margin_mm >= 0),
    clamp_zones JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(clamp_zones) = 'array'),
    tool_ids UUID[] NOT NULL DEFAULT '{}',
    postprocessor_id TEXT NOT NULL DEFAULT 'neutral-ops-v1',
    postprocessor_version TEXT NOT NULL DEFAULT '1',
    units TEXT NOT NULL DEFAULT 'mm',
    encoding TEXT NOT NULL DEFAULT 'utf-8',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, code)
);
CREATE INDEX cnc_machines_org_idx ON public.cnc_machines (org_id);

CREATE TABLE public.cnc_programs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    work_order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE RESTRICT,
    machine_id UUID NOT NULL REFERENCES public.cnc_machines(id) ON DELETE RESTRICT,
    member_id TEXT NOT NULL CHECK (length(btrim(member_id)) > 0),
    member_label TEXT NOT NULL DEFAULT '',
    program_no TEXT NOT NULL CHECK (length(btrim(program_no)) > 0),
    operation_count INTEGER NOT NULL CHECK (operation_count >= 0),
    verdict TEXT NOT NULL CHECK (verdict IN ('PASS', 'WARN', 'BLOCK')),
    fingerprint TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    identity JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(identity) = 'object'),
    files JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(files) = 'object'),
    status TEXT NOT NULL DEFAULT 'CURRENT' CHECK (status IN ('CURRENT', 'SUPERSEDED')),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, program_no)
);
-- One live program per (order, member, machine); history stays SUPERSEDED.
CREATE UNIQUE INDEX cnc_programs_current_uq
ON public.cnc_programs (org_id, work_order_id, member_id, machine_id)
WHERE status = 'CURRENT';
CREATE INDEX cnc_programs_order_idx ON public.cnc_programs (work_order_id);
CREATE INDEX cnc_programs_org_idx ON public.cnc_programs (org_id);

ALTER TABLE public.cnc_tools ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cnc_machines ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cnc_programs ENABLE ROW LEVEL SECURITY;

CREATE POLICY cnc_tools_isolation ON public.cnc_tools FOR ALL
USING (org_id IN (SELECT private.current_user_org_ids()))
WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY cnc_machines_isolation ON public.cnc_machines FOR ALL
USING (org_id IN (SELECT private.current_user_org_ids()))
WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY cnc_programs_isolation ON public.cnc_programs FOR ALL
USING (org_id IN (SELECT private.current_user_org_ids()))
WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));

REVOKE ALL ON public.cnc_tools FROM anon, authenticated;
REVOKE ALL ON public.cnc_machines FROM anon, authenticated;
REVOKE ALL ON public.cnc_programs FROM anon, authenticated;
GRANT SELECT ON public.cnc_tools TO authenticated;
GRANT SELECT ON public.cnc_machines TO authenticated;
GRANT SELECT ON public.cnc_programs TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cnc_tools TO documentary_backend;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.cnc_machines TO documentary_backend;
GRANT SELECT, INSERT, UPDATE ON public.cnc_programs TO documentary_backend;
GRANT ALL ON public.cnc_tools TO service_role;
GRANT ALL ON public.cnc_machines TO service_role;
GRANT ALL ON public.cnc_programs TO service_role;
-- Programs are immutable artifacts: status flips CURRENT → SUPERSEDED via
-- UPDATE, contents never change. Nothing deletes them.
REVOKE DELETE, TRUNCATE ON public.cnc_programs FROM authenticated, documentary_backend, service_role;

-- Program generation is a production event like WO_OPTIMIZED.
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
        'WO_DISPATCH_VOIDED', 'QC_CHECK', 'WO_CNC_PROGRAM'
    ));
