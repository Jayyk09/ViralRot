# Cloudflare Hosting Fit for the ViratRot Backend

**Status:** Research only — no application code changed.  
**Date:** 2026-07-30  
**Scope:** Whether Cloudflare can host the repository's current Python/FastAPI backend or a practical equivalent, with emphasis on FFmpeg, Pillow, WebSockets, background work, temporary disk, Neon Postgres, R2, and secure remote-image ingestion.

Claims are labeled:

- **[code]** — verified by reading this repository at `ca403a0` plus the current working tree.
- **[sourced]** — verified against official Cloudflare documentation/changelog or first-party Pyodide documentation.
- **[analysis]** — conclusion drawn from those facts.
- **[rec]** — practical recommendation.

---

## 1. Executive conclusion

**Cloudflare now has a product that can run this backend: Cloudflare Containers.** Containers became generally available on April 13, 2026, run `linux/amd64` images in isolated VMs, provide a full Linux filesystem/runtime, and are explicitly intended for existing container images and CPU/memory/disk-intensive applications. They are available on the Workers Paid plan. [Cloudflare Containers GA](https://developers.cloudflare.com/changelog/post/2026-04-13-containers-sandbox-ga/) · [Containers overview](https://developers.cloudflare.com/containers/) · [Container lifecycle](https://developers.cloudflare.com/containers/platform-details/architecture/) **[sourced]**

The repository's existing `backend/Dockerfile` is therefore a strong fit: it already uses `python:3.11-slim`, installs FFmpeg, installs the Python requirements, and launches Uvicorn. The application image can run **largely unchanged** in a Cloudflare Container, subject to building for `linux/amd64`. Deployment is not literally zero-change: a small JavaScript/TypeScript Worker and Wrangler configuration must select a Container instance and proxy HTTP/WebSocket traffic to it. **[code + sourced + analysis]**

**Cloudflare Workers, including Python Workers, cannot host the complete application unchanged.** Python Workers are still in beta and use CPython compiled to WebAssembly through Pyodide. FastAPI is supported through Cloudflare's ASGI adapter, and Pillow is available in Pyodide, but the runtime has no usable subprocess support, only an ephemeral in-memory filesystem, a 128 MB isolate limit, and a maximum five minutes of active CPU on paid plans. The current app also relies on `asyncio.to_thread`, synchronous boto3, psycopg2, FFmpeg subprocesses, and process-local job/WebSocket state. [Python Workers](https://developers.cloudflare.com/workers/languages/python/) · [FastAPI on Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/) · [Python Worker standard library](https://developers.cloudflare.com/workers/languages/python/stdlib/) · [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) · [Pyodide FAQ](https://pyodide.org/en/stable/usage/faq.html#can-i-use-threading-multiprocessing-subprocess) **[sourced + analysis]**

### Recommended MVP

1. **Use one Cloudflare Container instance behind a Worker, on at least `standard-2` (1 vCPU, 6 GiB RAM, 12 GB ephemeral disk), and route every API and WebSocket request to one fixed Container ID.** This preserves the current in-memory progress registry and keeps WebSockets attached to the same Uvicorn process. `standard-1` may be sufficient after measuring; `basic` provides only 1/4 vCPU and is a poor initial choice for 1080×1920 FFmpeg work. Instance specifications are official; the sizing choice is a recommendation, not a benchmark. [Container limits and instance types](https://developers.cloudflare.com/containers/platform-details/limits/) **[sourced + rec]**
2. **Keep Neon Postgres and R2.** In the Container, the existing psycopg2 connection and boto3 S3-compatible R2 client can use normal outbound networking, so neither database nor object storage needs migration. **[code + analysis]**
3. **Treat local disk strictly as scratch space.** Current render/upload/delete flows are compatible with ephemeral disk, but the asset cache is only a cache; nothing needed after a completed request/job may exist only on local disk. Cloudflare states that disk is reset when an instance sleeps or restarts. [Container lifecycle — persistent disk](https://developers.cloudflare.com/containers/platform-details/architecture/#persistent-disk) **[sourced]**
4. **Accept limited MVP reliability or harden jobs before production.** Cloudflare does not guarantee that a Container instance runs for any fixed period, host restarts can occur, built-in stateless autoscaling is not yet available, and the current job state is process-local. A restart loses active `BackgroundTasks`, WebSocket registrations, and progress/results that have not yet been persisted. [Container FAQ](https://developers.cloudflare.com/containers/faq/#how-long-can-instances-run-for-what-happens-when-a-host-server-is-shut-down) · [Scaling and routing](https://developers.cloudflare.com/containers/platform-details/scaling-and-routing/) **[sourced + code + analysis]**

If “MVP” requires jobs to survive restarts, make job state durable in Postgres and use Queues/Workflows to coordinate idempotent Container work before launch. That is an architectural change, not a hosting configuration change. **[rec]**

---

## 2. What this backend actually requires

The relevant runtime assumptions are:

- FastAPI/Uvicorn and ASGI lifespan; WebSocket endpoint `/ws/progress/{job_id}`. **[code: `backend/main.py`]**
- Blocking work moved with `asyncio.to_thread`; FastAPI `BackgroundTasks` starts transcript, narration, and video jobs after a 202 response. **[code: `backend/main.py`]**
- FFmpeg/ffprobe invoked with `subprocess.run` for audio concatenation, duration probing, and final video composition. **[code: `backend/backend_pipeline/audio_generation/{elevenLabs,minimax_tts}.py`, `backend/backend_pipeline/video_assembly/ffMpeg.py`]**
- Temporary directories/files and a local asset cache used to stage R2 downloads, narration, normalized images, render inputs, and final MP4 output. **[code: `backend/main.py`, `backend/services/editor_audio_service.py`, `backend/storage/assets.py`]**
- Pillow decodes PNG/JPEG/WebP, rejects animation and dimensions over 4096×4096, applies EXIF orientation, and re-encodes metadata-free WebP. The current upload path reads at most 10 MiB + 1 byte into memory before normalization. **[code: `backend/services/media_service.py`, `backend/main.py`]**
- Neon/Postgres through synchronous `psycopg2.connect(DATABASE_URL)`. **[code: `backend/db.py`]**
- R2 through synchronous boto3 against the R2 S3 endpoint, including upload/download/list/head/delete and presigned GET URLs. **[code: `backend/storage/r2_backend.py`]**
- Job state and WebSocket connection sets stored only in process memory, with a one-hour TTL. **[code: `backend/services/progress_service.py`]**
- The final export snapshots project metadata, downloads background/audio/overlay assets to local disk, runs FFmpeg, uploads the MP4 to R2, and deletes the temporary export directory. **[code: `backend/main.py`]**

These are conventional container assumptions, but several conflict directly with an isolate/WebAssembly runtime. **[analysis]**

---

## 3. Product comparison

| Option | Current availability/maturity | Existing app unchanged? | FFmpeg/processes | Filesystem | WebSockets | Background jobs | Verdict |
|---|---|---:|---|---|---|---|---|
| Workers (JS/TS) | Mature platform | **No** — Python rewrite | No OS subprocess | No conventional persistent local disk | Supported | HTTP work after response only up to 30s via `waitUntil`; Queue/Cron limits apply | Edge router/orchestrator only |
| Python Workers | **Open beta** | **No** — FastAPI shell may port, backend does not | No usable subprocess | Ephemeral in-memory FS | Worker runtime supports WebSockets; Cloudflare ASGI source includes WebSocket handling | Same Worker limits; threading is nonfunctional | Possible for a rewritten API/image edge service, not the renderer |
| Containers | **GA since 2026-04-13**, Paid plan | **Mostly** — image can run; Worker routing/config required | Yes, full Linux runtime | Full but ephemeral disk | Automatically proxied by Container `fetch()` | Process can continue, but no fixed lifetime guarantee; current jobs are not restart-safe | Best Cloudflare MVP host |
| Durable Objects | Mature; SQLite storage GA | **No** | No | Durable SQLite/KV, not a Linux filesystem | Excellent; hibernation API recommended | Alarms/requests use Worker CPU limits | Job status and WebSocket coordination after refactor |
| Queues | Available Free/Paid; at-least-once delivery | **No** | Consumer is still a Worker | No renderer scratch disk | Not its role | 15m wall time, up to 5m CPU, retries/DLQ | Reliable dispatch, not FFmpeg execution |
| Workflows | **GA since 2025-04-07** | **No** | Steps are still Worker code | Persisted workflow state, not Linux scratch disk | Not primary WebSocket endpoint | Durable retries/waits; each step up to 5m CPU, unlimited I/O wall time | Orchestration around Containers, not renderer replacement |

Sources: [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Python Workers](https://developers.cloudflare.com/workers/languages/python/), [Containers GA](https://developers.cloudflare.com/changelog/post/2026-04-13-containers-sandbox-ga/), [Container WebSockets](https://developers.cloudflare.com/containers/examples/websocket/), [Durable Object WebSockets](https://developers.cloudflare.com/durable-objects/best-practices/websockets/), [Queues limits](https://developers.cloudflare.com/queues/platform/limits/), [Queues delivery](https://developers.cloudflare.com/queues/reference/delivery-guarantees/), [Workflows GA](https://developers.cloudflare.com/changelog/post/2025-04-07-workflows-ga/), [Workflows limits](https://developers.cloudflare.com/workflows/reference/limits/). **[sourced]**

### 3.1 Workers and Python Workers

#### What works

- Workers can receive bodies up to 100 MB on Cloudflare Free/Pro, 200 MB on Business, and 500 MB by default on Enterprise; response bodies have no Worker-enforced size limit. A 10 MB application cap is therefore below the platform request cap. [Workers request/response limits](https://developers.cloudflare.com/workers/platform/limits/#request-and-response-limits) **[sourced]**
- Paid Workers allow up to five minutes of **active CPU** per request (30 seconds by default). Network/storage waits do not count as CPU. HTTP wall time has no hard limit while the caller remains connected. After the response completes or the client disconnects, `ctx.waitUntil()` provides at most 30 additional seconds. [Workers CPU and duration](https://developers.cloudflare.com/workers/platform/limits/#cpu-time) · [`waitUntil`](https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil) **[sourced]**
- Python Workers support FastAPI through Cloudflare's ASGI adapter. The current first-party ASGI implementation also contains WebSocket request handling. [FastAPI docs](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/) · [Cloudflare ASGI source](https://github.com/cloudflare/workers-py/blob/main/packages/runtime-sdk/src/asgi.py) **[sourced]**
- Python packages can be pure Python, PyEmscripten wheels, or packages included with Pyodide. Pillow and SQLAlchemy are in Pyodide's package set. [Python Worker packages](https://developers.cloudflare.com/workers/languages/python/packages/) · [Pyodide packages](https://pyodide.org/en/stable/usage/packages-in-pyodide.html) **[sourced]**
- R2 has a native Worker binding whose `put` accepts a `ReadableStream`, and Hyperdrive explicitly supports Neon/Postgres. [R2 Worker API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/) · [Hyperdrive](https://developers.cloudflare.com/hyperdrive/) **[sourced]**

#### Blocking incompatibilities

1. **No FFmpeg subprocesses.** Python Workers execute inside Pyodide/WebAssembly; Pyodide's first-party FAQ states that `threading`, `multiprocessing`, and `subprocess` cannot be used. The existing backend calls FFmpeg/ffprobe repeatedly. [Pyodide WebAssembly constraints](https://pyodide.org/en/stable/usage/wasm-constraints.html) · [Pyodide FAQ](https://pyodide.org/en/stable/usage/faq.html#can-i-use-threading-multiprocessing-subprocess) **[sourced + code]**
2. **The current blocking adapter fails.** `backend/main.py` runs nearly all repository/storage/Pillow work through `asyncio.to_thread`; Cloudflare documents `threading` as importable but nonfunctional in Python Workers. [Python Worker standard library](https://developers.cloudflare.com/workers/languages/python/stdlib/#excluded-modules) **[sourced + code]**
3. **The current database/storage clients are not Worker-compatible as written.** `psycopg2-binary` is a native CPython package rather than a PyEmscripten package, and boto3/botocore uses synchronous HTTP. Cloudflare says only asynchronous Python HTTP libraries are supported, currently aiohttp and httpx. A Worker port should use a compatible Postgres driver/Hyperdrive and the native R2 binding rather than the current psycopg2+boto3 path. [Python Worker packages — HTTP clients](https://developers.cloudflare.com/workers/languages/python/packages/#http-client-libraries) **[sourced + code + analysis]**
4. **Memory is tight for Pillow normalization.** Every Worker isolate is limited to 128 MB, shared by concurrent requests. A 4096×4096 RGBA decode alone is 64 MiB before Python/Pyodide, input/output buffers, conversion copies, and FastAPI overhead. Although the encoded input is capped at 10 MiB and Pillow exists in Pyodide, the current maximum-dimension operation is not reliably safe in a 128 MB isolate. [Workers memory limit](https://developers.cloudflare.com/workers/platform/limits/#memory) **[sourced + analysis]**
5. **The filesystem semantics do not match.** Python Workers expose only an ephemeral, in-memory filesystem, not a multi-GB Linux scratch disk. That cannot stage background MP4/audio assets or FFmpeg output and also consumes the isolate's memory budget. [Python Worker in-memory filesystem](https://developers.cloudflare.com/workers/languages/python/stdlib/#in-memory-filesystem) **[sourced + analysis]**
6. **FastAPI `BackgroundTasks` is not durable execution.** The current 202 response detaches work that can take far longer than 30 seconds. A Worker may cancel such work once its response is complete; Queues or Workflows are required for longer reliable work. [Workers duration](https://developers.cloudflare.com/workers/platform/limits/#duration) · [`waitUntil`](https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil) **[sourced + code + analysis]**
7. **Process-local progress is unsafe across isolates.** Workers can create/evict isolates and a request can land on another isolate; the app assumes a single Python process owns both `PROGRESS_STORAGE` and every WebSocket object. Durable Objects are Cloudflare's stateful coordination primitive. [What are Durable Objects?](https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/) **[sourced + code + analysis]**

**Conclusion for Workers:** a rewritten control plane is viable, and a rewritten image-only endpoint may be viable, but the complete repository backend is not. Removing FFmpeg alone is insufficient; database, R2, threading, job state, and scratch-storage paths also require redesign. **[analysis]**

### 3.2 Containers

#### Runtime and resource fit

Cloudflare says Containers support existing container images, any language/runtime, CPU-intensive applications, and applications needing a full filesystem or Linux environment. Each instance runs in a VM and must target `linux/amd64`. [Containers overview](https://developers.cloudflare.com/containers/) · [Container runtime](https://developers.cloudflare.com/containers/platform-details/architecture/#container-runtime) **[sourced]**

Available predefined sizes range from `lite` (1/16 vCPU, 256 MiB, 2 GB disk) through `standard-4` (4 vCPU, 12 GiB, 20 GB disk); custom types support up to 4 vCPU, 12 GiB, and 20 GB. [Container limits](https://developers.cloudflare.com/containers/platform-details/limits/) **[sourced]**

That environment supports the existing Uvicorn, Pillow, psycopg2, boto3, local temp files, and FFmpeg subprocess model. The repository's checked-in backend assets are about 815 MB and therefore fit in the documented image/disk sizes, although runtime downloads and output MP4s must also fit the chosen instance's disk. **[code + sourced + analysis]**

#### Ingress, WebSockets, and networking

- Every request first enters a Worker, then passes through the Container's Durable Object and into the Container. Public ingress is HTTP only; clients cannot connect directly with arbitrary TCP/UDP. [Container request lifecycle](https://developers.cloudflare.com/containers/platform-details/architecture/#lifecycle-of-a-request) **[sourced]**
- WebSocket upgrades are automatically forwarded by the Container class's default `fetch()` method. [Container WebSocket example](https://developers.cloudflare.com/containers/examples/websocket/) **[sourced]**
- Public internet access is enabled by default. Cloudflare supports `enableInternet`, `allowedHosts`, `deniedHosts` (including IP/CIDR rules), and programmable HTTP/HTTPS outbound handlers. Non-HTTP traffic can use the public network but is not intercepted by HTTP handlers. [Container outbound traffic](https://developers.cloudflare.com/containers/platform-details/outbound-traffic/) **[sourced]**

This permits direct psycopg2 TCP/TLS to Neon and HTTPS to R2/external APIs. If egress is switched to deny-by-default, the configuration must explicitly preserve Neon database traffic as well as R2 and TTS/AI APIs. **[analysis]**

#### Lifecycle and disk constraints

- Cold starts are commonly 1–3 seconds but vary with image size and entrypoint work. [Container cold starts](https://developers.cloudflare.com/containers/platform-details/architecture/#cold-starts) **[sourced]**
- Disk is ephemeral; after sleep/restart the instance gets a fresh disk from the image. R2 FUSE is available, but Cloudflare cautions not to expect native SSD performance. [Container persistent disk](https://developers.cloudflare.com/containers/platform-details/architecture/#persistent-disk) **[sourced]**
- Cloudflare does not impose a fixed maximum running time, but also does not guarantee an instance will run for any fixed duration. Host restarts occur on an irregular cadence; shutdown sends SIGTERM, then SIGKILL after 15 minutes, and the instance is restarted elsewhere. [Container FAQ — lifetime](https://developers.cloudflare.com/containers/faq/#how-long-can-instances-run-for-what-happens-when-a-host-server-is-shut-down) **[sourced]**
- Built-in stateless autoscaling is not available today. Developers manually address instances by ID or randomly distribute requests over a fixed number. [Container scaling](https://developers.cloudflare.com/containers/platform-details/scaling-and-routing/) **[sourced]**

These limitations do not prevent an MVP, but they expose weaknesses already present in the app: an interrupted render has no durable claim/retry record, progress exists only in RAM, and horizontal replicas would not share WebSocket/job state. **[code + analysis]**

#### “Unchanged” assessment

**Can the image start unchanged? Yes, likely. Can the application architecture operate correctly at scale unchanged? No.** **[analysis]**

Required deployment work, without changing application code:

1. Build/publish the existing Dockerfile as `linux/amd64`.
2. Add Wrangler Container configuration with the selected instance type and secrets/environment variables.
3. Add a Worker/Container class with `defaultPort = 8000`.
4. Route all paths, including `/ws/*`, to one stable instance ID.
5. Set an inactivity policy long enough that a render is not stopped merely because the initiating HTTP request has returned. Keeping an instance warm incurs provisioned memory/disk charges; Containers otherwise scale to zero. [Container pricing](https://developers.cloudflare.com/containers/pricing/) **[sourced + rec]**

Production hardening that **does** require application/architecture changes:

- Persist jobs, status, error, result, and idempotency keys in Postgres.
- Make render execution restartable/idempotent and clean stale temp prefixes.
- Separate API/WebSocket coordination from render workers before adding multiple instances.
- Replace in-process `BackgroundTasks` with durable dispatch.
- Ensure each completed stage uploads artifacts to R2 before acknowledging it.

**[rec]**

### 3.3 Durable Objects, Queues, and Workflows

These products complement Containers; none can run FFmpeg or preserve this backend unchanged.

#### Durable Objects

Durable Objects give each named object single-location coordination plus strongly consistent attached storage. The recommended WebSocket Hibernation API keeps clients connected while the object leaves memory and wakes it on the next event. SQLite-backed Durable Object storage is GA. [Durable Objects overview](https://developers.cloudflare.com/durable-objects/) · [WebSocket hibernation](https://developers.cloudflare.com/durable-objects/best-practices/websockets/) **[sourced]**

They still run under Worker limits: 128 MB isolate memory and 30 seconds active CPU by default, configurable to five minutes. [Durable Object limits](https://developers.cloudflare.com/durable-objects/platform/limits/) **[sourced]**

**Suitable role:** one object per job/project for durable status and WebSocket fan-out, while the Container performs rendering. This would replace `PROGRESS_STORAGE` and `WEBSOCKET_CONNECTIONS`, so it is a meaningful rewrite. **[analysis]**

#### Queues

Queues provide at-least-once delivery, retries, delays, and dead-letter queues. Messages may be delivered more than once, so render jobs need an idempotency key. A push consumer is a Worker invocation with a 15-minute wall-clock cap, a 30-second default CPU cap configurable to five minutes, and 128 KB messages. [Queues delivery guarantees](https://developers.cloudflare.com/queues/reference/delivery-guarantees/) · [Queues limits](https://developers.cloudflare.com/queues/platform/limits/) **[sourced]**

**Suitable role:** durable render dispatch containing only IDs/R2 keys, not media. A Queue consumer could start or call a Container, but the FFmpeg work should not execute in the consumer itself. Long renders exceeding the consumer's 15-minute wall limit should be started asynchronously with durable state or orchestrated/polled by Workflows. **[analysis + rec]**

#### Workflows

Workflows has been GA since April 2025 and persists multi-step state, retries failed steps, sleeps, and waits for external events. Paid steps have 30 seconds active CPU by default, configurable to five minutes, while I/O wall time per step is unlimited. [Workflows GA](https://developers.cloudflare.com/changelog/post/2025-04-07-workflows-ga/) · [Workflows limits](https://developers.cloudflare.com/workflows/reference/limits/) **[sourced]**

**Suitable role:** orchestrate “fetch inputs → ask Container to render → wait/poll → upload/record result,” with retries and compensation. It does not make Pillow/FFmpeg executable in the Worker runtime, and introducing it requires moving the current Python background-job lifecycle into explicit durable steps. **[analysis]**

---

## 4. Explicit assessment: secure server-side remote image fetching

The repository currently implements proxied multipart image upload, not a URL-fetch endpoint. The following evaluates whether a future server-side remote fetch can enforce: SSRF controls, a 10 MB streaming cap, Pillow normalization, and R2 upload. **[code]**

### 4.1 Cloudflare Container: **yes**

All four operations are practical in the existing Python stack. **[analysis]**

A safe implementation should:

1. Accept only `http`/`https`; reject credentials in URLs and unexpected ports.
2. Resolve the hostname and reject loopback, private, link-local, multicast, documentation, reserved, and cloud metadata ranges for both IPv4 and IPv6.
3. Connect only to a validated address/hostname, use short connect/read/total timeouts, and do not automatically trust redirects. Re-parse and re-validate every redirect target with a small redirect limit.
4. Reject a declared `Content-Length > 10 MiB`, but never rely on it. Stream chunks, keep a running byte count, and abort/delete the partial buffer as soon as byte 10 MiB + 1 arrives.
5. Validate decoded type/dimensions/animation and normalize through the existing `normalize_image()` path.
6. Upload the normalized WebP to a server-generated R2 key, then insert the database row; retain the existing compensating R2 delete if the DB insert fails.

**[rec; steps 4–6 match the repository's existing upload invariant]**

Cloudflare can add a second SSRF boundary at the Container network layer: `deniedHosts` supports host, IP, and CIDR blocks; allowlists become deny-by-default; programmable outbound handlers can inspect or reject HTTP/HTTPS requests. `deniedHosts` is evaluated before outbound handlers. [Container outbound traffic](https://developers.cloudflare.com/containers/platform-details/outbound-traffic/#block-or-allow-traffic-by-host) **[sourced]**

For arbitrary user-provided public images, a finite hostname allowlist may not be usable, so application-level DNS/IP/redirect checks remain necessary. Configure denied IPv4/IPv6 non-public ranges as defense in depth and test DNS rebinding/redirect cases. Do not set `enableInternet = false` without ensuring Neon TCP and every required API/R2 host remain reachable. **[analysis + rec]**

The 10 MB cap applies to **encoded bytes**. The existing 4096×4096 cap applies before full Pillow decode and limits decompression-bomb memory. A Container with GiBs of RAM has comfortable headroom for the worst allowed RGBA image plus WebP output, unlike a 128 MB Worker isolate. **[code + analysis]**

### 4.2 Python Worker using Pillow: **possible only after a rewrite; not recommended for this exact contract**

- Async httpx/aiohttp or the runtime `fetch()` API can retrieve a remote response, and streaming code can count bytes and cancel after 10 MiB. [Python Worker packages](https://developers.cloudflare.com/workers/languages/python/packages/#http-client-libraries) · [Workers Streams](https://developers.cloudflare.com/workers/runtime-apis/streams/) **[sourced]**
- Pillow is available through Pyodide, and the Python Worker filesystem can hold a temporary in-memory file. [Pyodide packages](https://pyodide.org/en/stable/usage/packages-in-pyodide.html) · [Python Worker filesystem](https://developers.cloudflare.com/workers/languages/python/stdlib/#in-memory-filesystem) **[sourced]**
- R2 upload should use the native R2 binding, which accepts streams/byte buffers, rather than the current synchronous boto3 client. [R2 Worker API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/) **[sourced]**

However, Pillow needs the encoded input buffered/seekable and then allocates decoded pixels and output. At the app's maximum 4096×4096 dimensions, 128 MB per isolate is too little safety margin. The current implementation also calls Pillow via `asyncio.to_thread`, which is nonfunctional. Therefore this is not a reliable lift-and-shift and would need lower pixel limits, strict concurrency control, no thread offload, native bindings, and load/memory tests. **[code + sourced + analysis]**

### 4.3 Worker with Cloudflare Images binding: **best Worker-native equivalent to Pillow normalization**

The Images binding accepts a `ReadableStream` from `fetch()`, request bodies, or R2, decodes/transforms it outside the application's own Pillow path, and can output WebP. Binding input is capped by Cloudflare at 20 MB, so the application must still enforce its stricter 10 MB streaming limit. [Images binding](https://developers.cloudflare.com/images/optimization/binding/) · [Images limits/formats](https://developers.cloudflare.com/images/get-started/limits/#limits-for-the-images-binding) **[sourced]**

A Worker-native flow could be:

`validated fetch stream → 10 MiB counting transform → Images .info()/WebP output → R2 binding → Postgres`

This is a suitable **equivalent**, but it is not guaranteed to reproduce every current Pillow policy automatically. The Worker must still enforce the allowlist (PNG/JPEG/WebP only), reject animation, enforce 4096×4096, decide metadata/EXIF behavior, and preserve DB/R2 compensation. It also does nothing for FFmpeg, WebSockets/job state, or the rest of the backend. **[analysis]**

### 4.4 Bottom line for the remote-fetch feature

| Target | SSRF controls | 10 MB streaming cap | Normalize | R2 upload | Result |
|---|---|---|---|---|---|
| Container + current Python libraries | Yes: app checks + Container egress policy | Yes | Existing Pillow code | Existing boto3 | **Recommended; straightforward** |
| Python Worker + Pillow | Must be rewritten | Yes | Technically available, memory-risky at 4096² | Rewrite to binding | **Not recommended at current limits** |
| Worker + Images binding | Must be written in Worker | Yes, before 20 MB binding cap | Cloudflare Images WebP equivalent | Native binding | **Good edge microservice after policy validation** |

---

## 5. Practical deployment shape

### Phase A — MVP with no application-code changes

```text
Browser
  │ HTTP + WebSocket
  ▼
Cloudflare Worker (thin router; one fixed Container ID)
  ▼
Cloudflare Container: existing FastAPI/Uvicorn image
  ├── Neon Postgres (existing DATABASE_URL / psycopg2)
  ├── R2 S3 endpoint (existing boto3)
  ├── external AI/TTS APIs
  └── ephemeral local scratch → FFmpeg → upload final artifact to R2
```

Configuration recommendations: **[rec]**

- Start with `standard-2`; measure FFmpeg wall time, peak RSS, and scratch use before downsizing/upgrading.
- Set `defaultPort = 8000` and route every HTTP/WebSocket request to a stable ID such as `viratrot-mvp`.
- Keep one instance only. Random routing would break process-local jobs/WebSockets.
- Choose a long `sleepAfter` or lifecycle policy relative to maximum render duration; verify experimentally that an HTTP 202 followed by no client traffic does not stop an active Python background job.
- Enable Container/Worker observability and log job IDs, project IDs, stage transitions, FFmpeg exit status, duration, output bytes, and peak disk use.
- Keep only scratch/cache data locally; R2/Postgres remain sources of truth.
- Add Container `deniedHosts` rules for non-public networks before enabling remote URL ingestion.

### Phase B — first reliability changes

```text
API Container → Postgres job row → Queue/Workflow → Render Container
      │                                      │
      └──────── Durable Object/WebSocket status fan-out ────────┘
```

- Persist every job transition/result/error in Postgres.
- Enqueue only IDs and object keys; Queues messages are limited to 128 KB and are at-least-once.
- Make output keys deterministic per attempt or use idempotency keys.
- Acknowledge completion only after R2 upload and DB commit.
- Let WebSocket clients reconnect and reconstruct current status from durable state.
- Scale render Containers independently after eliminating process-local ownership assumptions.

**[rec]**

---

## 6. Decision

**Use Cloudflare Containers if the goal is to keep this backend on Cloudflare with minimal work.** It is now GA and is the only Cloudflare compute product that directly satisfies CPython + native wheels + FFmpeg subprocesses + GiB-scale scratch/RAM + WebSockets. The existing backend image is close to deployable; the required immediate addition is Cloudflare's Worker/Container routing configuration, not a Python rewrite. **[sourced + analysis]**

For an MVP, a fixed single Container instance is reasonable if occasional interrupted jobs can be retried manually. It preserves current behavior but not durable-job guarantees. Before production or horizontal scaling, move process-local progress and `BackgroundTasks` into durable Postgres/Queue/Workflow/DO coordination. **[rec]**

**Do not port the whole app to Python Workers.** FastAPI and Pillow support can make that option look closer than it is, but FFmpeg/subprocess, thread offload, synchronous clients, 128 MB memory, in-memory filesystem, background duration, and isolate-local job state are decisive blockers. **[analysis]**

**The remote-image fetch requirement can run safely in the Container** with application SSRF validation, a streaming 10 MiB counter, current Pillow normalization, and existing boto3 R2 upload. A Worker + Cloudflare Images + R2 binding is a credible future edge equivalent, but would be a separate implementation and must reproduce the app's type/animation/dimension/metadata and SSRF policies explicitly. **[analysis + rec]**

---

## 7. Primary sources

### Cloudflare

- [Containers overview](https://developers.cloudflare.com/containers/)
- [Containers and Sandboxes are now generally available (2026-04-13)](https://developers.cloudflare.com/changelog/post/2026-04-13-containers-sandbox-ga/)
- [Container lifecycle, runtime, shutdown, and ephemeral disk](https://developers.cloudflare.com/containers/platform-details/architecture/)
- [Container limits and instance types](https://developers.cloudflare.com/containers/platform-details/limits/)
- [Container scaling and routing](https://developers.cloudflare.com/containers/platform-details/scaling-and-routing/)
- [Container FAQ](https://developers.cloudflare.com/containers/faq/)
- [Container outbound traffic controls](https://developers.cloudflare.com/containers/platform-details/outbound-traffic/)
- [Container WebSocket forwarding](https://developers.cloudflare.com/containers/examples/websocket/)
- [Container pricing](https://developers.cloudflare.com/containers/pricing/)
- [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Workers Context / `waitUntil`](https://developers.cloudflare.com/workers/runtime-apis/context/#waituntil)
- [Python Workers overview (beta)](https://developers.cloudflare.com/workers/languages/python/)
- [Python Worker packages](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Python Worker standard library and in-memory filesystem](https://developers.cloudflare.com/workers/languages/python/stdlib/)
- [FastAPI on Python Workers](https://developers.cloudflare.com/workers/languages/python/packages/fastapi/)
- [Cloudflare Python ASGI adapter source](https://github.com/cloudflare/workers-py/blob/main/packages/runtime-sdk/src/asgi.py)
- [R2 Workers API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)
- [Hyperdrive (including Neon support)](https://developers.cloudflare.com/hyperdrive/)
- [Durable Objects overview](https://developers.cloudflare.com/durable-objects/)
- [Durable Object limits](https://developers.cloudflare.com/durable-objects/platform/limits/)
- [Durable Object WebSocket hibernation](https://developers.cloudflare.com/durable-objects/best-practices/websockets/)
- [Queues overview](https://developers.cloudflare.com/queues/)
- [Queues delivery guarantees](https://developers.cloudflare.com/queues/reference/delivery-guarantees/)
- [Queues limits](https://developers.cloudflare.com/queues/platform/limits/)
- [Workflows is GA (2025-04-07)](https://developers.cloudflare.com/changelog/post/2025-04-07-workflows-ga/)
- [Workflows limits](https://developers.cloudflare.com/workflows/reference/limits/)
- [Cloudflare Images binding](https://developers.cloudflare.com/images/optimization/binding/)
- [Cloudflare Images limits and formats](https://developers.cloudflare.com/images/get-started/limits/)

### Pyodide (runtime owner; first-party)

- [WebAssembly constraints](https://pyodide.org/en/stable/usage/wasm-constraints.html)
- [FAQ: threading, multiprocessing, subprocess](https://pyodide.org/en/stable/usage/faq.html#can-i-use-threading-multiprocessing-subprocess)
- [Packages included in Pyodide](https://pyodide.org/en/stable/usage/packages-in-pyodide.html)

### Repository evidence

- `backend/Dockerfile`, `backend/requirements.txt`
- `backend/main.py`, `backend/db.py`
- `backend/services/media_service.py`, `backend/services/progress_service.py`, `backend/services/editor_audio_service.py`
- `backend/storage/r2_backend.py`, `backend/storage/assets.py`
- `backend/backend_pipeline/audio_generation/{elevenLabs,minimax_tts}.py`
- `backend/backend_pipeline/video_assembly/ffMpeg.py`
