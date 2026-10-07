-- P18 — Desempeño térmico y normativa chilena (OGUC art. 4.1.10).
--
-- Tres nuevas autoridades de catálogo con la tríada de procedencia de P16:
--   · glazing_spacers          — Ψg declarado por tipo de separador
--                                (el enum SpacerKind del motor).
--   · system_frame_uf          — Uf declarado por sistema, por grupo de
--                                miembro ('ALL' = valor único del sistema).
--   · system_performance_tests — clases de permeabilidad aire/agua/viento
--                                con su informe de ensayo (documento,
--                                laboratorio, fecha, alcance dimensional).
--
-- Proyecto: zona térmica (A–I, NCh 1079), uso térmico (residencial /
-- equipamiento educación-salud) y superficies de paramentos verticales por
-- orientación — datos que el usuario declara; DEKOPEN no los inventa.
-- Posición: orientación del paramento donde se instala ('ROOF' = ventana en
-- plano ≤60° desde la horizontal, la exigencia de techumbre).

-- ─── Separadores acristalamiento (Ψg) ─────────────────────────────────────
CREATE TABLE public.glazing_spacers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- NULL = dato global compartido (autoridad de plataforma); con org_id el
    -- taller declara el suyo y sombrea el global con el mismo code.
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    -- El código es el kind que declara la composición del vidrio
    -- (SpacerKind del motor): hoy ALUMINIUM | WARM_EDGE. Extensible.
    code TEXT NOT NULL CHECK (code IN ('ALUMINIUM', 'WARM_EDGE')),
    name TEXT NOT NULL CHECK (length(btrim(name)) > 0),
    -- Puente térmico lineal del borde de vidrio (W/m·K).
    psi_w_m_k NUMERIC(6, 4) NOT NULL
        CHECK (psi_w_m_k > 0.0000 AND psi_w_m_k < 1.0000),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id, code)
);
COMMENT ON TABLE public.glazing_spacers IS
    'P18 Ψg declarado por tipo de separador (bordes de DVH/TVH). Dato '
    'declarado/certificado — nunca calculado.';

-- ─── Uf del sistema por grupo de miembro ──────────────────────────────────
-- El fabricante declara Uf por combinación de perfiles; 'ALL' cubre el caso
-- común de un único valor para toda la serie. El motor pondera Af por grupo.
CREATE TABLE public.system_frame_uf (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE CASCADE,
    member_group TEXT NOT NULL CHECK (member_group IN (
        'ALL', 'FRAME', 'SASH', 'MULLION', 'COUPLER', 'THRESHOLD')),
    uf_w_m2k NUMERIC(6, 3) NOT NULL
        CHECK (uf_w_m2k > 0.000 AND uf_w_m2k <= 12.000),
    -- Referencia legible: ficha técnica del fabricante, informe o memoria.
    source_ref TEXT,
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE NULLS NOT DISTINCT (org_id, system_id, member_group)
);
COMMENT ON TABLE public.system_frame_uf IS
    'P18 Uf declarado por sistema y grupo de miembro (ALL/FRAME/SASH/'
    'MULLION/COUPLER/THRESHOLD) con fuente y revisor.';

-- ─── Ensayos de desempeño del sistema (clases) ────────────────────────────
-- Una fila por informe de ensayo. typology_scope NULL = aplica a toda la
-- serie; un alcance declarado ('PRACTICABLE', 'CORREDERA', ...) restringe la
-- clase a esa familia. Las dimensiones ensayadas delimitan el alcance: una
-- posición mayor que el ejemplar ensayado no puede reclamar la clase.
CREATE TABLE public.system_performance_tests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES public.tenancy_organizations(id) ON DELETE CASCADE,
    system_id UUID NOT NULL REFERENCES public.profile_systems(id) ON DELETE CASCADE,
    typology_scope TEXT CHECK (typology_scope IS NULL OR length(btrim(typology_scope)) > 0),
    -- Clase final de permeabilidad al aire medida a 100 Pa (NCh 3296/3297).
    air_class SMALLINT CHECK (air_class IS NULL OR air_class BETWEEN 1 AND 5),
    water_class TEXT CHECK (water_class IS NULL OR length(btrim(water_class)) > 0),
    wind_class TEXT CHECK (wind_class IS NULL OR length(btrim(wind_class)) > 0),
    report_ref TEXT,
    laboratory TEXT,
    tested_on DATE,
    tested_width_mm NUMERIC(10, 2) CHECK (tested_width_mm IS NULL OR tested_width_mm > 0),
    tested_height_mm NUMERIC(10, 2) CHECK (tested_height_mm IS NULL OR tested_height_mm > 0),
    data_provenance TEXT NOT NULL DEFAULT 'MANUAL'
        CHECK (data_provenance IN ('SEED_SYNTHETIC', 'MANUAL', 'IMPORT', 'LEGACY_UNVERIFIED')),
    technical_reviewed_at TIMESTAMPTZ,
    technical_reviewed_by UUID,
    review_pending BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMENT ON TABLE public.system_performance_tests IS
    'P18 informe de ensayo del sistema: clases aire/agua/viento con '
    'laboratorio, fecha y alcance dimensional ensayado.';

-- ─── Zona térmica del proyecto + orientación de la posición ───────────────
ALTER TABLE public.projects
    ADD COLUMN thermal_zone CHAR(1)
        CHECK (thermal_zone IS NULL OR thermal_zone IN
               ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I')),
    -- RESIDENTIAL = numeral 1 del art. 4.1.10 (Tablas 3 y 9); EQUIPMENT =
    -- equipamiento educación/salud y hoteles (Tablas 12 y 16).
    ADD COLUMN thermal_use TEXT NOT NULL DEFAULT 'RESIDENTIAL'
        CHECK (thermal_use IN ('RESIDENTIAL', 'EQUIPMENT')),
    -- Superficies de paramentos verticales por orientación, m² — las declara
    -- el usuario; DEKOPEN no conoce la envolvente del proyecto. Claves
    -- válidas: N, OP, S, OGT (OGT = total de paramentos verticales).
    ADD COLUMN thermal_wall_areas JSONB
        CHECK (thermal_wall_areas IS NULL
               OR jsonb_typeof(thermal_wall_areas) = 'object');

ALTER TABLE public.project_positions
    -- Orientación del paramento vertical donde se instala la posición:
    -- 'N' | 'OP' | 'S' | 'OGT'; 'ROOF' = ventana en techumbre (plano ≤60°).
    ADD COLUMN thermal_orientation TEXT
        CHECK (thermal_orientation IS NULL
               OR thermal_orientation IN ('N', 'OP', 'S', 'OGT', 'ROOF'));

-- Los SELECT de projects/project_positions son por columna (shot-08) — hay
-- que otorgar las nuevas explícitamente.
GRANT SELECT (thermal_zone, thermal_use, thermal_wall_areas)
    ON public.projects TO authenticated;
GRANT SELECT (thermal_orientation)
    ON public.project_positions TO authenticated;

-- ─── RLS + grants del catálogo térmico (patrón glass_products) ────────────
ALTER TABLE public.glazing_spacers ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_frame_uf ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_performance_tests ENABLE ROW LEVEL SECURITY;

CREATE POLICY glazing_spacers_read
ON public.glazing_spacers FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY system_frame_uf_read
ON public.system_frame_uf FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));
CREATE POLICY system_performance_tests_read
ON public.system_performance_tests FOR SELECT TO authenticated, documentary_backend
USING (auth.uid() IS NOT NULL AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids())));

CREATE POLICY glazing_spacers_backend_write
ON public.glazing_spacers FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY system_frame_uf_backend_write
ON public.system_frame_uf FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));
CREATE POLICY system_performance_tests_backend_write
ON public.system_performance_tests FOR ALL TO catalog_backend
USING (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()))
WITH CHECK (org_id IS NULL OR org_id IN (SELECT * FROM private.current_user_org_ids()));

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'glazing_spacers',
        'system_frame_uf',
        'system_performance_tests'
    ] LOOP
        EXECUTE format(
            'REVOKE ALL ON public.%I FROM anon', table_name);
        EXECUTE format(
            'REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER '
            'ON public.%I FROM authenticated', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO authenticated', table_name);
        EXECUTE format(
            'GRANT ALL ON public.%I TO catalog_backend', table_name);
        EXECUTE format(
            'GRANT ALL ON public.%I TO service_role', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO pricing_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO documentary_backend', table_name);
        EXECUTE format(
            'GRANT SELECT ON public.%I TO ai_backend', table_name);
        -- P16: el sello de certificación exige el rol de revisor técnico.
        EXECUTE format(
            'CREATE TRIGGER catalog_certification_guard
             BEFORE INSERT OR UPDATE ON public.%I
             FOR EACH ROW EXECUTE FUNCTION private.guard_catalog_certification()',
            table_name);
    END LOOP;
END;
$$;

-- La evidencia de parámetros del catálogo (D02/P16) también ampara a las
-- nuevas autoridades térmicas.
ALTER TABLE public.catalog_parameter_evidence
    DROP CONSTRAINT catalog_parameter_evidence_authority_table_check;
ALTER TABLE public.catalog_parameter_evidence
    ADD CONSTRAINT catalog_parameter_evidence_authority_table_check
    CHECK (authority_table IN (
        'profile_systems', 'profile_articles', 'glazing_bead_matrix',
        'hardware_kits', 'infill_articles',
        'manufacturing_placement_policies', 'handle_requirement_policies',
        'reinforcement_cut_policies', 'glass_purchase_mappings',
        'fitting_purchase_mappings', 'catalog_imports',
        'glazing_spacers', 'system_frame_uf', 'system_performance_tests'));
