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

from typing import Callable

from . import tasks
from . import upload

Handler = Callable[[dict], tuple[int, dict]]


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
    ("GET", "/api/tasks/<id>"): _get_task,
    ("POST", "/api/upload"): _upload,
    ("GET", "/report/<name>"): _report_placeholder,
}
