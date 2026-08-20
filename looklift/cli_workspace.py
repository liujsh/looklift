"""本地 CLI Attempt 的最小数据 Workspace 与环境清理。"""

from __future__ import annotations

import os
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .agent_adapter import AgentRunInput


_ALLOWED_ENVIRONMENT = frozenset(
    {
        "appdata",
        "comspec",
        "home",
        "localappdata",
        "path",
        "pathext",
        "systemdrive",
        "systemroot",
        "temp",
        "tmp",
        "userprofile",
        "windir",
    }
)


@dataclass(frozen=True)
class CliWorkspace:
    """只包含允许交给本地 CLI 的 Attempt 文件。"""

    path: Path
    domain_pack_path: Path
    proxy_path: Path
    candidates_path: Path


class CliWorkspaceManager:
    """创建不含 Run/Attempt 明文的随机 Workspace。"""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def create(self, run_input: AgentRunInput) -> CliWorkspace:
        path = self._root / f"attempt-{uuid.uuid4().hex}"
        path.mkdir()
        candidates = path / "candidates"
        candidates.mkdir()
        domain_path = path / "DOMAIN_PACK.md"
        proxy_path = path / "proxy.jpg"
        domain_path.write_text(
            f"{run_input.domain_pack.instructions}\n\n"
            f"# 本轮目标\n\n{run_input.domain_pack.user_message}\n",
            encoding="utf-8",
        )
        proxy_path.write_bytes(run_input.proxy_image.content)
        return CliWorkspace(
            path=path,
            domain_pack_path=domain_path,
            proxy_path=proxy_path,
            candidates_path=candidates,
        )

    def write_candidate(self, workspace: CliWorkspace, content: bytes) -> str:
        name = f"candidate-{uuid.uuid4().hex}.jpg"
        destination = workspace.candidates_path / name
        temporary = workspace.candidates_path / f".{name}.tmp"
        temporary.write_bytes(content)
        os.replace(temporary, destination)
        return destination.relative_to(workspace.path).as_posix()

    def dispose(self, workspace: CliWorkspace) -> None:
        resolved = workspace.path.resolve()
        if resolved.parent != self._root or not resolved.name.startswith("attempt-"):
            raise ValueError("拒绝清理不属于 CLI Workspace 根目录的路径")
        shutil.rmtree(resolved, ignore_errors=True)


def sanitized_cli_environment(source: Mapping[str, str]) -> dict[str, str]:
    """只保留启动和 CLI 自有登录所需环境，不继承 Provider 密钥。"""
    cleaned = {
        key: value
        for key, value in source.items()
        if key.casefold() in _ALLOWED_ENVIRONMENT
    }
    cleaned["PYTHONIOENCODING"] = "utf-8"
    cleaned["NO_COLOR"] = "1"
    return cleaned
