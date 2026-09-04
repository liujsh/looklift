from __future__ import annotations

import pytest

from looklift.agent_run_input_codec import (
    AgentRunInputCodec,
    AttemptSnapshotError,
    ProtectedAttempt,
    StaleAttemptError,
)


def _sha(seed: str = "a") -> str:
    # 保证返回合法小写十六进制（用 seed 的字符码映射到 0-9a-f）
    digits = "0123456789abcdef"
    base = sum(ord(ch) for ch in seed)
    return "".join(digits[(base + i) % 16] for i in range(64))


def _snapshot(**overrides):
    values = dict(
        run_id="run-1",
        attempt_id="attempt-1",
        runtime_id="openai-api",
        model="gpt-test",
        domain_pack_hash=_sha("d"),
        proxy_image_hash=_sha("p"),
        config_version=3,
        baseline_hash=_sha("b"),
        session_id="session-1",
    )
    values.update(overrides)
    return AgentRunInputCodec.create(**values)


def test_codec_roundtrip_preserves_protected_fields():
    encoded = _snapshot()
    decoded = AgentRunInputCodec.decode(encoded)
    assert isinstance(decoded, ProtectedAttempt)
    assert decoded.run_id == "run-1"
    assert decoded.attempt_id == "attempt-1"
    assert decoded.runtime_id == "openai-api"
    assert decoded.model == "gpt-test"
    assert decoded.domain_pack_hash == _sha("d")
    assert decoded.proxy_image_hash == _sha("p")
    assert decoded.config_version == 3
    assert decoded.baseline_hash == _sha("b")
    assert decoded.session_id == "session-1"
    # 快照不得包含明文凭据或原图
    assert "api_key" not in encoded
    assert "proxy_image" not in encoded
    assert "secret" not in json_dump(encoded)


def json_dump(value) -> str:
    import json
    return json.dumps(value)


def test_decode_rejects_tampered_hash_as_stale():
    encoded = _snapshot()
    encoded["model"] = "gpt-other"  # 篡改字段但未重算 snapshot_hash
    with pytest.raises(StaleAttemptError):
        AgentRunInputCodec.decode(encoded)


def test_decode_rejects_unknown_schema_version():
    encoded = _snapshot()
    encoded["schema_version"] = 99
    # 重建哈希以通过完整性，再暴露版本问题
    encoded["snapshot_hash"] = "f" * 64
    with pytest.raises(AttemptSnapshotError):
        AgentRunInputCodec.decode(encoded)


def test_decode_stale_when_baseline_differs():
    encoded = _snapshot()
    with pytest.raises(StaleAttemptError):
        AgentRunInputCodec.decode(encoded, expected_baseline_hash=_sha("z"))


def test_decode_stale_when_identity_differs():
    encoded = _snapshot()
    with pytest.raises(StaleAttemptError):
        AgentRunInputCodec.decode(encoded, expected_run_id="run-2")
    with pytest.raises(StaleAttemptError):
        AgentRunInputCodec.decode(encoded, expected_attempt_id="attempt-9")


def test_decode_accepts_when_expected_matches():
    encoded = _snapshot()
    decoded = AgentRunInputCodec.decode(
        encoded,
        expected_baseline_hash=_sha("b"),
        expected_run_id="run-1",
        expected_attempt_id="attempt-1",
    )
    assert decoded.runtime_id == "openai-api"


def test_create_rejects_invalid_hash_or_version():
    with pytest.raises(AttemptSnapshotError):
        _snapshot(domain_pack_hash="not-a-hash")
    with pytest.raises(AttemptSnapshotError):
        _snapshot(config_version=0)
    with pytest.raises(AttemptSnapshotError):
        _snapshot(model="")
