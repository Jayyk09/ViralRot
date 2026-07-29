# Grok API contract for search-grounded structured generation

**Status:** AFK research; no application code changed
**Date verified:** 2026-07-29
**Scope:** xAI text generation for (a) structured Peter/Stewie dialogue and (b) a structured, post-narration visual plan. Only first-party xAI documentation and the published xAI OpenAPI specification are used.

Labels used below:

- **[Documented]** — stated by an official xAI guide or specification.
- **[Recommendation]** — proposed application behavior, not an xAI guarantee.
- **[Unknown]** — not settled by the official material.
- **[Conflict]** — current official sources disagree.

## Executive answer

1. **Use `POST https://api.x.ai/v1/responses`, not legacy Chat Completions.** xAI calls Responses the preferred API; it is the native surface for server-side Web Search and X Search, state, structured output with tools, and detailed usage. [`grok-4.5` currently supports structured outputs, function calling, and reasoning, with a 500,000-token context window.][model-45] Structured output combined with tools is documented only for supported Grok 4-family models. [Documented; [Responses comparison][comparison], [Structured Outputs][structured]]
2. **Conditional research:** supply `tools: [{"type":"web_search"},{"type":"x_search"}]` and use or omit `tool_choice: "auto"`. The model may use neither, either, or both. [Documented; [Tools overview][tools], [OpenAPI][openapi]]
3. **Guaranteed attempt at X Search:** supply **only** `{"type":"x_search"}` and set `tool_choice: "required"`. `required` guarantees at least one enabled tool is selected; with X Search as the only enabled tool, that selection must be X Search. It does **not** guarantee a successful search result. [Documented consequence; [OpenAPI][openapi], [Tool usage][tool-usage]]
4. **There is no documented modern-tool setting that means “X Search is required, while Web Search remains optional” in one request.** With both tools and `tool_choice: "required"`, only *some* tool is required. The documented specific-tool object applies to custom functions, not built-in `x_search`. [Unknown; [Function calling / Tool Choice][function-calling], [OpenAPI][openapi]]
5. **Structured search-grounded output is supported.** On Responses, put the JSON Schema at `text.format` with `type: "json_schema"`; do not use the Chat Completions `response_format` envelope. Supported schema constructs are grammar-constrained, but semantic facts and several JSON Schema keywords remain best-effort. [Documented; [Structured Outputs][structured]]
6. **Cap output with `max_output_tokens`, but budget for reasoning.** The limit includes visible output **and reasoning tokens** and defaults to 128,000 if omitted. A too-small cap can return `status: "incomplete"` with `incomplete_details.reason: "max_output_tokens"`, leaving no usable complete plan/dialogue. [Documented; [REST reference][rest], [OpenAPI][openapi]]
7. **Tool calls have a turn limit, not a precise call-count limit.** `max_turns` caps agentic assistant/tool turns; one turn may make multiple calls in parallel. The undisclosed server global cap applies when omitted. `parallel_tool_calls: false` prevents parallel calls but does not document a total-call cap. [Documented; [Tool usage][tool-usage]]
8. **For machine JSON, opt out of inline citation Markdown** with `include: ["no_inline_citations"]`. Responses enables inline citations by default; disabling them leaves source annotations potentially available out of band. Capture those annotations/citation URLs immediately. [Recommendation based on documented behavior; [Citations][citations]]
9. **`store: false` prevents later server retrieval/state continuation, not generation.** xAI does not document a citation exception for non-stored responses. Because a non-stored response cannot be fetched later, persist the parsed result, raw output, annotations/citations, usage, model, and response ID in the application at receipt time. [Documented + recommendation; [Generate Text][generate], [Citations][citations]]
10. **Concurrency is allowed but bounded by per-model RPS and TPM, not by a separately published text-request concurrency number.** Current Tier-0 `grok-4.5` limits are 150 RPS and 50,000,000 TPM, but the team Console is authoritative. All prompt, completion, reasoning, and cached prompt tokens count toward TPM. [Documented; [Rate Limits][rate], [Async Requests][async]]

## 1. Current capability and endpoint

### 1.1 Recommended surface

**[Documented]** The Responses API supports:

- text/image input and typed output items;
- built-in server-side tools including Web Search and X Search;
- structured output together with server-side tools on supported Grok 4-family models;
- optional state via `previous_response_id` and `store`;
- streaming; and
- usage/cost/tool counters.
Sources: [Responses vs Chat Completions][comparison], [Tools overview][tools], [Structured Outputs with Tools][structured-tools], [REST reference][rest].

**[Documented]** Chat Completions is deprecated for this use case and its `tools` field is described as custom functions only. It has a separate older `search_parameters` surface, but new agentic capabilities are delivered to Responses first. Source: [Responses comparison][comparison], [REST reference][rest].

### 1.2 Model

**[Documented]** `grok-4.5` currently advertises:

- text and image input to text output;
- 500,000-token context;
- structured outputs: yes;
- function calling: yes;
- reasoning: yes;
- aliases `grok-4.5-latest` and `grok-build-latest`;
- Tier-0 150 RPS / 50,000,000 TPM on the public model page.
Source: [`grok-4.5` model card][model-45].

**[Recommendation]** Use `grok-4.5` and record the actual `response.model`. Run a provider contract fixture whenever an alias changes. A moving alias is useful for capability access but is not a reproducibility guarantee.

**[Documented]** Grok 4.5's training knowledge cutoff is 2026-02-01; real-time information requires search tools. Source: [Models][models].

## 2. Exact Responses request contract

The stable common envelope is:

```json
{
  "model": "grok-4.5",
  "instructions": "<system/developer instructions>",
  "input": [
    {"role": "user", "content": "<task and source material>"}
  ],
  "tools": [],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "max_turns": 4,
  "max_output_tokens": 8000,
  "include": ["no_inline_citations"],
  "store": false,
  "text": {
    "format": {
      "type": "json_schema",
      "name": "<schema_name>",
      "strict": true,
      "schema": {"type": "object", "properties": {}, "required": []}
    }
  }
}
```

**[Documented]** `input` is required. The OpenAPI specification describes `model`, `instructions`, `tools`, `tool_choice`, `parallel_tool_calls`, `max_turns`, `max_output_tokens`, `include`, `store`, and `text.format`. `store` defaults to true, `parallel_tool_calls` defaults to true, and `max_output_tokens` defaults to 128,000. Sources: [OpenAPI specification][openapi], [REST reference][rest].

**[Recommendation]** Set every behaviorally important default explicitly. The numerical values above are placeholders to tune through tests, not xAI recommendations.

### 2.1 Conditional X + web research

```json
{
  "tools": [
    {"type": "web_search"},
    {"type": "x_search"}
  ],
  "tool_choice": "auto"
}
```

**[Documented]** `auto` is the default when tools are present. It lets Grok answer directly or call one or more tools. Supplying both tools allows autonomous orchestration; it does not require either source. Sources: [Advanced Tool Usage][advanced-tools], [OpenAPI][openapi].

**[Recommendation]** Use this only when the product genuinely allows an unsearched answer. Do not infer that search occurred from the prompt or from having listed tools; inspect usage/output (§6).

### 2.2 Force an X Search attempt

```json
{
  "tools": [
    {"type": "x_search"}
  ],
  "tool_choice": "required"
}
```

**[Documented]** `required` means the model must select one or more tools. With X Search as the sole tool, this forces an X Search attempt. Sources: [Function calling / Tool Choice][function-calling], [OpenAPI][openapi].

**[Documented]** An attempt can still fail because of a deleted X post, malformed tool arguments, network/service trouble, or another execution error. Failed attempts are present among attempted tool calls but absent from successful, billable server-side usage. Source: [Tool Usage Details][tool-usage].

**[Recommendation]** Treat “forced X” as satisfied only if the completed response reports `usage.server_side_tool_usage_details.x_search_calls >= 1` (or the xAI SDK's successful `server_side_tool_usage` contains X Search). Otherwise fail or retry according to product policy; do not silently label the result X-grounded.

### 2.3 X required while web remains optional

**[Unknown]** The official modern-tool contract does not document a built-in-tool selector such as `{"type":"x_search"}` for `tool_choice`. Its specific-tool form is described only for a named custom function. Therefore:

```json
{
  "tools": [
    {"type": "x_search"},
    {"type": "web_search"}
  ],
  "tool_choice": "required"
}
```

requires at least one tool, **not X specifically and not both**.

**[Recommendation]** If X is a hard requirement, choose one of these explicit product designs:

1. one request with only forced X Search; or
2. a first forced-X research request followed by a structured synthesis request that may additionally use Web Search.

A two-request design changes cost, latency, citation handling, and grounding transfer, so it should be an intentional architecture decision rather than hidden SDK behavior.

### 2.4 Disable search

Use no search tools, or set `tool_choice: "none"`. `none` makes the model ignore supplied tools. [Documented; [OpenAPI][openapi]]

### 2.5 Alternate `search_parameters` surface

**[Documented]** The current OpenAPI schema also exposes this separate surface:

```json
{
  "search_parameters": {
    "mode": "auto",
    "from_date": "2026-07-01",
    "to_date": "2026-07-29",
    "max_search_results": 15,
    "return_citations": true,
    "sources": [
      {"type": "x", "included_x_handles": ["xai"]},
      {"type": "web", "allowed_websites": ["x.ai"]}
    ]
  }
}
```

Its specified controls are:

- `mode`: `off`, `auto`, or `on`;
- `max_search_results`: 1–30, specified default 15;
- global `from_date` / `to_date` in `YYYY-MM-DD`;
- `return_citations`;
- source objects for `x`, `web`, `news`, or `rss`.
Source: [OpenAPI][openapi].

**[Conflict]** The OpenAPI property's machine default for `mode` is `"auto"`, while its prose calls `"on"` the default in one sentence. The current Web/X Search guides teach the `tools` surface instead. The spec says `search_parameters` takes precedence over `web_search_preview`, but does not define how it composes with current `web_search` and `x_search` tools.

**[Recommendation]** Do not mix `search_parameters` with modern built-in search tools without an authenticated contract test. Use `tools` for the planned integration. Do not use `search_parameters.mode: "on"` as the sole basis for a claim that both X and web definitely returned successful results; validate successful counters.

## 3. Search-tool fields and controls

### 3.1 X Search

```json
{
  "type": "x_search",
  "allowed_x_handles": ["xai"],
  "from_date": "2026-07-01",
  "to_date": "2026-07-29",
  "enable_image_understanding": false,
  "enable_video_understanding": false
}
```

Replace `allowed_x_handles` with `excluded_x_handles` when needed; the two may not be combined. Dates are inclusive and use `YYYY-MM-DD`. X Search supports keyword, semantic, user, and thread retrieval. Image and video understanding are opt-in. [Documented; [X Search][x-search]]

**[Conflict]** The X Search guide says each handle list has a maximum of **20**. The current published OpenAPI schema sets `maxItems: 10` for the modern `x_search` tool. [X Search][x-search], [OpenAPI][openapi].

**[Recommendation]** Enforce 10 until an authenticated API contract test or xAI clarification resolves the conflict. Avoid leading `@` in handles, matching official examples.

### 3.2 Web Search

Raw REST tool shape:

```json
{
  "type": "web_search",
  "allowed_domains": ["x.ai"],
  "enable_image_understanding": false,
  "enable_image_search": false
}
```

- `allowed_domains` and `excluded_domains` are mutually exclusive, maximum 5.
- `enable_image_understanding` lets Grok inspect images encountered while browsing. If X Search is also enabled, Web Search image understanding also enables it for X Search.
- `enable_image_search` lets Grok search for images and may place Markdown image embeds in text. It is separate from image understanding.
- X video understanding has no Web Search counterpart.
[Documented; [Web Search][web-search], [OpenAPI][openapi]]

**[Documented SDK wrinkle]** The OpenAI Responses SDK examples nest domain controls under `filters`, for example `{"type":"web_search","filters":{"allowed_domains":[...]}}`, while the raw OpenAPI tool also exposes top-level `allowed_domains` / `excluded_domains`. Source: [Web Search][web-search], [OpenAPI][openapi].

**[Recommendation]** Use the representation accepted by the chosen SDK and pin that SDK. Keep image search disabled for the dialogue/plan JSON calls unless there is an explicit requirement, because Markdown image embeds are presentation output, not a dependable structured asset-discovery contract.

## 4. Structured-output compatibility and constraints

### 4.1 What is guaranteed

**[Documented]** Supported-schema output is guaranteed to match the supported JSON Schema subset. The recommended Responses shape is:

```json
{
  "text": {
    "format": {
      "type": "json_schema",
      "name": "dialogue",
      "strict": true,
      "schema": {"...": "..."}
    }
  }
}
```

The OpenAI Python SDK can instead call `client.responses.parse(..., text_format=PydanticModel)`. Source: [Structured Outputs][structured].

Supported constructs include strings, numbers, integers, booleans, null, enum, const, arrays, objects, `anyOf`, `oneOf` (same behavior as `anyOf`), single-schema `allOf`, and non-circular `$ref`/`$defs`. `additionalProperties` defaults to false. Optionality comes from omission from `required`; nullability must be stated separately. [Documented; [Structured Outputs][structured]]

Enforced formats are `date`, `time`, `date-time`, `email`, `uuid`, `ipv4`, `ipv6`, and `uri`. [Documented; [Structured Outputs][structured]]

### 4.2 Structural limits

The output engine guarantees these constraints only through the stated thresholds:

| Constraint | Guaranteed through |
|---|---:|
| numeric min/max/exclusive bounds | no stated limit |
| `minLength` / `maxLength` | 2,048 |
| `minItems` / `maxItems` | 256 |
| `minProperties` / `maxProperties` | 64 |

Schemas over a threshold are accepted, but conformance becomes model-dependent. `not`, `if`/`then`/`else`, multi-schema `allOf`, unsupported string formats, and over-threshold constraints are best-effort, not structurally guaranteed. [Documented; [Structured Outputs][structured]]

Rejected with HTTP 400:

- empty `enum` or empty `anyOf`;
- property schemas equal to bare `true` or `false`;
- `maxContains` / `minContains`;
- tuple `items` as an array (use `prefixItems`).
[Documented; [Structured Outputs][structured]]

Patterns use a restricted ECMA-262 subset; lookaround, backreferences, Unicode property escapes, word boundaries, and inline modifiers are unsupported, and patterns are implicitly whole-string. [Documented; [Structured Outputs][structured]]

### 4.3 Dialogue-specific consequences

A useful schema can strictly constrain:

- root envelope and title;
- `dialogue` array count (for example 15–25);
- `speaker` enum to `PETER | STEWIE`;
- `emotion` enum to `neutral | angry | excited | confused`;
- string character lengths; and
- absence of unexpected fields.

**[Recommendation]** Keep facts and citations out of caption strings. A minimal shape is:

```json
{
  "type": "object",
  "properties": {
    "dialogue_data": {
      "type": "object",
      "properties": {
        "title": {"type": "string", "minLength": 1, "maxLength": 120},
        "dialogue": {
          "type": "array",
          "minItems": 1,
          "maxItems": 25,
          "items": {
            "type": "object",
            "properties": {
              "caption": {"type": "string", "minLength": 1, "maxLength": 240},
              "speaker": {"type": "string", "enum": ["PETER", "STEWIE"]},
              "emotion": {"type": "string", "enum": ["neutral", "angry", "excited", "confused"]}
            },
            "required": ["caption", "speaker", "emotion"],
            "additionalProperties": false
          }
        }
      },
      "required": ["title", "dialogue"],
      "additionalProperties": false
    }
  },
  "required": ["dialogue_data"],
  "additionalProperties": false
}
```

**[Unknown / semantic]** JSON Schema does not guarantee 8–15 *words* per caption, 200–300 words total, natural conversation, educational correctness, preservation of supplied wording, both speakers appearing, or Stewie asking a question. Those require prompt instructions and application validation/repair. A schema-valid response can still fail them.

### 4.4 Visual-plan-specific consequences

**[Documented consequence]** A maximum of 12 slots is safely grammar-enforceable with `maxItems: 12`, because it is below 256. Enums can strictly constrain fixed layouts and media intent. Numeric bounds can constrain individual timestamps. [Structured Outputs][structured]

**[Recommendation]** Generate the plan only after sending immutable narration facts (composition/revision ID, total duration, line IDs, captions, and actual `start_ms`/`end_ms`). Return line IDs or millisecond times, not inferred text indexes. A minimal shape should resemble:

```json
{
  "type": "object",
  "properties": {
    "narration_revision": {"type": "string"},
    "slots": {
      "type": "array",
      "maxItems": 12,
      "items": {
        "type": "object",
        "properties": {
          "start_ms": {"type": "integer", "minimum": 0},
          "end_ms": {"type": "integer", "minimum": 1},
          "layout": {"type": "string", "enum": ["top", "center", "bottom"]},
          "query": {"type": "string", "minLength": 1, "maxLength": 240},
          "purpose": {"type": "string", "minLength": 1, "maxLength": 500}
        },
        "required": ["start_ms", "end_ms", "layout", "query", "purpose"],
        "additionalProperties": false
      }
    }
  },
  "required": ["narration_revision", "slots"],
  "additionalProperties": false
}
```

The layout enum above is illustrative, not a settled product contract.

**[Unknown / semantic]** JSON Schema cannot robustly guarantee `end_ms > start_ms`, chronological sort, no overlap between adjacent slots, in-range alignment to the supplied narration, coverage quality, or that a query will yield a valid/licensable image. Validate all of these after parsing. `if`/`then`/`else` would only be best-effort, and cross-array-item non-overlap has no practical supported grammar constraint.

## 5. Output and tool-call controls

### 5.1 Output tokens

**Responses API:**

- `max_output_tokens` includes final visible output and reasoning tokens;
- default when omitted is 128,000;
- response status may be `completed`, `in_progress`, or `incomplete`;
- documented incomplete reasons are `max_output_tokens`, `max_prompt_tokens`, and `max_time_limit`.
[Documented; [REST reference][rest], [OpenAPI][openapi]]

**Legacy Chat Completions:** `max_completion_tokens` applies only to visible output and defaults to 128,000; `max_tokens` is deprecated. [Documented; [REST reference][rest]]

**[Recommendation]** Do not share one arbitrary cap between dialogue and visual planning. Measure visible JSON plus observed reasoning/tool overhead separately. Accept data only when the top-level response and output message are `completed`, the content type is `output_text`, JSON parsing and schema validation pass, and no refusal is present.

### 5.2 Tool limits

- `max_turns` limits agentic assistant/tool-loop turns, not calls.
- Multiple tools may execute in one turn.
- `parallel_tool_calls` controls whether parallel calls are allowed.
- If `max_turns` is omitted, an undisclosed global server cap applies.
- The API may make a final answer from information collected when the cap is reached.
- With mixed client/server tools, a client-side tool pauses execution; a follow-up request starts a fresh `max_turns` count.
[Documented; [Tool Usage Details][tool-usage], [Advanced Tool Usage][advanced-tools]]

**[Conflict / unknown]** The Responses response schema contains `max_tool_calls`, but the request schema exposes `max_turns`, not `max_tool_calls`. No official guide gives a hard maximum number of Web/X calls per request, and parallel turns prevent deriving one from `max_turns`. Source: [OpenAPI][openapi].

**[Recommendation]** Budget with `max_turns`, successful-call counters, elapsed time, and actual cost. Do not promise an exact maximum invocation count until xAI adds a documented request-side call cap.

## 6. Response, usage, cost, and grounding evidence

### 6.1 Usage fields on Responses

The official OpenAPI `usage` object specifies:

```text
input_tokens
input_tokens_details.cached_tokens
output_tokens
output_tokens_details.reasoning_tokens
total_tokens
num_sources_used
num_server_side_tools_used
server_side_tool_usage_details.web_search_calls
server_side_tool_usage_details.x_search_calls
server_side_tool_usage_details.code_interpreter_calls
server_side_tool_usage_details.file_search_calls
server_side_tool_usage_details.mcp_calls
server_side_tool_usage_details.document_search_calls
server_side_tool_usage_details.image_generation_calls
cost_in_usd_ticks          (optional in schema; documented on every inference response)
cost_in_nano_usd           (optional)
context_details.input_tokens/output_tokens (optional, latest context only)
```

Sources: [OpenAPI][openapi], [Cost Tracking][cost].

**[Documented]** For an agentic request, input/prompt usage is cumulative over the internal inference steps as history grows; final output/completion tokens cover final text, while reasoning tokens are separate. Cached prompt tokens identify cache hits. Successful server-side calls are billable; failed attempts are not. `cost_in_usd_ticks` is the exact per-request total after discounts and includes token and server-tool costs; 1 USD = 10,000,000,000 ticks. Sources: [Tool Usage Details][tool-usage], [Cost Tracking][cost].

**[Recommendation]** Persist all usage fields, elapsed time, HTTP status, response status, model, and a provider request/response ID. For grounding, separately record whether X and/or Web Search had at least one successful call. `num_sources_used` alone does not identify source type.

### 6.2 Calls versus successful usage

**[Documented]** Attempted tool calls and successful tool usage are different:

- attempted calls include failures;
- successful usage counts only meaningful successful responses and determines invocation billing;
- server-side tool outputs themselves are not returned to the client;
- Responses exposes server-side call items such as `web_search_call` and `x_search_call`; xAI SDK exposes detailed attempted `tool_calls`.
Source: [Tool Usage Details][tool-usage].

**[Recommendation]** Never accept “X-grounded” merely because an attempted `x_search_call` exists. Require the successful X counter and retain citations.

## 7. Citations and non-persistence

### 7.1 Citation behavior

**[Documented]** xAI describes two citation forms:

1. **All citations:** the xAI response `citations` attribute is a complete list of source URLs encountered during successful search. It is returned by default. Some listed URLs may not be referenced in the final answer.
2. **Inline citations:** Markdown links such as `[[1]](url)` plus `output_text.annotations` carrying `type: "url_citation"`, URL, title/number, and character offsets. Responses enables inline citations by default; the xAI Python SDK does not unless requested. Inline citations are not guaranteed on every answer.
Source: [Citations][citations].

For Responses, `include: ["no_inline_citations"]` removes Markdown citation links from text. Annotations may still be present, but without positional references they represent sources encountered rather than exact claim-to-source links. [Documented; [Citations][citations]]

### 7.2 `store: false`

**[Documented]** Responses normally stores request/response state for 30 days. `store: false` disables storage for later retrieval. Stateful continuation with `previous_response_id` depends on stored state; client-side continuation requires retaining output and encrypted agentic state. Sources: [Generate Text][generate], [Security / ZDR][security].

**[Documented distinction]** `store: false` is a Responses state/resource control, not a documented Zero Data Retention guarantee. xAI says API inputs/outputs are retained for 30 days by default for abuse auditing; only team-level ZDR guarantees that prompts and generated tokens are never persisted to disk, and ZDR disables stateful Responses features. Source: [Security / ZDR][security].

**[Unknown]** The citation guide does not explicitly test the cross-product of structured output, built-in search, `include: ["no_inline_citations"]`, and `store: false`. It states citations are returned by default and states no storage-related exception, but it does not promise later retrieval when storage is disabled.

**[Recommendation]** For each non-stored request, atomically persist on the application side:

- validated structured result;
- raw `output_text`;
- all returned annotations/citation URLs;
- successful tool counters and source count;
- usage/cost;
- response ID, actual model, timestamp, and request policy (`auto` vs forced X).

Do not rely on retrieving the response ID later. Keep inline citation Markdown disabled in machine JSON; treat annotations as out-of-band provenance. If claim-level provenance is required, add explicit source fields to the output schema and validate them against returned citation URLs—but note that xAI does not document a guarantee that model-generated source fields and annotations will correspond one-to-one.

## 8. Concurrency and rate limits

**[Documented]** Text-model limits have two dimensions per model and team: RPS and TPM. RPS is derived from RPM/60, so the full minute budget cannot be burst in one second. Team tier is based on cumulative spend, and exceeding either hard limit returns HTTP 429. The team Console shows the authoritative personalized values. Source: [Rate Limits][rate].

Current public `grok-4.5` limits:

| Tier | RPS | TPM |
|---|---:|---:|
| 0 | 150 | 50,000,000 |
| 1 | 172 | 53,000,000 |
| 2 | 208 | 60,000,000 |
| 3 | 312 | 74,000,000 |
| 4 | 500 | 100,000,000 |

All prompt text/image/audio tokens, completion tokens, reasoning tokens, and cached prompt tokens count toward TPM, although cached tokens are billed at a lower price. [Documented; [Rate Limits][rate]]

**[Documented]** xAI supports concurrent client requests through async clients and advises a semaphore/`max_concurrent` control. Requests cannot be run concurrently beyond Console rate limits. xAI recommends exponential backoff after 429. Sources: [Async Requests][async], [Rate Limits][rate].

**[Unknown]** No separate maximum number of concurrent in-flight **text Responses** requests is published. `parallel_tool_calls` concerns tools inside one response and is not a client concurrency quota. The official examples use a one-hour client timeout for reasoning calls, but this is example configuration rather than a service latency SLA. The response schema also allows `incomplete_details.reason: "max_time_limit"`. Sources: [Generate Text][generate], [OpenAPI][openapi].

**[Recommendation]** Queue dialogue and visual-plan jobs with a configurable semaphore, token-aware admission control, retry budget, jittered exponential backoff for 429/transient server failures, and idempotent application job IDs. Do not retry schema/validation 400/422 errors unchanged.

## 9. Relevant failure modes

### 9.1 Common provider failures

| Failure | Documented fact | Required handling recommendation |
|---|---|---|
| Invalid/unsupported schema | Certain schemas return HTTP 400; malformed fields may return 400/422. | Contract-test schemas at deploy time; do not blind-retry unchanged. |
| Rate limit | RPS or TPM excess returns 429. | Queue and retry with jittered exponential backoff. |
| Incomplete generation | `max_output_tokens`, `max_prompt_tokens`, or `max_time_limit` may produce `status: incomplete`. | Reject partial JSON; retry only under an explicit larger/different budget. |
| Refusal | Responses output supports a `refusal` content type; top-level `error` is available when generation fails. | Surface a typed provider/policy failure; never parse refusal text as JSON. |
| Tool execution failure | Deleted pages/posts, malformed arguments, and network/service issues can fail; the agent may continue another way. | Compare attempted versus successful usage; enforce the requested grounding policy. |
| Tool-turn exhaustion | Global/default or chosen `max_turns` can stop more searches and produce a final answer from gathered data. | Log the cap and successful calls; reject if mandatory source policy was not met. |
| Valid but wrong JSON semantics | Grammar guarantees shape, not factual or product correctness. | Apply domain validators and review/repair rules. |
| Lost provenance with `store: false` | Non-stored responses cannot be fetched later. | Persist result, raw response, citations, and usage before acknowledging the job. |
| Service/API errors | Official debugging lists 400, 401, 403, 404, 405, 415, 422, and 429 and points to status.x.ai for disruptions. | Classify permanent versus transient errors and preserve provider diagnostics. |

Sources: [Structured Outputs][structured], [OpenAPI][openapi], [Tool Usage Details][tool-usage], [Debugging Errors][debugging].

### 9.2 Peter/Stewie dialogue

**[Recommendation]** Reject or repair a structurally valid result if any application invariant fails:

- wrong envelope or empty dialogue;
- speaker/emotion outside enums (normally prevented by schema);
- caption word limits or total script word count violated;
- required speaker/question/tone/educational constraints absent;
- claims not supported by mandatory search evidence;
- citations leaked into spoken captions;
- a forced-X request has zero successful X calls;
- response is incomplete/refused/error; or
- output targets a different source/revision than the job.

**[Documented limitation applied to this task]** Word counts, conversational quality, educational correctness, and claim grounding are semantic and are not guaranteed merely by JSON Schema. Tool failures can be hidden by a graceful alternative trajectory unless successful usage is checked. Sources: [Structured Outputs][structured], [Tool Usage Details][tool-usage].

**[Recommendation]** Keep the schema small and strict; put content rules in instructions and revalidate in application code. Use search conditionally for supplied evergreen source text, but force X only for product modes that promise current X-grounded news. If both X and web are mandatory, model that as explicit staged research or reject unless both successful counters are nonzero.

### 9.3 Post-narration visual plan

**[Recommendation]** Reject or repair a structurally valid plan if:

- `narration_revision` does not match the active composition;
- there are more than 12 slots (normally prevented by schema);
- a slot has `end_ms <= start_ms`;
- slots overlap, are unsorted, or fall outside narration duration;
- a slot references nonexistent line IDs or stale timings;
- layout is unsupported (normally prevented by enum);
- a query is empty, unsafe for the selected provider, redundant, or too abstract;
- the plan treats a citation URL as a usable/licensed media asset;
- requested mandatory source search has no successful usage; or
- response is incomplete/refused/error.

**[Documented limitation applied to this task]** The API does not return server-side search result bodies. Citations are URLs encountered, not an asset-download, reachability, rights, or suitability contract. JSON Schema cannot enforce non-overlap across array items. Sources: [Tool Usage Details][tool-usage], [Citations][citations], [Structured Outputs][structured].

**[Recommendation]** Grok should produce search queries and planning metadata, not claim that it has selected a durable image asset. Keep actual image discovery, fetch validation, rights/product filtering, and persistence in the downstream image-provider boundary.

## 10. Contract decisions still open

These are not answered by xAI's public contract and must be product/architecture decisions:

1. Whether “current/news” means X is mandatory, Web is mandatory, or either is acceptable.
2. Whether mandatory X + optional web warrants two Grok calls.
3. Exact `max_turns` and `max_output_tokens` budgets for each job type.
4. Retry/repair limits for schema-valid but domain-invalid outputs.
5. Whether xAI-side 30-day storage is allowed; if not, exact local retention for prompts, results, citations, and encrypted state.
6. Whether citation URLs are audit-only or claim-level provenance is required.
7. Which fixed visual layouts and timing anchors belong in the final visual-plan schema.
8. How to handle the official 10-versus-20 X-handle limit conflict.
9. The authenticated observed behavior of structured JSON + no inline citations + `store: false`.

## 11. Recommended acceptance checks before implementation

Run authenticated, non-production contract fixtures against the selected SDK/version and save redacted raw responses:

1. conditional `auto` with no search needed;
2. conditional request that uses Web only, X only, and both;
3. forced X with `tools=[x_search]`, `tool_choice=required`;
4. forced X with a deliberately nonexistent/deleted target to verify attempted vs successful counters;
5. structured dialogue with `store:false` and `no_inline_citations`;
6. structured 12-slot visual plan with search;
7. low `max_output_tokens` to verify `incomplete` handling;
8. `max_turns: 1` with parallel tools on and off;
9. 10 and 11 X handles to resolve the live limit conservatively;
10. 429 behavior under the team's actual Console limits.

These tests are recommendations, not substitutes for the documented contract.

## Primary sources

- [xAI Responses vs Chat Completions][comparison]
- [xAI Generate Text / storage and state][generate]
- [xAI Structured Outputs][structured]
- [xAI Tools overview][tools]
- [xAI Advanced Tool Usage][advanced-tools]
- [xAI X Search][x-search]
- [xAI Web Search][web-search]
- [xAI Tool Usage Details][tool-usage]
- [xAI Citations][citations]
- [xAI Rate Limits][rate]
- [xAI Asynchronous Requests][async]
- [xAI Cost Tracking][cost]
- [xAI Models][models] and [`grok-4.5` model card][model-45]
- [xAI REST API reference: Chat / Responses][rest]
- [xAI OpenAPI 3.1 specification][openapi]
- [xAI Debugging Errors][debugging]
- [xAI Security / retention and ZDR][security]

[comparison]: https://docs.x.ai/developers/model-capabilities/text/comparison
[generate]: https://docs.x.ai/developers/model-capabilities/text/generate-text
[structured]: https://docs.x.ai/developers/model-capabilities/text/structured-outputs
[structured-tools]: https://docs.x.ai/developers/model-capabilities/text/structured-outputs#structured-outputs-with-tools
[tools]: https://docs.x.ai/developers/tools/overview
[advanced-tools]: https://docs.x.ai/developers/tools/advanced-usage
[x-search]: https://docs.x.ai/developers/tools/x-search
[web-search]: https://docs.x.ai/developers/tools/web-search
[tool-usage]: https://docs.x.ai/developers/tools/tool-usage-details
[function-calling]: https://docs.x.ai/developers/tools/function-calling#tool-choice
[citations]: https://docs.x.ai/developers/tools/citations
[rate]: https://docs.x.ai/developers/rate-limits
[async]: https://docs.x.ai/developers/advanced-api-usage/async
[cost]: https://docs.x.ai/developers/cost-tracking
[models]: https://docs.x.ai/developers/models
[model-45]: https://docs.x.ai/developers/models/grok-4.5
[rest]: https://docs.x.ai/developers/rest-api-reference/inference/chat
[openapi]: https://docs.x.ai/openapi.json
[debugging]: https://docs.x.ai/developers/debugging
[security]: https://docs.x.ai/developers/faq/security
