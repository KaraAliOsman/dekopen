-- D07: del vano de obra a la medida de fabricación.
--
-- * mounting_rules: reglas de montaje por organización y sistema, como datos
--   (misma autoridad versionada que las policy tables de shot-09: org_id NULL
--   = global, una fila por tenant gana; autoridad inmutable — nueva versión =
--   nueva fila). La autoridad JSONB lleva las holguras/solapes por lado,
--   los ensanches declarados y los accesorios de fijación.
-- * project_positions gana el registro del vano (medidas a 1–3 puntos, tipo
--   de muro, escuadra/desplome), la regla aplicada, la fijación manual y el
--   estado de medida: CLIENT_DECLARED → SITE_RECTIFIED → CONFIRMED.
-- * tenancy_organizations gana la tolerancia de descuadre del vano (Ajustes).
--
-- Las reglas sembradas son SEED_SYNTHETIC + review_pending: valores de
-- taller razonables pendientes de revisión técnica, no norma oficial.

BEGIN;

CREATE TABLE public.mounting_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE RESTRICT,
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE RESTRICT,
    code TEXT NOT NULL CHECK (
        code IN ('EN_VANO', 'PREMARCO', 'SOBRE_VANO', 'TRASLAPADO', 'RENOVACION')
    ),
    version INT NOT NULL CHECK (version >= 1),
    label TEXT NOT NULL CHECK (length(btrim(label)) > 0),
    authority JSONB NOT NULL CHECK (jsonb_typeof(authority) = 'object'),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (system_id, org_id, code, version),
    UNIQUE (id, system_id)
);
COMMENT ON TABLE public.mounting_rules IS
    'D07 mounting rule per system (and optionally per organization): signed '
    'per-side mm between the measured opening and the fabrication measure, '
    'plus declared build-outs and fixing accessories. Immutable authority — '
    'a revised rule lands as a new version row.';

ALTER TABLE public.mounting_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY mounting_rules_read
ON public.mounting_rules FOR SELECT
TO authenticated, documentary_backend, pricing_backend
USING (auth.uid() IS NOT NULL
       AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE TRIGGER immutable_authority BEFORE UPDATE OR DELETE ON public.mounting_rules
FOR EACH ROW EXECUTE FUNCTION private.reject_immutable_evidence();
REVOKE ALL ON public.mounting_rules FROM anon, authenticated;
GRANT SELECT ON public.mounting_rules TO authenticated, documentary_backend;
GRANT ALL ON public.mounting_rules TO service_role;

ALTER TABLE public.project_positions
    ADD COLUMN rough_opening_input JSONB
        CHECK (rough_opening_input IS NULL OR jsonb_typeof(rough_opening_input) = 'object'),
    ADD COLUMN mounting_rule_id UUID
        REFERENCES public.mounting_rules(id) ON DELETE RESTRICT,
    ADD COLUMN fabrication_lock JSONB
        CHECK (fabrication_lock IS NULL OR jsonb_typeof(fabrication_lock) = 'object'),
    ADD COLUMN measurement_state TEXT NOT NULL DEFAULT 'CLIENT_DECLARED'
        CHECK (measurement_state IN ('CLIENT_DECLARED', 'SITE_RECTIFIED', 'CONFIRMED')),
    ADD COLUMN measurement_confirmed_at TIMESTAMPTZ,
    ADD COLUMN measurement_confirmed_by UUID,
    ADD CONSTRAINT position_measurement_confirmed_stamp CHECK (
        (measurement_state = 'CONFIRMED')
        = (measurement_confirmed_at IS NOT NULL AND measurement_confirmed_by IS NOT NULL)
    );

-- Column-level SELECT on project_positions (shot-08 revoked the table grant):
-- the new evidence columns must be granted explicitly or member reads 409.
GRANT SELECT (rough_opening_input, mounting_rule_id, fabrication_lock,
              measurement_state, measurement_confirmed_at, measurement_confirmed_by)
    ON public.project_positions TO authenticated;
GRANT SELECT ON public.mounting_rules TO pricing_backend;

-- A position's mounting rule must belong to its own system and scope.
CREATE FUNCTION private.validate_position_mounting_rule_scope()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF NEW.mounting_rule_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.mounting_rules
        WHERE id = NEW.mounting_rule_id
          AND system_id = NEW.system_id
          AND (org_id IS NULL OR org_id = NEW.org_id)
    ) THEN
        RAISE EXCEPTION 'mounting_rule_scope_mismatch' USING ERRCODE = '23503';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION private.validate_position_mounting_rule_scope() FROM PUBLIC;
CREATE TRIGGER validate_position_mounting_rule_scope
BEFORE INSERT OR UPDATE OF mounting_rule_id, system_id ON public.project_positions
FOR EACH ROW EXECUTE FUNCTION private.validate_position_mounting_rule_scope();

-- Declared site-measurement spread tolerance, configurable per organization
-- in Ajustes. 10 mm is the workshop convention: beyond it the vano is out
-- of square enough that the smaller reading must be called out.
ALTER TABLE public.tenancy_organizations
    ADD COLUMN vano_spread_tolerance_mm NUMERIC(6, 2) NOT NULL DEFAULT 10.00
        CHECK (vano_spread_tolerance_mm >= 0.00 AND vano_spread_tolerance_mm <= 100.00);
GRANT UPDATE (vano_spread_tolerance_mm, updated_at)
    ON public.tenancy_organizations TO documentary_backend;

-- Seeded mounting rules — one version 1 per mounting type per existing
-- system. Signed adds: negative = deducted from the vano, positive = added
-- (overlap). Declared synthetic defaults pending technical review.
INSERT INTO public.mounting_rules (
    system_id, org_id, code, version, label, authority,
    data_provenance, review_pending
)
SELECT s.id, NULL, v.code, 1, v.label, v.authority::jsonb,
       'SEED_SYNTHETIC', TRUE
FROM public.profile_systems AS s
CROSS JOIN (
    VALUES (
        'EN_VANO',
        'En vano con holgura perimetral',
        '{"sides":{"top":{"mm":"-10.00","label":"Holgura superior"},'
            '"right":{"mm":"-10.00","label":"Holgura derecha"},'
            '"bottom":{"mm":"-10.00","label":"Holgura inferior"},'
            '"left":{"mm":"-10.00","label":"Holgura izquierda"}},'
            '"frame_extensions":[],'
            '"fixings":[{"label":"Anclaje perimetral","qty_per_unit":"8","note":"Cada 600 mm aprox., según muro"}],'
            '"wall_notes":{"PARTITION":"Tabique liviano: verifica anclaje con el instalador."}}'
    ), (
        'PREMARCO',
        'Con premarco',
        '{"sides":{"top":{"mm":"-40.00","label":"Holgura y premarco superior"},'
            '"right":{"mm":"-40.00","label":"Holgura y premarco derecho"},'
            '"bottom":{"mm":"-40.00","label":"Holgura y premarco inferior"},'
            '"left":{"mm":"-40.00","label":"Holgura y premarco izquierdo"}},'
            '"frame_extensions":[{"side":"all","label":"Premarco perimetral","mm":"30.00"}],'
            '"fixings":[{"label":"Anclaje de premarco","qty_per_unit":"8","note":"Al muro, según tipo"}],'
            '"wall_notes":{"PARTITION":"Tabique liviano: el premarco se ancla a la estructura, no al tabique."}}'
    ), (
        'SOBRE_VANO',
        'Sobre vano',
        '{"sides":{"top":{"mm":"20.00","label":"Solape superior"},'
            '"right":{"mm":"20.00","label":"Solape derecho"},'
            '"bottom":{"mm":"0.00","label":"Ajuste inferior"},'
            '"left":{"mm":"20.00","label":"Solape izquierdo"}},'
            '"frame_extensions":[],'
            '"fixings":[{"label":"Fijación sobre vano","qty_per_unit":"6","note":"Al paño, no al vano"}],'
            '"wall_notes":{}}'
    ), (
        'TRASLAPADO',
        'Traslapado',
        '{"sides":{"top":{"mm":"20.00","label":"Solape superior"},'
            '"right":{"mm":"20.00","label":"Solape derecho"},'
            '"bottom":{"mm":"20.00","label":"Solape inferior"},'
            '"left":{"mm":"20.00","label":"Solape izquierdo"}},'
            '"frame_extensions":[],'
            '"fixings":[{"label":"Fijación por solape","qty_per_unit":"8","note":"Al paño perimetral"}],'
            '"wall_notes":{}}'
    ), (
        'RENOVACION',
        'Renovación sobre marco existente',
        '{"sides":{"top":{"mm":"-5.00","label":"Holgura superior"},'
            '"right":{"mm":"-5.00","label":"Holgura derecha"},'
            '"bottom":{"mm":"-5.00","label":"Holgura inferior"},'
            '"left":{"mm":"-5.00","label":"Holgura izquierda"}},'
            '"frame_extensions":[],'
            '"fixings":[{"label":"Fijación al marco existente","qty_per_unit":"8","note":"Atornillado al marco"}],'
            '"wall_notes":{}}'
    )
) AS v(code, label, authority);

COMMIT;
