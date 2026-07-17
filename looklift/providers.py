"""VisionProvider 接口与实现:统一「发图+文字,按 schema 收 JSON」的传输层。

Block 约定:
  {"type": "text", "text": str}
  {"type": "image", "path": Path, "label": str}   # label 如 "原片"/"成片"/"效果图"
"""
from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Protocol

from . import config

MODEL = "claude-opus-4-8"
MAX_EDGE = 1568  # 控制图片 token 消耗;分析色调影调无需原始分辨率


class VisionProvider(Protocol):
    name: str

    def complete(self, system: str, blocks: list[dict], schema: dict) -> dict: ...


def _extract_json(text: str) -> dict[str, Any]:
    """从文本中提取第一个完整的 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"未能从模型输出中解析出 JSON:\n{text[:500]}")
    return json.loads(text[start : end + 1])


class ClaudeCliProvider:
    """走本地 Claude Code CLI(claude -p),prompt 从 stdin 传(Windows 8K 参数上限)。"""

    name = "cli"

    def complete(self, system: str, blocks: list[dict], schema: dict) -> dict:
        claude = shutil.which("claude")
        if not claude:
            raise RuntimeError("未找到 claude 命令,请先安装 Claude Code CLI。")
        parts = [system, ""]
        for b in blocks:
            if b["type"] == "text":
                parts.append(b["text"])
            else:
                parts.append(f"请用 Read 工具查看{b['label']}: {Path(b['path']).resolve()}")
        parts.append(
            "最终回答必须且只能是一个 JSON 对象(不要 markdown 代码块),严格符合以下 JSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False)
        )
        # prompt 从 stdin 传入:Windows 上 claude 是 .CMD 包装,命令行参数有 ~8K 长度上限,
        # 带完整 JSON Schema 的 prompt 会被截断
        proc = subprocess.run(
            [claude, "-p", "--output-format", "json", "--allowedTools", "Read"],
            input="\n".join(parts),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=600,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI 调用失败:\n{proc.stderr or proc.stdout}")
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(
                f"claude CLI 返回了非 JSON 输出:\nstdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:500]}"
            ) from None
        return _extract_json(envelope.get("result", ""))


class AnthropicProvider:
    """Anthropic 官方 API,json_schema 结构化输出。"""

    name = "api"

    def complete(self, system: str, blocks: list[dict], schema: dict) -> dict:
        import anthropic

        content: list[dict[str, Any]] = []
        for b in blocks:
            if b["type"] == "text":
                content.append({"type": "text", "text": b["text"]})
            else:
                content.append({"type": "text", "text": f"这是{b['label']}:"})
                content.append(_image_block(b["path"]))
        cfg = config.load_config()
        client = anthropic.Anthropic(api_key=cfg["api_key"] or None, base_url=cfg["base_url"] or None)
        model = cfg["model"] or MODEL
        with client.messages.stream(
            model=model,
            max_tokens=16000,
            system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            raise RuntimeError("模型拒绝了本次请求,请换一张照片重试。")
        return json.loads(next(b.text for b in response.content if b.type == "text"))


def _encode_image(path: str | Path) -> tuple[str, str]:
    """读取图片,必要时缩小,返回 (base64, media_type)。"""
    from PIL import Image

    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def _image_block(path: str | Path) -> dict[str, Any]:
    data, media_type = _encode_image(path)
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def get_provider(backend: str = "auto") -> VisionProvider:
    if backend == "auto":
        configured = config.load_config()["provider"]
        if configured in ("cli", "api"):
            backend = configured
    if backend == "auto":
        if os.environ.get("ANTHROPIC_API_KEY") or config.load_config()["api_key"]:
            backend = "api"
        elif shutil.which("claude"):
            backend = "cli"
        else:
            raise RuntimeError(
                "未找到可用后端:请设置 ANTHROPIC_API_KEY,或安装 Claude Code CLI(claude 命令)。"
            )
    return AnthropicProvider() if backend == "api" else ClaudeCliProvider()
