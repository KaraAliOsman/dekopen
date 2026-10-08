-- P07 — cobertura de SKU: el rol de servicio pricing_backend compone la lista
-- de cobertura leyendo las identidades de compra del catálogo
-- (repository.admin_list('coverage')). El defecto encontrado en QA:
--   * sin GRANT SELECT → 42501 y la API responde 409;
--   * sin política "TO pricing_backend" → filas vacías silenciosas: una
--     política "TO authenticated" no cubre al rol NOBYPASSRLS.
-- profile_articles y hardware_kits ya alcanzan al rol: shot_08 les otorgó
-- GRANT SELECT y sus políticas de lectura no declaran TO (son PUBLIC).

GRANT SELECT ON
    public.glass_purchase_mappings,
    public.panel_purchase_authorities,
    public.hardware_purchase_mappings,
    public.fitting_purchase_mappings
TO pricing_backend;

-- Las políticas replican la semántica de lectura del catálogo por tabla:
-- filas globales (org_id IS NULL, del sistema global) + filas de las
-- organizaciones del usuario. La restricción de rol la aplica el servicio.
CREATE POLICY profile_purchase_mappings_pricing_read
ON public.profile_purchase_mappings FOR SELECT TO pricing_backend
USING (
    auth.uid() IS NOT NULL
    AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids()))
);

CREATE POLICY reinforcement_articles_pricing_read
ON public.reinforcement_articles FOR SELECT TO pricing_backend
USING (
    auth.uid() IS NOT NULL
    AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids()))
);

CREATE POLICY infill_articles_pricing_read
ON public.infill_articles FOR SELECT TO pricing_backend
USING (
    (
        auth.uid() IS NOT NULL
        AND org_id IS NULL
        AND system_id IN (
            SELECT system.id FROM public.profile_systems AS system
            WHERE system.is_global = TRUE
        )
    )
    OR org_id IN (SELECT private.current_user_org_ids())
);

CREATE POLICY glass_purchase_mappings_pricing_read
ON public.glass_purchase_mappings FOR SELECT TO pricing_backend
USING (
    auth.uid() IS NOT NULL
    AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids()))
);

CREATE POLICY panel_purchase_authorities_pricing_read
ON public.panel_purchase_authorities FOR SELECT TO pricing_backend
USING (
    auth.uid() IS NOT NULL
    AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids()))
);

CREATE POLICY hardware_purchase_mappings_pricing_read
ON public.hardware_purchase_mappings FOR SELECT TO pricing_backend
USING (
    auth.uid() IS NOT NULL
    AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids()))
);

CREATE POLICY fitting_purchase_mappings_pricing_read
ON public.fitting_purchase_mappings FOR SELECT TO pricing_backend
USING (
    auth.uid() IS NOT NULL
    AND (org_id IS NULL OR org_id IN (SELECT private.current_user_org_ids()))
);
