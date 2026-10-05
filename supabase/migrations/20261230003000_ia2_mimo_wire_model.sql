-- IA2: la credencial vigente de MIMO habla con el endpoint
-- https://token-plan-sgp.xiaomimimo.com/v1, que sirve el modelo wire
-- `mimo-v2.6-pro`. El pin `primalabs-ai/MiMo-V2.6-Pro-RL` (20261203) es la
-- causa raíz IA1-1: este endpoint responde 400 a ese identificador y
-- api.primalabs.ai rechaza la clave — toda superficie IA caía con
-- proveedor_error. El pin vuelve al identificador que la credencial real
-- acepta; una migración futura repinará cuando el proveedor migre de verdad.
UPDATE public.ai_routes
SET provider_model = 'mimo-v2.6-pro'
WHERE provider = 'MIMO';
