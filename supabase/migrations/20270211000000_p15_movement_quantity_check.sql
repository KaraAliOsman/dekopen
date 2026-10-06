-- P15 (continuación) — regla de cantidad del libro de movimientos.
-- Vive en su propia migración: Postgres no deja usar 'MOVE' (enum nuevo en
-- 20270210000000) dentro de la misma transacción que lo creó (55P04).

ALTER TABLE public.inventory_movements
    DROP CONSTRAINT IF EXISTS inventory_movements_quantity_check;
ALTER TABLE public.inventory_movements
    ADD CONSTRAINT inventory_movements_quantity_check CHECK (
        -- Un movimiento de retazo no lleva cantidad: el retazo es la pieza,
        -- su largo/ancho ya vive en inventory_remnants. 'MOVE' es sólo de
        -- retazos — un item no se traslada con este tipo.
        (remnant_id IS NOT NULL AND quantity IS NULL)
        OR (item_id IS NOT NULL AND remnant_id IS NULL
            AND movement_type <> 'MOVE' AND quantity > 0)
    );
