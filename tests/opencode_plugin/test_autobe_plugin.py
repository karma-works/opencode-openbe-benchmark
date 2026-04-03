"""Tests for OpenCode plugin integration with autobe_generate tool.

Verifies that the @hacr/opencode-autobe plugin:
1. Loads correctly in opencode
2. Exposes the autobe_generate tool
3. Model actually invokes the tool when given a backend-generation task
4. Tool is NOT available when plugin is disabled

Design notes:
- Uses POST /session/{id}/prompt_async (fire-and-forget, 204) to start the agentic loop.
- Subscribes to GET /global/event (SSE) to detect events in real time.
- For "tool called" tests: aborts the session as soon as autobe_generate is seen in
  message.part.updated events — no need to wait for the full AutoBE pipeline (~10 min).
- For "files generated" tests: waits for session.status=idle (full pipeline run).
- Tool calls in OpenCode appear as parts with type="tool" and the tool name in the "tool"
  field (e.g. part["tool"] == "autobe_generate"), not part["name"].

Results are appended to test_results/opencode_plugin/test_outcomes.csv
and SVG charts are generated after the test session completes.
"""

import json
import queue
import threading
import time
from pathlib import Path

import pytest
import requests

from tests.opencode_plugin.conftest import (
    AUTOBE_MODEL,
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

# Explicit instruction to use the tool — reduces false negatives from models
# that would otherwise generate the code themselves without invoking autobe_generate.
TODO_APP_PROMPT = (
    "You MUST use the autobe_generate tool (do not write any code yourself). "
    "Call autobe_generate with this description: "
    "'NestJS + Prisma backend for a TODO app with users and todos. "
    "Users can create, read, update, and delete their todos.'"
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


def abort_session(base_url: str, session_id: str) -> None:
    try:
        requests.post(f"{base_url}/session/{session_id}/abort", timeout=5)
    except Exception:
        pass


def send_prompt_watch_tool(
    base_url: str,
    session_id: str,
    prompt: str,
    model: str = TEST_MODEL,
    timeout: float = 120.0,
    abort_on_tool_call: bool = False,
) -> tuple[list[str], list[dict]]:
    """Send a prompt via prompt_async and watch the SSE stream.

    Returns (tool_names_called, final_messages).

    If abort_on_tool_call=True, aborts the session as soon as any tool call
    part is seen in the SSE stream — useful for quickly confirming tool
    invocation without waiting for the full pipeline to complete.

    Otherwise waits for session.status=idle (full agentic loop completion).

    Tool calls in OpenCode appear as message.part.updated events where:
      part["type"] == "tool"  and  part["tool"] == <tool_name>
    """
    done_q: queue.Queue[str] = queue.Queue()
    tool_names: list[str] = []

    def sse_listener() -> None:
        try:
            with requests.get(
                f"{base_url}/global/event",
                stream=True,
                timeout=timeout + 10,
            ) as resp:
                for raw in resp.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
                    if not line.startswith("data:"):
                        continue
                    try:
                        ev = json.loads(line[5:])
                        payload = ev.get("payload", {})
                        props = payload.get("properties", {})
                        ptype = payload.get("type", "")

                        if ptype == "message.part.updated":
                            part = props.get("part", {})
                            # Tool calls: type="tool", tool name in part["tool"]
                            if part.get("type") == "tool":
                                tool_name = part.get("tool", "")
                                if tool_name and tool_name not in tool_names:
                                    tool_names.append(tool_name)
                                    if abort_on_tool_call:
                                        abort_session(base_url, session_id)
                                        done_q.put("tool_called")
                                        return

                        if (
                            ptype == "session.status"
                            and props.get("sessionID") == session_id
                            and props.get("status", {}).get("type") == "idle"
                        ):
                            done_q.put("idle")
                            return

                    except Exception:
                        pass
        except Exception as exc:
            done_q.put(f"error:{exc}")

    t = threading.Thread(target=sse_listener, daemon=True)
    t.start()
    time.sleep(0.3)  # allow SSE connection to establish

    provider_id, model_id = model.split("/", 1)
    resp = requests.post(
        f"{base_url}/session/{session_id}/prompt_async",
        json={
            "parts": [{"type": "text", "text": prompt}],
            "model": {"providerID": provider_id, "modelID": model_id},
        },
        timeout=10,
    )
    resp.raise_for_status()

    result = done_q.get(timeout=timeout)
    if result.startswith("error:"):
        raise RuntimeError(f"SSE listener error: {result}")

    messages = get_session_messages(base_url, session_id)
    return tool_names, messages


def get_session_messages(base_url: str, session_id: str) -> list[dict]:
    resp = requests.get(
        f"{base_url}/session/{session_id}/message",
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_tool_calls(messages: list[dict]) -> list[dict]:
    """Extract all tool-call parts from a message list.

    OpenCode stores tool calls as parts with type="tool" and the tool
    name in the "tool" field. The "name" field is not populated.
    """
    tool_calls = []
    for msg in messages:
        for part in msg.get("parts", []):
            if part.get("type") == "tool":
                tool_calls.append(part)
            # Older or alternative format
            if part.get("type") == "tool_use":
                tool_calls.append(part)
            for sub in part.get("subparts", []):
                if sub.get("type") in ("tool", "tool_use"):
                    tool_calls.append(sub)
    return tool_calls


def is_autobe_call(part: dict) -> bool:
    return (
        part.get("tool") == "autobe_generate"
        or part.get("name") == "autobe_generate"
        or part.get("tool_name") == "autobe_generate"
    )


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

        append_outcomes([
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=True,
                test_class="TestPluginToolAvailability",
                test_name="test_autobe_tool_available_with_plugin",
                status=status,
                duration_s=time.time() - t0,
                tool_calls_count=tool_count,
                autobe_calls_count=autobe_count,
                files_generated=0,
                error_message=error,
                session_id=session_id,
                work_dir=work_dir,
            )
        ])

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

        append_outcomes([
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
        ])


# ---------------------------------------------------------------------------
# Tests: Tool Execution (agentic — waits for real model response via SSE)
# ---------------------------------------------------------------------------


class TestPluginToolExecution:
    def test_autobe_tool_called(self, opencode_with_plugin):
        """Verify the model invokes autobe_generate.

        Aborts the session as soon as the tool call is detected — no need to
        wait for the full AutoBE pipeline (which can take 10+ minutes).
        """
        base_url, work_dir = opencode_with_plugin
        t0 = time.time()
        session_id = ""
        tool_count = 0
        autobe_count = 0
        error = ""
        status = "pass"

        try:
            session_id = create_session(base_url, "TODO App Test")
            tool_names, messages = send_prompt_watch_tool(
                base_url,
                session_id,
                TODO_APP_PROMPT,
                abort_on_tool_call=True,
                timeout=120.0,
            )
            tool_calls = get_tool_calls(messages)
            tool_count = len(tool_calls)
            autobe_count = sum(1 for n in tool_names if n == "autobe_generate")
            assert autobe_count > 0, (
                f"autobe_generate not called. Tools seen via SSE: {tool_names}; "
                f"tools in messages: {[tc.get('tool') or tc.get('name') for tc in tool_calls]}"
            )
        except Exception as e:
            status = "fail"
            error = str(e)

        append_outcomes([
            OutcomeRecord(
                model=TEST_MODEL,
                plugin_enabled=True,
                test_class="TestPluginToolExecution",
                test_name="test_autobe_tool_called",
                status=status,
                duration_s=time.time() - t0,
                tool_calls_count=tool_count,
                autobe_calls_count=autobe_count,
                files_generated=0,
                error_message=error,
                session_id=session_id,
                work_dir=work_dir,
            )
        ])

    def test_autobe_tool_generates_files(self, opencode_with_plugin):
        """Verify the full AutoBE pipeline runs and produces files.

        Waits for session.status=idle (pipeline completion). Requires
        AUTOBE_API_KEY / AUTOBE_BASE_URL to be configured so the plugin
        can reach an AI vendor. Uses a longer timeout (20 min).
        """
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
            tool_names, messages = send_prompt_watch_tool(
                base_url,
                session_id,
                TODO_APP_PROMPT,
                abort_on_tool_call=False,
                timeout=1200.0,  # 20 min — AutoBE pipeline is slow
            )
            tool_calls = get_tool_calls(messages)
            tool_count = len(tool_calls)
            autobe_count = sum(1 for n in tool_names if n == "autobe_generate")
            files = count_files(work_dir)
            assert files > 0, (
                f"No files generated in {work_dir}. "
                f"autobe_calls={autobe_count}, model={AUTOBE_MODEL}"
            )
        except Exception as e:
            status = "fail"
            error = str(e)

        append_outcomes([
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
        ])

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
            # Short prompt that doesn't ask the model to generate code —
            # just check whether autobe_generate is available.
            # A yes/no answer avoids the model spending minutes writing code.
            prompt = (
                "Is the autobe_generate tool available? "
                "If yes, call it with description='blog'. "
                "If not, reply with exactly: 'tool unavailable'."
            )
            tool_names, messages = send_prompt_watch_tool(
                base_url,
                session_id,
                prompt,
                abort_on_tool_call=False,
                timeout=120.0,
            )
            tool_calls = get_tool_calls(messages)
            tool_count = len(tool_calls)
            autobe_count = sum(1 for n in tool_names if n == "autobe_generate")
            assert autobe_count == 0, (
                f"autobe_generate should NOT be called without plugin. "
                f"Tools seen: {tool_names}"
            )
        except Exception as e:
            status = "fail"
            error = str(e)

        append_outcomes([
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
        ])
