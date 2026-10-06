-- P15 — Compras / Inventario / Retazos.
-- 1. Recepción registra la guía del proveedor y su fecha — la evidencia de
--    qué llegó de afuera vive en el encabezado de la recepción.
-- 2. El libro de movimientos aprende a hablar de retazos: el retazo es
--    material real, así que moverlo de rack o desecharlo deja huella con
--    actor y documento como cualquier item. Los movimientos de retazo no
--    llevan cantidad (el retazo es una pieza única) — 'MOVE' nace para eso.
-- 3. La propuesta de compra por proveedor declara precio unitario por línea:
--    purchase_allocations lo guarda y el lote sellado lo congela dentro del
--    snapshot de cada línea de la OC — el monto de la orden se deriva.
-- 4. Los días para la alerta de retazos viejos son decisión del taller,
--    configurable en Ajustes (ver docs/decisions/valores-por-defecto.md).
-- 5. El correo al proveedor se encola por el mismo outbox que el correo al
--    cliente — audiencia 'SUPPLIER'.

ALTER TYPE public.inventory_movement_type ADD VALUE IF NOT EXISTS 'MOVE';

ALTER TABLE public.order_receipts
    ADD COLUMN supplier_delivery_ref VARCHAR(100),
    ADD COLUMN supplier_delivery_date DATE;

ALTER TABLE public.inventory_movements
    ALTER COLUMN item_id DROP NOT NULL,
    ALTER COLUMN quantity DROP NOT NULL,
    ADD COLUMN remnant_id UUID
        REFERENCES public.inventory_remnants(id) ON DELETE RESTRICT;

ALTER TABLE public.inventory_movements
    DROP CONSTRAINT IF EXISTS inventory_movements_quantity_check;
-- La regla de cantidad vive en 20270211000000: Postgres no permite usar
-- 'MOVE' dentro de la misma transacción que lo creó como valor del enum.
-- Todo movimiento describe exactamente un sujeto: un item de stock o un
-- retazo — nunca ambos, nunca ninguno.
ALTER TABLE public.inventory_movements
    ADD CONSTRAINT inventory_movements_subject_check CHECK (
        num_nonnulls(item_id, remnant_id) = 1
    );

-- El guard de org hereda la nueva realidad: el sujeto del movimiento puede
-- ser un retazo — la verificación de org apunta a inventory_remnants.
CREATE OR REPLACE FUNCTION private.guard_inventory_org()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
    receipt_org UUID;
BEGIN
    IF TG_TABLE_NAME = 'order_receipts' THEN
        IF NOT EXISTS (
            SELECT 1 FROM public.orders
            WHERE id = NEW.order_id AND org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'order_receipt_lines' THEN
        SELECT org_id INTO receipt_org
        FROM public.order_receipts WHERE id = NEW.receipt_id;
        IF receipt_org IS NULL OR NOT EXISTS (
            SELECT 1 FROM public.order_requirement_lines
            WHERE id = NEW.order_line_id AND org_id = receipt_org
        ) THEN
            RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
        END IF;
    ELSIF TG_TABLE_NAME = 'inventory_movements' THEN
        IF NEW.remnant_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM public.inventory_remnants
                WHERE id = NEW.remnant_id AND org_id = NEW.org_id
            ) THEN
                RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
            END IF;
        ELSIF NOT EXISTS (
            SELECT 1 FROM public.inventory_items
            WHERE id = NEW.item_id AND org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
        END IF;
        IF NEW.order_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.orders
            WHERE id = NEW.order_id AND org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
        END IF;
        IF NEW.order_line_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.order_requirement_lines
            WHERE id = NEW.order_line_id AND org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
        END IF;
        IF NEW.receipt_line_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM public.order_receipt_lines line_
            JOIN public.order_receipts receipt ON receipt.id = line_.receipt_id
            WHERE line_.id = NEW.receipt_line_id AND receipt.org_id = NEW.org_id
        ) THEN
            RAISE EXCEPTION 'inventory_org_mismatch' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$function$;

ALTER TABLE public.purchase_allocations
    ADD COLUMN unit_price NUMERIC(14, 4)
        CHECK (unit_price IS NULL OR unit_price >= 0);

ALTER TABLE public.tenancy_organizations
    ADD COLUMN remnant_alert_days INTEGER NOT NULL DEFAULT 30
        CHECK (remnant_alert_days BETWEEN 1 AND 365);

ALTER TABLE public.mail_messages
    DROP CONSTRAINT mail_messages_audience_check;
ALTER TABLE public.mail_messages
    ADD CONSTRAINT mail_messages_audience_check
        CHECK (audience IN ('CLIENT', 'INTERNAL', 'SUPPLIER'));

-- El movimiento ganó una columna: el INSERT/SELECT de tabla ya cubre las
-- columnas nuevas para authenticated y documentary_backend, sin grants extra.
-- order_receipts igual (GRANT SELECT, INSERT a nivel tabla) y
-- purchase_allocations tiene GRANT de tabla a documentary_backend.
-- tenancy_organizations es column-grant: el ajuste se escribe por la misma
-- vía de branding (policy tenancy_organizations_branding_update, OWNER/ESTIMATOR).
GRANT UPDATE (remnant_alert_days, updated_at)
    ON public.tenancy_organizations TO documentary_backend;
