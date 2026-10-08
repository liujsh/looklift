from __future__ import annotations

from pathlib import Path

import pytest

from looklift.plugin_assets import AssetBrokerError, PluginAssetBroker


def test_asset_broker_exposes_only_anonymous_refs_and_stages_selected_bytes(tmp_path: Path):
    broker = PluginAssetBroker(tmp_path)
    refs = broker.freeze(
        project_id="project-a",
        version_ids=("version-1", "version-2"),
        contents=(b"jpeg-one", b"jpeg-two"),
        media_type="image/jpeg",
    )

    public = [ref.public_dict() for ref in refs]
    assert all("path" not in item for item in public)
    staged = broker.stage(
        project_id="project-a",
        action_id="a" * 32,
        asset_ids=tuple(ref.asset_id for ref in reversed(refs)),
    )
    assert [path.read_bytes() for path in staged] == [b"jpeg-two", b"jpeg-one"]
    assert all(path.parent.name == "a" * 32 for path in staged)


def test_asset_broker_rejects_cross_project_and_unknown_paths(tmp_path: Path):
    broker = PluginAssetBroker(tmp_path)
    ref = broker.freeze(
        project_id="project-a",
        version_ids=("version-1",),
        contents=(b"jpeg",),
        media_type="image/jpeg",
    )[0]

    with pytest.raises(AssetBrokerError, match="项目"):
        broker.stage(project_id="project-b", action_id="b" * 32, asset_ids=(ref.asset_id,))
    with pytest.raises(AssetBrokerError, match="素材"):
        broker.stage(project_id="project-a", action_id="b" * 32, asset_ids=("C:/original.jpg",))


def test_asset_broker_revocation_removes_staging_but_keeps_audit_identity(tmp_path: Path):
    broker = PluginAssetBroker(tmp_path)
    ref = broker.freeze(
        project_id="project-a",
        version_ids=("version-1",),
        contents=(b"jpeg",),
        media_type="image/jpeg",
    )[0]
    paths = broker.stage(project_id="project-a", action_id="c" * 32, asset_ids=(ref.asset_id,))
    broker.revoke_action("c" * 32)

    assert not paths[0].exists()
    assert broker.get(ref.asset_id).content_hash == ref.content_hash
