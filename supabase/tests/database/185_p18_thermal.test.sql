BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(14);

-- ── P18: autoridades térmicas (psi_g separador, Uf por grupo, informes de
-- ensayo con clases) + zona térmica del proyecto + orientación de posición. ──

SELECT has_table('public', 'glazing_spacers', 'glazing_spacers existe');
SELECT has_table('public', 'system_frame_uf', 'system_frame_uf existe');
SELECT has_table('public', 'system_performance_tests',
    'system_performance_tests existe');
SELECT has_column('public', 'projects', 'thermal_zone',
    'projects.thermal_zone existe');
SELECT has_column('public', 'project_positions', 'thermal_orientation',
    'project_positions.thermal_orientation existe');

-- Fixture: org con revisor + sistema.
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('88888888-8888-4888-8888-888888888888', 'Tenant P18', 'P18');
INSERT INTO public.tenancy_memberships (org_id, user_id, role) VALUES
 ('88888888-8888-4888-8888-888888888888','eeeeeeee-0000-4000-8000-0000000000a0','WORKSHOP_MANAGER'),
 ('88888888-8888-4888-8888-888888888888','eeeeeeee-0000-4000-8000-0000000000a1','ESTIMATOR');

-- ── Sección catalog_backend: pgTAP no se puede invocar bajo este rol
-- (sin USAGE en extensions, como documenta P16) → los resultados se
-- capturan en GUCs y se afirman de vuelta en authenticated. ──
SET LOCAL ROLE catalog_backend;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-0000000000a0","role":"authenticated","aal":"aal1"}', TRUE);

INSERT INTO public.profile_systems (id, org_id, name, code, depth_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm)
VALUES ('88888888-aaaa-4888-8888-888888888888',
        '88888888-8888-4888-8888-888888888888', 'P18', 'P18', 60.00,
        0.00, 0.00, 0.00);

DO $p18$
BEGIN
    INSERT INTO public.glazing_spacers (org_id, code, name, psi_w_m_k)
    VALUES ('88888888-8888-4888-8888-888888888888',
            'ALUMINIUM', 'Separador aluminio', 0.0600);
    INSERT INTO public.system_frame_uf (org_id, system_id, member_group,
        uf_w_m2k, source_ref)
    VALUES ('88888888-8888-4888-8888-888888888888',
            '88888888-aaaa-4888-8888-888888888888', 'ALL', 1.400,
            'Ficha técnica fabricante');
    INSERT INTO public.system_performance_tests (org_id, system_id,
        air_class, water_class, report_ref, laboratory, tested_on,
        tested_width_mm, tested_height_mm)
    VALUES ('88888888-8888-4888-8888-888888888888',
            '88888888-aaaa-4888-8888-888888888888', 3, '7A',
            'INF-2024-118', 'DICTUC', '2024-03-12', 2400.00, 1800.00);
    PERFORM set_config('p18.thermal_write', 'yes', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p18.thermal_write', SQLSTATE, TRUE);
END $p18$;

-- Dominios declarados: psi>0, air_class 1..5, member_group enumerado.
DO $p18$
BEGIN
    INSERT INTO public.glazing_spacers (org_id, code, name, psi_w_m_k)
    VALUES ('88888888-8888-4888-8888-888888888888',
            'WARM_EDGE', 'Borde cálido', 0.0000);
    PERFORM set_config('p18.psi_zero', 'inserted', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p18.psi_zero', SQLSTATE, TRUE);
END $p18$;

DO $p18$
BEGIN
    INSERT INTO public.system_performance_tests (org_id, system_id, air_class)
    VALUES ('88888888-8888-4888-8888-888888888888',
            '88888888-aaaa-4888-8888-888888888888', 6);
    PERFORM set_config('p18.air_class_six', 'inserted', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p18.air_class_six', SQLSTATE, TRUE);
END $p18$;

DO $p18$
BEGIN
    INSERT INTO public.system_frame_uf (org_id, system_id, member_group,
        uf_w_m2k)
    VALUES ('88888888-8888-4888-8888-888888888888',
            '88888888-aaaa-4888-8888-888888888888', 'BEAD', 1.2);
    PERFORM set_config('p18.member_group', 'inserted', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p18.member_group', SQLSTATE, TRUE);
END $p18$;

-- Sello de certificación sin ser revisor: el guard de P16 bloquea (42501).
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-0000000000a1","role":"authenticated","aal":"aal1"}', TRUE);
DO $p18$
BEGIN
    INSERT INTO public.glazing_spacers (org_id, code, name, psi_w_m_k,
        technical_reviewed_at)
    VALUES ('88888888-8888-4888-8888-888888888888',
            'WARM_EDGE', 'Borde cálido', 0.0400, NOW());
    PERFORM set_config('p18.nonreviewer', 'inserted', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p18.nonreviewer', SQLSTATE, TRUE);
END $p18$;

RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-0000000000a0","role":"authenticated","aal":"aal1"}', TRUE);

SELECT is(current_setting('p18.thermal_write', TRUE), 'yes',
    'catalog_backend inserta las tres tablas térmicas'::text);
SELECT is(current_setting('p18.psi_zero', TRUE), '23514',
    'psi_w_m_k en cero es rechazado'::text);
SELECT is(current_setting('p18.air_class_six', TRUE), '23514',
    'air_class fuera de 1..5 es rechazado'::text);
SELECT is(current_setting('p18.member_group', TRUE), '23514',
    'member_group fuera del enum es rechazado'::text);
SELECT is(current_setting('p18.nonreviewer', TRUE), '42501',
    'estampar certificación sin rol revisor es bloqueado por el guard'::text);

-- Lectura autenticada del catálogo térmico de su org.
SELECT ok(
    (SELECT count(*) FROM public.glazing_spacers
      WHERE org_id = '88888888-8888-4888-8888-888888888888') = 1,
    'authenticated lee el psi_g de su org'::text);

-- Escritura autenticada directa prohibida.
SELECT throws_matching(
    $$INSERT INTO public.glazing_spacers
        (org_id, code, name, psi_w_m_k)
      VALUES ('88888888-8888-4888-8888-888888888888',
        'WARM_EDGE', 'Borde cálido', 0.0400)$$,
    'permission denied',
    'authenticated no puede escribir el catálogo térmico'::text);

-- Orientación/zona del proyecto: lectura por columna otorgada a
-- authenticated (los SELECT son por columna desde shot-08).
DO $$
BEGIN
  PERFORM thermal_zone, thermal_use, thermal_wall_areas
    FROM public.projects LIMIT 1;
  PERFORM thermal_orientation FROM public.project_positions LIMIT 1;
END $$;
SELECT ok(TRUE, 'authenticated puede leer las columnas térmicas'::text);

RESET ROLE;

-- Zona térmica del proyecto: el CHECK rechaza zonas fuera de A–I.
INSERT INTO public.projects (id, org_id, code, name, client_name, created_by)
VALUES ('88888888-bbbb-4888-8888-888888888888',
        '88888888-8888-4888-8888-888888888888', 'P18-1', 'Proyecto P18',
        'Cliente', 'eeeeeeee-0000-4000-8000-0000000000a0');
SELECT throws_matching(
    $$UPDATE public.projects SET thermal_zone = 'J'
      WHERE id = '88888888-bbbb-4888-8888-888888888888'$$,
    'projects_thermal_zone_check',
    'thermal_zone fuera de A–I es rechazado'::text);

SELECT finish();
ROLLBACK;
