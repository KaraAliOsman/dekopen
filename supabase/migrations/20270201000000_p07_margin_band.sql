-- P07 — banda de margen por organización.
--
-- El workspace de precios compara el margen realizado contra una banda
-- declarada por el dueño: mínimo (bajo el cual un estimador no aplica
-- directo — pide aprobación), objetivo (default_margin_pct, ya existente)
-- y máximo. Decisión registrada en docs/decisions/valores-por-defecto.md:
-- mínimo 25 % (§11), máximo 60 % (techo operativo — sobre él también se
-- requiere confirmación del dueño).
--
-- La banda vive en pricing_rules (fila única por org, la misma autoridad
-- de merma/MO/IVA) y hereda su RLS + auditoría; el dominio numérico se
-- redeclara incluyendo las dos columnas nuevas.

ALTER TABLE public.pricing_rules
  ADD COLUMN margin_min_pct NUMERIC(6,4) NOT NULL DEFAULT 0.2500,
  ADD COLUMN margin_max_pct NUMERIC(6,4) NOT NULL DEFAULT 0.6000;

ALTER TABLE public.pricing_rules DROP CONSTRAINT pricing_rules_numeric_domain;
ALTER TABLE public.pricing_rules ADD CONSTRAINT pricing_rules_numeric_domain CHECK(
  default_margin_pct>=0 AND default_margin_pct<1 AND tax_rate_pct>=0 AND tax_rate_pct<=1
  AND waste_factor_pct=0.08 AND labor_rate_per_m2>=0 AND installation_rate_per_m2>=0
  AND labor_rate_per_m2<'Infinity'::numeric AND installation_rate_per_m2<'Infinity'::numeric
  AND margin_min_pct>=0 AND margin_min_pct<1
  AND margin_max_pct>margin_min_pct AND margin_max_pct<=1);
