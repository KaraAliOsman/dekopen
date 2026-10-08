-- P23 — Despacho, medición e instalación en obra, y postventa con
-- trazabilidad a la pieza.
--
-- 1) field_crews: vehículos y cuadrillas para planificar el despacho por
--    día; deliveries gana la cuadrilla, el orden de ruta y el instalador
--    asignado que alimenta la agenda del terreno.
-- 2) site_measurements: el registro del vano medido en obra (evidencia
--    inmutable con fotos) — la escritura sobre project_positions pasa por
--    una función definer porque el rol INSTALLER no tiene la política
--    comercial sobre posiciones.
-- 3) installation_checks: checklist por posición/unidad (instalada,
--    nivelada, sellada, regulada, limpia) — upsert idempotente por
--    operation_key para la cola offline.
-- 4) site_incidents: daño / medida incorrecta / faltante / regulación con
--    fotos, trazados a orden, unidad y código de pieza; la resolución crea
--    un remake (OT -RM), una solicitud de compra o un ticket de postventa.
-- 5) service_tickets: garantía/servicio con cliente, obra, posición y
--    plazo de garantía calculado desde el sello de la revisión aprobada.
-- 6) field_photos: registro de evidencia del bucket documents — la clave
--    firmada solo se entrega si la foto pertenece a la organización.
-- 7) doc_warranty_months en la organización y warranty_months por
--    cotización: el plazo se sella con la revisión igual que doc_terms.
--
-- Todo lo de terreno es idempotente por (org_id, operation_key): la cola
-- offline del celular reintenta y el servidor devuelve la fila existente
-- sin duplicar.

BEGIN;

-- ── 1) Cuadrillas y vehículos ─────────────────────────────────────────

CREATE TABLE public.field_crews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    kind TEXT NOT NULL CHECK (kind IN ('VEHICLE', 'TEAM')),
    plate VARCHAR(20),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, name)
);
CREATE INDEX field_crews_org_idx ON public.field_crews (org_id);

ALTER TABLE public.field_crews ENABLE ROW LEVEL SECURITY;
CREATE POLICY field_crews_isolation ON public.field_crews
    FOR ALL TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY field_crews_backend ON public.field_crews
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.field_crews FROM anon;
GRANT SELECT ON public.field_crews TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.field_crews TO documentary_backend;
GRANT ALL ON public.field_crews TO service_role;

ALTER TABLE public.deliveries
    ADD COLUMN crew_id UUID REFERENCES public.field_crews(id) ON DELETE SET NULL,
    ADD COLUMN route_order SMALLINT,
    ADD COLUMN installer_user_id UUID,
    ADD COLUMN load_checked_at TIMESTAMPTZ,
    ADD COLUMN load_checked_by UUID;
CREATE INDEX deliveries_plan_idx
    ON public.deliveries (org_id, scheduled_date, crew_id);

-- ── 2) Evidencia fotográfica (registro del bucket documents) ──────────

CREATE TABLE public.field_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    object_key TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    label TEXT,
    uploaded_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, object_key),
    CHECK (object_key LIKE 'org_' || org_id::text || '/field/%')
);
CREATE INDEX field_photos_org_idx ON public.field_photos (org_id);

ALTER TABLE public.field_photos ENABLE ROW LEVEL SECURITY;
CREATE POLICY field_photos_isolation ON public.field_photos
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY field_photos_backend ON public.field_photos
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.field_photos FROM anon;
GRANT SELECT ON public.field_photos TO authenticated;
GRANT SELECT, INSERT ON public.field_photos TO documentary_backend;
GRANT ALL ON public.field_photos TO service_role;

-- ── 3) Medición en obra ───────────────────────────────────────────────

CREATE TABLE public.site_measurements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    project_id UUID NOT NULL,
    position_id UUID NOT NULL,
    operation_key VARCHAR(80) NOT NULL,
    rough_opening_input JSONB NOT NULL CHECK (jsonb_typeof(rough_opening_input) = 'object'),
    mounting_rule_id UUID REFERENCES public.mounting_rules(id) ON DELETE RESTRICT,
    notes TEXT,
    photos JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(photos) = 'array'),
    -- diff para el estimador: el registro anterior + la resolución del motor.
    previous_input JSONB,
    resolution JSONB,
    applied_state TEXT NOT NULL CHECK (
        applied_state IN ('APPLIED', 'REVISION_CREATED', 'RECORDED')
    ),
    applied_revision_code VARCHAR(20),
    measured_by UUID,
    taken_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (position_id, project_id, org_id)
        REFERENCES public.project_positions(id, project_id, org_id) ON DELETE RESTRICT,
    UNIQUE (org_id, operation_key)
);
CREATE INDEX site_measurements_position_idx
    ON public.site_measurements (org_id, position_id);
CREATE INDEX site_measurements_project_idx
    ON public.site_measurements (org_id, project_id);

ALTER TABLE public.site_measurements ENABLE ROW LEVEL SECURITY;
CREATE POLICY site_measurements_isolation ON public.site_measurements
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY site_measurements_backend ON public.site_measurements
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.site_measurements FROM anon;
GRANT SELECT ON public.site_measurements TO authenticated;
GRANT SELECT, INSERT ON public.site_measurements TO documentary_backend;
GRANT ALL ON public.site_measurements TO service_role;

-- La escritura del vano desde terreno: INSTALLER no está en la política
-- comercial de project_positions, así que el UPDATE pasa por una función
-- definer que aplica solo las columnas D07. El guard_commercial_write
-- existente sigue protegiendo proyectos con precio aplicado — sobre uno
-- cotizado la medición solo se graba como evidencia (applied_state
-- RECORDED) y la revisión la abre el estimador.
CREATE FUNCTION private.apply_site_measurement(
    p_org_id UUID,
    p_position_id UUID,
    p_rough_opening_input JSONB,
    p_mounting_rule_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $func$
DECLARE
    v_position public.project_positions%ROWTYPE;
    v_changed BOOLEAN;
BEGIN
    IF p_org_id IS NULL
        OR NOT (p_org_id IN (SELECT private.current_user_org_ids())) THEN
        RAISE EXCEPTION 'field_access_denied' USING ERRCODE = '42501';
    END IF;
    SELECT * INTO v_position
    FROM public.project_positions
    WHERE id = p_position_id AND org_id = p_org_id
    FOR UPDATE;
    IF v_position.id IS NULL THEN
        RAISE EXCEPTION 'position_not_found' USING ERRCODE = 'P0002';
    END IF;
    v_changed :=
        v_position.rough_opening_input IS DISTINCT FROM p_rough_opening_input
        OR v_position.mounting_rule_id IS DISTINCT FROM p_mounting_rule_id;
    IF NOT v_changed THEN
        RETURN jsonb_build_object(
            'position_id', v_position.id,
            'measurement_state', v_position.measurement_state,
            'changed', FALSE
        );
    END IF;
    -- La evidencia confirmada jamás sobrevive a un cambio: vuelve a
    -- SITE_RECTIFIED y pide confirmación explícita (misma regla que el
    -- guardado del editor).
    UPDATE public.project_positions
    SET rough_opening_input = p_rough_opening_input,
        mounting_rule_id = p_mounting_rule_id,
        fabrication_lock = NULL,
        measurement_state = 'SITE_RECTIFIED',
        measurement_confirmed_at = NULL,
        measurement_confirmed_by = NULL,
        updated_at = clock_timestamp()
    WHERE id = p_position_id AND org_id = p_org_id;
    UPDATE public.projects
    SET updated_at = clock_timestamp()
    WHERE id = v_position.project_id AND org_id = p_org_id;
    RETURN jsonb_build_object(
        'position_id', p_position_id,
        'measurement_state', 'SITE_RECTIFIED',
        'changed', TRUE
    );
END
$func$;
REVOKE ALL ON FUNCTION private.apply_site_measurement(UUID, UUID, JSONB, UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.apply_site_measurement(UUID, UUID, JSONB, UUID)
    TO documentary_backend, service_role;

-- ── 4) Checklist de instalación ───────────────────────────────────────

CREATE FUNCTION public.installation_items_valid(items JSONB)
RETURNS BOOLEAN
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE WHEN jsonb_typeof(items) IS DISTINCT FROM 'object' THEN FALSE
    ELSE COALESCE((
        SELECT bool_and(jsonb_typeof(entry.val) = 'boolean')
           AND array_agg(entry.key ORDER BY entry.key)
               = ARRAY['adjusted','clean','installed','leveled','sealed']
        FROM jsonb_each(items) AS entry(key, val)
    ), FALSE) END
$$;
REVOKE ALL ON FUNCTION public.installation_items_valid(JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.installation_items_valid(JSONB)
    TO authenticated, documentary_backend, service_role;

CREATE TABLE public.installation_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE RESTRICT,
    unit_index SMALLINT,
    items JSONB NOT NULL CHECK (public.installation_items_valid(items)),
    notes TEXT,
    photos JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(photos) = 'array'),
    operation_key VARCHAR(80) NOT NULL,
    checked_by UUID,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id, order_id, unit_index),
    UNIQUE (org_id, operation_key)
);
CREATE INDEX installation_checks_order_idx
    ON public.installation_checks (org_id, order_id);

ALTER TABLE public.installation_checks ENABLE ROW LEVEL SECURITY;
CREATE POLICY installation_checks_isolation ON public.installation_checks
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY installation_checks_backend ON public.installation_checks
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.installation_checks FROM anon;
GRANT SELECT ON public.installation_checks TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.installation_checks TO documentary_backend;
GRANT ALL ON public.installation_checks TO service_role;

-- ── 5) Incidencias de obra ────────────────────────────────────────────

CREATE TABLE public.site_incidents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code VARCHAR(12) NOT NULL,
    order_id UUID NOT NULL REFERENCES public.orders(id) ON DELETE RESTRICT,
    delivery_id UUID REFERENCES public.deliveries(id) ON DELETE SET NULL,
    unit_index SMALLINT,
    piece_code VARCHAR(80),
    kind TEXT NOT NULL CHECK (
        kind IN ('DAMAGE', 'WRONG_MEASURE', 'MISSING', 'ADJUSTMENT')
    ),
    note TEXT,
    photos JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(photos) = 'array'),
    operation_key VARCHAR(80) NOT NULL,
    reported_by UUID,
    reported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CANCELLED')),
    resolution_kind TEXT CHECK (
        resolution_kind IS NULL
        OR resolution_kind IN ('REMAKE', 'PURCHASE', 'SERVICE', 'NONE')
    ),
    resolution_note TEXT,
    resolution_ref_id UUID,
    resolved_by UUID,
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, code),
    UNIQUE (org_id, operation_key),
    CHECK ((status = 'RESOLVED') = (resolution_kind IS NOT NULL))
);
CREATE INDEX site_incidents_org_idx
    ON public.site_incidents (org_id, status);
CREATE INDEX site_incidents_order_idx
    ON public.site_incidents (org_id, order_id);

ALTER TABLE public.site_incidents ENABLE ROW LEVEL SECURITY;
CREATE POLICY site_incidents_isolation ON public.site_incidents
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY site_incidents_backend ON public.site_incidents
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.site_incidents FROM anon;
GRANT SELECT ON public.site_incidents TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.site_incidents TO documentary_backend;
GRANT ALL ON public.site_incidents TO service_role;

-- Solicitud de compra levantada desde una incidencia: la pieza que falta
-- o se dañó no siempre amerita remake — a veces es un herraje, un sellante
-- o un vidrio que el comprador gestiona.
CREATE TABLE public.field_purchase_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code VARCHAR(12) NOT NULL,
    incident_id UUID NOT NULL
        REFERENCES public.site_incidents(id) ON DELETE RESTRICT,
    item TEXT NOT NULL CHECK (length(btrim(item)) > 0),
    quantity NUMERIC(12, 2) CHECK (quantity IS NULL OR quantity > 0),
    unit VARCHAR(20),
    supplier_hint TEXT,
    needed_at DATE,
    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ORDERED', 'RECEIVED', 'CANCELLED')),
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, code),
    UNIQUE (org_id, incident_id)
);
CREATE INDEX field_purchase_requests_org_idx
    ON public.field_purchase_requests (org_id, status);

ALTER TABLE public.field_purchase_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY field_purchase_requests_isolation ON public.field_purchase_requests
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY field_purchase_requests_backend ON public.field_purchase_requests
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.field_purchase_requests FROM anon;
GRANT SELECT ON public.field_purchase_requests TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.field_purchase_requests TO documentary_backend;
GRANT ALL ON public.field_purchase_requests TO service_role;

-- ── 6) Postventa ──────────────────────────────────────────────────────

CREATE TABLE public.service_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL
        REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code VARCHAR(12) NOT NULL,
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE RESTRICT,
    order_id UUID REFERENCES public.orders(id) ON DELETE SET NULL,
    unit_index SMALLINT,
    piece_code VARCHAR(80),
    incident_id UUID REFERENCES public.site_incidents(id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('WARRANTY', 'SERVICE')),
    description TEXT NOT NULL CHECK (length(btrim(description)) > 0),
    diagnosis TEXT,
    photos JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(photos) = 'array'),
    warranty_until DATE,
    warranty_months SMALLINT,
    status TEXT NOT NULL DEFAULT 'OPEN' CHECK (
        status IN ('OPEN', 'SCHEDULED', 'IN_PROGRESS', 'CLOSED', 'CANCELLED')
    ),
    scheduled_visit_at TIMESTAMPTZ,
    scheduled_crew_id UUID REFERENCES public.field_crews(id) ON DELETE SET NULL,
    visit_note TEXT,
    close_note TEXT,
    closed_at TIMESTAMPTZ,
    closed_by UUID,
    operation_key VARCHAR(80) NOT NULL,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, code),
    UNIQUE (org_id, operation_key),
    CHECK ((status = 'CLOSED') = (closed_at IS NOT NULL))
);
-- Un ticket por incidencia (los manuales llevan incident_id NULL).
CREATE UNIQUE INDEX service_tickets_incident_uq
    ON public.service_tickets (org_id, incident_id)
    WHERE incident_id IS NOT NULL;
CREATE INDEX service_tickets_org_idx
    ON public.service_tickets (org_id, status);
CREATE INDEX service_tickets_project_idx
    ON public.service_tickets (org_id, project_id);
CREATE INDEX service_tickets_visit_idx
    ON public.service_tickets (org_id, scheduled_visit_at)
    WHERE status IN ('SCHEDULED', 'IN_PROGRESS');

ALTER TABLE public.service_tickets ENABLE ROW LEVEL SECURITY;
CREATE POLICY service_tickets_isolation ON public.service_tickets
    FOR SELECT TO authenticated
    USING (org_id IN (SELECT private.current_user_org_ids()));
CREATE POLICY service_tickets_backend ON public.service_tickets
    FOR ALL TO documentary_backend
    USING (org_id IN (SELECT private.current_user_org_ids()))
    WITH CHECK (org_id IN (SELECT private.current_user_org_ids()));
REVOKE ALL ON public.service_tickets FROM anon;
GRANT SELECT ON public.service_tickets TO authenticated;
GRANT SELECT, INSERT, UPDATE ON public.service_tickets TO documentary_backend;
GRANT ALL ON public.service_tickets TO service_role;

-- ── 7) Códigos humanos IN- / SC- / PV- ────────────────────────────────

CREATE OR REPLACE FUNCTION private.next_human_code(
    target_org UUID,
    kind TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $func$
DECLARE
    v_next BIGINT;
BEGIN
    -- Lock por (kind, org): dos transacciones del mismo scope se
    -- serializan aquí — la segunda cuenta la fila cometida por la
    -- primera. Un rollback libera el lock y no deja hueco en el folio.
    PERFORM pg_advisory_xact_lock(
        hashtextextended(kind || ':' || target_org::text, 0)
    );
    IF kind = 'orders' THEN
        -- Órdenes de compra: los folios OT- pertenecen al taller; el
        -- contador OC- cubre todo lo que sale hacia proveedor.
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.orders
        WHERE org_id = target_org AND order_type <> 'WORKSHOP_OT';
        RETURN 'OC-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'inventory_remnants' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.inventory_remnants
        WHERE org_id = target_org;
        RETURN 'RT-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'order_receipts' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.order_receipts
        WHERE org_id = target_org;
        RETURN 'REC-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'site_incidents' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.site_incidents
        WHERE org_id = target_org;
        RETURN 'IN-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'field_purchase_requests' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.field_purchase_requests
        WHERE org_id = target_org;
        RETURN 'SC-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'service_tickets' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.service_tickets
        WHERE org_id = target_org;
        RETURN 'PV-' || lpad(v_next::text, 6, '0');
    END IF;
    RAISE EXCEPTION 'next_human_code: kind % desconocido', kind;
END
$func$;

-- El folio nunca se reasigna — igual que RT-/REC-.
CREATE TRIGGER site_incidents_code_immutable BEFORE UPDATE ON public.site_incidents
    FOR EACH ROW EXECUTE FUNCTION private.guard_human_code('code');
CREATE TRIGGER field_purchase_requests_code_immutable BEFORE UPDATE ON public.field_purchase_requests
    FOR EACH ROW EXECUTE FUNCTION private.guard_human_code('code');
CREATE TRIGGER service_tickets_code_immutable BEFORE UPDATE ON public.service_tickets
    FOR EACH ROW EXECUTE FUNCTION private.guard_human_code('code');

-- ── 8) Garantía: plazo en meses sellado con la revisión ───────────────

ALTER TABLE public.tenancy_organizations
    ADD COLUMN IF NOT EXISTS doc_warranty_months SMALLINT NOT NULL DEFAULT 24
        CONSTRAINT doc_warranty_months_range
        CHECK (doc_warranty_months BETWEEN 0 AND 240);
GRANT UPDATE (doc_warranty_months)
    ON public.tenancy_organizations TO documentary_backend;

ALTER TABLE public.project_documentary_inputs
    ADD COLUMN IF NOT EXISTS warranty_months SMALLINT
        CONSTRAINT warranty_months_range
        CHECK (warranty_months IS NULL OR warranty_months BETWEEN 0 AND 240);

-- ── 9) Lectura de la posición para el instalador ─────────────────────
--
-- El rol INSTALLER no es escritor documental: la ficha de obra lee la
-- posición (vano declarado, estado de medición, regla de montaje) bajo
-- documentary_backend, y la medición misma entra por el definer
-- apply_site_measurement — la política es de solo lectura.

CREATE POLICY position_field_installer_read ON public.project_positions
    FOR SELECT TO documentary_backend
    USING (private.documentary_role(org_id, ARRAY['INSTALLER']));

-- ── 10) Eventos de obra en la línea de tiempo de la OT ────────────────

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
        'WO_DISPATCH_VOIDED', 'QC_CHECK', 'WO_CNC_PROGRAM',
        'WO_SITE_MEASURED', 'WO_INSTALL_CHECKED',
        'WO_INCIDENT_REPORTED', 'WO_INCIDENT_RESOLVED',
        'WO_PURCHASE_REQUESTED',
        'WO_SERVICE_OPENED', 'WO_SERVICE_VISIT', 'WO_SERVICE_CLOSED'
    ));

COMMIT;
