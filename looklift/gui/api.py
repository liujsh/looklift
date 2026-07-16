"""业务路由 handler：HTTP 参数校验 + 核心模块调用 + JSON 响应。

`ROUTES` 是 `(method, pattern) -> handler` 的分发表，`pattern` 里最多一个
`<name>` 段参数，由 `server.py` 负责匹配解析、把请求上下文传给 handler。
handler 收到的不再只是段参数，而是一个请求上下文 dict：
`{"params": {...}, "body": bytes | None, "content_type": str, "query": {...}}`
（`body` 只有 `Content-Length` 头存在且 >0 时才不是 `None`），这样需要读请求体
的 handler（如 `/api/upload`）和只需要段参数的 handler 用同一套签名，不必再
分裂成两种 Handler 类型。

本文件只放 handler 表和已落地的业务 handler；未落地的路由（`/api/analyze`
等，见 design.md「API 路由一览」）留给对应任务实现，不预先占位。
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Callable

from .. import config
from . import tasks
from . import upload

Handler = Callable[[dict], tuple[int, dict]]

_VALID_PROVIDERS = {"auto", "cli", "api"}


def _ping(ctx: dict) -> tuple[int, dict]:
    """`GET /api/ping`：连通性探活。"""
    return 200, {"ok": True}


def _analyze_would_work(cfg: dict[str, Any]) -> bool:
    """纯函数：判断"分析请求现在发得出去"，即 GET /api/config 里的 `configured`。

    四选一即算配好：provider 被显式指到 cli/api（用户已经做过选择）、config
    里存了 api_key、环境变量 `ANTHROPIC_API_KEY` 有值（`providers.get_provider`
    在 backend="auto" 时就是把这个环境变量当"api 可用"的判据之一，见
    providers.py:136-137、design.md §10——这里的口径必须跟它保持一致，否则
    只用环境变量配置的用户每次启动都会被向导烦一遍，违反 requirements.md
    验收第 3 条"配置过一次后再次启动直接进主界面"）、或者本机 PATH 上有
    claude 命令。不直接依赖 `providers.get_provider`——那个函数在选不出
    后端时会抛异常，这里只想要一个布尔值，抽成独立纯函数也方便不起 HTTP
    server 单测。
    """
    if cfg["provider"] in ("cli", "api"):
        return True
    if cfg["api_key"]:
        return True
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    return shutil.which("claude") is not None


def _get_config(ctx: dict) -> tuple[int, dict]:
    """`GET /api/config`：配置向导/设置面板读取当前状态。

    绝不在响应里带 `api_key` 原文——`has_key` 布尔值够前端判断"要不要提示
    去填"，没必要把密钥吐回浏览器里。
    """
    cfg = config.load_config()
    return 200, {
        "configured": _analyze_would_work(cfg),
        "provider": cfg["provider"],
        "model": cfg["model"],
        "has_key": bool(cfg["api_key"]),
    }


def _post_config(ctx: dict) -> tuple[int, dict]:
    """`POST /api/config`：配置向导/设置面板保存。

    body 的字段全部可选，缺省字段保持磁盘上原有配置不变（partial update）；
    `api_key` 有个特例——空字符串代表"保留原值"而不是"清空"，因为前端出于
    安全考虑从不把已保存的密钥回填进输入框，用户不改密钥直接点保存时，
    表单提交上来的就是空字符串，不能把这个当成"用户想清空密钥"。真要清空
    密钥得走别的显式操作（当前 UI 未提供，也不在本任务范围）。

    合并基准用 `config.load_config(include_env=False)`——不能用带
    `LOOKLIFT_*` 环境变量覆盖的默认视图，否则这次进程运行期间生效的临时
    环境变量会被这次保存动作意外固化进 config.toml（比如设了
    `LOOKLIFT_LOOKS_DIR` 只是想临时换个目录跑一次，保存 provider 设置时却
    把这个目录也永久写进了配置文件）。
    """
    body = ctx.get("body")
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return 400, {"error": "请求体不是合法 JSON"}
    if not isinstance(payload, dict):
        return 400, {"error": "请求体必须是 JSON 对象"}

    provider = payload.get("provider")
    if provider is not None and provider not in _VALID_PROVIDERS:
        return 400, {"error": f"provider 必须是 auto/cli/api 之一，收到：{provider!r}"}

    cfg = config.load_config(include_env=False)
    for key in ("provider", "model", "base_url"):
        if key in payload:
            cfg[key] = payload[key]
    if payload.get("api_key"):  # 空字符串／缺省字段 → 保留原值
        cfg["api_key"] = payload["api_key"]

    config.save_config(cfg)
    return 200, {"ok": True}


def _get_task(ctx: dict) -> tuple[int, dict]:
    """`GET /api/tasks/<id>`：查询长任务状态；未知 id 返回 404。"""
    task_id = ctx["params"]["id"]
    task = tasks.get(task_id)
    if task is None:
        return 404, {"error": f"未知任务：{task_id}"}
    return 200, task


def _report_placeholder(ctx: dict) -> tuple[int, dict]:
    """`GET /report/<name>`：占位。真正的报告渲染在后续任务接入 `report.render_report`。"""
    return 501, {"error": "报告页尚未实现"}


def _upload(ctx: dict) -> tuple[int, dict]:
    """`POST /api/upload`：browser 模式专用（design.md 决策 4）——浏览器标签页
    拿不到拖拽文件的真实文件系统路径，只能把文件内容以 multipart/form-data
    上传，本地落一份临时文件，把临时路径回传给前端，后续分析请求带这个路径。

    只做 HTTP 参数校验 + 调用 `upload.py` 的纯逻辑 + 状态码/JSON 翻译，
    multipart 解析、文件名清洗、落盘细节都在 `upload.py`。校验顺序：内容
    类型/空 body → 大小上限 → multipart 解析 → 是否有文件字段 → 落盘（写入
    失败一律翻译成通用中文 400，不回显本地文件系统路径）。
    """
    body = ctx.get("body")
    content_type = ctx.get("content_type") or ""
    if not body or "multipart/form-data" not in content_type:
        return 400, {"error": "请求体为空，或不是 multipart/form-data 格式"}
    if len(body) > upload.MAX_UPLOAD_BYTES:
        limit_mb = upload.MAX_UPLOAD_BYTES // (1024 * 1024)
        return 413, {"error": f"文件超过大小上限（{limit_mb}MB）"}

    try:
        parsed = upload.parse_multipart_first_file(body, content_type)
    except Exception:  # noqa: BLE001 —— 任何解析异常都视为「请求体损坏」
        return 400, {"error": "multipart 请求体解析失败"}
    if parsed is None:
        return 400, {"error": "未找到上传文件字段"}

    filename, content = parsed
    try:
        dest = upload.save_upload(upload.upload_dir(), filename, content)
    except OSError:  # noqa: BLE001 —— 清洗兜不住的边角情况，绝不把本地路径回显给客户端
        return 400, {"error": "文件名不合法，无法保存"}
    return 200, {"path": str(dest)}


ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/api/ping"): _ping,
    ("GET", "/api/config"): _get_config,
    ("POST", "/api/config"): _post_config,
    ("GET", "/api/tasks/<id>"): _get_task,
    ("POST", "/api/upload"): _upload,
    ("GET", "/report/<name>"): _report_placeholder,
}
