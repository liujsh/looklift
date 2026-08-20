"""Pi 扩展使用的 localhost Tool Gateway 传输。"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

from PIL import Image

from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding
from looklift.scoped_tool_gateway import ScopedToolGateway
from looklift.scoped_tool_http import ScopedToolHttpServer


class FakeRenderer:
    def render(self, _image_path: Path, _analysis: dict) -> bytes:
        from io import BytesIO

        output = BytesIO()
        Image.new("RGB", (8, 8), (150, 150, 150)).save(output, format="JPEG")
        return output.getvalue()


def _runtime(sample_analysis: dict) -> CandidateRuntime:
    binding = RunBinding(
        run_id="run-http",
        attempt_id="attempt-http",
        lease="lease-http",
        base_version_id="version-http",
        image_path=Path(__file__),
    )
    return CandidateRuntime(
        binding=binding,
        authority=InMemoryRunAuthority(binding),
        baseline_analysis=deepcopy(sample_analysis),
        renderer=FakeRenderer(),
    )


def _post(url: str, token: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_http_bridge_returns_structured_result_and_real_jpeg(
    sample_analysis: dict,
) -> None:
    gateway = ScopedToolGateway()
    grant = gateway.bind(_runtime(sample_analysis))
    server = ScopedToolHttpServer(gateway)
    server.start()
    try:
        status, rendered = _post(
            f"{server.url}/tools/render_candidate",
            grant.token,
            {
                "operations": [
                    {
                        "type": "scalar",
                        "path": "basic.exposure",
                        "mode": "delta",
                        "value": 0.2,
                        "reason": "测试",
                    }
                ],
                "intent": "生成候选",
                "template_strength": None,
            },
        )
        assert status == 200
        assert rendered["result"]["ok"] is True
        assert base64.b64decode(rendered["preview_base64"]).startswith(b"\xff\xd8")

        status, finished = _post(
            f"{server.url}/tools/finish_candidate",
            grant.token,
            {
                "outcome": "candidate_ready",
                "candidate_id": rendered["result"]["candidate_id"],
                "summary": "完成",
                "review_items": [],
                "uncertainties": [],
                "limitations": [],
            },
        )
        assert status == 200
        assert finished["result"]["ok"] is True

        status, rejected = _post(
            f"{server.url}/tools/render_candidate",
            grant.token,
            {},
        )
        assert status == 401
        assert rejected == {"error": "unauthorized"}
    finally:
        server.close()


def test_http_bridge_rejects_missing_token_without_runtime_call(
    sample_analysis: dict,
) -> None:
    gateway = ScopedToolGateway()
    gateway.bind(_runtime(sample_analysis))
    server = ScopedToolHttpServer(gateway)
    server.start()
    try:
        status, result = _post(
            f"{server.url}/tools/render_candidate",
            "wrong-token",
            {},
        )
        assert status == 401
        assert result == {"error": "unauthorized"}
    finally:
        server.close()
