---
name: comfy-template-selection
description: Decide which ComfyUI template to run and where to find it — covers the built-in txt2img_basic template (what it's good for, required models, rough cost/time) plus project-local templates under COMFYUI_PROJECT_TEMPLATES_DIR / .seretos/comfy/workflows, the API-format PARAM_* placeholder requirement for project files, and the project-overrides-built-in collision rule. Load this skill before calling run_template or get_template_params, or whenever the user asks which template to use, how to add a project-local template, or why a template of theirs isn't showing up.
---

# ComfyUI Template Selection Skill

Load this skill before choosing a template for `run_template`/`get_template_params`, or when the user asks "which template should I use", "how do I add my own template", or "why isn't my template showing up". It is a decision aid layered on top of `comfy-image-workflows` (and the audio/video equivalents) — those skills cover the mechanics of calling the tools; this one covers *which template* and *where it comes from*.

## How templates are discovered

`list_templates()` returns every discoverable template — built-in (shipped with this plugin) and project-local (authored by the user in this git repo) — tagged with an `origin`:

```
{"templates": [
  {"name": "txt2img_basic", "origin": "built-in"},
  {"name": "my_project_widget", "origin": "project"}
]}
```

`get_template_params(name)` and `run_template(name, params)` resolve the same way: built-in set first, then the project-local directory, with **the project-local file winning any name collision**. A project template named `txt2img_basic.json` fully replaces the built-in `txt2img_basic` at every call site — not an addition alongside it, a full override. There is no way to reach the shadowed built-in by name once a project file of the same stem exists; rename one of the two files if you need both.

## Built-in templates

Only one built-in template ships today. **This section must be updated whenever a new built-in template is added to the plugin** — do not let this list silently fall out of sync with the packaged set.

### `txt2img_basic`

- **Good for:** standard single-image text-to-image generation — a prompt, a checkpoint, and a KSampler pipeline with sane defaults. This is the default choice for "generate an image of X" requests that don't need a bespoke node graph.
- **Required models:** one checkpoint (`.safetensors`/`.ckpt`) capable of text-to-image generation, selected via `list_models()`. No LoRA, ControlNet, or upscaler is wired in.
- **Rough cost/time:** a single KSampler pass at default settings (512x512, ~20 steps) typically completes in a few seconds to a couple of minutes on consumer GPU hardware, depending on the user's local ComfyUI machine and chosen checkpoint size — there is no fixed SLA since ComfyUI runs on infrastructure this plugin does not control. Treat it as the cheapest, fastest built-in option; nothing else ships to compare it against yet.

## Project-local templates

Project-local templates let a repository ship its own ComfyUI workflows alongside the code that uses them, discoverable with zero manual setup in a fresh session.

### Where they live

Resolution order (see `comfy_plugin.config._resolve_project_templates_dir`):

1. `COMFYUI_PROJECT_TEMPLATES_DIR` env var, if set — used verbatim.
2. Otherwise, walk up from the current working directory looking for a `.git` directory; if found, the default is `<git-root>/.seretos/comfy/workflows`.
3. If neither resolves (no env var and no `.git` ancestor), the feature is disabled — `list_templates()` returns only built-ins, and `get_template_params`/`run_template` only resolve built-in names.

The directory only needs to exist on disk at call time — it is fine for it to be created after the plugin starts; the feature enables itself as soon as the directory appears.

### File format requirement

**Every file in the project templates directory must already be a valid API-format ComfyUI workflow JSON file, with `PARAM_*` placeholders in place of the values that should be substituted at run time** (the same placeholder convention as the built-in templates, e.g. `PARAM_STR_POSITIVE_PROMPT`, `PARAM_OPT_STR_NEGATIVE_PROMPT|default:`, `PARAM_SEED_SEED`). This plugin performs no format conversion and no validation beyond JSON parsing — a raw ComfyUI **UI-format** export (the `nodes`/`links`/positions shape you get from "Save" in the ComfyUI canvas) will not work as-is and needs manual conversion to the node-id-keyed `class_type`/`inputs` API format, with the values you want callers to supply replaced by `PARAM_*` placeholders, before it belongs in this directory.

Each file's stem name (filename without `.json`) is the template's discoverable name.

### Collision rule

A project-local template whose stem name matches a built-in template's name **wins**, at every call site (`list_templates`, `get_template_params`, `run_template`) — see "How templates are discovered" above. Use this deliberately to override a built-in's defaults for a specific project (e.g. a project-local `txt2img_basic.json` pinned to a house checkpoint), and be aware of it as a footgun if you didn't intend to shadow the built-in.

## Decision guide

- Generating a standard image with no special project requirements → `txt2img_basic` (built-in).
- The project ships its own curated workflow (a specific checkpoint, LoRA stack, or node graph tuned for this repo) → check `list_templates()` for an `origin: "project"` entry first; prefer it over building a custom graph from scratch.
- Nothing built-in or project-local fits → fall back to the custom graph path documented in `comfy-image-workflows` (`list_node_types` + `get_node_schema` + `run_workflow`).
- Adding a new project template → author API-format JSON with `PARAM_*` placeholders by hand (or convert a UI export) and drop it in the resolved project templates directory; no restart or registration step is needed beyond the directory existing.
