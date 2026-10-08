BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(21);

-- ── P16: certificación del catálogo — solo el revisor técnico puede elevar
-- la procedencia a VERIFICADO, y la auditoría de importación es append-only. ──

SELECT has_function('private', 'can_review_catalog', ARRAY['uuid'],
    'private.can_review_catalog(uuid) existe');
SELECT has_function('private', 'guard_catalog_certification', ARRAY[]::text[],
    'trigger guard_catalog_certification existe');

-- Fixture: org A con revisor (WORKSHOP_MANAGER), miembro plano (ESTIMATOR)
-- y dueño; org B con su propio revisor (aislamiento de tenant).
INSERT INTO public.tenancy_organizations (id, name, tax_id)
VALUES ('66666666-6666-4666-8666-666666666666', 'Tenant P16-A', 'P16-A'),
       ('77777777-7777-4777-8777-777777777777', 'Tenant P16-B', 'P16-B');

INSERT INTO public.tenancy_memberships (org_id, user_id, role) VALUES
 ('66666666-6666-4666-8666-666666666666','eeeeeeee-0000-4000-8000-00000000000a','WORKSHOP_MANAGER'),
 ('66666666-6666-4666-8666-666666666666','eeeeeeee-0000-4000-8000-00000000000b','ESTIMATOR'),
 ('66666666-6666-4666-8666-666666666666','eeeeeeee-0000-4000-8000-00000000000c','OWNER'),
 ('77777777-7777-4777-8777-777777777777','eeeeeeee-0000-4000-8000-00000000000d','WORKSHOP_MANAGER');

-- can_review_catalog: reviewer sí, miembro plano no, owner sin aal2 no,
-- owner con aal2 sí, revisor de otra org no (regresión PR #107 global/org).
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000a","role":"authenticated","aal":"aal1"}', TRUE);
SELECT ok(private.can_review_catalog('66666666-6666-4666-8666-666666666666'),
    'WORKSHOP_MANAGER es revisor técnico');
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000b","role":"authenticated","aal":"aal2"}', TRUE);
SELECT ok(NOT private.can_review_catalog('66666666-6666-4666-8666-666666666666'),
    'ESTIMATOR no es revisor técnico');
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000c","role":"authenticated","aal":"aal1"}', TRUE);
SELECT ok(NOT private.can_review_catalog('66666666-6666-4666-8666-666666666666'),
    'OWNER sin aal2 no es revisor técnico');
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000c","role":"authenticated","aal":"aal2"}', TRUE);
SELECT ok(private.can_review_catalog('66666666-6666-4666-8666-666666666666'),
    'OWNER con aal2 es revisor técnico');
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000d","role":"authenticated","aal":"aal1"}', TRUE);
SELECT ok(NOT private.can_review_catalog('66666666-6666-4666-8666-666666666666'),
    'el revisor de la org B no es revisor en la org A');

RESET ROLE;
SET LOCAL ROLE catalog_backend;

-- Una fila de catálogo escrita por la API con claims del revisor.
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000a","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000a', TRUE);

INSERT INTO public.profile_systems (id, org_id, name, code, depth_mm,
    sliding_glazing_deduction_width_mm, sliding_glazing_deduction_height_mm,
    door_leaf_side_clearance_mm)
VALUES ('66666666-aaaa-4666-8666-666666666666',
        '66666666-6666-4666-8666-666666666666', 'P16', 'P16', 66.00,
        0.00, 0.00, 0.00);

INSERT INTO public.profile_articles (
    id, org_id, system_id, sku, name, role, face_width_mm)
VALUES ('66666666-bbbb-4666-8666-666666666666',
        '66666666-6666-4666-8666-666666666666',
        '66666666-aaaa-4666-8666-666666666666',
        'P16-FRAME', 'P16 Marco', 'FRAME', 50.00),
       ('66666666-bbbb-4666-8666-666666666667',
        '66666666-6666-4666-8666-666666666666',
        '66666666-aaaa-4666-8666-666666666666',
        'P16-BEAD', 'P16 Junquillo', 'GLAZING_BEAD', 14.00);

-- El revisor sí puede certificar (elevar a VERIFICADO). pgTAP no se
-- puede invocar bajo catalog_backend (sin USAGE en extensions): el
-- resultado se captura en un GUC y se afirma tras volver a authenticated.
DO $p16$
BEGIN
    UPDATE public.profile_articles
    SET technical_reviewed_at=now(),
        technical_reviewed_by='eeeeeeee-0000-4000-8000-00000000000a',
        review_pending=FALSE
    WHERE id='66666666-bbbb-4666-8666-666666666666';
    PERFORM set_config('p16.reviewer_stamp', 'yes', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p16.reviewer_stamp', SQLSTATE, TRUE);
END $p16$;

-- Un sello conservado de otro revisor es válido: clonar un catálogo
-- verificado copia la firma original y eso no es autocertificación.
DO $p16$
BEGIN
    UPDATE public.profile_articles
    SET technical_reviewed_at=now(),
        technical_reviewed_by='eeeeeeee-0000-4000-8000-00000000000c'
    WHERE id='66666666-bbbb-4666-8666-666666666666';
    PERFORM set_config('p16.clone_stamp', 'yes', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p16.clone_stamp', SQLSTATE, TRUE);
END $p16$;

-- Un miembro con escritura técnica pero SIN rol de revisor (OWNER a aal1)
-- no puede elevar la procedencia. En INSERT el trigger BEFORE ROW se
-- evalúa antes del WITH CHECK y rechaza con 42501.
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000c","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000c', TRUE);
DO $p16$
BEGIN
    INSERT INTO public.profile_articles (
        id, org_id, system_id, sku, name, role, face_width_mm,
        technical_reviewed_at, technical_reviewed_by)
    VALUES ('66666666-bbbb-4666-8666-666666666668',
            '66666666-6666-4666-8666-666666666666',
            '66666666-aaaa-4666-8666-666666666666',
            'P16-X', 'P16 X', 'ADDITIONAL', 10.00,
            now(), 'eeeeeeee-0000-4000-8000-00000000000c');
    PERFORM set_config('p16.nonreviewer_insert', 'inserted', TRUE);
EXCEPTION WHEN OTHERS THEN
    PERFORM set_config('p16.nonreviewer_insert', SQLSTATE, TRUE);
END $p16$;

RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000a","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000a', TRUE);
SELECT is(current_setting('p16.reviewer_stamp', TRUE), 'yes',
    'el revisor técnico puede estampar la revisión');
SELECT is(current_setting('p16.clone_stamp', TRUE), 'yes',
    'el revisor puede conservar el sello de otro revisor (clonación)');
SELECT is(current_setting('p16.nonreviewer_insert', TRUE), '42501',
    'miembro sin rol de revisor no puede insertar ya certificado');
-- En UPDATE el miembro directo (authenticated) no tiene column-grant sobre
-- el sello de revisión: la base lo rechaza con 42501 sin llegar a la fila.
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000c","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000c', TRUE);
SELECT throws_ok(
    $$UPDATE public.profile_articles
      SET technical_reviewed_at=now(),
          technical_reviewed_by='eeeeeeee-0000-4000-8000-00000000000c',
          review_pending=FALSE
      WHERE id='66666666-bbbb-4666-8666-666666666667'$$,
    '42501', NULL,
    'miembro sin rol de revisor no puede elevar la procedencia en UPDATE'
);
-- Y por la vía del backend: el claim sin rol de revisor tampoco llega —
-- la política de escritura org-scoped filtra la fila (0 filas afectadas).
SET LOCAL ROLE catalog_backend;
UPDATE public.profile_articles
SET technical_reviewed_at=now(),
    technical_reviewed_by='eeeeeeee-0000-4000-8000-00000000000c',
    review_pending=FALSE
WHERE id='66666666-bbbb-4666-8666-666666666667';

-- El revisor de la org B no puede certificar filas de la org A — la
-- autorización es por organización, no global (regresión PR #107).
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000d","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000d', TRUE);
UPDATE public.profile_articles
SET technical_reviewed_at=now(),
    technical_reviewed_by='eeeeeeee-0000-4000-8000-00000000000d'
WHERE id='66666666-bbbb-4666-8666-666666666667';

-- Escritura técnica normal bajo el guard: sigue funcionando. El UPDATE
-- crudo abortaría la transacción si el guard lo rechazara por error.
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000a","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000a', TRUE);
UPDATE public.profile_articles SET name='P16 Marco re-editado'
WHERE id='66666666-bbbb-4666-8666-666666666667';

-- Las filas son invisibles para la org B: las comprobaciones se hacen
-- con claims de un miembro de la org A bajo el rol authenticated.
RESET ROLE;
SET LOCAL ROLE authenticated;
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000a","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000a', TRUE);
SELECT is(
    (SELECT (technical_reviewed_at IS NULL)::text
       FROM public.profile_articles
      WHERE id='66666666-bbbb-4666-8666-666666666667'),
    'true',
    'el UPDATE del miembro sin rol no certificó la fila (RLS + guard)'
);
SELECT is(
    (SELECT (technical_reviewed_at IS NULL)::text
       FROM public.profile_articles
      WHERE id='66666666-bbbb-4666-8666-666666666667'),
    'true',
    'revisor de otra organización no puede certificar aquí'
);
SELECT is(
    (SELECT name FROM public.profile_articles
      WHERE id='66666666-bbbb-4666-8666-666666666667'),
    'P16 Marco re-editado',
    'la escritura técnica normal sigue funcionando bajo el guard'
);

-- ── catalog_import_events: lectura de miembros, escritura solo backend ──────
SET LOCAL ROLE documentary_backend;
INSERT INTO public.catalog_imports (id, org_id, file_name, kind, storage_path,
    created_by)
VALUES ('66666666-cccc-4666-8666-666666666666',
        '66666666-6666-4666-8666-666666666666',
        'catalogo.pdf', 'PDF', 'catalog-imports/x/y/catalogo.pdf',
        'eeeeeeee-0000-4000-8000-00000000000a');
INSERT INTO public.catalog_import_events (org_id, import_id, event, actor_id)
VALUES ('66666666-6666-4666-8666-666666666666',
        '66666666-cccc-4666-8666-666666666666',
        'UPLOADED', 'eeeeeeee-0000-4000-8000-00000000000a');

SET LOCAL ROLE authenticated;
SELECT is(
    (SELECT count(*)::int FROM public.catalog_import_events
      WHERE import_id='66666666-cccc-4666-8666-666666666666'),
    1, 'el miembro de la org lee el evento de importación'
);
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000d","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000d', TRUE);
SELECT is(
    (SELECT count(*)::int FROM public.catalog_import_events
      WHERE import_id='66666666-cccc-4666-8666-666666666666'),
    0, 'la org B no lee eventos de la org A'
);
SELECT set_config('request.jwt.claims',
    '{"sub":"eeeeeeee-0000-4000-8000-00000000000a","role":"authenticated","aal":"aal1"}', TRUE);
SELECT set_config('request.jwt.claim.sub',
    'eeeeeeee-0000-4000-8000-00000000000a', TRUE);
SELECT throws_ok(
    $$UPDATE public.catalog_import_events SET event='CONFIRMED'
      WHERE import_id='66666666-cccc-4666-8666-666666666666'$$,
    '42501', NULL,
    'un miembro no puede reescribir la auditoría de importación'
);
SELECT throws_ok(
    $$DELETE FROM public.catalog_import_events
      WHERE import_id='66666666-cccc-4666-8666-666666666666'$$,
    '42501', NULL,
    'un miembro no puede borrar la auditoría de importación'
);
SELECT lives_ok(
    $$UPDATE public.profile_systems SET name='P16 renombrado'
      WHERE id='66666666-aaaa-4666-8666-666666666666'$$,
    'miembro con columna-grant sigue escribiendo campos editables'
);

RESET ROLE;

-- ── catalog_imports reviewed_by/reviewed_at existen ────────────────────────
SELECT has_column('public', 'catalog_imports', 'reviewed_by',
    'catalog_imports guarda el revisor');
SELECT has_column('public', 'catalog_imports', 'reviewed_at',
    'catalog_imports guarda la fecha de revisión');

SELECT * FROM finish();
ROLLBACK;
