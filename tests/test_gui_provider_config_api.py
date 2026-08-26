from __future__ import annotations

import json
import os

import pytest

from looklift import config
from looklift.gui.api import ROUTES


@pytest.mark.skipif(os.name != "nt", reason="Provider 凭据端点依赖 Windows DPAPI")
def test_provider_config_commands_never_echo_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    save = ROUTES[("POST", "/api/providers/config")]
    status, result = save(
        {
            "body": json.dumps(
                {
                    "provider_id": "openai",
                    "base_url": "https://api.openai.com/v1",
                    "model": "gpt-5",
                    "max_tokens": 4096,
                    "api_key": "sk-secret",
                }
            ).encode()
        }
    )
    assert status == 200
    assert "sk-secret" not in str(result)

    status, query = ROUTES[("GET", "/api/providers/config")]({})
    assert status == 200
    assert query["has_key"] is True
    assert "api_key" not in query

    status, _ = ROUTES[("DELETE", "/api/providers/config")]({})
    assert status == 200
    assert ROUTES[("GET", "/api/providers/config")]({})[1]["configured"] is False
