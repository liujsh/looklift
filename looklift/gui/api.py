"""业务路由 handler：HTTP 参数校验 + 核心模块调用 + JSON 响应。

`ROUTES` 是 `(method, pattern) -> handler` 的分发表，`pattern` 里最多一个
`<name>` 段参数，由 `server.py` 负责匹配解析、把捕获到的值传给 handler。
本文件只放 handler 表和已落地的业务 handler；未落地的路由（`/api/config`、
`/api/analyze` 等，见 design.md「API 路由一览」）留给对应任务实现，不预先占位。
"""
from __future__ import annotations

from typing import Callable

from . import tasks

Handler = Callable[[dict[str, str]], tuple[int, dict]]


def _ping(params: dict[str, str]) -> tuple[int, dict]:
    """`GET /api/ping`：连通性探活。"""
    return 200, {"ok": True}


def _get_task(params: dict[str, str]) -> tuple[int, dict]:
    """`GET /api/tasks/<id>`：查询长任务状态；未知 id 返回 404。"""
    task_id = params["id"]
    task = tasks.get(task_id)
    if task is None:
        return 404, {"error": f"未知任务：{task_id}"}
    return 200, task


def _report_placeholder(params: dict[str, str]) -> tuple[int, dict]:
    """`GET /report/<name>`：占位。真正的报告渲染在后续任务接入 `report.render_report`。"""
    return 501, {"error": "报告页尚未实现"}


ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/api/ping"): _ping,
    ("GET", "/api/tasks/<id>"): _get_task,
    ("GET", "/report/<name>"): _report_placeholder,
}
