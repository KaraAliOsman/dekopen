-- P11 cobranza: vencimiento del link de pago, estado SII "aceptado con
-- reparos" y ruta IA del recordatorio de cobranza.

-- Vencimiento: un link PENDING caducado no puede quedar bloqueando un cobro
-- nuevo para siempre; el TTL de referencia es 72 h (docs/decisions).
ALTER TABLE public.project_payment_links
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

UPDATE public.project_payment_links
SET expires_at = created_at + INTERVAL '72 hours'
WHERE expires_at IS NULL
  AND status IN ('DISPATCHING', 'PENDING', 'UNCERTAIN');

CREATE INDEX IF NOT EXISTS project_payment_links_expiry_idx
    ON public.project_payment_links (org_id, project_id)
    WHERE status IN ('DISPATCHING', 'PENDING', 'UNCERTAIN');

-- "Aceptado con reparos" es un veredicto real del SII distinto de aceptado:
-- el documento timbró pero la liquidación trae observaciones que el dueño
-- debe ver como propio estado, no escondidas dentro de PENDING/ACCEPTED.
ALTER TABLE public.sii_envios
    DROP CONSTRAINT IF EXISTS sii_envios_status_check;
ALTER TABLE public.sii_envios
    ADD CONSTRAINT sii_envios_status_check
    CHECK (status IN ('PENDING', 'ACCEPTED', 'OBSERVED', 'REJECTED'));

-- Ruta IA del recordatorio de cobranza: como toda ruta del gateway queda
-- anclada al modelo cableado de la casa (MIMO/mimo-v2.6-pro — regla pgTAP
-- de 126_ai_gateway); un proveedor distinto se activa después
-- actualizando la ruta, nunca cambiando código.
INSERT INTO public.ai_routes
    (capability, public_name, provider, provider_model, prompt_version, credits_cost)
VALUES
    ('collection_reminder', 'DEKOPEN Cobranza™', 'MIMO', 'mimo-v2.6-pro', 'v1.0', 2)
ON CONFLICT (capability) DO NOTHING;

-- El resumen de cobranza y la cola de Hoy leen ai_audit_logs para saber si
-- ya existe un borrador de recordatorio. Mismo patrón que billing/pricing:
-- GRANT SELECT al rol documental + EXECUTE en documentary_role; la política
-- ai_audit_logs_select (TO public) sigue filtrando por org y rol.
GRANT SELECT ON public.ai_audit_logs TO documentary_backend;
GRANT EXECUTE ON FUNCTION private.documentary_role(UUID, TEXT[])
    TO documentary_backend;
