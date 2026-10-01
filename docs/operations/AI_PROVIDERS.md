# AI providers

The gateway (`ai_routes`) binds each capability to `{provider, provider_model}`.
Routes are platform config — tenants only ever see `public_name`. `MOCK` is the
deterministic default and performs no network I/O.

## Transports

| Route `provider` | Transport | Wire |
| --- | --- | --- |
| `MOCK` | `MockProvider` | none — deterministic output |
| `MIMO`, `OPENAI`, `OPENROUTER`, `DEEPSEEK`, `QWEN` | `OpenAICompatibleProvider` | `POST {base}/chat/completions` |
| anything else | `HttpProvider` | `POST {base}/invoke` generic JSON |

`AI_GATEWAY_{P}_PROTOCOL=openai|http` overrides the registry either way.

## Env contract (per provider name)

```text
AI_GATEWAY_{P}_API_KEY    bearer token (required)
AI_GATEWAY_{P}_BASE_URL   https endpoint; e.g. https://api.primalabs.ai/v1
AI_GATEWAY_{P}_MODEL      optional — overrides the route's provider_model
AI_GATEWAY_{P}_PROTOCOL   optional — openai | http
AI_GATEWAY_{P}_TIMEOUT_S  optional — whole-request bound in s (default 60, 1-600)
```

`AI_GATEWAY_MOCK_ENABLED` gates the deterministic provider: `1` opts in
explicitly, `0` forces it off. Unset, MOCK serves only development (`DEBUG=1`)
and the test suite — a production stack with MOCK routes refuses
`ai_provider_mock_disabled` instead of answering with fabricated content.

The OpenAI transport takes two control options from the *server-owned*
`provider_options` channel (callers can never set them): `system` (system
prompt) and `json_output` (requests `response_format` JSON mode). Everything
in `input_payload` is serialized as the user message.

## Activate MiMo for design_assist

1. Set `AI_GATEWAY_MIMO_API_KEY` (the `sk-…` key from the Primalabs
   console) and `AI_GATEWAY_MIMO_BASE_URL=https://api.primalabs.ai/v1`.
   `AI_GATEWAY_MIMO_MODEL` stays unset so the route's own `provider_model`
   pin decides — migrations pin every capability to the wire name
   `primalabs-ai/MiMo-V2.6-Pro-RL`.

   **Existing deployments**: `AI_GATEWAY_{P}_MODEL` overrides the route pin,
   so a previously-set `AI_GATEWAY_MIMO_MODEL=mimo-v2.6-pro` must be
   REMOVED (or updated to the Primalabs name) when switching endpoints —
   otherwise requests keep sending the old model identifier and fail.
   After the change, verify a live capability round-trips (an
   `ai_provider_*` error means the override survived).
2. Capability routing stays explicit — a privileged operational statement
   when a capability needs a different model:

   ```sql
   UPDATE public.ai_routes
      SET provider = 'MIMO',
          provider_model = 'primalabs-ai/MiMo-V2.6-Pro-RL',
          prompt_version = 'design-assist-v2'
    WHERE capability = 'design_assist';
   ```

   Capability routing stays intentional: a route can bind a different
   model per capability (`provider_model` on that route's row, or
   `AI_GATEWAY_{P}_MODEL` as a deliberate deployment-wide override —
   never a leftover) without any product-code change.

3. Revert any time by restoring `provider = 'MOCK'`.

Every invocation still flows through the gateway's reconcile → entitlement +
balance check → sealed audit → wallet debit; a provider misconfiguration fails
closed (`ai_provider_unavailable`) before any debit.
