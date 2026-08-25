"""把一次运行使用的 Skill 内容冻结到项目私有 staging。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Mapping


class SkillStagingError(ValueError):
    pass


@dataclass(frozen=True)
class StagedSkill:
    path: Path
    content_hash: str


_SAFE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SAFE_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){0,2}")


def stage_skill_snapshot(
    root: Path,
    *,
    project_id: str,
    skill_id: str,
    version: str,
    files: Mapping[str, str],
) -> StagedSkill:
    if not _SAFE_ID.fullmatch(project_id) or not _SAFE_ID.fullmatch(skill_id):
        raise SkillStagingError("项目或 Skill ID 不安全")
    if not _SAFE_VERSION.fullmatch(version):
        raise SkillStagingError("Skill 版本不安全")
    if "SKILL.md" not in files:
        raise SkillStagingError("Skill staging 缺少 SKILL.md")

    normalized: dict[str, str] = {}
    for relative, content in files.items():
        path = PurePosixPath(relative)
        if (
            path.is_absolute()
            or ".." in path.parts
            or (
                relative != "SKILL.md"
                and not relative.startswith("references/")
            )
            or not relative.endswith(".md")
        ):
            raise SkillStagingError("Skill staging 路径不在白名单")
        normalized[relative] = content.replace("\r\n", "\n").replace("\r", "\n")

    digest = hashlib.sha256(
        json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    target = Path(root) / project_id / skill_id / version / digest
    for relative, content in normalized.items():
        destination = target.joinpath(*PurePosixPath(relative).parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return StagedSkill(path=target, content_hash=digest)
