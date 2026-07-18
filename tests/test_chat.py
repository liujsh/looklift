"""v2.1 无状态 AI 对话核心。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from looklift.chat import ChatCancelled, ChatStepError, chat_step


class CaptureProvider:
    name = "mock"

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response or {}
        self.error = error
        self.system = ""
        self.blocks: list[dict] = []
        self.schema: dict = {}
        self.image_existed_during_call = False

    def complete(self, system: str, blocks: list[dict], schema: dict) -> dict:
        self.system = system
        self.blocks = deepcopy(blocks)
        self.schema = deepcopy(schema)
        image = next(block for block in blocks if block["type"] == "image")
        self.image_existed_during_call = Path(image["path"]).is_file()
        if self.error:
            raise self.error
        return deepcopy(self.response)


def _photo(tmp_path: Path, *, with_exif: bool = False) -> Path:
    path = tmp_path / "photo.jpg"
    exif = Image.Exif()
    if with_exif:
        exif[34855] = 320
        exif[42033] = "SECRET-SERIAL"
    Image.new("RGB", (800, 600), (90, 120, 150)).save(path, "JPEG", exif=exif)
    return path


def _response(*, operations: list[dict] | None = None) -> dict:
    return {
        "operations": operations or [],
        "explanation": "画面略暗，先轻微提亮。",
        "limitations": [],
        "approximation": "",
        "manual_steps": [],
        "done": False,
    }


def test_chat_step_sends_proxy_context_and_returns_normalized_result(tmp_path, sample_analysis):
    provider = CaptureProvider(_response(operations=[{
        "type": "scalar",
        "path": "basic.exposure",
        "mode": "delta",
        "value": 0.25,
        "reason": "提亮主体",
    }]))
    original = deepcopy(sample_analysis)

    result = chat_step(
        image_path=_photo(tmp_path),
        current_analysis=sample_analysis,
        message="帮我提亮一点",
        history=[{"role": "user", "content": "之前的问题"}],
        include_metadata=False,
        provider=provider,
    )

    assert sample_analysis == original
    assert result.analysis["basic"]["exposure"] == pytest.approx(0.6)
    assert result.changes[0]["path"] == "basic.exposure"
    assert result.explanation == "画面略暗，先轻微提亮。"
    assert result.provider == "mock"
    assert result.proxy_count == 1
    assert result.metadata_sent is False
    assert provider.image_existed_during_call is True
    image_path = Path(next(block for block in provider.blocks if block["type"] == "image")["path"])
    assert not image_path.exists()
    combined_text = "\n".join(block["text"] for block in provider.blocks if block["type"] == "text")
    assert "帮我提亮一点" in combined_text
    assert "basic.exposure" in provider.system
    assert "局部" in provider.system


def test_chat_step_keeps_only_recent_history(tmp_path, sample_analysis):
    provider = CaptureProvider(_response())
    history = [{"role": "user", "content": f"消息-{index}"} for index in range(12)]

    chat_step(
        image_path=_photo(tmp_path),
        current_analysis=sample_analysis,
        message="继续",
        history=history,
        include_metadata=False,
        provider=provider,
    )

    text = "\n".join(block["text"] for block in provider.blocks if block["type"] == "text")
    assert "消息-3" not in text
    assert "消息-4" in text
    assert "消息-11" in text


def test_chat_step_sends_only_safe_metadata_when_enabled(tmp_path, sample_analysis):
    provider = CaptureProvider(_response())

    result = chat_step(
        image_path=_photo(tmp_path, with_exif=True),
        current_analysis=sample_analysis,
        message="分析曝光",
        history=[],
        include_metadata=True,
        provider=provider,
    )

    text = "\n".join(block["text"] for block in provider.blocks if block["type"] == "text")
    assert '"iso": 320' in text
    assert "SECRET-SERIAL" not in text
    assert result.metadata_sent is True


@pytest.mark.parametrize(
    ("error", "code", "message_fragment"),
    [
        (TimeoutError("sk-secret timeout"), "timeout", "超时"),
        (ChatCancelled(), "cancelled", "取消"),
        (RuntimeError("401 api_key=sk-secret"), "auth", "鉴权"),
        (RuntimeError("C:/private/photo.jpg exploded"), "provider_error", "调用失败"),
    ],
)
def test_chat_step_maps_provider_failures_without_leaking_details(
    tmp_path, sample_analysis, error, code, message_fragment
):
    provider = CaptureProvider(error=error)

    with pytest.raises(ChatStepError) as raised:
        chat_step(
            image_path=_photo(tmp_path),
            current_analysis=sample_analysis,
            message="调整",
            history=[],
            include_metadata=False,
            provider=provider,
        )

    assert raised.value.code == code
    assert message_fragment in str(raised.value)
    assert "sk-secret" not in str(raised.value)
    assert "C:/private" not in str(raised.value)


@pytest.mark.parametrize(
    "response",
    [
        [],
        {"operations": "bad", "explanation": "x", "limitations": [], "approximation": "", "manual_steps": [], "done": False},
        {"operations": [], "explanation": 3, "limitations": [], "approximation": "", "manual_steps": [], "done": False},
        {"operations": [], "explanation": "x", "limitations": [3], "approximation": "", "manual_steps": [], "done": False},
        {"operations": [], "explanation": "x", "limitations": [], "approximation": "", "manual_steps": [], "done": "yes"},
    ],
)
def test_chat_step_rejects_invalid_provider_response(tmp_path, sample_analysis, response):
    provider = CaptureProvider(response)  # type: ignore[arg-type]

    with pytest.raises(ChatStepError) as raised:
        chat_step(
            image_path=_photo(tmp_path),
            current_analysis=sample_analysis,
            message="调整",
            history=[],
            include_metadata=False,
            provider=provider,
        )

    assert raised.value.code == "invalid_response"
    assert "格式" in str(raised.value)


def test_all_invalid_operations_return_explanation_without_change(tmp_path, sample_analysis):
    provider = CaptureProvider(_response(operations=[{
        "type": "scalar", "path": "local.mask", "mode": "set", "value": 1,
    }]))

    result = chat_step(
        image_path=_photo(tmp_path),
        current_analysis=sample_analysis,
        message="局部提亮脸部",
        history=[],
        include_metadata=False,
        provider=provider,
    )

    assert result.analysis == sample_analysis
    assert result.changes == ()
    assert len(result.rejected) == 1
    assert result.explanation


def test_capability_only_response_preserves_manual_guidance(tmp_path, sample_analysis):
    response = _response()
    response.update({
        "limitations": ["当前不支持局部蒙版"],
        "approximation": "可先小幅提高全局阴影",
        "manual_steps": ["在右侧基础面板调整阴影"],
        "done": True,
    })

    result = chat_step(
        image_path=_photo(tmp_path),
        current_analysis=sample_analysis,
        message="只提亮人物脸部",
        history=[],
        include_metadata=False,
        provider=CaptureProvider(response),
    )

    assert result.changes == ()
    assert result.limitations == ("当前不支持局部蒙版",)
    assert result.approximation == "可先小幅提高全局阴影"
    assert result.manual_steps == ("在右侧基础面板调整阴影",)
    assert result.done is True
