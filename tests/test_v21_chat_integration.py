"""v2.1 离线全链路：消息候选、渲染、确认/撤销与重启恢复。"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from looklift.chat import ChatStepError, chat_step
from looklift.render import render
from looklift.session_store import SessionStore


class StubProvider:
    name = "mock"

    def __init__(self, response: dict | None = None, error: Exception | None = None):
        self.response = response
        self.error = error

    def complete(self, _system: str, _blocks: list[dict], _schema: dict) -> dict:
        if self.error:
            raise self.error
        return deepcopy(self.response)  # type: ignore[arg-type]


def _photo(tmp_path: Path) -> Path:
    path = tmp_path / "photo.jpg"
    Image.new("RGB", (96, 64), (80, 105, 130)).save(path, "JPEG")
    return path


def _response(delta: float = 0.25) -> dict:
    return {
        "operations": [{
            "type": "scalar", "path": "basic.exposure", "mode": "delta",
            "value": delta, "reason": "提亮主体",
        }],
        "explanation": "先轻微提亮。", "limitations": [], "approximation": "",
        "manual_steps": [], "done": False,
    }


def test_message_candidate_preview_accept_and_restart(tmp_path, sample_analysis):
    photo = _photo(tmp_path)
    database = tmp_path / "looklift.db"
    store = SessionStore(database)
    initial = store.create_or_resume(str(photo), sample_analysis)

    candidate = chat_step(
        image_path=photo, current_analysis=initial.current_analysis,
        message="提亮一点", history=[], include_metadata=False,
        provider=StubProvider(_response()),
    )
    # 候选可真实渲染，但在用户确认前数据库指针和正式参数均不改变。
    preview = render(Image.open(photo).convert("RGB"), candidate.analysis)
    assert preview.size == (96, 64)
    assert store.load(initial.id).current_version_id == initial.current_version_id

    committed = store.commit_exchange(
        initial.id,
        [{"role": "user", "content": "提亮一点"},
         {"role": "assistant", "content": candidate.explanation, "provider": "mock"}],
        candidate.analysis,
        "chat",
    )
    restarted = SessionStore(database).load(initial.id)
    assert restarted.current_version_id == committed.current_version_id
    assert restarted.current_analysis["basic"]["exposure"] == pytest.approx(
        sample_analysis["basic"]["exposure"] + 0.25
    )
    assert [message.role for message in restarted.messages] == ["user", "assistant"]


def test_discard_and_provider_failures_never_move_formal_pointer(tmp_path, sample_analysis):
    photo = _photo(tmp_path)
    store = SessionStore(tmp_path / "looklift.db")
    initial = store.create_or_resume(str(photo), sample_analysis)

    discarded = chat_step(
        image_path=photo, current_analysis=initial.current_analysis,
        message="再提亮", history=[], include_metadata=False,
        provider=StubProvider(_response(0.5)),
    )
    assert discarded.changes
    assert store.load(initial.id).current_version_id == initial.current_version_id

    for error, code in [(TimeoutError(), "timeout"), (RuntimeError("401 unauthorized"), "auth")]:
        with pytest.raises(ChatStepError, match="正式版本|重试|配置") as captured:
            chat_step(
                image_path=photo, current_analysis=initial.current_analysis,
                message="继续", history=[], include_metadata=False,
                provider=StubProvider(error=error),
            )
        assert captured.value.code == code
        restored = SessionStore(store.path).load(initial.id)
        assert restored.current_version_id == initial.current_version_id
        assert restored.current_analysis == sample_analysis
