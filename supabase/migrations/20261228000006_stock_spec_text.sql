-- §08 mandate follow-up: inventory search must reach the received
-- specification, not just sku/name. The full specification is already stored
-- on inventory_items.attributes at receipt time; projecting it onto the
-- derived stock view lets list_stock hand a searchable spec_text to the UI
-- without duplicating the canonical hash logic.

CREATE OR REPLACE VIEW public.inventory_stock
    WITH (security_invoker = true) AS
SELECT
    item.id AS item_id,
    item.org_id,
    item.sku,
    item.name,
    item.category,
    item.unit,
    item.variant_key,
    COALESCE(SUM(CASE
        WHEN movement.movement_type IN ('RECEIPT', 'RETURN', 'ADJUSTMENT')
            THEN movement.quantity
        WHEN movement.movement_type IN ('CONSUMPTION', 'SCRAP')
            THEN -movement.quantity
        ELSE 0
    END), 0)::NUMERIC(14, 2) AS on_hand_qty,
    COALESCE(SUM(CASE
        WHEN movement.movement_type = 'RESERVATION' THEN movement.quantity
        WHEN movement.movement_type IN ('RELEASE', 'CONSUMPTION')
            THEN -movement.quantity
        ELSE 0
    END), 0)::NUMERIC(14, 2) AS reserved_qty,
    item.attributes
FROM public.inventory_items item
LEFT JOIN public.inventory_movements movement
    ON movement.item_id = item.id
GROUP BY item.id, item.org_id, item.sku, item.name,
    item.category, item.unit, item.variant_key, item.attributes;
