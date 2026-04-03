"""Shared fixtures for OpenCode plugin tests."""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

from tests.opencode_plugin.chart_generator import generate_all_charts


BENCHMARKS_DIR = Path(__file__).resolve().parent.parent.parent
OPENCODE_BIN = os.environ.get("OPENCODE_BIN", "opencode")
PLUGIN_PACKAGE = os.environ.get("PLUGIN_PACKAGE", "@hacr/opencode-autobe")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TEST_MODEL = os.environ.get("TEST_MODEL", "openrouter/openai/gpt-4.1-mini")
SERVER_HOST = "127.0.0.1"
BASE_PORT = 18932

# AutoBE plugin API key — defaults to OpenRouter so one key covers both OpenCode and AutoBE.
# The plugin also accepts ANTHROPIC_API_KEY or OPENAI_API_KEY directly.
AUTOBE_API_KEY = os.environ.get("AUTOBE_API_KEY") or OPENROUTER_API_KEY
AUTOBE_BASE_URL = os.environ.get("AUTOBE_BASE_URL", "https://openrouter.ai/api/v1")
AUTOBE_MODEL = os.environ.get("AUTOBE_MODEL", "openai/gpt-4.1-mini")


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    """Regenerate all charts after the test session completes."""
    if session.config.getoption("collectonly"):
        return
    try:
        paths = generate_all_charts()
        for name, path in paths.items():
            print(f"\n  Chart: {name} -> {path}")
    except Exception as e:
        print(f"\n  Warning: chart generation failed: {e}")


def wait_for_server(url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(f"{url}/global/health", timeout=2)
            if resp.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    return False


def write_base_config(work_dir: str) -> None:
    """Write a minimal opencode.json with provider config but no plugin."""
    config = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "openrouter": {
                "options": {"apiKey": "{env:OPENROUTER_API_KEY}"},
            }
        },
        "mode": {"build": {"model": TEST_MODEL}},
    }
    (Path(work_dir) / "opencode.json").write_text(json.dumps(config, indent=2))


def install_plugin(work_dir: str, package: str = PLUGIN_PACKAGE) -> None:
    """Install an opencode plugin via `opencode plugin <package>`."""
    result = subprocess.run(
        [OPENCODE_BIN, "plugin", package],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"opencode plugin install failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )


def start_opencode_server(
    cwd: str,
    port: int = BASE_PORT,
    env_overrides: dict | None = None,
    pure: bool = False,
) -> subprocess.Popen:
    env = os.environ.copy()
    if OPENROUTER_API_KEY:
        env["OPENROUTER_API_KEY"] = OPENROUTER_API_KEY
    # Pass autobe plugin credentials so the tool can call the AI vendor.
    if AUTOBE_API_KEY:
        env["AUTOBE_API_KEY"] = AUTOBE_API_KEY
    if AUTOBE_BASE_URL:
        env["AUTOBE_BASE_URL"] = AUTOBE_BASE_URL
    if AUTOBE_MODEL:
        env["AUTOBE_MODEL"] = AUTOBE_MODEL
    if env_overrides:
        env.update(env_overrides)

    cmd = [OPENCODE_BIN, "serve", "--port", str(port), "--hostname", SERVER_HOST]
    if pure:
        cmd.append("--pure")

    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://{SERVER_HOST}:{port}"
    if not wait_for_server(base_url):
        proc.kill()
        stdout, stderr = proc.communicate(timeout=5)
        raise RuntimeError(
            f"opencode serve failed to start.\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )
    return proc


@pytest.fixture(scope="module")
def opencode_server_with_plugin(tmp_path_factory):
    work_dir = str(tmp_path_factory.mktemp("opencode_with_plugin"))
    write_base_config(work_dir)
    install_plugin(work_dir)

    proc = start_opencode_server(work_dir, port=BASE_PORT)
    base_url = f"http://{SERVER_HOST}:{BASE_PORT}"
    try:
        yield base_url, work_dir
    finally:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture(scope="module")
def opencode_server_without_plugin(tmp_path_factory):
    work_dir = str(tmp_path_factory.mktemp("opencode_without_plugin"))
    write_base_config(work_dir)

    proc = start_opencode_server(work_dir, port=BASE_PORT + 1, pure=True)
    base_url = f"http://{SERVER_HOST}:{BASE_PORT + 1}"
    try:
        yield base_url, work_dir
    finally:
        proc.kill()
        proc.wait(timeout=10)
