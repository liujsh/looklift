"""一次性 Scoped Tool Token 的权限、过期和共享 Runtime 契约。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from PIL import Image

from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding
from looklift.scoped_tool_gateway import ScopedToolGateway, agent_tool_definitions


class FakeRenderer:
    def render(self, _image_path: Path, _analysis: dict) -> bytes:
        from io import BytesIO

        output = BytesIO()
        Image.new("RGB", (8, 8), (128, 128, 128)).save(output, format="JPEG")
        return output.getvalue()


def _runtime(sample_analysis: dict) -> CandidateRuntime:
    binding = RunBinding(
        run_id="private-run",
        attempt_id="private-attempt",
        lease="private-lease",
        base_version_id="private-version",
        image_path=Path(__file__),
    )
    return CandidateRuntime(
        binding=binding,
        authority=InMemoryRunAuthority(binding),
        baseline_analysis=deepcopy(sample_analysis),
        renderer=FakeRenderer(),
    )


def _render_arguments() -> dict:
    return {
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
    }


def test_gateway_exposes_only_two_tools_and_shared_candidate_runtime(
    sample_analysis: dict,
) -> None:
    runtime = _runtime(sample_analysis)
    gateway = ScopedToolGateway()
    grant = gateway.bind(runtime)

    rendered = gateway.call(grant.token, "render_candidate", _render_arguments())

    assert rendered.payload["ok"] is True
    assert rendered.preview_jpeg is not None
    assert rendered.preview_jpeg.startswith(b"\xff\xd8")
    assert len(runtime.candidates) == 1
    forbidden = gateway.call(grant.token, "shell", {})
    assert forbidden.payload["error"]["code"] == "tool_not_allowed"

    finished = gateway.call(
        grant.token,
        "finish_candidate",
        {
            "outcome": "candidate_ready",
            "candidate_id": rendered.payload["candidate_id"],
            "summary": "候选完成",
            "review_items": [],
            "uncertainties": [],
            "limitations": [],
        },
    )
    assert finished.payload["ok"] is True
    assert gateway.call(grant.token, "render_candidate", _render_arguments()).payload[
        "error"
    ]["code"] == "token_revoked"


def test_token_is_opaque_expires_and_can_be_revoked(sample_analysis: dict) -> None:
    now = [100.0]
    gateway = ScopedToolGateway(clock=lambda: now[0])
    runtime = _runtime(sample_analysis)
    grant = gateway.bind(runtime, ttl_seconds=5)

    assert "private-run" not in grant.token
    assert "private-attempt" not in grant.token
    assert gateway.call("wrong-token", "render_candidate", {}).payload["error"][
        "code"
    ] == "token_invalid"

    now[0] = 106.0
    assert gateway.call(grant.token, "render_candidate", {}).payload["error"][
        "code"
    ] == "token_expired"

    second = gateway.bind(runtime)
    gateway.revoke(second.token)
    assert gateway.call(second.token, "render_candidate", {}).payload["error"][
        "code"
    ] == "token_revoked"


def test_invalid_arguments_are_correctable_tool_result(sample_analysis: dict) -> None:
    gateway = ScopedToolGateway()
    grant = gateway.bind(_runtime(sample_analysis))

    result = gateway.call(
        grant.token,
        "render_candidate",
        {"operations": "not-a-list", "intent": "测试"},
    )

    assert result.payload["ok"] is False
    assert result.payload["error"] == {
        "code": "invalid_arguments",
        "message": "工具参数不符合契约",
        "correctable": True,
    }


def test_mcp_schema_is_projected_from_pydantic_contract_without_private_identity() -> None:
    import json

    definitions = agent_tool_definitions()
    serialized = json.dumps(definitions)

    assert {definition["name"] for definition in definitions} == {
        "render_candidate",
        "finish_candidate",
    }
    assert "basic.exposure" in serialized
    assert "run_id" not in serialized
    assert "attempt_id" not in serialized
    assert "image_path" not in serialized
