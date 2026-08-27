"""Global Rules、Memory、Project Context 的可审查持久化存储。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .proposal import Proposal, ProposalService


_SAFE_ID = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_SAFE_SOURCE = re.compile(r"^[a-z0-9][a-z0-9:._-]{0,127}$")
_WINDOWS_PATH = re.compile(r"(?i)\b[a-z]:\\[^\r\n]+")
_HOME_PATH = re.compile(r"(?m)(?:/home/|/Users/)[^\s\r\n]+")
_SECRET = re.compile(r"(?i)(?:api[_-]?key|token|bearer)\s*[:=]\s*\S+|\bsk-[A-Za-z0-9_-]+")
_EXIF_LINE = re.compile(r"(?im)^\s*exif\s*:[^\r\n]*")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ContextEntry:
    entry_id: str
    entry_type: str
    content: str
    source: str
    version: int = 1
    state: str = "active"
    enabled: bool = True
    name: str = ""
    description: str = ""
    scope: str = "global"
    project_id: str | None = None
    run_id: str | None = None
    expires_at: str | None = None
    source_event_id: str | None = None
    confidence: float = 1.0
    evidence: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class ContextMemoryStore:
    """以受限 Markdown 条目保存用户可审查上下文。"""

    TYPES = frozenset(
        {"profile", "rule", "fact", "preference", "project", "reference", "feedback"}
    )
    SCOPES = frozenset({"global", "project", "run"})
    DEFAULT_CONFIG = {"enabled": True, "auto_extract": False}

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.proposals = ProposalService(path=self.root / "proposals.json")
        self._entries: dict[str, ContextEntry] = {}
        self._load_entries()

    def put(self, entry: ContextEntry) -> ContextEntry:
        self._validate(entry)
        self._entries[entry.entry_id] = entry
        self._atomic_write(self.root / f"{entry.entry_id}.md", self._serialize(entry))
        self._write_index()
        return entry

    def user_put(
        self,
        entry_id: str,
        *,
        entry_type: str,
        content: str,
        name: str = "",
        description: str = "",
        scope: str = "global",
        project_id: str | None = None,
        run_id: str | None = None,
        expires_at: str | None = None,
    ) -> ContextEntry:
        """用户设置页直接写入 active 条目。"""
        previous = self._entries.get(entry_id)
        timestamp = _now()
        return self.put(
            ContextEntry(
                entry_id=entry_id,
                entry_type=entry_type,
                content=content,
                source="user",
                version=(previous.version + 1) if previous else 1,
                state="active",
                enabled=True,
                name=name,
                description=description,
                scope=scope,
                project_id=project_id,
                run_id=run_id,
                expires_at=expires_at,
                created_at=previous.created_at if previous else timestamp,
                updated_at=timestamp,
            )
        )

    def get(self, entry_id: str) -> ContextEntry:
        self._validate_id(entry_id)
        return self._entries[entry_id]

    def list(self, *, entry_type: str | None = None) -> tuple[ContextEntry, ...]:
        entries = self._entries.values()
        if entry_type is not None:
            entries = (item for item in entries if item.entry_type == entry_type)
        return tuple(sorted(entries, key=lambda item: item.entry_id))

    def snapshot(self) -> tuple[ContextEntry, ...]:
        return tuple(
            replace(item, content=_sanitize_for_harness(item.content))
            for item in self.list()
            if item.enabled and item.state == "active" and not self._expired(item)
        )

    def disable(self, entry_id: str) -> ContextEntry:
        target = self.get(entry_id)
        if not target.enabled and target.state == "disabled":
            return target
        return self.put(replace(target, enabled=False, state="disabled", version=target.version + 1, updated_at=_now()))

    def config(self) -> dict[str, bool]:
        path = self.root / "config.json"
        if not path.is_file():
            return dict(self.DEFAULT_CONFIG)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Context 配置损坏") from exc
        result = dict(self.DEFAULT_CONFIG)
        for key in result:
            if key in payload:
                if not isinstance(payload[key], bool):
                    raise ValueError("Context 配置字段必须是布尔值")
                result[key] = payload[key]
        return result

    def update_config(self, **changes: bool) -> dict[str, bool]:
        if set(changes) - set(self.DEFAULT_CONFIG) or any(not isinstance(value, bool) for value in changes.values()):
            raise ValueError("Context 配置字段不合法")
        updated = {**self.config(), **changes}
        self._atomic_write(
            self.root / "config.json",
            json.dumps(updated, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        return updated

    def proposal(
        self,
        *,
        target_id: str,
        content: str,
        base_hash: str,
        source_packet_ids: tuple[str, ...] = (),
        target_type: str | None = None,
    ) -> Proposal:
        target = self.get(target_id)
        resolved_type = target_type or ("ProjectContext" if target.entry_type == "project" else "Memory")
        return self.proposals.preview(
            target_type=resolved_type,
            target_id=target_id,
            base_hash=base_hash,
            patch={"content": content},
            source_packet_ids=source_packet_ids,
        )

    def apply_proposal(self, proposal_id: str) -> Proposal:
        proposal = self.proposals.get(proposal_id)
        if proposal.target_type not in {"Memory", "ProjectContext"}:
            raise ValueError("该 Proposal 目标不属于 Context Store")
        target = self.get(proposal.target_id)
        return self.proposals.apply(
            proposal_id,
            current_hash=target.content_hash,
            apply_target=self._apply,
        )

    def _apply(self, proposal: Proposal) -> str:
        target = self.get(proposal.target_id)
        unknown = set(proposal.patch) - {"content", "name", "description", "scope", "enabled"}
        if unknown or "content" not in proposal.patch:
            raise ValueError("Context Proposal patch 不合法")
        for key in ("content", "name", "description", "scope"):
            if key in proposal.patch and not isinstance(proposal.patch[key], str):
                raise ValueError(f"Context Proposal {key} 必须是字符串")
        if "enabled" in proposal.patch and not isinstance(proposal.patch["enabled"], bool):
            raise ValueError("Context Proposal enabled 必须是布尔值")
        updated = replace(
            target,
            content=proposal.patch["content"],
            name=proposal.patch.get("name", target.name),
            description=proposal.patch.get("description", target.description),
            scope=proposal.patch.get("scope", target.scope),
            enabled=proposal.patch.get("enabled", target.enabled),
            version=target.version + 1,
            state="active",
            updated_at=_now(),
        )
        self.put(updated)
        return updated.content_hash

    def _validate(self, entry: ContextEntry) -> None:
        self._validate_id(entry.entry_id)
        if entry.entry_type not in self.TYPES:
            raise ValueError("Context 条目类型不合法")
        if entry.scope not in self.SCOPES:
            raise ValueError("Context 条目作用域不合法")
        if (
            not isinstance(entry.version, int)
            or isinstance(entry.version, bool)
            or entry.version < 1
            or entry.state not in {"active", "disabled", "deleted"}
            or not isinstance(entry.enabled, bool)
            or not isinstance(entry.content, str)
            or not isinstance(entry.source, str)
            or not isinstance(entry.name, str)
            or not isinstance(entry.description, str)
            or not isinstance(entry.scope, str)
            or (entry.scope == "project" and not entry.project_id)
            or (entry.scope == "run" and (not entry.run_id or not entry.expires_at))
            or not isinstance(entry.confidence, (int, float))
            or isinstance(entry.confidence, bool)
            or not 0 <= entry.confidence <= 1
            or not isinstance(entry.created_at, str)
            or not isinstance(entry.updated_at, str)
            or not entry.content.strip()
            or _SAFE_SOURCE.fullmatch(entry.source) is None
        ):
            raise ValueError("Context 条目不合法")
        if len(entry.content) > 65_536 or len(entry.name) > 120 or len(entry.description) > 500:
            raise ValueError("Context 条目内容过长")
        if any("\x00" in value for value in (entry.content, entry.name, entry.description, entry.source)):
            raise ValueError("Context 条目包含非法字符")

    @staticmethod
    def _validate_id(entry_id: str) -> None:
        if not isinstance(entry_id, str) or _SAFE_ID.fullmatch(entry_id) is None:
            raise ValueError("Context 条目 ID 必须是安全 slug")

    def _load_entries(self) -> None:
        for path in sorted(self.root.glob("*.md")):
            entry = self._parse(path.read_text(encoding="utf-8"))
            if path.stem != entry.entry_id:
                raise ValueError("Context 条目文件名与 ID 不一致")
            self._validate(entry)
            self._entries[entry.entry_id] = entry

    @staticmethod
    def _serialize(entry: ContextEntry) -> str:
        metadata = asdict(entry)
        metadata.pop("content")
        lines = ["---"]
        for key, value in metadata.items():
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
        lines.extend([f"content_hash: {json.dumps(entry.content_hash)}", "---", "", entry.content, ""])
        return "\n".join(lines)

    @staticmethod
    def _parse(text: str) -> ContextEntry:
        if not text.startswith("---\n") or "\n---\n" not in text[4:]:
            raise ValueError("Context Markdown frontmatter 不完整")
        header, content = text[4:].split("\n---\n", 1)
        values: dict[str, Any] = {}
        for line in header.splitlines():
            if ":" not in line:
                raise ValueError("Context Markdown 元数据不合法")
            key, raw = line.split(":", 1)
            try:
                values[key] = json.loads(raw.strip())
            except json.JSONDecodeError:
                values[key] = raw.strip()
        declared_hash = values.pop("content_hash", "")
        values["content"] = content.strip("\n")
        # 兼容首版仅含 id/type/version/confirmed/source 的条目。
        if "id" in values:
            values["entry_id"] = values.pop("id")
        if "type" in values:
            values["entry_type"] = values.pop("type")
        # 兼容旧版 confirmed 字段：仅用于一次性迁移，不再写回。
        if "confirmed" in values and "state" not in values:
            values["state"] = "active" if values.pop("confirmed") else "disabled"
        defaults = {
            "enabled": True,
            "state": "active",
            "name": "",
            "description": "",
            "scope": "global",
            "project_id": None,
            "run_id": None,
            "expires_at": None,
            "source_event_id": None,
            "confidence": 1.0,
            "evidence": "",
            "created_at": _now(),
            "updated_at": _now(),
        }
        for key, value in defaults.items():
            values.setdefault(key, value)
        if set(values) != set(ContextEntry.__dataclass_fields__):
            raise ValueError("Context Markdown 元数据字段不合法")
        entry = ContextEntry(**values)
        if not isinstance(entry.content, str):
            raise ValueError("Context Markdown 正文不合法")
        if declared_hash and declared_hash != entry.content_hash:
            raise ValueError("Context 条目摘要不匹配")
        return entry

    def auto_put(self, candidate: "object") -> ContextEntry | None:
        """经过 MemoryGate 后自动写入；重复候选不产生新版本。"""
        from .memory_gate import MemoryCandidate, MemoryGate

        if not isinstance(candidate, MemoryCandidate):
            raise TypeError("candidate 必须是 MemoryCandidate")
        decision = MemoryGate().evaluate(candidate, self.list())
        if decision.action == "merge":
            return self.get(decision.duplicate_id) if decision.duplicate_id else None
        if decision.action not in {"write", "downgrade"} or decision.candidate is None:
            return None
        item = decision.candidate
        previous = self._entries.get(item.entry_id)
        now = _now()
        return self.put(
            ContextEntry(
                entry_id=item.entry_id,
                entry_type=item.entry_type,
                content=item.content,
                source=item.source,
                state="active",
                version=(previous.version + 1) if previous else 1,
                name=item.name,
                description=item.description,
                scope=item.scope,
                project_id=item.project_id,
                run_id=item.run_id,
                expires_at=item.expires_at,
                source_event_id=item.source_event_id,
                confidence=item.confidence,
                evidence=item.evidence,
                created_at=previous.created_at if previous else now,
                updated_at=now,
            )
        )

    @staticmethod
    def _expired(entry: ContextEntry) -> bool:
        if not entry.expires_at:
            return False
        try:
            return datetime.fromisoformat(entry.expires_at) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    def _write_index(self) -> None:
        payload = {
            "schema_version": 1,
            "entries": [
                {
                    "id": item.entry_id,
                    "type": item.entry_type,
                    "version": item.version,
                    "content_hash": item.content_hash,
                    "enabled": item.enabled,
                    "state": item.state,
                }
                for item in self.list()
            ],
        }
        self._atomic_write(
            self.root / "index.json",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)


def _sanitize_for_harness(content: str) -> str:
    """保留本地原文，只在冻结给 Harness 的快照上清除敏感明细。"""
    result = _WINDOWS_PATH.sub("[已脱敏]", content)
    result = _HOME_PATH.sub("[已脱敏]", result)
    result = _SECRET.sub("[已脱敏]", result)
    return _EXIF_LINE.sub("[已脱敏]", result)
