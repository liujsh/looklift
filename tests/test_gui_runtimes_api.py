from looklift.gui.api import ROUTES


def test_runtime_list_api_exposes_safe_picker_data():
    status, body = ROUTES[("GET", "/api/runtimes")]({})
    assert status == 200
    assert [item["id"] for item in body["runtimes"]] == [
        "pydantic-api",
        "pi-cli",
        "fake",
    ]
    assert all("command" not in item and "endpoint" not in item for item in body["runtimes"])
