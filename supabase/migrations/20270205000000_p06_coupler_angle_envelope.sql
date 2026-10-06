-- P06 — Bow/bay y conjuntos acoplados: compatibilidad ángulo ↔ acoplador
-- desde el catálogo (autoridad, no código).
--
-- Un cople declara la envolvente de deflexiones que admite sobre la magnitud
-- del ángulo de la unión (|angle_deg|): un mismo perfil sirve la unión
-- +45° o −45° montado en espejo, así que el rango se compara sobre el
-- absoluto. NULL en ambos = el catálogo no declaró envolvente — estado
-- UNKNOWN de primer orden: el artículo sigue existiendo y ofreciéndose,
-- pero ni el motor ni el editor pueden verificarlo.
--
-- Solo aplica a role='COUPLER'; el CHECK obliga el par completo o nulo.

BEGIN;

ALTER TABLE public.profile_articles
    ADD COLUMN coupler_angle_min_deg NUMERIC(5,1) NULL,
    ADD COLUMN coupler_angle_max_deg NUMERIC(5,1) NULL;

ALTER TABLE public.profile_articles
    ADD CONSTRAINT profile_articles_coupler_angle_envelope
    CHECK (
        (coupler_angle_min_deg IS NULL) = (coupler_angle_max_deg IS NULL)
        AND (
            coupler_angle_min_deg IS NULL
            OR (coupler_angle_min_deg >= 0 AND coupler_angle_max_deg <= 180
                AND coupler_angle_min_deg <= coupler_angle_max_deg)
        )
    );

COMMENT ON COLUMN public.profile_articles.coupler_angle_min_deg IS
    'P06: deflexión mínima admisible de la unión en grados, sobre |angle_deg|. NULL = sin declarar.';
COMMENT ON COLUMN public.profile_articles.coupler_angle_max_deg IS
    'P06: deflexión máxima admisible de la unión en grados, sobre |angle_deg|. NULL = sin declarar.';

-- Envolventes del catálogo DEMO — datos de catálogo sintético, no valores de
-- ingeniería. La regla: coples "angulares" cubren una banda variable, coples
-- de escuadra cubren la zona de 90°, canales estructurales solo el plano.
UPDATE public.profile_articles SET
    coupler_angle_min_deg = 0.0, coupler_angle_max_deg = 60.0
    WHERE sku = 'COPLE-60' AND role = 'COUPLER';
UPDATE public.profile_articles SET
    coupler_angle_min_deg = 60.0, coupler_angle_max_deg = 120.0
    WHERE sku = 'COPLE-90' AND role = 'COUPLER';
UPDATE public.profile_articles SET
    coupler_angle_min_deg = 0.0, coupler_angle_max_deg = 0.0
    WHERE sku = 'CANAL-U' AND role = 'COUPLER';
UPDATE public.profile_articles SET
    coupler_angle_min_deg = 0.0, coupler_angle_max_deg = 30.0
    WHERE sku IN ('COPLE-A-30', 'COPLE-G-30') AND role = 'COUPLER';
UPDATE public.profile_articles SET
    coupler_angle_min_deg = 85.0, coupler_angle_max_deg = 95.0
    WHERE sku IN ('COPLE-A-90', 'COPLE-G-90') AND role = 'COUPLER';
UPDATE public.profile_articles SET
    coupler_angle_min_deg = 0.0, coupler_angle_max_deg = 0.0
    WHERE sku IN ('COPLE-CORR', 'REMATE-G', 'CANAL-A-U', 'CANAL-G-U') AND role = 'COUPLER';

COMMIT;
