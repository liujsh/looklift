from looklift.gui.api import ROUTES


def test_runtime_list_api_exposes_safe_picker_data():
    status, body = ROUTES[("GET", "/api/runtimes")]({})
    assert status == 200
    assert [item["id"] for item in body["runtimes"]] == [
        "claude-code",
        "codex-cli",
        "pi-cli",
        "deepseek-cli",
        "openai-api",
    ]
    assert all("command" not in item and "endpoint" not in item for item in body["runtimes"])
    assert next(item for item in body["runtimes"] if item["id"] == "pi-cli")[
        "support_level"
    ] == "stable"
    plugin_support = {
        item["id"]: item["plugin_task_support"] for item in body["runtimes"]
    }
    assert plugin_support == {
        "claude-code": "unverified",
        "codex-cli": "unverified",
        "pi-cli": "verified",
        "deepseek-cli": "unsupported",
        "openai-api": "verified",
    }
