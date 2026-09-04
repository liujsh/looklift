from __future__ import annotations

import asyncio
import base64
import http.client
import json
import threading

from looklift.agent_adapter import AgentEvent, AgentEventKind, ScriptedAgentEvent
from looklift.agent_assembly import make_openai_adapter_factory
from looklift import config
from looklift.fake_agent_adapter import FakeAgentAdapter
from looklift.gui import agent_stream, api, server as gui_server
from looklift.provider_snapshot import ProviderProtocol, ProviderSnapshot
from looklift.session_store import SessionStore


def _body(**overrides):
    payload = {
        "run_id": "run-sse",
        "attempt_id": "attempt-1",
        "model": "gpt-test",
        "domain_pack": {
            "instructions": "只生成白盒候选，禁止正式提交。",
            "user_message": "自然提亮",
        },
        "proxy_jpeg": base64.b64encode(b"\xff\xd8\xff\xe0jpeg").decode(),
        "runtime_id": "fake",
    }
    payload.update(overrides)
    return payload


def _collect(streamer):
    frames: list[bytes] = []
    streamer(frames.append)
    return frames


def _sse(value: dict) -> bytes:
    return f"data: {json.dumps(value)}\n\n".encode()


def test_stream_route_emits_unique_terminal_via_sse(tmp_path, monkeypatch):
    agent_stream.clear_runtime_factories()
    agent_stream.register_runtime_factory(
        "fake",
        lambda: FakeAgentAdapter(
            [ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})]
        ),
    )
    try:
        status, content_type, streamer = api.ROUTES[
            ("POST", "/api/agent/runs/<id>/stream")
        ]({"params": {"id": "run-sse"}, "body": json.dumps(_body()).encode(), "content_type": "application/json", "query": {}})
        assert status == 200
        assert content_type == "text/event-stream"
        frames = _collect(streamer)
    finally:
        agent_stream.clear_runtime_factories()

    joined = b"".join(frames)
    assert b"event: harness" in joined
    parsed = [
        json.loads(line[len("data: "):])
        for frame in frames
        for line in frame.decode().splitlines()
        if line.startswith("data: ")
    ]
    types = [item["type"] for item in parsed]
    assert types[0] == "run_started"
    assert types[-1] == "run_finished"
    # 唯一终态：只有一条 run_finished/run_failed
    assert sum(t in {"run_finished", "run_failed"} for t in types) == 1
    assert [item["sequence"] for item in parsed] == list(range(1, len(parsed) + 1))


def test_stream_route_returns_400_for_bad_body(tmp_path, monkeypatch):
    status, body = api.ROUTES[("POST", "/api/agent/runs/<id>/stream")](
        {"params": {"id": "run-sse"}, "body": json.dumps({"runtime_id": "fake"}).encode(), "content_type": "application/json", "query": {}}
    )
    assert status == 400
    assert "Attempt 输入" in body["error"]

    status, body = api.ROUTES[("POST", "/api/agent/runs/<id>/stream")](
        {"params": {"id": "run-sse"}, "body": json.dumps(_body(runtime_id="")).encode(), "content_type": "application/json", "query": {}}
    )
    assert status == 400


def test_cancel_route_returns_202_and_sets_token(tmp_path, monkeypatch):
    status, body = api.ROUTES[("POST", "/api/agent/runs/<id>/cancel")](
        {"params": {"id": "run-cancel-token"}, "body": None, "content_type": "", "query": {}}
    )
    assert status == 202
    assert body["cancelled"] == "run-cancel-token"


class _BlockingAdapter:
    """先发出 run_started 后阻塞在 await 上，直到被取消。"""

    def __init__(self) -> None:
        self.cancelled = False

    async def start(self, run_input):
        yield AgentEvent(AgentEventKind.RUN_STARTED, run_input.run_id, run_input.attempt_id, 1, {})
        try:
            while not self.cancelled:
                await asyncio.sleep(0.02)
        except asyncio.CancelledError:
            raise

    async def cancel(self, run_id: str) -> None:
        self.cancelled = True

    async def dispose(self, run_id: str) -> None:
        await self.cancel(run_id)


def test_cancel_route_interrupts_blocking_stream_with_terminal(tmp_path, monkeypatch):
    adapter = _BlockingAdapter()
    agent_stream.clear_runtime_factories()
    agent_stream.register_runtime_factory("fake", lambda: adapter)
    try:
        status, content_type, streamer = api.ROUTES[
            ("POST", "/api/agent/runs/<id>/stream")
        ]({"params": {"id": "run-blocking"}, "body": json.dumps(_body(run_id="run-blocking")).encode(), "content_type": "application/json", "query": {}})
        assert status == 200
        frames: list[bytes] = []
        stop = threading.Event()

        def run():
            streamer(frames.append)
            stop.set()

        thread = threading.Thread(target=run)
        thread.start()
        # 等待流真正启动（出现第一帧）
        for _ in range(200):
            if frames:
                break
            threading.Event().wait(0.01)
        api.ROUTES[("POST", "/api/agent/runs/<id>/cancel")](
            {"params": {"id": "run-blocking"}, "body": None, "content_type": "", "query": {}}
        )
        assert stop.wait(3.0), "streamer 未在取消后退出"
        thread.join(timeout=1.0)
    finally:
        agent_stream.clear_runtime_factories()

    parsed = [
        json.loads(line[len("data: "):])
        for frame in frames
        for line in frame.decode().splitlines()
        if line.startswith("data: ")
    ]
    assert parsed[0]["type"] == "run_started"
    assert parsed[-1]["type"] == "run_failed"
    assert parsed[-1]["payload"]["code"] == "cancelled"
    assert sum(t in {"run_finished", "run_failed"} for t in [p["type"] for p in parsed]) == 1


def test_stream_route_requires_session_for_openai(tmp_path, monkeypatch):
    """openai-api 运行必须携带 session_id，缺失或会话无效时拒绝。"""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")

    status, body = api.ROUTES[("POST", "/api/agent/runs/<id>/stream")](
        {"params": {"id": "run-openai"}, "body": json.dumps(_body(run_id="run-openai", runtime_id="openai-api")).encode(), "content_type": "application/json", "query": {}}
    )
    assert status == 400
    assert "session_id" in body["error"]


def test_stream_route_api_mode_rejects_cli_runtime_without_fallback(tmp_path, monkeypatch):
    """API 模式显式传 CLI Runtime 必须拒绝，不得回退到本机 CLI。"""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    status, body = api.ROUTES[("POST", "/api/agent/runs/<id>/stream")](
        {
            "params": {"id": "run-openai"},
            "body": json.dumps(_body(
                run_id="run-openai",
                runtime_id="claude-code",
                execution_mode="api",
                cli_available=True,
            )).encode(),
            "content_type": "application/json",
            "query": {},
        }
    )
    assert status == 400
    assert "不一致" in body["error"]


def test_stream_route_wires_openai_from_session(tmp_path, monkeypatch):
    """openai-api 从会话解析基线/图片/版本，并走装配好的工厂流式执行。"""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    session = SessionStore().create_or_resume(
        str(tmp_path / "photo.jpg"),
        {"summary": "初始", "basic": {}, "tone_curve": [], "hsl": [], "color_grading": {}, "effects": {}},
    )

    captured = {}

    def fake_wire(**kwargs):
        captured.update(kwargs)
        return lambda: FakeAgentAdapter(
            [ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})]
        )

    monkeypatch.setattr(api, "_wire_openai_factory", fake_wire)
    body = _body(run_id="run-openai", runtime_id="openai-api", session_id=session.id)
    status, content_type, streamer = api.ROUTES[("POST", "/api/agent/runs/<id>/stream")](
        {"params": {"id": "run-openai"}, "body": json.dumps(body).encode(), "content_type": "application/json", "query": {}}
    )
    assert status == 200
    assert content_type == "text/event-stream"
    # 装配函数收到会话事实
    assert captured["baseline_analysis"]["summary"] == "初始"
    assert captured["base_version_id"] == session.current_version_id
    assert captured["image_path"] == session.image_path
    frames = _collect(streamer)
    parsed = [
        json.loads(line[len("data: "):])
        for frame in frames
        for line in frame.decode().splitlines()
        if line.startswith("data: ")
    ]
    assert parsed[0]["type"] == "run_started"
    assert parsed[-1]["type"] == "run_finished"


def test_stream_route_over_http(tmp_path, monkeypatch):
    """真实起 server，POST stream 路由应返回 text/event-stream 且含唯一终态。"""
    agent_stream.clear_runtime_factories()
    agent_stream.register_runtime_factory(
        "fake",
        lambda: FakeAgentAdapter(
            [ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})]
        ),
    )
    try:
        srv = gui_server.create_server(port=0)
        thread = threading.Thread(target=srv.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=10)
            try:
                conn.request(
                    "POST",
                    "/api/agent/runs/run-http/stream",
                    body=json.dumps(_body(run_id="run-http")).encode(),
                    headers={"Content-Type": "application/json"},
                )
                resp = conn.getresponse()
                assert resp.status == 200
                assert resp.getheader("Content-Type").startswith("text/event-stream")
                body = resp.read().decode()
            finally:
                conn.close()
        finally:
            srv.shutdown()
            srv.server_close()
            thread.join(timeout=5)
    finally:
        agent_stream.clear_runtime_factories()

    parsed = [
        json.loads(line[len("data: "):])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    assert parsed[0]["type"] == "run_started"
    assert parsed[-1]["type"] == "run_finished"
    assert sum(t in {"run_finished", "run_failed"} for t in [p["type"] for p in parsed]) == 1


def test_make_streamer_runs_openai_adapter_factory_with_fake_transport(tmp_path, monkeypatch):
    """8.1 装配：make_openai_adapter_factory + fake transport 走通 make_streamer 闭环。"""
    snapshot = ProviderSnapshot(
        "openai",
        "https://api.openai.com/v1",
        "gpt-test",
        "credential://openai/default",
        ProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        4096,
        3,
    )

    class FakeTransport:
        async def stream(self, _snapshot, request, *, api_key):
            assert api_key == "sk-test"
            yield _sse(
                {
                    "choices": [
                        {
                            "delta": {"content": "正在分析…"},
                            "finish_reason": "stop",
                        }
                    ]
                }
            )

    factory = make_openai_adapter_factory(
        snapshot_resolver=lambda _run_input: snapshot,
        credential_resolver=lambda _ref: "sk-test",
        baseline_analysis={"summary": "初始", "basic": {}, "tone_curve": [], "hsl": [], "color_grading": {}, "effects": {}},
        image_path=str(tmp_path / "photo.jpg"),
        base_version_id="v" * 64,
        transport=FakeTransport(),
    )
    run_input = agent_stream.build_run_input(_body(run_id="run-openai", runtime_id="openai-api"))
    streamer = agent_stream.make_streamer(
        "openai-api", run_input, factories={"openai-api": factory}
    )
    frames = _collect(streamer)

    parsed = [
        json.loads(line[len("data: "):])
        for frame in frames
        for line in frame.decode().splitlines()
        if line.startswith("data: ")
    ]
    types = [item["type"] for item in parsed]
    assert types[0] == "run_started"
    assert "text_delta" in types
    assert types[-1] in {"run_finished", "run_failed"}
    assert sum(t in {"run_finished", "run_failed"} for t in types) == 1
