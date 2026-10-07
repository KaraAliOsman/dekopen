BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(18);

-- D08 tipologías avanzadas: el dominio de familia cubre las cuatro
-- familias nuevas y cada serie DEMO declara su oferta completa
-- (sistema, artículos, kits, reglas, límites, capacidades).

SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_systems
        WHERE code = 'DEMO_ELEVACION_90' AND system_family = 'LIFT_SLIDE' AND is_global
    ),
    'DEMO_ELEVACION_90 es una serie de familia LIFT_SLIDE'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_systems
        WHERE code = 'DEMO_PSK_90' AND system_family = 'PARALLEL_SLIDE' AND is_global
    ),
    'DEMO_PSK_90 es una serie de familia PARALLEL_SLIDE'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_systems
        WHERE code = 'DEMO_PLEGABLE_70' AND system_family = 'FOLDING' AND is_global
    ),
    'DEMO_PLEGABLE_70 es una serie de familia FOLDING'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_systems
        WHERE code = 'DEMO_PIVOTANTE_120' AND system_family = 'PIVOT' AND is_global
    ),
    'DEMO_PIVOTANTE_120 es una serie de familia PIVOT'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_systems
        WHERE code = 'DEMO_GUILLOTINA_60' AND system_family = 'VERTICAL_SLIDE' AND is_global
    ),
    'DEMO_GUILLOTINA_60 es una serie de familia VERTICAL_SLIDE'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.profile_systems
        WHERE code = 'DEMO_PUERTA_CORREDERA_70' AND system_family = 'SLIDING' AND is_global
    ),
    'DEMO_PUERTA_CORREDERA_70 es una serie corredera con unidades de puerta'
);

-- La puerta corredera existe como unidad DOOR declarada sobre una serie
-- corredera: capability SLIDE que admite DOOR + kit DOOR_SLIDING.
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.system_opening_capabilities c
        JOIN public.profile_systems s ON s.id = c.system_id
        WHERE s.code = 'DEMO_PUERTA_CORREDERA_70' AND c.movement = 'SLIDE'
          AND c.unit_kinds @> '{DOOR}'::text[]
    ),
    'DEMO_PUERTA_CORREDERA_70 declara SLIDE sobre unidades DOOR'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.hardware_kits k
        JOIN public.profile_systems s ON s.id = k.system_id
        WHERE s.code = 'DEMO_PUERTA_CORREDERA_70' AND k.opening_type = 'DOOR_SLIDING'
    ),
    'DEMO_PUERTA_CORREDERA_70 declara su kit de puerta corredera'
);

-- El plegable cabe en más de un par: el CHECK admite hasta 8 hojas.
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.system_opening_capabilities c
        JOIN public.profile_systems s ON s.id = c.system_id
        WHERE s.code = 'DEMO_PLEGABLE_70' AND c.movement = 'FOLD'
          AND c.max_leaves = 4
    ),
    'DEMO_PLEGABLE_70 declara composiciones plegables de 4 hojas'
);

-- Kits por familia: cada tipología tiene su clase de herraje.
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.hardware_kits k
        JOIN public.profile_systems s ON s.id = k.system_id
        WHERE s.code = 'DEMO_ELEVACION_90' AND k.opening_type = 'LIFT_SLIDE'
          AND k.max_leaf_weight_kg = 400.00
    ),
    'la elevable declara la clase HST reforzada de 400 kg'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.hardware_kits k
        JOIN public.profile_systems s ON s.id = k.system_id
        WHERE s.code = 'DEMO_PSK_90' AND k.opening_type = 'PARALLEL_SLIDE'
    ),
    'la osciloparalela declara su herraje basculante+paralelo'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.hardware_kits k
        JOIN public.profile_systems s ON s.id = k.system_id
        WHERE s.code = 'DEMO_PLEGABLE_70' AND k.opening_type = 'FOLD'
    ),
    'el plegable declara su kit de carros y guías'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.hardware_kits k
        JOIN public.profile_systems s ON s.id = k.system_id
        WHERE s.code = 'DEMO_PIVOTANTE_120' AND k.opening_type = 'PIVOT'
    ),
    'la pivotante declara sus pivotes'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.hardware_kits k
        JOIN public.profile_systems s ON s.id = k.system_id
        WHERE s.code = 'DEMO_GUILLOTINA_60' AND k.opening_type = 'VERTICAL_SLIDE'
    ),
    'la guillotina declara contrapesos o balances'
);

-- Límites dimensionales por tipología (los mismos que el motor congela).
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.system_typology_limits l
        JOIN public.profile_systems s ON s.id = l.system_id
        WHERE s.code = 'DEMO_ELEVACION_90' AND l.opening_type = 'DOOR:LIFT_SLIDE'
          AND l.max_leaf_weight_kg = 400.00
    ),
    'la elevable declara el sobre de la hoja elevable de puerta'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.system_typology_limits l
        JOIN public.profile_systems s ON s.id = l.system_id
        WHERE s.code = 'DEMO_GUILLOTINA_60' AND l.opening_type = 'VERTICAL_SLIDE'
    ),
    'la guillotina declara el sobre de su hoja'
);

-- Sin capacidad declarada no hay oferta: la serie DEMO_60 (casement) no
-- fabrica tipologías avanzadas.
SELECT is_empty(
    $$ SELECT 1 FROM public.system_opening_capabilities c
        JOIN public.profile_systems s ON s.id = c.system_id
        WHERE s.code = 'DEMO_60' AND c.movement IN
            ('LIFT_SLIDE','PARALLEL_SLIDE','FOLD','PIVOT_V','PIVOT_H','VERTICAL_SLIDE') $$,
    'DEMO_60 no declara tipologías avanzadas — no se ofrecen'
);

-- Todo marcado como datos sintéticos.
SELECT is_empty(
    $$ SELECT 1 FROM public.profile_systems
        WHERE code LIKE 'DEMO_%' AND system_family IN
            ('LIFT_SLIDE','PARALLEL_SLIDE','FOLDING','PIVOT','VERTICAL_SLIDE')
          AND data_provenance <> 'SEED_SYNTHETIC' $$,
    'las series D08 se marcan SEED_SYNTHETIC'
);

SELECT * FROM finish();
ROLLBACK;
