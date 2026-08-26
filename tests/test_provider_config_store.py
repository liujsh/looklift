from __future__ import annotations

import pytest

from looklift.credential_store import DpapiCredentialStore
from looklift.provider_config_store import ProviderConfigStore


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI 仅适用于 Windows")
def test_provider_config_stores_only_encrypted_credential_reference(tmp_path) -> None:
    credentials = DpapiCredentialStore(tmp_path / "credentials")
    store = ProviderConfigStore(tmp_path / "providers.json", credentials=credentials)

    saved = store.save(
        provider_id="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5",
        protocol="openai_chat_completions",
        max_tokens=4096,
        api_key="sk-secret-value",
    )

    raw = (tmp_path / "providers.json").read_text(encoding="utf-8")
    assert "sk-secret-value" not in raw
    assert saved.api_key_ref == "dpapi://openai-1"
    assert credentials.get(saved.api_key_ref) == "sk-secret-value"
    assert store.query()["has_key"] is True
    assert "api_key" not in store.query()


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI 仅适用于 Windows")
def test_provider_config_delete_removes_credential_and_metadata(tmp_path) -> None:
    credentials = DpapiCredentialStore(tmp_path / "credentials")
    store = ProviderConfigStore(tmp_path / "providers.json", credentials=credentials)
    snapshot = store.save(
        provider_id="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5",
        protocol="openai_chat_completions",
        max_tokens=4096,
        api_key="sk-secret-value",
    )

    store.delete()

    assert store.query()["configured"] is False
    with pytest.raises(KeyError):
        credentials.get(snapshot.api_key_ref or "")


@pytest.mark.skipif(__import__("os").name != "nt", reason="DPAPI 仅适用于 Windows")
def test_switching_to_ollama_drops_previous_remote_credential(tmp_path) -> None:
    credentials = DpapiCredentialStore(tmp_path / "credentials")
    store = ProviderConfigStore(tmp_path / "providers.json", credentials=credentials)
    remote = store.save(
        provider_id="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5",
        protocol="openai_chat_completions",
        max_tokens=4096,
        api_key="sk-secret-value",
    )

    local = store.save(
        provider_id="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3-vl",
        protocol="ollama_openai_compatible",
        max_tokens=4096,
    )

    assert local.api_key_ref is None
    with pytest.raises(KeyError):
        credentials.get(remote.api_key_ref or "")
