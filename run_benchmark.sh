#!/usr/bin/env bash
# run_benchmark.sh — run the OpenCode + AutoBE plugin benchmark for one or more models.
#
# Usage:
#   ./run_benchmark.sh                          # run default model list
#   ./run_benchmark.sh openrouter/my/model      # run a single model
#   ./run_benchmark.sh model1 model2 model3     # run multiple models
#
# Results accumulate in test_results/opencode_plugin/test_outcomes.csv
# Charts are regenerated as SVG after each run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present
if [[ -f .env ]]; then
  # shellcheck disable=SC2046
  export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

if [[ -z "${OPENROUTER_API_KEY:-}" ]]; then
  echo "ERROR: OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in."
  exit 1
fi

# Default model list
DEFAULT_MODELS=(
  "openrouter/openai/gpt-oss-120b:free"
  "openrouter/qwen/qwen3-6b-plus-preview:free"
  "openrouter/qwen/qwen3.5-flash-02-23"
  "openrouter/z-ai/glm-5v-turbo"
  "openrouter/google/gemini-3.1-flash-lite-preview"
)

# Use CLI args if given, otherwise default list
if [[ $# -gt 0 ]]; then
  MODELS=("$@")
else
  MODELS=("${DEFAULT_MODELS[@]}")
fi

# Resolve Python
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
  echo "ERROR: python3 not found. Set PYTHON= or install Python 3.12+."
  exit 1
fi

# Install deps if not already in venv
if [[ ! -d .venv ]]; then
  echo "Creating virtualenv..."
  "$PYTHON" -m venv .venv
fi
source .venv/bin/activate
pip install -q -e .

echo ""
echo "========================================"
echo "  OpenCode + AutoBE Plugin Benchmark"
echo "  Models: ${#MODELS[@]}"
echo "========================================"
echo ""

PASS=0
FAIL=0
ERRORS=()

for MODEL in "${MODELS[@]}"; do
  echo "--- Model: $MODEL ---"
  if TEST_MODEL="$MODEL" python -m pytest tests/opencode_plugin/test_autobe_plugin.py -v --tb=short; then
    echo "  PASSED"
    ((PASS++)) || true
  else
    echo "  FAILED"
    ((FAIL++)) || true
    ERRORS+=("$MODEL")
  fi
  echo ""
done

echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
if [[ ${#ERRORS[@]} -gt 0 ]]; then
  echo "  Failed models:"
  for m in "${ERRORS[@]}"; do echo "    - $m"; done
fi
echo "  CSV:    test_results/opencode_plugin/test_outcomes.csv"
echo "  Charts: test_results/opencode_plugin/charts/"
echo "========================================"
