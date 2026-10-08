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
AI_GATEWAY_{P}_BASE_URL   https endpoint; e.g. https://token-plan-sgp.xiaomimimo.com/v1
AI_GATEWAY_{P}_MODEL      optional — overrides the route's provider_model
AI_GATEWAY_{P}_PROTOCOL   optional — openai | http
AI_GATEWAY_{P}_TIMEOUT_S  optional — whole-request bound in s (default 60, 1-600)
AI_GATEWAY_{P}_RETRIES    optional — retries on transient failures (default 2, 0-4)
```

Route columns `timeout_s` / `retry_max` override the env values per capability
(migration `20270106000000_ia3_provider_runtime.sql`). Only transient failures
retry — transport timeouts/connect errors, 5xx, 408/425 and 429 carrying
`Retry-After` — with bounded backoff (0.4·2ⁿ + jitter, capped 30 s, honors
Retry-After). Quota (bare 429), auth (401/403) and rejection (other 4xx) are
terminal: retrying a billed call can double-spend.

## Tool calling + strict-JSON fallback

Server callers pass OpenAI-shaped `tools`/`tool_choice` in `provider_options`
(never `input_payload`); the model answers `choices[0].message.tool_calls`,
which the gateway normalizes into `{id, name, arguments}` triples and the
agent executes server-side as audited query steps. `tools_enabled=false` on a
route strips the option server-side. If the endpoint rejects tool calling
(`ai_provider_rejected` on a request that carried tools), the provider retries
exactly once with `response_format={"type":"json_object"}` — the same document
contract without tools — and marks the result `tools_fallback`.

## Costs + budget

Every committed call writes `public.ai_audit_logs.est_cost_usd` (tokens ×
`ai_model_prices` — NULL when the model has no price row) and one row in
`public.ai_invocations` (content-free: capability, public model, tokens,
latency, credits, estimated USD, status). Failed and budget-blocked calls
write their row after the request's transaction rolls back, so the log is
complete even when the work wasn't.

`ai_org_settings.monthly_credit_budget` is the org's own ceiling in wallet
credits for the calendar month (NULL = no cap). Inside the wallet lock the
gateway checks `spent + credits > budget` and refuses `ai_budget_exceeded` —
a soft block the OWNER lifts in Settings › Inteligencia artificial (no plan
change). Activity for `/jobs` comes from `GET /api/v1/ai/activity/` (OWNER,
filterable by capability and status); per-job spend rides `ai.jobs.cost`.

## Development defaults

Local development should talk to the real provider — `.env` carries
`AI_GATEWAY_MIMO_API_KEY` + `AI_GATEWAY_MIMO_BASE_URL` and MOCK stays for tests
and the explicit "Modo de prueba" (`AI_GATEWAY_MOCK_ENABLED=1`). A local
`.env` that forces MOCK makes the whole UI silently deterministic — never
commit it; the flag belongs to the developer's shell only.

## MOCK safety

`AI_GATEWAY_MOCK_ENABLED` gates the deterministic provider: `1` opts in
explicitly, `0` forces it off. Unset, MOCK serves only development (`DEBUG=1`)
and the test suite — a production stack with MOCK routes refuses
`ai_provider_mock_disabled` instead of answering with fabricated content, and
DEBUG or a stray pytest process can never open it (test:
`test_mock_refused_in_production_without_explicit_flag`). When MOCK serves,
every member sees the "Modo de prueba" badge in the shell and the activity
panel marks each row `test`.

The OpenAI transport takes control options from the *server-owned*
`provider_options` channel (callers can never set them): `system` (system
prompt), `json_output` (requests `response_format` JSON mode), `tools`,
`tool_choice`, `extra_messages`. Everything in `input_payload` is serialized
as the user message.

## Activate MiMo

1. Set `AI_GATEWAY_MIMO_API_KEY` (the `tp-…` token-plan key — interactive
   dev/testing only; production needs a pay-as-you-go credential) and
   `AI_GATEWAY_MIMO_BASE_URL=https://token-plan-sgp.xiaomimimo.com/v1`.
   `AI_GATEWAY_MIMO_MODEL` stays unset so the route's own `provider_model`
   pin decides — migrations pin every capability to `mimo-v2.6-pro`.

   **Existing deployments**: `AI_GATEWAY_{P}_MODEL` overrides the route pin,
   so a leftover `AI_GATEWAY_MIMO_MODEL` must be REMOVED (or updated) when
   switching endpoints — otherwise requests keep sending the old model
   identifier and fail. After the change, use Settings › Inteligencia
   artificial › "Probar conexión" (an `ai_provider_*` error means the
   override or the quota is the problem).
2. Capability routing stays explicit — a privileged operational statement
   when a capability needs a different model:

   ```sql
   UPDATE public.ai_routes
      SET provider = 'MIMO',
          provider_model = 'mimo-v2.6-pro',
          prompt_version = 'design-assist-v2'
    WHERE capability = 'design_assist';
   ```

   Capability routing stays intentional: a route can bind a different
   model per capability (`provider_model` on that route's row, or
   `AI_GATEWAY_{P}_MODEL` as a deliberate deployment-wide override —
   never a leftover) without any product-code change.

3. Revert any time by restoring `provider = 'MOCK'`.

Every invocation still flows through the gateway's reconcile → entitlement +
balance + monthly-budget check → sealed audit → wallet debit; a provider
misconfiguration fails closed (`ai_provider_unavailable`) before any debit.
