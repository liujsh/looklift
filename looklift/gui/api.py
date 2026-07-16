"""业务路由 handler：HTTP 参数校验 + 核心模块调用 + JSON 响应。

`ROUTES` 是 `(method, pattern) -> handler` 的分发表，`pattern` 里最多一个
`<name>` 段参数，由 `server.py` 负责匹配解析、把请求上下文传给 handler。
handler 收到的不再只是段参数，而是一个请求上下文 dict：
`{"params": {...}, "body": bytes | None, "content_type": str, "query": {...}}`
（`body` 只有 `Content-Length` 头存在且 >0 时才不是 `None`），这样需要读请求体
的 handler（如 `/api/upload`）和只需要段参数的 handler 用同一套签名，不必再
分裂成两种 Handler 类型。

本文件只放 handler 表和已落地的业务 handler；未落地的路由（`/api/config`、
`/api/analyze` 等，见 design.md「API 路由一览」）留给对应任务实现，不预先占位。
"""
from __future__ import annotations

import email
import tempfile
import uuid
from email.policy import default as _email_default_policy
from pathlib import Path
from typing import Callable

from . import tasks

Handler = Callable[[dict], tuple[int, dict]]

# `POST /api/upload` 大小上限：50MB。测试里会 monkeypatch 这个模块级常量来验
# 证 413 分支，别把它内联进函数体。
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# 本进程的上传临时目录，`tempfile.mkdtemp` 只在第一次真正用到时创建（惰性），
# 之后一直复用到进程退出——不是每次上传都新建一个目录。
_upload_dir_path: Path | None = None


def _ping(ctx: dict) -> tuple[int, dict]:
    """`GET /api/ping`：连通性探活。"""
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

    校验顺序：内容类型/空 body → 大小上限 → multipart 解析 → 是否有文件字段。
    """
    body = ctx.get("body")
    content_type = ctx.get("content_type") or ""
    if not body or "multipart/form-data" not in content_type:
        return 400, {"error": "请求体为空，或不是 multipart/form-data 格式"}
    if len(body) > _MAX_UPLOAD_BYTES:
        limit_mb = _MAX_UPLOAD_BYTES // (1024 * 1024)
        return 413, {"error": f"文件超过大小上限（{limit_mb}MB）"}

    try:
        parsed = _parse_multipart_first_file(body, content_type)
    except Exception:  # noqa: BLE001 —— 任何解析异常都视为「请求体损坏」
        return 400, {"error": "multipart 请求体解析失败"}
    if parsed is None:
        return 400, {"error": "未找到上传文件字段"}

    filename, content = parsed
    dest = _upload_dir() / f"{uuid.uuid4().hex}_{_sanitize_filename(filename)}"
    dest.write_bytes(content)
    return 200, {"path": str(dest)}


def _upload_dir() -> Path:
    """本进程的上传临时目录，惰性创建、之后复用（模块级缓存）。"""
    global _upload_dir_path
    if _upload_dir_path is None:
        _upload_dir_path = Path(tempfile.mkdtemp(prefix="looklift-upload-"))
    return _upload_dir_path


def _parse_multipart_first_file(body: bytes, content_type: str) -> tuple[str, bytes] | None:
    """从 multipart/form-data 请求体里解析出第一个带文件名的字段，返回
    `(filename, content_bytes)`；没有文件字段时返回 `None`。

    实现选择：用 stdlib `email` 模块而不是手写 boundary 切分——Python 3.13
    移除了曾经常用于这个场景的 `cgi.FieldStorage`，`email.message_from_bytes`
    本身就能正确处理 multipart 的边界解析（转义、结尾 `--`、CRLF 细节），比
    自己重新实现一遍这些边角情况更可靠。做法是把 HTTP 请求已经拿到的
    `Content-Type`（含 boundary 参数）当成一封 MIME 邮件的头部，拼在 body 前面
    交给 `email` 解析，再遍历各 part 找 `Content-Disposition` 带 `filename` 的
    那个。
    """
    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = email.message_from_bytes(header + body, policy=_email_default_policy)
    if not message.is_multipart():
        return None
    for part in message.iter_parts():
        filename = part.get_filename()
        if filename:
            return filename, part.get_payload(decode=True) or b""
    return None


def _sanitize_filename(filename: str) -> str:
    """只保留文件名本身，去掉任何路径分隔符（`/` 或 `\\`）——防止恶意
    `filename` 里带 `../` 之类的段试图跳出上传目录。"""
    normalized = filename.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].strip()
    return name or "upload"


ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/api/ping"): _ping,
    ("GET", "/api/tasks/<id>"): _get_task,
    ("POST", "/api/upload"): _upload,
    ("GET", "/report/<name>"): _report_placeholder,
}
