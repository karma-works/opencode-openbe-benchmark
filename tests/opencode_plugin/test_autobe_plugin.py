"""Tests for OpenCode plugin integration with autobe_generate tool.

Verifies that the @hacr/opencode-autobe plugin:
1. Loads correctly in opencode
2. Exposes the autobe_generate tool
3. Can execute the tool and produce expected output
4. Tool is NOT available when plugin is disabled

Results are appended to test_results/opencode_plugin/test_outcomes.csv
and SVG charts are generated after the test session completes.
"""

import time
from pathlib import Path

import pytest
import requests

from tests.opencode_plugin.conftest import (
    BASE_PORT,
    SERVER_HOST,
    TEST_MODEL,
    install_plugin,
    start_opencode_server,
    write_base_config,
    wait_for_server,
)
from tests.opencode_plugin.reporter import OutcomeRecord, append_outcomes


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BENCHMARKS_DIR = Path(__file__).resolve().parent.parent.parent
TODO_APP_PROMPT = (
    "Generate a NestJS + Prisma backend for a TODO app with users and todos. "
    "Users can create, read, update, and delete their todos. "
    "Use the autobe_generate tool to create this backend."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def list_tools(base_url: str, model: str = TEST_MODEL) -> list[dict]:
    provider_id, model_id = model.split("/", 1)
    resp = requests.get(
        f"{base_url}/experimental/tool",
        params={"provider": provider_id, "model": model_id},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def create_session(base_url: str, title: str = "Test Session") -> str:
    resp = requests.post(
        f"{base_url}/session",
        json={"title": title},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def send_prompt(
    base_url: str,
    session_id: str,
    prompt: str,
    model: str = TEST_MODEL,
    timeout: float = 300.0,
) -> dict:
    provider_id, model_id = model.split("/", 1)
    resp = requests.post(
        f"{base_url}/session/{session_id}/message",
        json={
            "parts": [{"type": "text", "text": prompt}],
            "model": {"providerID": provider_id, "modelID": model_id},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def get_session_messages(base_url: str, session_id: str) -> list[dict]:
    resp = requests.get(
        f"{base_url}/session/{session_id}/message",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_tool_calls(messages: list[dict]) -> list[dict]:
    tool_calls = []
    for msg in messages:
        for part in msg.get("parts", []):
            if part.get("type") == "tool":
                tool_calls.append(part)
            if part.get("type") == "tool_use":
                tool_calls.append(part)
            if part.get("type") == "assistant":
                for sub in part.get("subparts", []):
                    if sub.get("type") in ("tool", "tool_use"):
                        tool_calls.append(sub)
    return tool_calls


def count_files(work_dir: str) -> int:
    p = Path(work_dir)
    return len(
        list(p.glob("**/*.ts"))
        + list(p.glob("**/*.prisma"))
        + list(p.glob("**/*.json"))
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def opencode_with_plugin(tmp_path_factory):
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
def opencode_without_plugin(tmp_path_factory):
    work_dir = str(tmp_path_factory.mktemp("opencode_without_plugin"))
    write_base_config(work_dir)

    proc = start_opencode_server(work_dir, port=BASE_PORT + 1, pure=True)
    base_url = f"http://{SERVER_HOST}:{BASE_PORT + 1}"
    try:
        yield base_url, work_dir
    finally:
        proc.kill()
        proc.wait(timeout=10)


# ---------------------------------------------------------------------------
# Tests: Tool Availability
# ---------------------------------------------------------------------------


class TestPluginToolAvailability:
    def test_autobe_tool_available_with_plugin(self, opencode_with_plugin):
        base_url, work_dir = opencode_with_plugin
        t0 = time.time()
        session_id = ""
        tool_count = 0
        autobe_count = 0
        files = 0
        error = ""
        status = "pass"

        try:
            tools = list_tools(base_url)
            tool_ids = [t.get("id", "") for t in tools]
            assert "autobe_generate" in tool_ids
            tool_count = len(tools)
            autobe_count = 1
        except Exception as e:
            status = "fail"
            error = str(e)

        outcomes = [
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=True,
                test_class="TestPluginToolAvailability",
                test_name="test_autobe_tool_available_with_plugin",
                status=status,
                duration_s=time.time() - t0,
                tool_calls_count=tool_count,
                autobe_calls_count=autobe_count,
                files_generated=files,
                error_message=error,
                session_id=session_id,
                work_dir=work_dir,
            )
        ]
        append_outcomes(outcomes)

    def test_autobe_tool_not_available_without_plugin(self, opencode_without_plugin):
        base_url, work_dir = opencode_without_plugin
        t0 = time.time()
        error = ""
        status = "pass"

        try:
            tools = list_tools(base_url)
            tool_ids = [t.get("id", "") for t in tools]
            assert "autobe_generate" not in tool_ids
        except Exception as e:
            status = "fail"
            error = str(e)

        outcomes = [
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=False,
                test_class="TestPluginToolAvailability",
                test_name="test_autobe_tool_not_available_without_plugin",
                status=status,
                duration_s=time.time() - t0,
                error_message=error,
                work_dir=work_dir,
            )
        ]
        append_outcomes(outcomes)


# ---------------------------------------------------------------------------
# Tests: Tool Execution
# ---------------------------------------------------------------------------


class TestPluginToolExecution:
    def test_autobe_tool_called(self, opencode_with_plugin):
        base_url, work_dir = opencode_with_plugin
        t0 = time.time()
        session_id = ""
        tool_count = 0
        autobe_count = 0
        files = 0
        error = ""
        status = "pass"

        try:
            session_id = create_session(base_url, "TODO App Test")
            send_prompt(base_url, session_id, TODO_APP_PROMPT)
            messages = get_session_messages(base_url, session_id)
            tool_calls = get_tool_calls(messages)
            tool_count = len(tool_calls)
            autobe_calls = [
                tc
                for tc in tool_calls
                if tc.get("name") == "autobe_generate"
                or tc.get("tool_name") == "autobe_generate"
            ]
            autobe_count = len(autobe_calls)
            assert autobe_count > 0, (
                f"autobe_generate not called. Found: "
                f"{[tc.get('name') or tc.get('tool_name') for tc in tool_calls]}"
            )
        except Exception as e:
            status = "fail"
            error = str(e)

        outcomes = [
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=True,
                test_class="TestPluginToolExecution",
                test_name="test_autobe_tool_called",
                status=status,
                duration_s=time.time() - t0,
                tool_calls_count=tool_count,
                autobe_calls_count=autobe_count,
                files_generated=files,
                error_message=error,
                session_id=session_id,
                work_dir=work_dir,
            )
        ]
        append_outcomes(outcomes)

    def test_autobe_tool_generates_files(self, opencode_with_plugin):
        base_url, work_dir = opencode_with_plugin
        t0 = time.time()
        session_id = ""
        tool_count = 0
        autobe_count = 0
        files = 0
        error = ""
        status = "pass"

        try:
            session_id = create_session(base_url, "TODO App Files")
            send_prompt(base_url, session_id, TODO_APP_PROMPT)
            messages = get_session_messages(base_url, session_id)
            tool_calls = get_tool_calls(messages)
            tool_count = len(tool_calls)
            autobe_calls = [
                tc
                for tc in tool_calls
                if tc.get("name") == "autobe_generate"
                or tc.get("tool_name") == "autobe_generate"
            ]
            autobe_count = len(autobe_calls)
            files = count_files(work_dir)
            assert files > 0, f"No files generated in {work_dir}"
        except Exception as e:
            status = "fail"
            error = str(e)

        outcomes = [
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=True,
                test_class="TestPluginToolExecution",
                test_name="test_autobe_tool_generates_files",
                status=status,
                duration_s=time.time() - t0,
                tool_calls_count=tool_count,
                autobe_calls_count=autobe_count,
                files_generated=files,
                error_message=error,
                session_id=session_id,
                work_dir=work_dir,
            )
        ]
        append_outcomes(outcomes)

    def test_autobe_tool_not_called_without_plugin(self, opencode_without_plugin):
        base_url, work_dir = opencode_without_plugin
        t0 = time.time()
        session_id = ""
        tool_count = 0
        autobe_count = 0
        error = ""
        status = "pass"

        try:
            session_id = create_session(base_url, "No Plugin Test")
            prompt = (
                "Generate a NestJS + Prisma backend for a simple blog. "
                "Use the autobe_generate tool if available."
            )
            send_prompt(base_url, session_id, prompt)
            messages = get_session_messages(base_url, session_id)
            tool_calls = get_tool_calls(messages)
            tool_count = len(tool_calls)
            autobe_calls = [
                tc
                for tc in tool_calls
                if tc.get("name") == "autobe_generate"
                or tc.get("tool_name") == "autobe_generate"
            ]
            autobe_count = len(autobe_calls)
            assert autobe_count == 0, (
                "autobe_generate should NOT be called without plugin"
            )
        except Exception as e:
            status = "fail"
            error = str(e)

        outcomes = [
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=False,
                test_class="TestPluginToolExecution",
                test_name="test_autobe_tool_not_called_without_plugin",
                status=status,
                duration_s=time.time() - t0,
                tool_calls_count=tool_count,
                autobe_calls_count=autobe_count,
                error_message=error,
                session_id=session_id,
                work_dir=work_dir,
            )
        ]
        append_outcomes(outcomes)
