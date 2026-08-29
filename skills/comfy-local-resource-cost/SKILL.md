---
name: comfy-local-resource-cost
description: Local-resource cost guardrails for ComfyUI generation via the agent-comfy MCP server. Use BEFORE calling run_txt2img, run_txt2audio, run_txt2video, run_workflow or run_template, or before any ComfyUI image / picture / artwork / audio / music / speech / video / animation generation or rendering request — ComfyUI runs on the user's own machine and one job can saturate their GPU/CPU for minutes. Covers what a job costs (steps, resolution, batch size, duration), when a get_queue_status pre-flight check is mandatory versus advisory, how to tell the queue is already busy via get_queue_status and get_job, and what to do instead of queuing more work (cancel_job, small pilot runs, asking the user first).
---

# ComfyUI runs on the user's own machine

ComfyUI is not a remote API — it is a service the user runs locally, on the
same machine that is doing everything else: their editor, their builds, and
any other agent work. When you submit a generation job through this MCP
server, that job's GPU and CPU cost lands on the user's own hardware, right
now, competing with whatever else they are doing. A single careless job can
tie up the machine for minutes. Treat every call to `run_txt2img`,
`run_txt2audio`, `run_workflow`, or `run_template` as a "borrow this
person's computer" request, not a fire-and-forget API call. (`run_txt2video`
is the exception — see below: it is currently a stub that costs nothing.)

## Read this before your first generation call

- Jobs are **not free**: cost scales with steps, resolution, batch size, and
  (for audio) duration — see "What a job actually costs" below.
- **Mandatory** pre-flight: call `get_queue_status()` first for any
  hand-built video workflow (`run_txt2video` itself is currently a stub
  that always errors at zero cost — see below), any batched job,
  `steps > 30`, resolution above 1024x1024, or audio `seconds > 30`.
  **Advisory** (recommended, not required) for an ordinary cheap single
  image or short audio clip at or below those thresholds.
- Extra jobs **queue behind** the current one, they do not run in parallel —
  submitting more work never speeds anything up, it only makes the user wait
  longer.

## What a job actually costs

Hardware varies wildly — a 4090 and an integrated GPU are two orders of
magnitude apart. Treat every number below as an **order of magnitude**, not
a promise; use it to decide "seconds or minutes?", never to quote a user an
ETA.

| Job | Rough cost |
| --- | --- |
| 512x512, 20 steps, 1 image (the `run_txt2img` defaults) | seconds (roughly 1-30 s) |
| 1024x1024, 30 steps, 1 image | tens of seconds (roughly 10 s-2 min) |
| Batch of 8 at 1024x1024 | minutes (roughly 1-15 min) — ~linear in batch size |
| Audio, default 47 s at 20 steps (the `run_txt2audio` defaults) | tens of seconds to minutes — ~linear in `seconds` and `steps` |
| `run_txt2video` | none — it is currently a stub that always raises `NotImplementedError` and returns `{"error": ...}` immediately, before ever reaching ComfyUI |
| Hand-built video workflow (`run_workflow` / `run_template` graph with real video/animation nodes) | minutes to tens of minutes — the most expensive thing you can submit through this server by a wide margin; assume it is never cheap |

Scaling rules of thumb:

- ~linear in `steps`.
- ~linear in `batch_size`.
- ~linear in audio `seconds`.
- ~linear in **pixel count** — doubling both `width` and `height` is ~4x the
  cost, not 2x.
- CPU-only ComfyUI installs are 10-100x slower again. This MCP server has
  no way to detect GPU availability — if generation is unusually slow,
  assume a CPU-only or weak-GPU install and escalate every estimate above
  by one tier.

## How to tell the machine is already busy

Call `get_queue_status()` — it is a read-only probe that bypasses the
submission guard, so it is safe to call at any time, even while a job is
running. It returns `{"running": [...], "pending": [...]}`. Either list
being non-empty means ComfyUI is already busy.

Other signals of an already-loaded machine:

- `run_workflow` / `run_template` / `run_txt2img` / `run_txt2audio` return
  `timed_out: true` (with `state: "running"`) when the default 120-second
  wait expires before the job finishes — the job is still running, it just
  outlasted the wait. (`run_txt2video` is excluded: it is currently a stub
  that always returns `{"error": ...}` immediately, so it can never be
  `timed_out` or `state: "running"`.)
- Repeated `get_job(prompt_id)` polls keep returning `state: "running"` or
  `state: "queued"`.

## Pre-flight check: mandatory vs. advisory

Before submitting, call `get_config()` and check whether `comfy_url` points
at `localhost`/`127.0.0.1` — that confirms the same-machine case this skill
is about.

**Mandatory** — call `get_queue_status()` before submitting when any of
these hold:

- Any hand-built video workflow — a `run_workflow` / `run_template` graph
  containing real video/animation nodes. (`run_txt2video` itself is
  currently a stub: it always raises `NotImplementedError` and returns
  `{"error": ...}` immediately, before ever reaching ComfyUI, so it costs
  nothing and needs no pre-flight check.)
- `batch_size > 1` — `Txt2AudioParams.batch_size`, or an
  `EmptyLatentImage`/latent `batch_size > 1` inside a hand-built
  `run_workflow` graph. (`Txt2ImgParams` exposes no `batch_size` field at
  all, so image batching can only arrive via `run_workflow` /
  `run_template`.)
- `steps > 30`.
- Resolution above 1024x1024 (`width * height > 1024 * 1024`).
- Audio `seconds > 30`.

Because hand-built video graphs expose no steps/frames knob to keep them
cheap by construction, **every hand-built video workflow is unconditionally
in the mandatory tier** — real video generation is by far the most
expensive thing you can submit through this server.

**Advisory** — everything else: a single image at or below 1024x1024 with
`steps <= 30` and no batching (the 512x512 / steps 20 defaults sit squarely
here), or audio at `seconds <= 30`. Checking first is still a good habit,
but not required.

## Timeouts are not cancellations

`run_workflow`, `run_template`, `run_txt2img`, and `run_txt2audio` all
accept a `timeout` parameter (default `120.0` seconds) that bounds only how
long the tool call **waits**, not how long the job itself runs. (`run_txt2video`
also has a `timeout` parameter for signature consistency, but it never
matters: the tool is currently a stub that always errors immediately, so no
timeout ever elapses and nothing ever runs in the background for it.) When
the timeout expires, the response carries `state: "running"` and
`timed_out: true` — the job keeps running on the user's GPU/CPU in the
background, still consuming resources. A timeout is never a cancellation.

Once a job reaches `state: "running"`, there is **no way through this MCP
server to abort the in-flight GPU work**. `cancel_job(prompt_id)` only
removes a job that is still `state: "queued"` (pending) — the underlying
client posts a queue-delete request that is a no-op against a job already
running, and `cancel_job`'s own `{"cancelled": prompt_id}` response is
returned unconditionally, so it is **not confirmation the job actually
stopped**. For an already-running job, the only options are to wait it out
or keep polling with `get_job(prompt_id)` until `state` becomes
`"completed"` or `"error"`.

## What to do instead of queuing blindly

**Mandatory tier:**

- Call `get_queue_status()` first.
- If `running` or `pending` is non-empty, either wait for it to clear or ask
  the user before adding to the queue.
- Before committing the user to a minutes-long render (any hand-built video
  workflow, a large batch, a big image), ask them first rather than
  assuming it's fine.

**Advisory tier:**

- Just run it — one job at a time is the norm.
- Poll `get_job(prompt_id)` instead of resubmitting the same request.

**Always:**

- Start with a small pilot run at the defaults, confirm the prompt/model
  work as expected, then scale up steps/resolution/batch size/duration.
- Use `cancel_job(prompt_id)` to abandon work you no longer need **while it
  is still `state: "queued"` (pending)** — once a job is `state: "running"`
  it cannot be aborted through this server; you can only wait it out or
  poll `get_job(prompt_id)`.
- Never retry a failed job in a loop — each retry is a full-cost job again;
  diagnose the `error` field first.

## Related skills

For the actual workflow-building mechanics once you've confirmed a job is
worth submitting, see `comfy-image-workflows`, `comfy-audio-workflows`, and
`comfy-video-workflows`.
