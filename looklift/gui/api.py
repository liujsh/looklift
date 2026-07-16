"""业务路由 handler：HTTP 参数校验 + 核心模块调用 + JSON 响应。

`ROUTES` 是 `(method, pattern) -> handler` 的分发表，`pattern` 里最多一个
`<name>` 段参数，由 `server.py` 负责匹配解析、把请求上下文传给 handler。
handler 收到的不再只是段参数，而是一个请求上下文 dict：
`{"params": {...}, "body": bytes | None, "content_type": str, "query": {...}}`
（`body` 只有 `Content-Length` 头存在且 >0 时才不是 `None`），这样需要读请求体
的 handler（如 `/api/upload`）和只需要段参数的 handler 用同一套签名，不必再
分裂成两种 Handler 类型。

本文件只放 handler 表和已落地的业务 handler；未落地的路由（`/api/preview`
`/api/looks` 等，见 design.md「API 路由一览」）留给对应任务实现，不预先
占位。
"""
from __future__ import annotations

import io
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .. import analyzer, config, intensity, render
from . import tasks
from . import upload

# handler 返回 `(status, dict)`（JSON 响应）或 `(status, bytes, content_type)`
# （二进制响应，目前只有 `/api/preview` 用）；`server.py` 按返回值长度分发。
Handler = Callable[[dict], "tuple[int, dict] | tuple[int, bytes, str]"]

_VALID_PROVIDERS = {"auto", "cli", "api"}

_ANALYZE_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

# `/api/preview` 风险清单「大图内存」缓解:预览统一缩到长边这个上限再渲染,
# 不用原始分辨率做仅供观感的预览(见 design.md)。
_PREVIEW_MAX_EDGE = 2048
_PREVIEW_JPEG_QUALITY = 88


def _validate_image_path(path: Any) -> "tuple[Path, None] | tuple[None, tuple[int, dict]]":
    """校验图片路径:必填、文件存在、扩展名受支持。

    `/api/analyze` 和 `/api/preview` 共用同一份规则,抽成一个函数避免两处
    分别维护、容易漂移。返回 `(Path, None)` 表示校验通过;`(None, (status,
    body))` 表示校验失败,调用方直接 `return err` 即可。
    """
    if not path:
        return None, (400, {"error": "缺少 path 字段"})
    image_path = Path(path)
    if not image_path.is_file():
        return None, (400, {"error": f"文件不存在：{path}"})
    if image_path.suffix.lower() not in _ANALYZE_ALLOWED_EXTS:
        return None, (400, {"error": f"不支持的图片格式：{image_path.suffix or '（无扩展名）'}"})
    return image_path, None


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


def _analyze(ctx: dict) -> tuple[int, dict]:
    """`POST /api/analyze`：提交分析任务，立即返回 `task_id`（design.md 决策 2
    轮询 + 风险清单「长任务卡 UI」）。真正的 `analyzer.analyze` 调用要 30-120
    秒，必须经 `tasks.submit` 在后台守护线程里跑，这里只做参数校验 + 起任务，
    不能等分析跑完才返回，否则会把 HTTP 请求处理线程（进而 pywebview 窗口）
    卡住。

    body 字段：`path`（必填，成片路径）、`original`（可选，原片路径，用于
    原片/成片对比模式）、`hint`（可选，风格提示）、`backend`（可选，透传给
    `analyzer.analyze`，缺省 "auto"，见 design.md API 路由一览）。
    """
    body = ctx.get("body")
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return 400, {"error": "请求体不是合法 JSON"}
    if not isinstance(payload, dict):
        return 400, {"error": "请求体必须是 JSON 对象"}

    image_path, err = _validate_image_path(payload.get("path"))
    if err is not None:
        return err

    original = payload.get("original") or None
    hint = payload.get("hint") or None
    backend = payload.get("backend") or "auto"

    task_id = tasks.submit(analyzer.analyze, image_path, original=original, style_hint=hint, backend=backend)
    return 200, {"task_id": task_id}


def _render_preview(image_path: Path, analysis: dict, factor: float) -> bytes:
    """预览渲染管线:开图 → 缩到长边 `_PREVIEW_MAX_EDGE`(风险清单「大图内存」)
    → `intensity.scale_analysis` → `render.render` → JPEG 编码。抽成独立函数
    而不是散在 handler 里——这是这个路由唯一的"业务逻辑"，`_preview` 只做
    HTTP 参数校验和分发，图像管线细节集中在这一处，符合分层规范。
    """
    with Image.open(image_path) as opened:
        img = opened.convert("RGB")
    img.thumbnail((_PREVIEW_MAX_EDGE, _PREVIEW_MAX_EDGE), Image.LANCZOS)
    scaled = intensity.scale_analysis(analysis, factor)
    rendered = render.render(img, scaled)
    buf = io.BytesIO()
    rendered.save(buf, format="JPEG", quality=_PREVIEW_JPEG_QUALITY)
    return buf.getvalue()


def _preview(ctx: dict) -> "tuple[int, dict] | tuple[int, bytes, str]":
    """`POST /api/preview`：按当前强度 `factor` 渲染 before/after 预览图
    （design.md 强度缩放语义「GUI 侧用法」+ API 路由一览 `/api/preview` 行）。

    body 字段：`path`（必填，图片路径，复用 `_validate_image_path`）、
    `analysis`（必填，完整分析结果 dict）、`factor`（必填，0-1 浮点，对应
    滑杆 0%-100%）。`factor=0` 时 `scale_analysis` 把所有偏移量归零，等价于
    "无调整渲染"——前端用它同时取 before 图（尺寸经过同一条缩放管线，与
    after 图对齐），不用另外维护一条不缩放的路径。

    同步处理，不走 `tasks.py` 的后台任务队列：2048px 长边的渲染耗时约
    1-2 秒，量级上远低于 `analyze` 的 30-120 秒——那才是必须后台线程 + 轮询
    的场景（见 design.md 决策 2）。这里一次同步 HTTP 往返用户可接受，引入
    task_id/轮询只会增加前端复杂度，不成比例。
    """
    body = ctx.get("body")
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return 400, {"error": "请求体不是合法 JSON"}
    if not isinstance(payload, dict):
        return 400, {"error": "请求体必须是 JSON 对象"}

    image_path, err = _validate_image_path(payload.get("path"))
    if err is not None:
        return err

    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return 400, {"error": "缺少 analysis 字段"}

    if "factor" not in payload:
        return 400, {"error": "缺少 factor 字段"}
    factor = payload["factor"]
    if isinstance(factor, bool) or not isinstance(factor, (int, float)):
        return 400, {"error": f"factor 必须是 0-1 之间的数字，收到：{factor!r}"}
    factor = float(factor)
    if not (0.0 <= factor <= 1.0):
        return 400, {"error": f"factor 必须在 0-1 之间，收到：{factor}"}

    jpeg_bytes = _render_preview(image_path, analysis, factor)
    return 200, jpeg_bytes, "image/jpeg"


ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/api/ping"): _ping,
    ("GET", "/api/config"): _get_config,
    ("POST", "/api/config"): _post_config,
    ("GET", "/api/tasks/<id>"): _get_task,
    ("POST", "/api/upload"): _upload,
    ("POST", "/api/analyze"): _analyze,
    ("POST", "/api/preview"): _preview,
    ("GET", "/report/<name>"): _report_placeholder,
}
