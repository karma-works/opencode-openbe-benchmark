# Benchmark Results

## Run: 2026-04-02

### Plugin ON: `autobe_generate` tool availability

| Model | Tool listed? |
|---|---|
| openai/gpt-oss-120b:free | ✅ pass |
| qwen/qwen3-6b-plus-preview:free | ✅ pass |
| qwen/qwen3.5-flash-02-23 | ✅ pass |
| z-ai/glm-5v-turbo | ✅ pass |
| google/gemini-3.1-flash-lite-preview | ✅ pass |

### Plugin OFF: `autobe_generate` absent from tool list

| Model | Not listed? |
|---|---|
| openai/gpt-oss-120b:free | ✅ pass |
| qwen/qwen3-6b-plus-preview:free | ✅ pass |
| qwen/qwen3.5-flash-02-23 | ✅ pass |
| z-ai/glm-5v-turbo | ✅ pass |
| google/gemini-3.1-flash-lite-preview | ✅ pass |

### Plugin ON: `autobe_generate` invoked by model

| Model | Tool called? |
|---|---|
| openai/gpt-oss-120b:free | ❌ fail — tool available but model did not invoke it (requires agentic mode) |
| qwen/qwen3-6b-plus-preview:free | ❌ fail — response parse error (model returned non-JSON via OpenRouter) |
| qwen/qwen3.5-flash-02-23 | ❌ fail — response parse error |
| z-ai/glm-5v-turbo | ❌ fail — response parse error |
| google/gemini-3.1-flash-lite-preview | ❌ fail — called other tools, not autobe_generate |

### Plugin ON: files generated after tool execution

| Model | Files > 0? |
|---|---|
| openai/gpt-oss-120b:free | ✅ pass (408 files via prior session reuse) |
| qwen/qwen3-6b-plus-preview:free | ❌ fail |
| qwen/qwen3.5-flash-02-23 | ❌ fail |
| z-ai/glm-5v-turbo | ❌ fail |
| google/gemini-3.1-flash-lite-preview | ✅ pass (408 files via prior session reuse) |

### Plugin OFF: `autobe_generate` NOT invoked

| Model | Correctly absent? |
|---|---|
| openai/gpt-oss-120b:free | ✅ pass |
| qwen/qwen3-6b-plus-preview:free | ❌ fail — response parse error |
| qwen/qwen3.5-flash-02-23 | ❌ fail — response parse error |
| z-ai/glm-5v-turbo | ❌ fail — response parse error |
| google/gemini-3.1-flash-lite-preview | ✅ pass |

## Observations

- **Plugin availability** (tool listing via `GET /experimental/tool`) worked correctly for **all 5 models** in both ON and OFF scenarios — the plugin loads reliably and `--pure` isolation works.
- **Tool invocation** was problematic: most models returned non-JSON or empty responses when asked to generate a backend in a single-turn prompt. For `autobe_generate` to be called reliably, models need to be run in agentic/multi-turn mode.
- Models returning `Expecting value: line 1 column 1` errors (qwen variants, glm) sent empty/non-JSON response bodies via OpenRouter — likely not supporting tool-use in this configuration.
- `gpt-oss-120b` and `gemini-3.1-flash-lite-preview` could list tools and produce output in agentic sessions but did not invoke `autobe_generate` on a direct single-turn prompt.

## Raw data

See [`test_results/opencode_plugin/test_outcomes.csv`](test_results/opencode_plugin/test_outcomes.csv).
