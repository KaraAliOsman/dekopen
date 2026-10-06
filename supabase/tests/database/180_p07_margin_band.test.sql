BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(7);

-- P07 — banda de margen en pricing_rules: mínimo/objetivo/máximo por org.
-- El CHECK de dominio vuelve a declararse con las columnas nuevas; las
-- filas preexistentes y las nuevas sin banda explícita heredan los
-- defaults §11 (0.25 / 0.60).

SELECT has_column(
    'public', 'pricing_rules', 'margin_min_pct',
    'pricing_rules lleva el mínimo de la banda de margen'
);
SELECT has_column(
    'public', 'pricing_rules', 'margin_max_pct',
    'pricing_rules lleva el máximo de la banda de margen'
);

INSERT INTO public.tenancy_organizations(id, name, tax_id) VALUES
    ('88880000-0000-4000-8000-000000000098', 'P07 Band', 'P07-BAND');

SELECT lives_ok(
    $$INSERT INTO public.pricing_rules (org_id)
      VALUES ('88880000-0000-4000-8000-000000000098')$$,
    'la fila sin banda explícita se acepta'
);
SELECT is(
    (SELECT margin_min_pct FROM public.pricing_rules
      WHERE org_id = '88880000-0000-4000-8000-000000000098'),
    0.2500::numeric,
    'el mínimo por defecto es 25 %'
);
SELECT is(
    (SELECT margin_max_pct FROM public.pricing_rules
      WHERE org_id = '88880000-0000-4000-8000-000000000098'),
    0.6000::numeric,
    'el máximo por defecto es 60 %'
);

-- El dominio numérico rechaza bandas invertidas o fuera de [0,1].
SELECT throws_ok(
    $$INSERT INTO public.pricing_rules
        (org_id, margin_min_pct, margin_max_pct)
      VALUES ('88880000-0000-4000-8000-000000000098', 0.60, 0.25)$$,
    '23514',
    NULL,
    'una banda invertida viola el dominio numérico'
);
SELECT throws_ok(
    $$INSERT INTO public.pricing_rules
        (org_id, margin_min_pct, margin_max_pct)
      VALUES ('88880000-0000-4000-8000-000000000098', -0.05, 0.60)$$,
    '23514',
    NULL,
    'un mínimo negativo viola el dominio numérico'
);

SELECT * FROM finish();
ROLLBACK;
