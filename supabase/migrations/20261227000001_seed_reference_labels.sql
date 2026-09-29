-- Reference-catalog relabeling: the seeded demo families used test-scaffolding
-- strings ("SYNTHETIC TEST DATA", "TEST-SUPPLIER", "TEST-BUY-*") which leaked
-- into catalog/purchasing surfaces. Global (org_id IS NULL) reference rows are
-- renamed to business-readable labels. Org-owned data is untouched.
BEGIN;

UPDATE public.profile_purchase_mappings
SET commercial_sku = REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(commercial_sku,
        'TEST-BUY-', 'COMPRA-'),
        'DEMO-BUY-', 'COMPRA-'),
        'DEMO-STEEL-BAR-', 'COMPRA-ACERO-'),
        'DEMO-STEEL-', 'ACERO-'),
        'DEMO-BAR-', 'COMPRA-'),
    manufacturer_name = CASE manufacturer_name
        WHEN 'SYNTHETIC TEST DATA' THEN 'Referencia DEKOPEN'
        WHEN 'DEMO_60 SYNTHETIC FIXTURE' THEN 'Catálogo de demostración'
        ELSE manufacturer_name END,
    supplier_name = CASE supplier_name
        WHEN 'TEST-SUPPLIER' THEN 'Proveedor de referencia'
        WHEN 'DEMO-SUPPLIER' THEN 'Proveedor de referencia'
        ELSE supplier_name END
WHERE org_id IS NULL;

UPDATE public.hardware_purchase_mappings
SET purchasing_sku = REPLACE(REPLACE(purchasing_sku, 'TEST-BUY-', 'COMPRA-'), 'DEMO-BUY-', 'COMPRA-'),
    manufacturer_name = CASE manufacturer_name
        WHEN 'SYNTHETIC TEST DATA' THEN 'Referencia DEKOPEN'
        WHEN 'DEMO_60 SYNTHETIC FIXTURE' THEN 'Catálogo de demostración'
        ELSE manufacturer_name END,
    provenance = CASE
        WHEN provenance->>'source' IN ('SYNTHETIC TEST DATA', 'DEMO_60 SYNTHETIC FIXTURE')
        THEN jsonb_set(provenance, '{source}', '"Referencia DEKOPEN"')
        ELSE provenance END
WHERE org_id IS NULL;

UPDATE public.glass_purchase_mappings
SET purchasing_sku = CASE
        WHEN purchasing_sku = 'DEMO-GLASS-FINISHED-UNIT' THEN 'VIDRIO-TERMINADO'
        ELSE REPLACE(REPLACE(purchasing_sku, 'TEST-BUY-', 'COMPRA-'), 'DEMO-BUY-', 'COMPRA-')
        END,
    technical_sku = CASE technical_sku WHEN 'GLASS-BASE' THEN 'VIDRIO-BASE' ELSE technical_sku END,
    manufacturer_name = CASE manufacturer_name
        WHEN 'SYNTHETIC TEST DATA' THEN 'Referencia DEKOPEN'
        WHEN 'DEMO_60 SYNTHETIC FIXTURE' THEN 'Catálogo de demostración'
        ELSE manufacturer_name END,
    provenance = CASE
        WHEN provenance->>'source' IN ('SYNTHETIC TEST DATA', 'DEMO_60 SYNTHETIC FIXTURE')
        THEN jsonb_set(provenance, '{source}', '"Referencia DEKOPEN"')
        ELSE provenance END
WHERE org_id IS NULL;

UPDATE public.panel_purchase_authorities
SET purchasing_sku = REPLACE(REPLACE(purchasing_sku, 'TEST-BUY-', 'COMPRA-'), 'DEMO-BUY-', 'COMPRA-'),
    manufacturer_name = CASE manufacturer_name
        WHEN 'SYNTHETIC TEST DATA' THEN 'Referencia DEKOPEN'
        WHEN 'DEMO_60 SYNTHETIC FIXTURE' THEN 'Catálogo de demostración'
        ELSE manufacturer_name END,
    provenance = CASE
        WHEN provenance->>'source' IN ('SYNTHETIC TEST DATA', 'DEMO_60 SYNTHETIC FIXTURE')
        THEN jsonb_set(provenance, '{source}', '"Referencia DEKOPEN"')
        ELSE provenance END
WHERE org_id IS NULL;

UPDATE public.reinforcement_articles
SET sku = REPLACE(sku, 'DEMO-STEEL-', 'ACERO-'),
    commercial_sku = REPLACE(commercial_sku, 'DEMO-STEEL-BAR-', 'COMPRA-ACERO-'),
    manufacturer_name = CASE manufacturer_name
        WHEN 'SYNTHETIC TEST DATA' THEN 'Referencia DEKOPEN'
        WHEN 'DEMO_60 SYNTHETIC FIXTURE' THEN 'Catálogo de demostración'
        ELSE manufacturer_name END,
    supplier_name = CASE supplier_name
        WHEN 'TEST-SUPPLIER' THEN 'Proveedor de referencia'
        WHEN 'DEMO-SUPPLIER' THEN 'Proveedor de referencia'
        ELSE supplier_name END
WHERE org_id IS NULL;

UPDATE public.cutting_profiles
SET name = CASE name WHEN 'DEMO_60 SYNTHETIC FIXTURE' THEN 'Catálogo de demostración' ELSE name END
WHERE org_id IS NULL;

COMMIT;
