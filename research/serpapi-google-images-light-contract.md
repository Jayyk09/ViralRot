# SerpApi Google Images Light contract and image retrieval behavior

**Ticket:** [ViralRot #11](https://github.com/Jayyk09/ViralRot/issues/11)  
**Status:** AFK research only; no application code changed  
**Verified:** 2026-07-29 against first-party SerpApi documentation and published API samples

Labels used below:

- **Documented fact** — stated or demonstrated by an official SerpApi source.
- **Recommendation** — proposed application behavior, not a SerpApi guarantee.
- **Unknown** — not specified by the cited SerpApi contract.

## Decision summary

Use a `GET` request to `https://serpapi.com/search` with the three documented required query parameters `engine=google_images_light`, `q`, and `api_key`. Request `safe=active` explicitly; omission is not equivalent to that setting—the documentation says omitted SafeSearch leaves Google blurring explicit content. JSON is the default output. The Light API paginates with the result offset `start` (`0..999`) and returns `serpapi_pagination.next`/`previous`; it does **not** document `ijn`, `num`, or any other page-size control. [Google Images Light API](https://serpapi.com/google-images-light-api), [required parameters](https://serpapi.com/google-images-light-api#api-parameters-search-query-q), [SafeSearch](https://serpapi.com/google-images-light-api#api-parameters-advanced-filters-safe), [pagination](https://serpapi.com/google-images-light-api#api-parameters-pagination-start)

For a four-candidate review, consume at most the first four ranked objects from `images_results` and retain `position`, a preview URL (`serpapi_thumbnail`, with `thumbnail` as a fallback), `original`, dimensions, `title`, `source`, `link`, and safety/license fields when present. For literal first-result automatic mode, select the first/lowest-`position` item; do not silently call a later fallback the “first result.” The `original` value is only a result URL, usually hosted by a third party. It is not documented as a SerpApi-managed download or availability guarantee, and it can even be a non-HTTP `x-raw-image://` reference for images extracted from PDFs. [result schema and examples](https://serpapi.com/google-images-light-api#api-examples)

Only successful SerpApi responses consume a search; cached, errored, and failed searches do not. A successful response costs one search regardless of whether it has 100 results or an empty result set. Identical requests may use SerpApi's free one-hour cache unless `no_cache=true`. A successful pagination request is therefore operationally another search unless that exact request is cached. [SerpApi pricing FAQ](https://serpapi.com/pricing), [`no_cache`](https://serpapi.com/google-images-light-api#api-parameters-serpapi-parameters-no-cache)

## 1. Exact request contract

### 1.1 Endpoint and minimum request

**Documented facts**

- Method/endpoint: `GET https://serpapi.com/search?engine=google_images_light`. The same documentation's generated pagination URLs use `https://serpapi.com/search.json`; JSON is also the default `output`, so `.json` is convenient but not necessary. [Google Images Light API](https://serpapi.com/google-images-light-api)
- Required query parameters:
  - `engine=google_images_light`
  - `q=<search query>`
  - `api_key=<private SerpApi key>`
- `q` accepts normal Google Images Light query syntax, including operators such as `inurl:`, `site:`, and `intitle:`. [`q`](https://serpapi.com/google-images-light-api#api-parameters-search-query-q)
- `output=json` is the default; `output=html` returns Google's raw HTML rather than the structured result. [`output`](https://serpapi.com/google-images-light-api#api-parameters-serpapi-parameters-output)

Minimum JSON request:

```http
GET https://serpapi.com/search.json?engine=google_images_light&q=Coffee&api_key=SECRET_API_KEY
```

Recommended production baseline (the added parameters are policy choices, not mandatory API fields):

```http
GET https://serpapi.com/search.json?engine=google_images_light&q=Coffee&safe=active&google_domain=google.com&gl=us&hl=en&device=desktop&api_key=SECRET_API_KEY
```

**Recommendation:** send a stable `google_domain`, `gl`, `hl`, and `device` so rank and content do not drift with SerpApi's proxy locale or an implicit device. Keep the API key server-side and URL-encode every value.

### 1.2 Complete documented parameter surface

The following is the complete parameter list shown on the Google Images Light documentation page as verified. [API parameters](https://serpapi.com/google-images-light-api#api-parameters)

| Group | Parameter | Required / values and behavior |
|---|---|---|
| Query | `q` | **Required.** Search query. |
| Location | `location` | Optional location; mutually exclusive with `uule`. If omitted, search may inherit proxy location. City-level value is recommended by SerpApi. |
| Location | `uule` | Optional Google-encoded location; mutually exclusive with `location`. A coordinates-based `uule` requires matching `gl` for consistent results. |
| Localization | `google_domain` | Optional; default `google.com`. |
| Localization | `gl` | Optional two-letter country code. |
| Localization | `hl` | Optional two-letter language code. |
| Localization | `cr` | Optional source-country restriction, e.g. `countryFR|countryDE`. |
| Time | `period_unit` | Optional: `s`, `n`, `h`, `d`, `w`, `m`, `y`; incompatible with `start_date`/`end_date`; overrides `tbs`'s `qdr`. |
| Time | `period_value` | Optional value used with `period_unit`; default `1`, range `1..2147483647`. |
| Time | `start_date` | Optional `YYYYMMDD`; incompatible with `period_unit`/`period_value`; blank `end_date` means through today. |
| Time | `end_date` | Optional `YYYYMMDD`; incompatible with `period_unit`/`period_value`; blank `start_date` means before this date. |
| Filter | `tbs` | Optional advanced Google search filters not expressible in `q`. |
| Filter | `imgar` | Aspect: `s` square, `t` tall, `w` wide, `xw` panoramic. |
| Filter | `imgsz` | Size: `l`, `m`, `i`, `qsvga`, `vga`, `svga`, `xga`, `2mp`, `4mp`, `6mp`, `8mp`, `10mp`, `12mp`, `15mp`, `20mp`, `40mp`, `70mp`. |
| Filter | `image_color` | `bw`, `trans`, or named color `red`, `orange`, `yellow`, `green`, `teal`, `blue`, `purple`, `pink`, `white`, `gray`, `black`, `brown`; overrides corresponding `tbs` components. |
| Filter | `image_type` | `face`, `photo`, `clipart`, `lineart`, `animated`; overrides corresponding `tbs` component. |
| Filter | `licenses` | `f`, `fc`, `fm`, `fmc`, `cl`, `ol`; meanings are documented as free/share/commercial/modify, Creative Commons, or commercial-and-other scopes; overrides corresponding `tbs` component. |
| Safety | `safe` | `active` or `off`; when omitted, Google blurs explicit content. |
| Query behavior | `nfpr` | `1` excludes auto-corrected-query results; `0` includes them (default), although Google may still correct when no other results exist. |
| Deduplication | `filter` | `1` enables Similar/Omitted Results filtering (default); `0` disables it. |
| Pagination | `start` | Result offset; minimum `0`, maximum `999`. |
| SerpApi | `engine` | **Required:** `google_images_light`. |
| SerpApi | `device` | `desktop` (default), `tablet`, or `mobile`. |
| SerpApi | `no_cache` | `false` (default) permits cache; `true` forces a fresh fetch. Cannot be combined with `async`. |
| SerpApi | `async` | `false` (default) waits; `true` submits for later Search Archive retrieval. Cannot be combined with `no_cache`; SerpApi says not to use it with Ludicrous Speed. |
| SerpApi | `zero_trace` | Enterprise-only boolean; `true` disables storage of search parameters/files/metadata. |
| SerpApi | `api_key` | **Required private key.** |
| SerpApi | `output` | `json` (default) or `html`. |
| SerpApi | `json_restrictor` | Optional response-field restriction to reduce payload. |

**Documented absence:** the Light page exposes `start`, not the regular Images API's `ijn`; it exposes no `num`/count/page-size parameter. Neither `ijn` nor a fixed requested result count should be treated as part of this contract.

## 2. SafeSearch

**Documented facts**

- The only documented `safe` values are `active` and `off`.
- If `safe` is omitted, “by default Google will blur explicit content.” That is a distinct documented default behavior; the page does not say omission is an alias for `active`.
- Result objects may include `unsafe`, described as a boolean indicating that the image is marked unsafe. The schema does not say this field is always present. [`safe`](https://serpapi.com/google-images-light-api#api-parameters-advanced-filters-safe), [JSON structure](https://serpapi.com/google-images-light-api#api-examples)

**Recommendation**

- Always request `safe=active` for this product.
- If `unsafe` is present and true, reject the candidate even when `safe=active` was requested. Treat the field's absence as “unknown,” not an affirmative safety classification.
- Do not use `safe=off` or omitted/blur mode for a backend that will download originals: a blurred Google preview does not establish that the third-party original is blurred.

**Unknown:** SerpApi does not document false-negative guarantees, classifier coverage, or whether every result receives `unsafe`.

## 3. JSON result contract

### 3.1 Top-level fields needed for control flow

**Documented facts**

- Structured image results are in `images_results`.
- `search_metadata.status` moves through `Processing` to `Success` or `Error` for synchronous search documentation; the shared status page additionally lists `Queued` for queued searches.
- A top-level `error` string contains a human-readable message when a search fails or has empty results. Empty search-engine results can still have `search_metadata.status="Success"`.
- `search_metadata.id` is SerpApi's search ID. [Light API results](https://serpapi.com/google-images-light-api#api-results), [status/error contract](https://serpapi.com/api-status-and-error-codes#search-api-status-and-errors)

**Recommendation:** success handling must require an acceptable HTTP status, `search_metadata.status == "Success"`, no actionable top-level `error`, and a non-empty `images_results` array. Retain `search_metadata.id` in logs for support, but it is not needed for candidate selection.

### 3.2 Per-image fields

The official Light schema lists these possible fields. [JSON structure overview](https://serpapi.com/google-images-light-api#api-examples)

| Field | Documented meaning | Use in ViralRot |
|---|---|---|
| `position` | Integer rank on the search page | **Keep:** ranking, review order, literal first-result selection. |
| `thumbnail` | Image thumbnail URL | **Keep as preview fallback.** It is commonly a Google-hosted URL in examples. |
| `serpapi_thumbnail` | Thumbnail URL served by SerpApi | **Keep as preferred review preview.** It does not replace the original. |
| `title` | Short image description | Keep for review context/accessibility; not required to fetch pixels. |
| `source` | Displayed source-site value | Keep for provenance in review; not required to fetch pixels. |
| `link` | Source page providing the image | Keep for provenance/open-source-page action. |
| `raw_link` | “Google page related to the image” in the schema | Ignore unless a later product requirement distinguishes it from `link`; examples can show the same value. |
| `original` | Original image URL (full resolution) | **Technically necessary for original retrieval**, subject to validation below. |
| `original_width`, `original_height` | Original pixel dimensions | Keep to pre-filter quality/aspect ratio; verify after download. |
| `license_details_url` | License-details URL | Keep only if license review is surfaced; do not treat existence as proof of permission. |
| `unsafe` | Whether image is marked unsafe | Keep and enforce when present. |
| `related_content_id` | ID for image-related content | Ignore for the two requested modes. |
| `serpapi_related_content_link` | SerpApi link to fetch related content | Ignore; following it is another API operation and is not needed. |
| `is_product`, `in_stock` | Product/inventory indicators | Ignore for editorial image selection. |

Examples also contain opportunistic fields such as `source_logo`; these are not needed. Search metadata timestamps, fetched Google URL, raw HTML URL, processing duration, echoed `search_parameters`, spelling state, and pagination metadata can all be omitted from persisted candidates, except that status/error/search ID should be used during request handling.

**Unknown:** the schema describes fields but does not mark per-result fields as universally required. Code must tolerate a missing preview, dimensions, safety flag, license URL, or even an unusable `original` value.

### 3.3 Four-candidate review

**Recommendation**

1. Preserve API rank (`position`; returned order as fallback).
2. Take at most the first four eligible objects from the first response. A second page is unnecessary when four eligible candidates are already present.
3. A review card should use `serpapi_thumbnail` then `thumbnail`, and show `title`, `source`, dimensions, and a link to `link`.
4. Carry `original` through selection, but download it only after selection unless product latency requires prefetching.
5. Reject `unsafe=true`, unsupported/non-HTTP original schemes, and candidates that fail product quality rules. If fewer than four survive, show fewer or deliberately request the documented `serpapi_pagination.next` page; do not invent offsets.

Only `images_results`, rank/order, a usable preview, and a candidate identity are technically necessary to render four choices. `original` becomes necessary when selection must produce a full-resolution asset. The descriptive/provenance fields are strongly useful but not pixel-retrieval requirements.

### 3.4 First-result automatic mode

**Recommendation**

- Define literal “first result” as the first returned item / lowest `position` (normally `position=1`). Required data is a non-empty `images_results` list and a retrievable HTTP(S) `original` for that item.
- If rank 1 cannot be downloaded or validated, fail that strict mode explicitly. If product wants fallback to rank 2+, name the behavior “first usable result” and record both the selected rank and rejection reason; it is observably different from first-result mode.
- Do not use `thumbnail` as though it were the original. It is a separate lower-resolution preview field.

## 4. Pagination and result-list behavior

**Documented facts**

- `start` is an offset that skips that number of results; allowed range is `0..999`.
- The response schema's `serpapi_pagination` can contain:
  - `current`: current page index;
  - `next`: SerpApi URL for the next page;
  - `previous`: SerpApi URL for the previous page.
- `images_results` is an ordered array whose objects carry page position.
- No Light parameter controls requested result count/page size. [`start`](https://serpapi.com/google-images-light-api#api-parameters-pagination-start), [pagination response](https://serpapi.com/google-images-light-api#api-examples)

**Important observed API-sample behavior, not a guarantee:** the official downloadable Coffee sample currently contains 100 objects at positions 1–100 and a `next` URL with `start=100`. The rendered documentation example on the same page shows `start=10`. This is direct evidence not to hard-code a Light page size. [Official Coffee sample JSON](https://serpapi.com/samples/documentation/google_images_light_api_71ce7c86a5.json), [rendered examples](https://serpapi.com/google-images-light-api#api-examples)

**Recommendation:** follow `serpapi_pagination.next` exactly, stop when it is absent, de-duplicate across pages by a normalized `original`/`link` tuple if needed, and cap the number of page fetches. Do not calculate `start += 10` or `start += 100`.

**Unknowns:** no guaranteed minimum/maximum objects per page, stable ordering across separate fresh searches, total-result count, end-of-list sentinel beyond absence of `next`, or snapshot consistency across pages is documented.

## 5. Billing, cache, and query semantics

**Documented facts**

- Only successful searches count toward the monthly allowance; cached, errored, and failed searches do not.
- Result count does not affect cost: a response with 100 results and an empty result set each count as one successful search.
- With default `no_cache=false`, SerpApi may serve a cached result only when the query **and all parameters are exactly identical**. Cache expires after one hour. Cached searches are free and do not count toward the monthly searches.
- `no_cache=true` forces a fetch and cannot be combined with `async`.
- The free Account API (`GET https://serpapi.com/account.json?api_key=...`) exposes monthly/remaining usage and hourly throughput data. [pricing FAQ](https://serpapi.com/pricing), [`no_cache`](https://serpapi.com/google-images-light-api#api-parameters-serpapi-parameters-no-cache), [Account API](https://serpapi.com/account-api)

**Operational inference:** each successful page request with a different `start` is a separate response/search and will normally consume one search, because its parameters differ from the first page; an exact cached repeat is free. This follows the documented per-response charging and exact-parameter cache rules, but the Light page does not separately state “pagination costs one credit.”

**Recommendation:** one query should normally service both modes: return the first four objects for review or the first object for automatic mode. Do not request additional pages merely to obtain exactly four if the first response already has them. Leave caching enabled unless freshness is a demonstrated requirement.

## 6. Rate limits and errors

### 6.1 HTTP and JSON error contract

**Documented facts**

| HTTP status | Meaning documented by SerpApi |
|---|---|
| `200` | Success at the HTTP layer; search results may still be empty. |
| `400` | Bad request, including a missing required parameter. |
| `401` | No valid API key. |
| `403` | Key's account lacks permission, commonly a deleted account. |
| `404` | Requested resource does not exist. |
| `410` | Archived search expired/deleted. |
| `429` | Either hourly throughput exceeded **or** account has run out of searches. |
| `500`, `503` | SerpApi server failure. |

Non-search/request errors return a top-level JSON `error` string. Search API responses additionally use `search_metadata.status` (`Queued`, `Processing`, `Success`, `Error`); failed or empty-result searches can include top-level `error`. [Status and Error Codes](https://serpapi.com/api-status-and-error-codes), [Search API status](https://serpapi.com/api-status-and-error-codes#search-api-status-and-errors)

Example documented messages include `Invalid API key...`, `Your account has run out of searches.`, and `Missing query q parameter.` The message is human-readable, not a documented stable machine code.

### 6.2 Rate/usage fields

The Account API's official example includes:

- `searches_per_month`
- `plan_searches_left`
- `extra_credits`
- `total_searches_left`
- `this_month_usage`
- `this_hour_searches`
- `last_hour_searches`
- `account_rate_limit_per_hour`

The Account API itself is free and does not consume monthly quota. [Account API](https://serpapi.com/account-api)

**Recommendation:** distinguish `429` quota exhaustion from throughput pressure using the error text and, when operationally useful, Account API fields. Retry transient `429` throughput and `5xx` failures with bounded exponential backoff/jitter; do not retry invalid parameters/key/permission without correction. Log HTTP status, top-level `error`, `search_metadata.status`, and `search_metadata.id` when available.

**Unknown:** the cited docs specify no stable error code field, `Retry-After` guarantee, or `X-RateLimit-*` response-header contract. Do not build correctness around such headers unless separately verified in a future API contract.

## 7. Downloading `original` images

### 7.1 What SerpApi documents

- `original` is described as the “Original image URL (full resolution).” Typical official examples point directly to publisher/CDN domains, not SerpApi. `link` is the source page, while `serpapi_thumbnail` is explicitly the thumbnail served by SerpApi. [Light result schema](https://serpapi.com/google-images-light-api#api-examples)
- For PDF search results, `original` may instead begin with `x-raw-image://`, an internal XObject reference. That value is not an HTTP download URL. [PDF example](https://serpapi.com/google-images-light-api#api-examples-results-for-diagram-filetype-pdf)
- The Light API supports a `licenses` search filter and may return `license_details_url`; the docs define those values/fields but do not grant a license or promise that metadata is present/correct for every result. [`licenses`](https://serpapi.com/google-images-light-api#api-parameters-advanced-filters-licenses), [result schema](https://serpapi.com/google-images-light-api#api-examples)

### 7.2 What is not in the contract

**Unknown / not guaranteed by the cited SerpApi docs**

- that SerpApi downloaded, validated, or stores the bytes at `original`;
- continued URL availability, expiry behavior, status code, redirect behavior, or resistance to publisher hotlink controls;
- browser CORS permission, required `Referer`/cookies/headers, or whether a URL is fetchable outside Google's context;
- MIME type, file extension, byte size, decoded format, dimensions matching metadata, or that the response is an image rather than an HTML block/error page;
- that third-party content may legally be copied/reused merely because Google indexed it or a license filter/URL appears;
- a SerpApi proxy for full-resolution originals. `serpapi_thumbnail` is documented only as a thumbnail.

### 7.3 Retrieval recommendation

Treat `original` as untrusted, ephemeral third-party input:

1. Accept only `http`/`https`; reject `x-raw-image://` and all other schemes.
2. Download server-side, not directly from the browser, because CORS is not guaranteed.
3. Apply SSRF controls to the initial URL and every redirect: deny loopback, link-local, private, metadata-service, and disallowed ports/hosts after DNS resolution.
4. Enforce connection/read timeouts, redirect and byte caps, and an allowed decoded-image format list.
5. Require an image MIME type **and** verify magic bytes/decode; do not trust URL suffix or `Content-Type` alone.
6. Recompute dimensions from downloaded bytes and enforce quality/aspect limits; result metadata is useful for pre-filtering only.
7. Store an application-owned copy after validation rather than relying on the remote URL for rendering/export.
8. Preserve `link`, `source`, and any `license_details_url` for provenance; rights review remains a product/legal responsibility.
9. On retrieval failure, report the selected rank as failed. Only fall through to another candidate in an explicitly named “first usable” policy.

These are engineering recommendations, not behavior supplied by SerpApi.

## 8. Minimal retained contract

For the requested feature, the smallest defensible data/control surface is:

```text
Request:
  engine, q, api_key                  # required by SerpApi
  safe=active                         # required by product policy, not API validity
  google_domain, gl, hl, device       # recommended deterministic context

Response control flow:
  HTTP status, error
  search_metadata.status
  search_metadata.id                  # logs/support only
  images_results
  serpapi_pagination.next             # only if deliberate paging is needed

Candidate:
  position
  serpapi_thumbnail or thumbnail      # review preview
  original                            # selected full-resolution retrieval
  original_width, original_height     # pre-filter only
  unsafe                              # enforce if present
  title, source, link                 # review/provenance
  license_details_url                 # only if rights UI needs it
```

Everything else can be ignored for four-candidate review and literal first-result mode. “Can be ignored” does not mean SerpApi will omit it; use `json_restrictor` only after its selected-field behavior has been integration-tested, since the feature does not need payload restriction to establish correctness.

## Sources

All sources are first-party SerpApi pages/API samples:

1. [Google Images Light API](https://serpapi.com/google-images-light-api)
2. [Official Google Images Light Coffee sample JSON](https://serpapi.com/samples/documentation/google_images_light_api_71ce7c86a5.json)
3. [SerpApi Status and Error Codes](https://serpapi.com/api-status-and-error-codes)
4. [SerpApi Account API](https://serpapi.com/account-api)
5. [SerpApi pricing and billing FAQ](https://serpapi.com/pricing)
