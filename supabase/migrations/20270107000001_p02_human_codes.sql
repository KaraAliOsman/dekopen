-- P02 — códigos humanos por organización: OC- órdenes de compra,
-- RT- retazos, REC- recepciones de compra.
--
-- El mecanismo es el mismo que recibos de pago (RC-), guías (GD-) y
-- facturas (FAC-): contador por org_id, serializado por advisory lock de
-- transacción, jamás reutilizado e inmutable una vez asignado. La
-- diferencia es que el contador vive en una función compartida para que
-- las tres superficies de escritura (órdenes de compra, retazos manuales y
-- producidos, recepciones) pasen por el mismo camino y pgTAP pueda
-- ejercitarlo.
--
-- Órdenes de compra ya emitidas conservan su folio PO-…: el código viaja
-- dentro del payload_json sellado y order_snapshot_hash lo firma.
-- Renumerarlas reescribiría evidencia emitida, así que el contador OC-
-- arranca después de las filas existentes (cuentan como folios ocupados).

CREATE OR REPLACE FUNCTION private.next_human_code(
    target_org UUID,
    kind TEXT
)
RETURNS TEXT
LANGUAGE plpgsql
AS $func$
DECLARE
    v_next BIGINT;
BEGIN
    -- Lock por (kind, org): dos transacciones del mismo scope se
    -- serializan aquí — la segunda cuenta la fila cometida por la
    -- primera. Un rollback libera el lock y no deja hueco en el folio.
    PERFORM pg_advisory_xact_lock(
        hashtextextended(kind || ':' || target_org::text, 0)
    );
    IF kind = 'orders' THEN
        -- Órdenes de compra: los folios OT- pertenecen al taller; el
        -- contador OC- cubre todo lo que sale hacia proveedor.
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.orders
        WHERE org_id = target_org AND order_type <> 'WORKSHOP_OT';
        RETURN 'OC-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'inventory_remnants' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.inventory_remnants
        WHERE org_id = target_org;
        RETURN 'RT-' || lpad(v_next::text, 6, '0');
    ELSIF kind = 'order_receipts' THEN
        SELECT COUNT(*) + 1 INTO v_next
        FROM public.order_receipts
        WHERE org_id = target_org;
        RETURN 'REC-' || lpad(v_next::text, 6, '0');
    END IF;
    RAISE EXCEPTION 'next_human_code: kind % desconocido', kind;
END
$func$;

-- Solo los roles de backend llaman la función: bajo `authenticated` la
-- política orders RLS escondería las órdenes de proveedor y el contador
-- OC- contaría mal en silencio. Un uso indebido debe fallar fuerte.
REVOKE ALL ON FUNCTION private.next_human_code(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION private.next_human_code(UUID, TEXT)
    TO documentary_backend, pricing_backend, service_role;

-- El folio no se reasigna jamás: el status machine sí toca la fila
-- (retazo AVAILABLE→RESERVED→CONSUMED) pero el código queda sellado.
CREATE FUNCTION private.guard_human_code()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = ''
AS $func$
DECLARE
    col TEXT := TG_ARGV[0];
BEGIN
    IF to_jsonb(NEW) ->> col IS DISTINCT FROM to_jsonb(OLD) ->> col THEN
        RAISE EXCEPTION 'human_code_immutable' USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$func$;
REVOKE ALL ON FUNCTION private.guard_human_code() FROM PUBLIC;

-- ── Retazos: folio RT-NNNNNN ─────────────────────────────────────────
ALTER TABLE public.inventory_remnants
    ADD COLUMN remnant_code VARCHAR(30);

WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY org_id ORDER BY created_at, id
           ) AS seq
    FROM public.inventory_remnants
)
UPDATE public.inventory_remnants remnant
SET remnant_code = 'RT-' || lpad(numbered.seq::text, 6, '0')
FROM numbered
WHERE remnant.id = numbered.id;

ALTER TABLE public.inventory_remnants
    ALTER COLUMN remnant_code SET NOT NULL;
ALTER TABLE public.inventory_remnants
    ADD CONSTRAINT inventory_remnants_code_format_chk
    CHECK (remnant_code ~ '^RT-[0-9]{6,}$');
ALTER TABLE public.inventory_remnants
    ADD CONSTRAINT uk_org_remnant_code UNIQUE (org_id, remnant_code);

CREATE TRIGGER inventory_remnants_code_immutable
BEFORE UPDATE ON public.inventory_remnants
FOR EACH ROW EXECUTE FUNCTION private.guard_human_code('remnant_code');

-- ── Recepciones de compra: folio REC-NNNNNN ──────────────────────────
ALTER TABLE public.order_receipts
    ADD COLUMN receipt_code VARCHAR(30);

WITH numbered AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY org_id ORDER BY created_at, id
           ) AS seq
    FROM public.order_receipts
)
UPDATE public.order_receipts receipt
SET receipt_code = 'REC-' || lpad(numbered.seq::text, 6, '0')
FROM numbered
WHERE receipt.id = numbered.id;

ALTER TABLE public.order_receipts
    ALTER COLUMN receipt_code SET NOT NULL;
ALTER TABLE public.order_receipts
    ADD CONSTRAINT order_receipts_code_format_chk
    CHECK (receipt_code ~ '^REC-[0-9]{6,}$');
ALTER TABLE public.order_receipts
    ADD CONSTRAINT uk_org_order_receipt_code UNIQUE (org_id, receipt_code);

CREATE TRIGGER order_receipts_code_immutable
BEFORE UPDATE ON public.order_receipts
FOR EACH ROW EXECUTE FUNCTION private.guard_human_code('receipt_code');
