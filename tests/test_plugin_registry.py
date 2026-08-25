from __future__ import annotations

import pytest

from looklift.capabilities import CapabilityGrant, ScopedTokenStore
from looklift.plugin_registry import PluginManifest, PluginManifestError, PluginRegistry
from looklift.skill_staging import SkillStagingError, stage_skill_snapshot


def _manifest(version: str, digest: str = "a" * 64) -> PluginManifest:
    return PluginManifest(
        1,
        "catalog-tools",
        version,
        "connector",
        "catalog",
        "declarative",
        ("catalog",),
        frozenset({"connector.read_catalog"}),
        digest,
    )


def test_registry_resolves_semver_and_uninstall_preserves_history():
    registry = PluginRegistry()
    registry.install(_manifest("1.9.0"))
    registry.install(_manifest("1.10.0", "b" * 64))
    assert registry.resolve("catalog-tools").version == "1.10.0"
    registry.uninstall("catalog-tools", "1.10.0")
    assert registry.resolve("catalog-tools").version == "1.9.0"
    assert registry.resolve("catalog-tools", "1.10.0", include_disabled=True).enabled is False


def test_manifest_rejects_bad_digest_and_privileged_capability():
    with pytest.raises(PluginManifestError, match="摘要"):
        _manifest("1.0.0", "bad")
    with pytest.raises(PluginManifestError, match="禁止"):
        PluginManifest(1, "bad", "1.0.0", "connector", "x", "declarative", (), frozenset({"workspace.read_original"}), "a" * 64)


def test_skill_staging_freezes_whitelisted_snapshot(tmp_path):
    staged = stage_skill_snapshot(
        tmp_path,
        project_id="project-a",
        skill_id="catalog-tools",
        version="1.0.0",
        files={"SKILL.md": "规则", "references/check.md": "检查"},
    )
    assert (staged.path / "SKILL.md").read_text(encoding="utf-8") == "规则"
    assert len(staged.content_hash) == 64
    with pytest.raises(SkillStagingError, match="路径"):
        stage_skill_snapshot(
            tmp_path,
            project_id="p",
            skill_id="s",
            version="1",
            files={"SKILL.md": "规则", "../escape.md": "x"},
        )


def test_scoped_token_revocation_invalidates_attempt_immediately():
    grant = CapabilityGrant("plugin", frozenset({"connector.read_catalog"}), "p", "a" * 64, scope="attempt")
    store = ScopedTokenStore()
    token = store.issue(grant, attempt_id="a1")
    assert store.validate(token, capability="connector.read_catalog", project_id="p", attempt_id="a1") is True
    store.revoke_subject("plugin", version_hash="a" * 64)
    assert store.validate(token, capability="connector.read_catalog", project_id="p", attempt_id="a1") is False
