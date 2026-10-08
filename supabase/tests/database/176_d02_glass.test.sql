BEGIN;
CREATE EXTENSION IF NOT EXISTS pgtap;
SET LOCAL search_path = public, private, auth, extensions, pg_temp;
SELECT plan(20);

-- D02 vidrios de verdad: catálogo de productos con composición estructurada,
-- recargos declarados, reglas de seguridad NCh 135 (aviso, MANDATORY es
-- decisión de la organización) y límites por tipo de vidrio — todo como
-- datos auditables con data_provenance + review_pending.

SELECT has_table('public', 'glass_products', 'glass_products exists');
SELECT has_table('public', 'glass_product_surcharges', 'glass_product_surcharges exists');
SELECT has_table('public', 'glass_safety_rules', 'glass_safety_rules exists');
SELECT has_table('public', 'glass_type_limits', 'glass_type_limits exists');
SELECT has_column(
    'public', 'project_positions', 'glass_composition',
    'positions carry the resolved composition map (bay:leaf → dict)'
);
SELECT has_column(
    'public', 'project_positions', 'glass_review_pending',
    'positions flag declared specs the parser could not resolve'
);
SELECT col_has_check(
    'public', 'glass_products', 'price_tier',
    'price_tier is a checked 1..5 declared band'
);
SELECT policies_are(
    'public', 'glass_products',
    ARRAY['glass_products_backend_write', 'glass_products_read'],
    'glass products: member read + backend write only'
);
SELECT policies_are(
    'public', 'glass_product_surcharges',
    ARRAY['glass_product_surcharges_backend_write', 'glass_product_surcharges_read'],
    'surcharges: member read + backend write only'
);
SELECT policies_are(
    'public', 'glass_safety_rules',
    ARRAY['glass_safety_rules_backend_write', 'glass_safety_rules_read'],
    'safety rules: member read + backend write only'
);
SELECT policies_are(
    'public', 'glass_type_limits',
    ARRAY['glass_type_limits_backend_write', 'glass_type_limits_read'],
    'type limits: member read + backend write only'
);
SELECT col_has_check(
    'public', 'glass_product_surcharges', 'kind',
    'surcharge kind is a closed CHECK domain'
);
SELECT ok(
    EXISTS(
        SELECT 1
        FROM public.glass_products p
        JOIN public.profile_systems s ON s.id = p.system_id
        WHERE s.code = 'DEMO_60' AND s.is_global
          AND p.sku = 'VIDRIO-BASE'
          AND p.composition->'layers'->0->>'type' = 'lamina'
          AND p.composition->'layers'->1->>'type' = 'chamber'
          AND p.composition->'layers'->2->>'type' = 'lamina'
    ),
    'DEMO_60 base DVH carries the structured lamina/cámara/lamina stack'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.glass_safety_rules
        WHERE code = 'GLASS-SAFETY-DOOR'
          AND required_safety = 'SAFETY_GLASS'
          AND severity = 'WARNING'
          AND requires_door = TRUE
          AND review_pending = TRUE
          AND source_ref LIKE 'NCh 135%'
    ),
    'NCh 135 door rule ships as a WARNING with its cited source, pending official text'
);
SELECT ok(
    NOT EXISTS(
        SELECT 1 FROM public.glass_safety_rules
        WHERE sill_below_mm IS NOT NULL
    ),
    'no floor-distance rule is seeded — the unit base is not the floor'
);
SELECT ok(
    NOT EXISTS(
        SELECT 1 FROM public.glass_safety_rules
        WHERE severity = 'MANDATORY'
    ),
    'no seeded safety rule blocks — MANDATORY is an org decision'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.glass_type_limits
        WHERE code = 'GLASS-LIMIT-TEMPERED-EXACT-CUT'
          AND lamina_kind = 'TEMPERED'
          AND requires_exact_cut = TRUE
    ),
    'tempered exact-cut limit ships as org-editable data'
);
SELECT ok(
    EXISTS(
        SELECT 1
        FROM public.glass_product_surcharges r
        JOIN public.glass_products p ON p.id = r.product_id
        WHERE r.kind = 'TEMPERED' AND r.unit = 'M2'
    ),
    'a tempered surcharge seeds a per-m² rate'
);
SELECT ok(
    EXISTS(
        SELECT 1 FROM public.glass_products
        WHERE sku = 'VIDRIO-LAM-638'
          AND total_thickness_mm = 6.38
          AND safety_class = 'A'
    ),
    'laminated 3+3 declares class A and its PVB-inclusive thickness'
);
SELECT ok(
    NOT EXISTS(
        SELECT 1 FROM public.profile_systems s
        WHERE s.is_global = TRUE
          AND NOT EXISTS(
              SELECT 1 FROM public.glass_products p
              WHERE p.system_id = s.id AND p.is_active = TRUE
          )
    ),
    'every active global system offers at least one glass product'
);

SELECT * FROM finish();
ROLLBACK;
