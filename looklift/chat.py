"""v2.1 无状态 AI 对话流程：安全上下文、结构化建议与本地契约校验。"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ai_proxy import prepare_ai_proxy
from .chat_contract import apply_chat_operations
from .providers import VisionProvider, get_provider
from .render.contract import ai_scalar_paths, param_bounds

_MAX_HISTORY_MESSAGES = 8


class ChatCancelled(Exception):
    """调用方明确取消本轮模型请求。"""


class ChatStepError(RuntimeError):
    """可安全返回给界面的稳定对话错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ChatStepResult:
    analysis: dict
    changes: tuple[dict, ...]
    rejected: tuple[dict, ...]
    explanation: str
    limitations: tuple[str, ...]
    approximation: str
    manual_steps: tuple[str, ...]
    done: bool
    provider: str
    proxy_count: int
    metadata_sent: bool


def chat_step(
    *,
    image_path: Path,
    current_analysis: dict,
    factor: float = 1.0,
    message: str,
    history: list[dict],
    include_metadata: bool,
    provider: VisionProvider | None = None,
) -> ChatStepResult:
    """执行一次无状态模型建议，并把原始输出限制在本地白盒参数契约内。"""
    selected = provider
    if selected is None:
        try:
            selected = get_provider("auto")
        except Exception as exc:  # provider 配置错误也必须转换成稳定文案
            raise _map_provider_error(exc) from None

    try:
        with prepare_ai_proxy(
            Path(image_path),
            analysis=current_analysis,
            factor=factor,
            include_metadata=include_metadata,
        ) as proxy:
            blocks = _request_blocks(
                proxy_path=proxy.path,
                metadata=proxy.metadata,
                current_analysis=current_analysis,
                factor=factor,
                message=message,
                history=history,
            )
            raw = selected.complete(_system_prompt(), blocks, CHAT_RESPONSE_SCHEMA)
            metadata_sent = bool(proxy.metadata)
    except ChatStepError:
        raise
    except (ChatCancelled, TimeoutError, subprocess.TimeoutExpired) as exc:
        # TimeoutError 是 OSError 的子类，必须先于图像 I/O 分支匹配。
        raise _map_provider_error(exc) from None
    except OSError:
        raise ChatStepError("image_error", "无法生成 AI 代理图，请重新选择照片。") from None
    except ValueError:
        # provider JSON 解析失败不能回显原始响应。
        raise ChatStepError("invalid_response", "AI 返回格式无效，请重试或继续手调。") from None
    except Exception as exc:
        raise _map_provider_error(exc) from None

    normalized = _normalize_response(raw)
    applied = apply_chat_operations(current_analysis, normalized["operations"])
    return ChatStepResult(
        analysis=applied.analysis,
        changes=applied.changes,
        rejected=applied.rejected,
        explanation=normalized["explanation"],
        limitations=tuple(normalized["limitations"]),
        approximation=normalized["approximation"],
        manual_steps=tuple(normalized["manual_steps"]),
        done=normalized["done"],
        provider=selected.name,
        proxy_count=1,
        metadata_sent=metadata_sent,
    )


def _request_blocks(
    *,
    proxy_path: Path,
    metadata: dict,
    current_analysis: dict,
    factor: float,
    message: str,
    history: list[dict],
) -> list[dict]:
    recent_history = history[-_MAX_HISTORY_MESSAGES:] if isinstance(history, list) else []
    context = {
        "current_analysis": current_analysis,
        "factor": factor,
        "recent_history": recent_history,
        "user_message": message,
    }
    blocks: list[dict] = [{
        "type": "text",
        "text": "本轮编辑上下文：\n" + json.dumps(context, ensure_ascii=False, sort_keys=True),
    }]
    if metadata:
        blocks.append({
            "type": "text",
            "text": "用户允许发送的安全拍摄信息：\n"
            + json.dumps(metadata, ensure_ascii=False, sort_keys=True),
        })
    blocks.append({"type": "image", "path": proxy_path, "label": "当前调色预览"})
    return blocks


def _system_prompt() -> str:
    scalar_contract = [
        {"path": path, "minimum": param_bounds(path)[0], "maximum": param_bounds(path)[1]}
        for path in ai_scalar_paths()
    ]
    return (
        "你是 LookLift 的白盒修图助手。只能建议下列标量参数的 delta/set，"
        "或一次性替换 tone_curve 主明度曲线。不得生成像素、局部蒙版、RGB 分通道曲线，"
        "也不得把不支持的局部请求偷换成无关的全局调整。超出能力时必须说明限制、"
        "可达到的近似方案和右侧面板手动步骤。所有解释使用中文。\n"
        "当前渲染画面是本轮效果事实，current_analysis 只是形成该画面的可编辑参数。"
        "不要因为参数来自用户手调或已经非零就默认保护它；只有用户明确要求保留某项效果时，"
        "才不得修改对应参数。对于当前引擎支持、且根据用户目标与当前画面判断需要调整的全局参数，"
        "必须在本次响应中返回 operation，不得只说之后可由用户手动微调。"
        "不得仅凭参数绝对值判断画面有问题，必须结合当前渲染画面和用户目标；"
        "没有 operation 时，只能是当前效果已经满足目标，或所需能力确实不受支持。\n"
        "标量参数契约：\n"
        + json.dumps(scalar_contract, ensure_ascii=False, separators=(",", ":"))
    )


def _normalize_response(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ChatStepError("invalid_response", "AI 返回格式无效，请重试或继续手调。")
    required_types = {
        "operations": list,
        "explanation": str,
        "limitations": list,
        "approximation": str,
        "manual_steps": list,
        "done": bool,
    }
    if any(key not in raw or not isinstance(raw[key], expected) for key, expected in required_types.items()):
        raise ChatStepError("invalid_response", "AI 返回格式无效，请重试或继续手调。")
    if not all(isinstance(item, str) for item in raw["limitations"]):
        raise ChatStepError("invalid_response", "AI 返回格式无效，请重试或继续手调。")
    if not all(isinstance(item, str) for item in raw["manual_steps"]):
        raise ChatStepError("invalid_response", "AI 返回格式无效，请重试或继续手调。")
    return {
        "operations": raw["operations"],
        "explanation": raw["explanation"].strip(),
        "limitations": [item.strip() for item in raw["limitations"] if item.strip()],
        "approximation": raw["approximation"].strip(),
        "manual_steps": [item.strip() for item in raw["manual_steps"] if item.strip()],
        "done": raw["done"],
    }


def _map_provider_error(exc: Exception) -> ChatStepError:
    if isinstance(exc, ChatCancelled):
        return ChatStepError("cancelled", "本轮 AI 调用已取消，当前正式版本未改变。")
    if isinstance(exc, (TimeoutError, subprocess.TimeoutExpired)):
        return ChatStepError("timeout", "AI 服务响应超时，请重试或继续手调。")
    lowered = str(exc).lower()
    if any(token in lowered for token in ("401", "403", "api_key", "鉴权", "unauthorized")):
        return ChatStepError("auth", "AI 服务鉴权失败，请检查供应商配置。")
    return ChatStepError("provider_error", "AI 服务调用失败，请重试或继续手调。")


CHAT_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["scalar", "tone_curve"]},
                    "path": {"type": "string"},
                    "mode": {"type": "string", "enum": ["delta", "set"]},
                    "value": {"type": "number"},
                    "points": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "input": {"type": "number", "minimum": 0, "maximum": 255},
                                "output": {"type": "number", "minimum": 0, "maximum": 255},
                            },
                            "required": ["input", "output"],
                            "additionalProperties": False,
                        },
                    },
                    "reason": {"type": "string"},
                },
                "required": ["type"],
                "additionalProperties": False,
            },
        },
        "explanation": {"type": "string"},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "approximation": {"type": "string"},
        "manual_steps": {"type": "array", "items": {"type": "string"}},
        "done": {"type": "boolean"},
    },
    "required": [
        "operations",
        "explanation",
        "limitations",
        "approximation",
        "manual_steps",
        "done",
    ],
    "additionalProperties": False,
}
