from __future__ import annotations

import json
import http.client
import threading

from looklift import chat
from looklift.gui import api
from looklift.gui import server as gui_server


def _call(payload):
    return api.ROUTES[("POST", "/api/chat/step")](
        {"params": {}, "body": json.dumps(payload).encode(), "query": {}}
    )


def test_chat_step_returns_candidate_without_persistence(monkeypatch, tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    captured = {}

    def fake_chat_step(**kwargs):
        captured.update(kwargs)
        return chat.ChatStepResult(
            analysis=sample_analysis,
            changes=({"path": "basic.exposure", "before": 0, "after": 0.3},),
            rejected=(),
            explanation="稍微提亮",
            limitations=("不支持局部蒙版",),
            approximation="使用全局曝光近似",
            manual_steps=("在人像软件中局部提亮面部",),
            done=False,
            provider="mock",
            proxy_count=1,
            metadata_sent=True,
        )

    monkeypatch.setattr(api.chat, "chat_step", fake_chat_step)
    status, body = _call(
        {
            "path": str(photo),
            "current_analysis": sample_analysis,
            "message": "提亮一点",
            "history": [{"role": "assistant", "content": "可以"}],
            "include_metadata": True,
        }
    )

    assert status == 200
    assert body["analysis"] == sample_analysis
    assert body["changes"][0]["path"] == "basic.exposure"
    assert captured["image_path"] == photo
    assert captured["include_metadata"] is True


def test_chat_step_validates_request(tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    base = {
        "path": str(photo),
        "current_analysis": sample_analysis,
        "message": "调整",
        "history": [],
        "include_metadata": False,
    }
    invalid = [
        ([], "JSON 对象"),
        ({**base, "current_analysis": []}, "current_analysis"),
        ({**base, "message": "  "}, "message"),
        ({**base, "history": {}}, "history"),
        ({**base, "history": [{"role": "tool", "content": "x"}]}, "history"),
        ({**base, "include_metadata": 1}, "include_metadata"),
    ]
    for payload, expected in invalid:
        status, body = _call(payload)
        assert status == 400
        assert expected in body["error"]


def test_chat_step_maps_stable_error(monkeypatch, tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")

    def fail(**_kwargs):
        raise chat.ChatStepError("timeout", "AI 响应超时，请重试。")

    monkeypatch.setattr(api.chat, "chat_step", fail)
    status, body = _call(
        {
            "path": str(photo),
            "current_analysis": sample_analysis,
            "message": "调整",
            "history": [],
            "include_metadata": False,
        }
    )
    assert status == 504
    assert body == {"error": "AI 响应超时，请重试。", "code": "timeout"}


def test_chat_route_requires_token_and_allows_trusted_cors(monkeypatch, tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    monkeypatch.setattr(
        api.chat,
        "chat_step",
        lambda **_kwargs: chat.ChatStepResult(
            sample_analysis, (), (), "完成", (), "", (), True, "mock", 1, False
        ),
    )
    server = gui_server.create_server(port=0, token="secret")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    payload = json.dumps(
        {
            "path": str(photo),
            "current_analysis": sample_analysis,
            "message": "调整",
            "history": [],
            "include_metadata": False,
        }
    )
    try:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request("POST", "/api/chat/step", body=payload)
        assert connection.getresponse().status == 401
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", server.server_port)
        connection.request(
            "POST",
            "/api/chat/step",
            body=payload,
            headers={
                "Content-Type": "application/json",
                "X-Looklift-Token": "secret",
                "Origin": "http://localhost:1420",
            },
        )
        response = connection.getresponse()
        response.read()
        assert response.status == 200
        assert response.getheader("Access-Control-Allow-Origin") == "http://localhost:1420"
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
