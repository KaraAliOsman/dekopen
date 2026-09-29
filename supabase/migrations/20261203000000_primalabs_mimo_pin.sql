-- Wire-model pin: the provider account moved to Primalabs. Their OpenAI-
-- compatible endpoint names the model `primalabs-ai/MiMo-V2.6-Pro-RL`; every
-- MIMO route's provider_model must send that identifier (the API key and
-- base URL stay deployment env config, never catalog data).
UPDATE public.ai_routes
SET provider_model = 'primalabs-ai/MiMo-V2.6-Pro-RL'
WHERE provider = 'MIMO';
