from __future__ import annotations

import json

import pytest

from looklift.automation_store import AutomationStore


def test_workflow_roundtrip_and_validation(tmp_path):
    store = AutomationStore(tmp_path / "automation")

    created = store.create_workflow(
        name="胶片批处理",
        look_name="柔和胶片",
        factor=0.8,
        suffix="-film",
        quality=93,
    )

    assert store.list_workflows() == [created]
    assert store.get_workflow(created["id"]) == created
    assert json.loads((tmp_path / "automation" / "workflows" / f"{created['id']}.json").read_text("utf-8")) == created

    with pytest.raises(ValueError, match="同名"):
        store.create_workflow(
            name="胶片批处理",
            look_name="柔和胶片",
            factor=0.5,
            suffix="-other",
            quality=90,
        )
    with pytest.raises(ValueError, match="强度"):
        store.create_workflow(name="x", look_name="x", factor=1.1, suffix="-x", quality=90)
    with pytest.raises(ValueError, match="后缀"):
        store.create_workflow(name="x", look_name="x", factor=1, suffix="../x", quality=90)
    with pytest.raises(ValueError, match="质量"):
        store.create_workflow(name="x", look_name="x", factor=1, suffix="-x", quality=20)

    assert store.delete_workflow(created["id"]) is True
    assert store.delete_workflow(created["id"]) is False


def test_plan_freezes_analysis_and_reports_output_conflicts(tmp_path, sample_analysis):
    source_a = tmp_path / "输入一" / "照片.jpg"
    source_b = tmp_path / "输入二" / "照片.png"
    source_a.parent.mkdir()
    source_b.parent.mkdir()
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")
    output = tmp_path / "输出"
    output.mkdir()
    store = AutomationStore(tmp_path / "automation")
    workflow = store.create_workflow(
        name="统一风格",
        look_name="清透日系",
        factor=0.75,
        suffix="-looklift",
        quality=92,
    )

    conflict = store.create_plan(workflow, sample_analysis, [str(source_a), str(source_b)], str(output))

    assert conflict["ready"] is False
    assert [item["status"] for item in conflict["items"]] == ["conflict", "conflict"]
    assert all("同批输出重名" in item["error"] for item in conflict["items"])

    source_b = source_b.with_name("另一张.png")
    source_b.write_bytes(b"b")
    ready = store.create_plan(workflow, sample_analysis, [str(source_a), str(source_b)], str(output))
    sample_analysis["basic"]["contrast"] = 99

    assert ready["ready"] is True
    assert ready["analysis"]["basic"]["contrast"] != 99
    assert ready["items"][0]["output"].endswith("照片-looklift.jpg")
    assert store.get_plan(ready["id"]) == ready


def test_plan_rejects_missing_input_and_existing_output(tmp_path, sample_analysis):
    source = tmp_path / "照片.jpg"
    source.write_bytes(b"jpeg")
    output = tmp_path / "输出"
    output.mkdir()
    (output / "照片-ok.jpg").write_bytes(b"existing")
    store = AutomationStore(tmp_path / "automation")
    workflow = store.create_workflow(
        name="已有输出",
        look_name="青橙经典",
        factor=1,
        suffix="-ok",
        quality=90,
    )

    plan = store.create_plan(
        workflow,
        sample_analysis,
        [str(source), str(tmp_path / "不存在.jpg")],
        str(output),
    )

    assert plan["ready"] is False
    assert plan["items"][0]["status"] == "conflict"
    assert "已存在" in plan["items"][0]["error"]
    assert plan["items"][1]["status"] == "invalid"
    assert "不存在" in plan["items"][1]["error"]
