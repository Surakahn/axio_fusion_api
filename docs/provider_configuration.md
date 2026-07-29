# Provider Configuration And Model Replicas

The standalone package requires Python 3.10 or newer. Install it in an
isolated virtual environment before using the console entrypoint; do not use a
system Python 3.8/3.9 interpreter or a distribution-managed `pip`:

Both CLI entry points check this requirement before parsing an operation or
opening a provider connection. An unsupported interpreter exits with code `2`
and cannot start a discovery, enrollment, or serving attempt.

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
axio-fusion-api-standalone --help
```

Axio accepts any number of remote HTTP(S) provider channels. Each channel is
described through environment variable *names*, never through copied endpoint
or credential values. Supported upstream input protocols are `chat`,
`responses`, `anthropic`, and `gemini`.

## Image Capability Isolation

Image models are registered beside text models but use a separate capability
contract. A name such as `gpt-image-*` is never enough to admit a model: the
profile must explicitly declare `model_kind: "image"` (or `"multimodal"`), an
audited image transport, its allowed operations, and a successful image
endpoint probe. Image profiles are excluded from the text pre-Fusion
candidate pool, Judge, Synthesizer, and text benchmark path.

The configuration shape is:

```json
{
  "model": "gpt-image-2",
  "model_kind": "image",
  "image_capabilities": {
    "status": "candidate",
    "transport": "images_api",
    "operations": ["generation", "editing"],
    "streaming": true,
    "max_input_images": 1
  },
  "image_probe_status": "not_run"
}
```

The checked-in example remains `candidate`/`not_run`; it cannot serve images
until an operator performs an endpoint-bound generation/edit probe and carries
the resulting `verified`/`passed` state into the private serving registry.
This prevents a model-list entry or a copied vendor claim from turning a text
endpoint into an image endpoint.

The `images_api` transport uses `/images/generations` and `/images/edits`. A
Responses-compatible image-generation tool may instead declare
`responses_image_generation`; it uses `/responses` with a native
`image_generation` tool and supports generation only. Editing is admitted only
for `images_api`, so a Responses declaration cannot accidentally send a
multipart edit request to a Responses endpoint.

The public image routes are deliberately outside the four text protocol
adapters:

- `POST /v1/images/generations` accepts the allow-listed OpenAI Images JSON
  fields and returns one image response with the requested Axio tier.
- `POST /v1/images/edits` accepts `multipart/form-data` with `image`, optional
  `mask`, and `prompt`; it enforces the admitted provider's input-image limit.

`stream: true` uses image-native SSE event names such as
`image_generation.partial_image` and `image_edit.completed`. Base64 image
data is returned only as the requested public image artifact; it is never
converted into text Fusion candidates or persisted in internal traces. The
same proxy policy, credential pool, same-model failover, and 90-second hard
provider ceiling apply to image requests.

Run the image capability control plane against the exact private registry. A
dry run never contacts a provider; live mode must be explicit and sends only
the fixed non-benchmark generation/edit controls declared by each profile:

```bash
axio-fusion-api-standalone \
  --registry <PRIVATE_IMAGE_CANDIDATE_REGISTRY.json> \
  image-probe --live --timeout 90 \
  --output <PRIVATE_WORK_DIR>/image_probe.private.json
```

The probe records only operation status, timing, stream framing, endpoint
hashes, and result-shape digests. `redact-image-probe` creates a hash-only
receipt offline. Promotion is a separate exact-cohort operation; it checks the
profile set, current endpoint binding, declared transport, and every declared
operation before writing a new private registry:

```bash
axio-fusion-api-standalone image-probe-bind \
  --registry-file <PRIVATE_IMAGE_CANDIDATE_REGISTRY.json> \
  --probe-file <PRIVATE_WORK_DIR>/image_probe.private.json \
  --output-registry <PRIVATE_IMAGE_VERIFIED_REGISTRY.json> \
  --output <SAFE_WORK_DIR>/image_probe_binding.safe.json
```

Partial, stale, failed, transient, or endpoint-mismatched evidence blocks
promotion and leaves the source registry unchanged. Image probe prompts and
source image bytes are never used for benchmark calibration or Fusion prompt
tuning.

## Reasoning Strength Transport

`FusionRequest.reasoning_effort` is Axio's protocol-neutral logical control.
It accepts only `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, and
`max`; invalid values are omitted. The gateway reads the native public shape
first, then accepts the other spelling only as a compatibility fallback:

- Chat Completions: top-level `reasoning_effort`.
- Responses: `reasoning: {"effort": "..."}`.

Axio does not pass a generic `extra_body`, configurable JSON path, or an
unknown vendor field upstream. A model must carry a model-level
`reasoning_transport` declaration before Axio can send a wire control:

```json
{
  "model": "channel-model-alias",
  "reasoning_transport": {
    "status": "verified",
    "transport": "responses_reasoning",
    "supported_efforts": ["low", "medium", "high"],
    "effort_map": {"xhigh": "high", "max": "high"}
  }
}
```

The supported transports are `chat_reasoning_effort` for a Chat Completions
model, `responses_reasoning` for a standard Responses `reasoning.effort`
object, and `responses_reasoning_effort` for a Responses-compatible gateway
that documents the top-level `reasoning_effort` spelling. The latter is a
provider-local compatibility variant, not an inferred default for every
Responses endpoint. `status` must be `verified`; `unknown`, `candidate`, and
`unsupported` omit the field.
An `effort_map` is optional and only permits an explicit non-escalating
downgrade to a declared supported level. For example, it can map `xhigh` to
`high` or `max` to `high`, but it cannot map `low` to `high`. The current
NVIDIA and TokenAPIs candidate examples use this safe map because their common
initial probe subset is `low`/`medium`/`high`; the map becomes active only
after that exact profile is verified.

For the current two-channel template, the request bodies are deliberately
different:

```jsonc
// NVIDIA Chat Completions
{"reasoning_effort": "high"}

// TokenAPIs Responses
{"reasoning": {"effort": "high"}}
```

Do not replace either with a provider-wide `extra_body` convention. The
checked-in template intentionally remains `candidate`, even though the current
private deployment has endpoint-bound live evidence for its configured
profiles, because a copied manifest may point at a different endpoint or model
alias. In particular, omitted NVIDIA `reasoning_effort` is not native `none`:
the NVIDIA reference documents a default of `medium` for reasoning-capable
models. Only a model-level verified declaration may promise a specific native
level; unverified or unsupported profiles omit the field and cannot be used to
claim that a caller's non-default level was enforced.

Promotion to `verified` requires a live, fixed, non-benchmark streaming
control request followed by one request per declared effort. Store only
hashes, status codes, timing, and stream-framing receipts. Do not promote on a
directory listing, a vendor claim, or a successful ordinary request alone; do
not send `reasoning.summary` unless a separate product requirement and
model-level verification justify retaining it.

Use the dedicated control-plane command against a private serving registry:

```bash
axio-fusion-api-standalone \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  reasoning-probe --live --timeout 20 \
  --output <PRIVATE_WORK_DIR>/provider_reasoning_probe.private.json
```

It probes only model-level `candidate` declarations. The command sends a
strict streamed request with no reasoning field, then repeats the same fixed
non-benchmark control request once per declared level using the exact upstream
wire shape. `redact-reasoning-probe` creates a hash-only evidence receipt from
an existing private artifact without making any network request. Dynamic
runtime enrollment and file-backed `enroll-providers` run this calibration by
default; it can be bounded with the corresponding `reasoning-probe-*` options
or explicitly disabled with `--no-reasoning-calibration`.

An explicit, non-transient parameterized 4xx after a successful control
request records that exact profile as `unsupported`. A timeout, 5xx, network
failure, rate limit, malformed stream, or failed control request is
indeterminate and leaves the profile at `candidate`; it must never be
converted into a global provider-level verdict.

When a completed enrollment's reasoning calibration must be carried into a
different private serving registry, use the endpoint-bound reconciliation
control plane rather than copying model rows or manually editing status:

```bash
axio-fusion-api-standalone reconcile-reasoning-transport \
  --source-registry <PRIVATE_PREFUSION_REGISTRY.json> \
  --calibration-registry <PRIVATE_ENROLLMENT_REGISTRY.json> \
  --reasoning-probe <PRIVATE_REASONING_PROBE.json> \
  --output-registry <NEW_PRIVATE_SERVING_REGISTRY.json> \
  --output <SAFE_WORK_DIR>/reasoning_transport_reconciliation.safe.json
```

This command performs no provider calls. It accepts only a complete probe
cohort whose hash-only endpoint, protocol, canonical-model, and transport
binding matches both registries. The source registry is never overwritten,
and the safe receipt contains hashes/counts only. A legacy probe without this
binding is intentionally rejected and must be rerun after a channel changes.
`calibrate-registry` also checks an endpoint-bound probe before it can update
a local reasoning status, but it is not a substitute for this full-cohort
cross-registry handoff.

For a Hermes Fusion route, the caller's explicit level is an upper bound for a
role's internal cognitive budget. Direct `axio-fast` cascades preserve the
caller level. Actual wire forwarding remains profile-specific, so an
unverified model receives no reasoning parameter even when a logical role
budget exists.

## Upstream Traffic Control

`traffic_control` is a closed, local scheduling contract for a provider
profile. It never changes the upstream request body and it stores neither an
endpoint nor a credential. It may be declared on a provider and overridden on
an individual model; the runtime normalizes only these fields:

```json
{
  "traffic_control": {
    "scope": "channel",
    "max_in_flight": 1,
    "min_request_interval_ms": 0,
    "post_rate_limit_min_request_interval_ms": 1000,
    "rate_limit_key_pool": "shared",
    "fallback_cooldown_ms": 5000,
    "max_cooldown_ms": 60000
  }
}
```

`scope: "profile"` applies to one physical provider/model profile. `scope:
"channel"` shares a gate across models that use the same provider endpoint
and credential environment, which is appropriate when a gateway applies a
single account-level quota. `max_in_flight: 0` is initially unconstrained;
after an observed `429`, that scope becomes serial unless an explicit finite
limit was configured. The post-limit interval remains active for the process
lifetime so a single successful retry cannot immediately recreate a burst.

`rate_limit_key_pool: "shared"` is the conservative default. A `429` stops
the current logical call from sweeping through the rest of its API-key pool;
the next request waits for a bounded `Retry-After` value, or the configured
fallback when the header is absent. `independent` is reserved for operators
who know each key has an independent quota. Every gate wait is charged to the
same per-turn 90-second deadline. If the wait cannot fit, the transport fails
with the closed `rate_limit_cooldown_exceeded` code instead of sending a late
request. Safe receipts retain only wait milliseconds, rate-limit event counts,
and whether a shared-pool short circuit occurred.

For a normal deployment, set `AXIO_FUSION_PROVIDER_CONFIG_FILE` to a JSON file
such as `config/provider_configs.example.json`. The file may contain provider
labels, environment variable names, and model aliases, but never copied endpoint
or credential values. `config/current_channels.example.json` is the non-secret
starting point for the currently configured Responses and Chat Completions
channels. The current manifest contains NVIDIA Chat Completions and TokenAPIs
Responses; optional CPA Plus and AISZ labels remain supported by the generic
loader but are not enabled in this manifest. The file intentionally contains
no endpoint value, API key, or discovered model id.

The CLI also accepts the manifest explicitly. Place the option before the
subcommand so the same channel schema is used by the serving process and
operator commands:

```bash
axio-fusion-api-standalone \
  --provider-config-file config/current_channels.example.json \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  serve --live
```

This option sets only the manifest path in the current process. Endpoint and
credential values continue to come from the manifest's environment-variable
references and are never copied into the registry or receipts.

The long-running CLI can perform the same process-local enrollment at startup:

```bash
axio-fusion-api-standalone \
  --provider-config-file config/current_channels.example.json \
  serve --host 127.0.0.1 --port 8789 --live --enroll \
  --enrollment-receipt-output <PRIVATE_WORK_DIR>/enrollment_receipt.safe.json
```

`--enroll` requires `--live`, cannot be combined with `--registry`, and serves
only profiles that pass the bounded text probe. Native tool calibration can be
disabled with `--no-tool-calibration` when a deployment does not expose tool
calling. Tool calibration is an independent operational stage and can be
bounded separately with `--enrollment-tool-probe-timeout`,
`--enrollment-tool-probe-max-models`, and
`--enrollment-tool-probe-max-models-per-provider`; unprobed models do not gain
native-tool eligibility from a text health response. `--discover` is a separate
discovery-only startup mode; it is useful for operator diagnostics but does not
prove model health. The optional receipt is hash/count-only and never contains
endpoint values, credentials, prompts, or provider outputs.

`AXIO_FUSION_PROVIDER_CONFIGS` and the legacy
`AXIO_FUSION_PROVIDERS_JSON` remain available for ephemeral deployments. File
configuration is read first; inline configuration is read afterward and can
override the same provider/model profile for a single process. The loader
accepts only valid environment-variable names in `base_url_env`, `api_key_env`,
and `models_env`, so a literal URL or API key cannot accidentally become part of
the configuration schema.

Run the network-free manifest check before enrollment or serving:

```bash
axio-fusion-api-standalone \
  --provider-config-file config/current_channels.example.json \
  provider-config-summary
```

The command reports only source validity, profile counts, protocol counts, and
hashes. It never calls `/models` and never prints endpoint values, credential
values, provider labels, or model aliases. Provider authentication defaults to
Bearer, with `x-api-key`, `x-goog-api-key`, `query`, and `none` available as
explicit `auth_scheme` values for compatible gateways. A channel using
`auth_scheme: none` may omit `api_key_env`; all other schemes require a
credential environment-variable reference. The no-auth option only disables
the outbound authentication header/query parameter; it does not permit an
unsafe URL or bypass provider transport, timeout, retry, or circuit policy.

For hosts that already receive channel credentials from a secret manager, the
same diagnostic contract is available without mutating process environment or
writing a private manifest to disk. A direct runtime manifest may contain a literal
`base_url` and one `api_key`/`api_keys` value because it is process-local; the
values are never copied to a safe profile or receipt:

```python
from axio_fusion_api import FusionEngine
from axio_fusion_api.server import create_http_server

engine = FusionEngine.from_runtime_channels(
    {
        "providers": [
            {
                "provider": "runtime-responses-channel",
                "api_format": "responses",
                "base_url": secret_manager.get("RESPONSES_BASE_URL"),
                "api_keys": secret_manager.get_many("RESPONSES_API_KEYS"),
                "models": ["provider-model-alias"],
            }
        ]
    },
    diagnostic_only=True,
)
server = create_http_server(engine=engine, live=True)
```

The static construction above is diagnostic-only. Production static model rows
must pass the pre-Fusion research and strict streaming admission through
`enroll_runtime_channels(..., require_prefusion=True)`, or be loaded from a
validated pre-Fusion private registry.

When the provider's model catalog response is the source of truth, the same
constructor can perform bounded discovery before serving. By default the
client requests `<base_url>/models`; a channel can override that with the
relative `models_endpoint`/`model_list_endpoint` field. Discovered profiles
remain process-local and should be passed through the normal enrollment/probe
workflow before being promoted to a formal benchmark registry:

```python
engine = FusionEngine.from_runtime_channels(
    runtime_manifest,
    secret_resolver=secret_manager.get,
    discover=True,
    live=True,
    discovery_timeout=15,
    diagnostic_only=True,
)
```

This is an inventory diagnostic only. `discover=True` cannot create a
production serving engine unless the caller explicitly sets
`diagnostic_only=True`; production model admission must use
`enroll_runtime_channels(..., require_prefusion=True)` (the default for a
non-diagnostic enrollment).

For a single-process gateway, `create_runtime_http_server(...)` combines the
same steps and accepts an arbitrary provider manifest directly. It supports all
four public API surfaces and keeps the endpoint/key values only in the
in-memory engine:

```python
server = create_runtime_http_server(
    runtime_manifest,
    discover=True,
    secret_resolver=secret_manager.get,
    live=True,
    diagnostic_only=True,
)
```

The gateway above is also diagnostic-only. A production dynamic gateway must
use `enroll=True`, which forces the pre-Fusion research ranking, strict SSE or
NDJSON observation, non-empty output hashing, and the 90-second latency gate.

For a live dynamic manifest, set `enroll=True` so discovery is followed by the
bounded text health probe and the optional native-tool probe. This prevents a
provider's `/models` inventory from being promoted to serving solely because
it was listed:

```python
server = create_runtime_http_server(
    runtime_manifest,
    enroll=True,
    secret_resolver=secret_manager.get,
    live=True,
    enrollment_max_workers=8,
    enrollment_calibrate_tools=True,
    enrollment_tool_probe_timeout=20,
    enrollment_tool_probe_max_models=24,
    enrollment_tool_probe_max_models_per_provider=8,
)
server.runtime_channel_enrollment_receipt  # safe counts/status/hashes only
```

The running server also exposes an atomic channel refresh operation. It runs a
complete discovery -> text probe -> optional native-tool probe enrollment in a
candidate engine, then swaps that candidate only after the registry readiness
gate and generation fence pass. A failed enrollment, an incomplete candidate,
or a concurrent generation change keeps the old engine serving:

```python
receipt = server.refresh_runtime_channels(
    next_manifest,
    expected_generation=server.runtime_engine_snapshot()["generation"],
    secret_resolver=secret_manager.get,
    live=True,
    enrollment_tool_probe_timeout=8,
    enrollment_tool_probe_max_models=6,
)
assert receipt["old_engine_preserved"] is not False
```

The refresh operation uses the client attached to the engine that is active at
the start of the refresh, rather than a stale client captured at server
construction. The candidate is never partially installed. Returned receipts
contain only generation state, counts, status codes, and hashes; endpoint
values, credentials, provider/model identifiers, prompts, and outputs remain
out of the receipt.

Direct process-local manifests also accept the common aliases `baseurl`,
`apikey`, `protocol`, `channel`, `model_id`, and `modelsEnv`. The canonical
names `base_url`, `api_key(s)`, `api_format`, `provider`, `model`, and
`models_env` are preferred for long-lived configuration. `models_env` may
point to a comma-, semicolon-, or newline-separated model list, or a secret
resolver may return a sequence of model ids. Static `models` rows and the
environment list are merged with stable first-seen ordering; a later row for
the same model overrides its earlier metadata. Aliases do not weaken URL,
authentication, or protocol validation.

Endpoint and credential resolution uses one explicit precedence order:
model-level direct value, model-level named secret, channel-level direct value,
then channel-level named secret. A model-scoped `base_url_env` or `api_key_env`
therefore cannot be shadowed by a channel-scoped literal default. Resolver
failures are normalized at the configuration boundary; secret-manager exception
messages, backend paths, environment names, and values are not copied into
public errors or safe receipts.

Model discovery is an optional control-plane operation, not a requirement for
building candidate inventory. For a provider such as native Anthropic Messages
that does not expose a compatible model catalog, declare static model rows and
set `discover_models: false`; production enrollment still probes those rows
through the same pre-Fusion gate:

```json
{
  "provider": "anthropic-channel",
  "api_format": "anthropic",
  "base_url_env": "AXIO_ANTHROPIC_BASE_URL",
  "api_key_env": "AXIO_ANTHROPIC_API_KEY",
  "discover_models": false,
  "models": ["claude-model-alias"]
}
```

For a custom catalog, use a relative path such as
`models_endpoint: "/catalog/models"`. Absolute URLs, query strings,
fragments, and parent-directory traversal are rejected. The configured API
authentication scheme is applied to both catalog discovery and model calls;
the API key is never accepted through the catalog URL itself.

The benchmark package also exposes
`run_runtime_benchmark_campaign(...)`. This is a diagnostic runner for an
in-memory engine: it uses fixed local cases, all selected Axio public API
surfaces, resumable hash-only run artifacts, and an explicit
`final_claims_allowed: false` contract. It must not be used to bypass the
formal registry, external top-three baseline freeze, or official harness
imports required by the final 21-suite claim.

For live admission without a persisted registry, use
`enroll_runtime_channels(...)`. In production, call it with
`require_prefusion=True` (or include a `prefusion` block in the runtime
manifest). It then performs `/models` discovery, the pre-Fusion research
ranking, and three independent real streamed text probes per physical profile
by default. Every sample must satisfy the 90-second hard ceiling before the
profile can enter the generated screening registry; a production count below
two is blocked and the count is bounded to five. Set
`prefusion.stream_probe_samples` in the manifest or pass
`prefusion_stream_probe_samples` to the runtime API when an explicit override
is required. Only then does the function return profile objects bound by the
generated screening registry.
Its `receipt.prefusion` projection contains only counts and hashes. Text
health success alone does not promote native tool support; the optional tool
probe runs only after pre-Fusion admission and must pass separately.

The runtime loader accepts all four upstream formats, model-level endpoint/key
overrides, multiple keys, and direct `/models` discovery through
`discover_runtime_profiles`. Direct values are held only by in-memory profiles;
`safe_dict()`, route receipts, traces, and registry artifacts exclude them.
The file-backed environment-variable manifest remains the recommended path for
the long-running CLI service because it cleanly separates deployment config
from secrets.

Provider manifests validate all four input protocol families strictly. The
accepted aliases resolve to `chat`, `responses`, `anthropic`, or `gemini`; an
unknown value such as `respones` rejects that provider row instead of silently
falling back to Chat Completions. This prevents a configuration typo from
directing credentials and prompts to an unintended endpoint.

Fusion outbound HTTP(S) traffic uses one explicit three-state policy. Set
`AXIO_FUSION_NETWORK_MODE=auto|on|off`; the default is `auto`. The default
system proxy is `AXIO_FUSION_SYSTEM_PROXY=http://127.0.0.1:10808`.

- `auto` performs a short TCP listener check. A listening proxy is selected;
  otherwise Fusion uses a no-proxy opener and connects directly.
- `on` requires a valid, listening proxy and fails closed with
  `proxy_unavailable` when it cannot be reached.
- `off` always uses a no-proxy opener, explicitly bypassing inherited
  `HTTP_PROXY`, `HTTPS_PROXY`, and `ALL_PROXY` values.

`AXIO_FUSION_HTTP_PROXY` remains a legacy custom-proxy override and
`AXIO_FUSION_USE_SYSTEM_PROXY=1` remains a legacy forced-on setting when the
new mode variable is absent. Only HTTP(S) proxy URLs without embedded
credentials, query strings, fragments, or non-root paths are accepted. Runtime
summaries expose only mode, listener state, transport, and reason codes; the
proxy URL is never persisted.

Provider transport has two bounded recovery layers. The transient transport
retry is controlled by `AXIO_FUSION_PROVIDER_MAX_ATTEMPTS_PER_KEY`. A separate
`AXIO_FUSION_PROVIDER_EMPTY_RESPONSE_RETRIES` setting handles an HTTP-success
response with neither visible text nor a native tool call; it defaults to one
retry and then becomes a semantic provider failure so the orchestrator can
select another same-model replica or a bounded fallback.

For the currently supplied two-channel portfolio, the non-secret manifest is
[`config/current_channels.example.json`](../config/current_channels.example.json)
and the environment contract is
[`config/current_channels.env.example`](../config/current_channels.env.example).
Once those environment variables are injected by the process supervisor, the
operator can run the complete enrollment sequence with one command:

```bash
axio-fusion-api-standalone enroll-providers \
  --config-file config/current_channels.example.json \
  --live \
  --output-dir <PRIVATE_WORK_DIR>/current_channel_enrollment
```

The command is generic: it supports any configured provider labels and any mix
of `chat`, `responses`, `anthropic`, and `gemini`. It performs live `/models`
discovery when a provider-level endpoint is configured, probes each candidate
with a fixed non-benchmark prompt, generates a probe-bound runtime registry,
runs the fixed native-tool probe, and applies only operational calibration. A
failed stage never marks a partial registry as the serving registry.

The manifest never contains a literal URL or key. A literal transport value in
`base_url_env` or `api_key_env` is rejected. This keeps arbitrary endpoints and
credentials usable without making them part of source control, process output,
trace receipts, or benchmark artifacts.

The configuration source is summarized only as hashes, source type, validity,
and counts in readiness receipts. Paths, environment variable names, provider
labels, model aliases, endpoint values, and credentials remain private.

When a custom manifest is present but contains no static model rows and its
`models_env` variables are empty, `load_registry()` returns an empty blocked
registry until `/models` discovery and probe-bound enrollment produces an
explicit runtime registry. It never falls back to the portable development
seed in this state. This prevents a newly configured deployment from silently
serving an unrelated stale model pool; a configured calibrated registry still
has precedence.

For a channel alias that is known to run the same real model as another
channel, configure the exact same `canonical_model_id` on both model rows:

```json
{
  "provider": "channel-a",
  "api_format": "responses",
  "base_url_env": "AXIO_CHANNEL_A_BASE_URL",
  "api_key_env": "AXIO_CHANNEL_A_API_KEY",
  "models": [
    {
      "model": "channel-a-alias",
      "canonical_model_id": "vendor-family-version"
    }
  ]
}
```

The canonical identifier is used in two deliberately separate ways:

- Serving uses it to keep duplicate channels out of the Fusion expert panel,
  choose healthy low-latency replicas, round-robin comparable replicas, and
  fail over to a same-model channel before using a different model.
- Scientific final-claim evaluation requires a separately attested canonical
  identity. A missing declaration may still serve through the normalized model
  alias, but it cannot satisfy the benchmark baseline-freeze contract.

For a channel whose `/models` endpoint is available, configure the provider
credentials by environment variable name and run the bounded discovery/probe
workflow. Once the operator has verified aliases, add model rows with
`canonical_model_id`; no probe, trace, public response, or safe artifact
persists raw endpoints, credentials, prompts, or provider outputs.

Native tool support has a separate operational calibration command. It sends a
fixed function declaration through the configured upstream protocol even when
the registry prior says `supports_tools: false`, then records only status,
latency, structural counts, and hashes. A successful text health probe alone
must never promote a model into the tool-worker pool:

```bash
axio-fusion-api-standalone \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  tool-probe --live --output <PRIVATE_TOOL_PROBE.json>

axio-fusion-api-standalone \
  --registry <PRIVATE_LIVE_REGISTRY.json> \
  calibrate-registry \
  --probe-file <PRIVATE_TEXT_PROBE.json> \
  --probe-file <PRIVATE_TOOL_PROBE.json> \
  --updated-registry-output <PRIVATE_CALIBRATED_REGISTRY.json>
```

The tool probe is an operational transport/capability check, not a benchmark
and not a source of benchmark labels or final model rankings.

Tool capability is represented independently from ordinary text health:
`tool_capability` is `proven`, `unproven`, or `failed`, while
`tool_probe_status` records whether this cohort was not selected, succeeded,
returned text only, or failed at transport/protocol parsing. `supports_tools`
is retained for compatibility and is true only for a successful operational
probe or an explicit external attestation. A bounded probe that does not select
a profile does not downgrade it; a failed probe does not erase an existing
external attestation. Tool-specialist routing requires the stronger
`tool_calling_eligible` state, so unproven and failed profiles cannot silently
enter the native-tool role.
