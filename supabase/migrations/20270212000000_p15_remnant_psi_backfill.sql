-- P15 — retazos con identidad física resoluble desde su autoridad de compra.
-- Los retazos BAR escritos antes de guardar psi sólo conocen
-- stock_authority_id; la identidad física canónica vive en la autoridad
-- (profile_purchase_mappings / reinforcement_articles). Backfill para que el
-- pool de cobertura y las ofertas "usar retazo" los vean.
UPDATE public.inventory_remnants r
SET physical_stock_identity = a.physical_stock_identity
FROM (
    SELECT id, physical_stock_identity
      FROM public.profile_purchase_mappings
    UNION ALL
    SELECT id, physical_stock_identity
      FROM public.reinforcement_articles
) a
WHERE r.stock_authority_id = a.id
  AND r.physical_stock_identity IS NULL
  AND a.physical_stock_identity IS NOT NULL;
