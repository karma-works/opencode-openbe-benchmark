# opencode-openbe-benchmark

Benchmark suite that measures **tool-calling accuracy** of language models in [OpenCode](https://opencode.ai) programmatic mode — once with the [@hacr/opencode-autobe](https://www.npmjs.com/package/@hacr/opencode-autobe) plugin active and once without.

The plugin exposes `autobe_generate`, a single tool that runs the full [AutoBE](https://github.com/samchon/autobe) vibe-coding pipeline (requirements → DB schema → OpenAPI → NestJS + Prisma code). The benchmark checks whether models correctly discover and invoke the tool when given a plain-language backend request.

## What is measured

| Scenario | Question |
|---|---|
| **Plugin ON** | Does the model call `autobe_generate` when it is available? |
| **Plugin OFF** | Does the model correctly *not* call it when it isn't registered? |

Five tests run per model, per scenario:

| Test | Plugin | Assertion |
|---|---|---|
| `tool_available_with_plugin` | ON | `autobe_generate` appears in the tool list |
| `tool_not_available_without_plugin` | OFF | `autobe_generate` is absent from the tool list |
| `tool_called` | ON | model invokes `autobe_generate` on a backend-generation prompt |
| `tool_generates_files` | ON | files are written to disk after the tool runs |
| `tool_not_called_without_plugin` | OFF | model does not hallucinate an `autobe_generate` call |

## Prerequisites

- Python 3.12+
- [OpenCode CLI](https://opencode.ai/docs/installation) (`opencode` on `PATH`)
- Node.js 20+ (for the plugin's dependencies)
- An [OpenRouter](https://openrouter.ai) API key

## Setup

```bash
# 1. Clone
git clone https://github.com/karma-works/opencode-openbe-benchmark
cd opencode-openbe-benchmark

# 2. Configure API key
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY=...
```

No additional setup required — the benchmark installs `@hacr/opencode-autobe` from npm automatically when running tests.

## Running the benchmark

```bash
# Run all default models
./run_benchmark.sh

# Run a single model
./run_benchmark.sh openrouter/openai/gpt-4o

# Run multiple specific models
./run_benchmark.sh openrouter/openai/gpt-4o openrouter/google/gemini-2.0-flash
```

Results accumulate in `test_results/opencode_plugin/test_outcomes.csv`.  
SVG charts are written to `test_results/opencode_plugin/charts/` after every run.

## Results

See [RESULTS.md](RESULTS.md) for benchmark results across models.

## Project structure

```
opencode-openbe-benchmark/
├── .opencode/plugins/autobe/   OpenCode plugin (@hacr/opencode-autobe)
├── opencode.json               OpenCode config (plugin path + provider)
├── run_benchmark.sh            Main entry point
├── tests/
│   └── opencode_plugin/
│       ├── test_autobe_plugin.py   Pytest test suite
│       ├── conftest.py             Server fixtures
│       ├── reporter.py             CSV result writer
│       └── chart_generator.py      SVG chart generator
└── test_results/
    └── opencode_plugin/
        ├── test_outcomes.csv   Accumulated results (all models, all runs)
        └── charts/             SVG visualizations
```

## How it works

Each test run starts two `opencode serve` instances on localhost — one with the plugin loaded, one without — then drives them via the OpenCode HTTP API:

- `GET /experimental/tool` — check tool availability
- `POST /session` + `POST /session/{id}/message` — send prompts and capture tool calls
- `GET /session/{id}/message` — inspect the conversation for `autobe_generate` invocations
