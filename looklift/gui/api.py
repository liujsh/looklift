"""业务路由 handler：HTTP 参数校验 + 核心模块调用 + JSON 响应。

`ROUTES` 是 `(method, pattern) -> handler` 的分发表，`pattern` 里最多一个
`<name>` 段参数，由 `server.py` 负责匹配解析、把请求上下文传给 handler。
handler 收到的不再只是段参数，而是一个请求上下文 dict：
`{"params": {...}, "body": bytes | None, "content_type": str, "query": {...}}`
（`body` 只有 `Content-Length` 头存在且 >0 时才不是 `None`），这样需要读请求体
的 handler（如 `/api/upload`）和只需要段参数的 handler 用同一套签名，不必再
分裂成两种 Handler 类型。

本文件只放 handler 表和业务 handler；design.md「API 路由一览」列出的路由
到 GUI-T10（风格库 + 报告页）为止已全部落地。
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .. import ai_proxy, analyzer, chat, config, intensity, report, xmp_writer
from ..render import contract as render_contract
from ..session_store import DatabaseRecoveryRequired, SessionSnapshot, SessionStore
from . import lookstore
from . import tasks
from . import upload

# handler 返回 `(status, dict)`（JSON 响应）或 `(status, bytes, content_type)`
# （二进制响应，`/api/preview` 的 JPEG 字节、`/report/<name>` 的 HTML 字节）；
# `server.py` 按返回值长度分发。
Handler = Callable[[dict], "tuple[int, dict] | tuple[int, bytes, str]"]

_VALID_PROVIDERS = {"auto", "cli", "api", "openai_compat", "ollama"}

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


_UNSAFE_LOOK_NAME_CHARS_RE = re.compile(r'[\\/<>:"|?*\x00-\x1f]')


def _validate_look_name(name: Any) -> str | None:
    """风格库名称安全校验：非空（含纯空白）、≤100 字符、不含路径分隔符/
    “..”/Windows 保留字符。不安全字符集与 `upload.py` 的 `sanitize_filename`
    一致，但语义相反——那边清洗的是用户看不到、不关心具体字符的上传文件名；
    这里的名字是用户自己起的、要在 UI 上原样展示出来，静默改写会让"存的
    名字"和"看到的名字"对不上，所以选择直接拒绝并提示中文原因，而不是静默
    清洗。所有 `/api/looks*` 与 `/report/<name>` 路由入口统一调用这个函数。

    返回 `None` 表示校验通过；否则返回中文错误信息，调用方直接包成
    `(400, {"error": ...})`。

    路径穿越是两层防御共同挡住的，这里只是第二层：`server.py` 的
    `_dispatch` 在按 `/` 切分路径段之前就先对整条路径 `unquote()` 过一遍
    （见 `_match_pattern` 按段数比较），所以 `..%2f..%2f` 这类编码过的斜杠
    在匹配路由前就已经展开成真正的 `/`，段数对不上 `<name>` 这个单段
    占位符，直接 404，走不到这个函数；这里补的是同一段里出现字面 `..`
    的情况（如 `/report/..`，只有两段，能匹配上路由），显式拒绝而不是
    依赖 `Path` 的行为——不同校验入口（json_path/xmp_path 拼接）对 `..`
    的处理方式不该是唯一的安全屏障。
    """
    if not isinstance(name, str) or not name.strip():
        return "风格名称不能为空"
    if len(name) > 100:
        return "风格名称过长（最多 100 字符）"
    if ".." in name:
        return "风格名称不能包含“..”"
    if _UNSAFE_LOOK_NAME_CHARS_RE.search(name):
        return '风格名称包含非法字符（不能有 / \\ < > : " | ? * 等）'
    return None


_ANALYSIS_TOP_LEVEL_KEYS = {"summary", "steps", "basic", "tone_curve", "hsl", "color_grading", "effects"}


def _validate_analysis(analysis: dict[str, Any]) -> str | None:
    """收藏前的最小结构校验（code review Critical/XSS 修复的第二层）。

    `POST /api/looks` 此前只检查 `analysis` 是不是一个 dict，任意内容都能
    落盘；`hsl[].color` 之类字段本该是固定枚举，`report.py` 的
    `_HSL_CN.get(color, color)` 在渲染报告页时把它当"受信任的固定词表"处理
    ——找不到映射就原样回退（现已在 report.py 补了 escape，见该文件注释），
    但源头本就不该让任意字符串混进这类字段。这里只挡"会被当成受信任枚举/
    固定类型使用"的最小集合，不是要在 GUI 层重新实现一遍
    `analyzer.ANALYSIS_SCHEMA` 那份完整 JSON Schema（那是给 AI 结构化输出
    用的强校验，字段更细、也没有 `additionalProperties` 之外的必要性）。

    返回 `None` 表示校验通过；否则返回中文错误信息。
    """
    if not set(analysis.keys()) <= _ANALYSIS_TOP_LEVEL_KEYS:
        return "analysis 包含未知字段"
    if "summary" in analysis and not isinstance(analysis["summary"], str):
        return "analysis.summary 必须是字符串"
    steps = analysis.get("steps", [])
    if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
        return "analysis.steps 必须是字符串数组"
    for entry in analysis.get("hsl") or []:
        if not isinstance(entry, dict) or entry.get("color") not in analyzer._COLOR_KEYS:
            return f"analysis.hsl 的 color 必须是以下之一：{', '.join(analyzer._COLOR_KEYS)}"
    return None


def _validate_factor(value: Any) -> "tuple[float, None] | tuple[None, tuple[int, dict]]":
    """校验 0-1 强度 factor 的类型 + 范围。`/api/preview`、`/api/looks`、
    `/api/looks/<name>/export` 三处都要校验同一份规则，抽成共享函数避免
    错误文案在三处慢慢漂移。字段本身是否必填由调用方各自决定（`/api/preview`
    必填；`/api/looks`/`export` 可选，缺省行为各不相同）。
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, (400, {"error": f"factor 必须是 0-1 之间的数字，收到：{value!r}"})
    value = float(value)
    if not (0.0 <= value <= 1.0):
        return None, (400, {"error": f"factor 必须在 0-1 之间，收到：{value}"})
    return value, None


def _ping(ctx: dict) -> tuple[int, dict]:
    """`GET /api/ping`：连通性探活。"""
    return 200, {"ok": True}


def _param_contract(ctx: dict) -> tuple[int, dict]:
    """把引擎参数契约机械投影给前端，不在 GUI 层维护范围或默认值副本。"""
    return 200, {
        path: {
            "min": render_contract.param_bounds(path)[0],
            "max": render_contract.param_bounds(path)[1],
            "default": render_contract.param_default(path),
        }
        for path in render_contract.param_paths()
    }


def _engine_probe(ctx: dict) -> tuple[int, dict]:
    """T1 打包门禁：经 HTTP 真实调用 pyvips 与 numba 融合渲染。"""
    from .sidecar import warm_engine

    return 200, warm_engine()


def _analyze_would_work(cfg: dict[str, Any]) -> bool:
    """纯函数：判断"分析请求现在发得出去"，即 GET /api/config 里的 `configured`。

    CLI/API 显式配置即可；OpenAI-compatible 还需 base_url/model，Ollama 还需 model。
    自动模式则是 config 里存了 api_key、环境变量 `ANTHROPIC_API_KEY` 有值（`providers.get_provider`
    在 backend="auto" 时就是把这个环境变量当"api 可用"的判据之一，见
    providers.py:136-137、design.md §10——这里的口径必须跟它保持一致，否则
    只用环境变量配置的用户每次启动都会被向导烦一遍，违反 requirements.md
    验收第 3 条"配置过一次后再次启动直接进主界面"）、或者本机 PATH 上有
    claude 命令。不直接依赖 `providers.get_provider`——那个函数在选不出
    后端时会抛异常，这里只想要一个布尔值，抽成独立纯函数也方便不起 HTTP
    server 单测。
    """
    provider = cfg["provider"]
    if provider in ("cli", "api"):
        return True
    if provider == "openai_compat":
        return bool(cfg["base_url"] and cfg["model"])
    if provider == "ollama":
        return bool(cfg["model"])
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
    # configured 判定要吃 env（LOOKLIFT_*/ANTHROPIC_API_KEY 都算"分析用得起来"），
    # 但表单可编辑字段 provider/model 必须回显磁盘原值：否则本次进程的临时 env
    # 覆盖会被回显进设置表单，用户一保存就固化进 config.toml（env baking）。
    cfg = config.load_config()
    disk_cfg = config.load_config(include_env=False)
    return 200, {
        "configured": _analyze_would_work(cfg),
        "provider": disk_cfg["provider"],
        "model": disk_cfg["model"],
        "base_url": disk_cfg["base_url"],
        "timeout": disk_cfg["timeout"],
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
        choices = "/".join(sorted(_VALID_PROVIDERS))
        return 400, {"error": f"provider 必须是 {choices} 之一，收到：{provider!r}"}

    cfg = config.load_config(include_env=False)
    for key in ("provider", "model"):
        if key in payload:
            cfg[key] = payload[key]
    # `GET /api/config` 已回填 base_url，故前端明确提交空字符串就是用户要清空、
    # 回到 Ollama 等后端默认地址；只有字段缺省才表示 partial update 的"保持不变"。
    if "base_url" in payload:
        cfg["base_url"] = payload["base_url"]
    if payload.get("api_key"):  # 空字符串／缺省字段 → 保留原值
        cfg["api_key"] = payload["api_key"]
    if "timeout" in payload:
        timeout = payload["timeout"]
        if timeout in ("", None):
            cfg["timeout"] = ""
        else:
            try:
                cfg["timeout"] = config.provider_timeout("api", timeout)
            except RuntimeError as exc:
                return 400, {"error": str(exc)}

    settings_error = _provider_settings_error(cfg)
    if settings_error:
        return 400, {"error": settings_error}

    config.save_config(cfg)
    return 200, {"ok": True}


def _provider_settings_error(cfg: dict[str, Any]) -> str | None:
    """校验新 provider 在保存后可实际发起分析所需的字段。"""
    if cfg["provider"] == "openai_compat":
        if not cfg["base_url"]:
            return "OpenAI-compatible 后端需要 base_url。"
        if not cfg["model"]:
            return "OpenAI-compatible 后端需要 model。"
    if cfg["provider"] == "ollama" and not cfg["model"]:
        return "Ollama 后端需要视觉模型 model。"
    return None


def _get_task(ctx: dict) -> tuple[int, dict]:
    """`GET /api/tasks/<id>`：查询长任务状态；未知 id 返回 404。"""
    task_id = ctx["params"]["id"]
    task = tasks.get(task_id)
    if task is None:
        return 404, {"error": f"未知任务：{task_id}"}
    return 200, task


def _post_looks(ctx: dict) -> tuple[int, dict]:
    """`POST /api/looks`：收藏当前分析结果到风格库（tasks.md T13 + design.md
    API 路由一览、requirements.md U4）。

    body：`name`（必填）、`analysis`（必填，完整分析结果 dict）、`factor`
    （可选，缺省 1.0——即滑杆在 100% 时收藏，与 CLI `analyze --name` 原样
    存下 AI 分析结果的行为一致）。收藏前先过 `intensity.scale_analysis` 把
    当前滑杆强度"烤"进落盘的 json/xmp（U20 验收"滑杆强度带入导出"）——这样
    后续导出/报告页直接读库里的 analysis，就是用户收藏那一刻看到的强度，
    不用在导出时再问一遍"要哪个强度"。重名一律拒绝（409），不静默覆盖：
    收藏是用户主动命名的操作，覆盖用户以为还在的旧风格是危险的静默行为。
    """
    body = ctx.get("body")
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return 400, {"error": "请求体不是合法 JSON"}
    if not isinstance(payload, dict):
        return 400, {"error": "请求体必须是 JSON 对象"}

    name = payload.get("name")
    name_err = _validate_look_name(name)
    if name_err:
        return 400, {"error": name_err}

    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return 400, {"error": "缺少 analysis 字段"}
    analysis_err = _validate_analysis(analysis)
    if analysis_err:
        return 400, {"error": analysis_err}

    factor, factor_err = _validate_factor(payload.get("factor", 1.0))
    if factor_err is not None:
        return factor_err

    looks_dir = config.looks_dir()
    if lookstore.exists(looks_dir, name):
        return 409, {"error": f"风格库中已存在同名条目：{name}"}
    # exists → save 之间不是原子操作:两个并发请求理论上都能通过这个检查、
    # 后写的覆盖先写的。GUI 是单用户本地进程模型(design.md 风险清单"本地
    # HTTP server 暴露面"——只信任本机同一用户,不做鉴权),不为这个边角
    # 情况引入文件锁,接受"后到请求赢"这个后果。

    scaled = intensity.scale_analysis(analysis, factor)
    lookstore.save(looks_dir, name, scaled)
    return 200, {"name": name}


def _get_looks(ctx: dict) -> tuple[int, dict]:
    """`GET /api/looks`：列出风格库，风格库面板卡片网格的数据源。

    响应包成 `{"looks": [...]}` 而不是裸数组——和本文件其余路由的响应形状
    （都是 JSON 对象）保持一致，也给以后加分页/总数之类的元数据留了口子，
    不用破坏性改响应的顶层类型。列表遍历/损坏 json 容错在 `lookstore.py`。
    """
    return 200, {"looks": lookstore.list_entries(config.looks_dir())}


def _get_look(ctx: dict) -> tuple[int, dict]:
    """`GET /api/looks/<name>`：读取某个风格的完整 analysis。"""
    name = ctx["params"]["name"]
    err = _validate_look_name(name)
    if err:
        return 400, {"error": err}
    analysis = lookstore.load(config.looks_dir(), name)
    if analysis is None:
        return 404, {"error": f"风格库中找不到：{name}"}
    return 200, analysis


def _export_look(ctx: dict) -> tuple[int, dict]:
    """`POST /api/looks/<name>/export`：按（可选覆盖的）强度导出预设/sidecar
    （tasks.md T13）。

    body：`factor`（可选——不传就直接用库里已经"烤"好的强度，传了就在那基础
    上再按 `intensity.scale_analysis` 缩放一次）、`sidecar`（可选，RAW 文件
    路径；给了就在其旁写同名 sidecar，不给就重新生成库内同名 `.xmp` 预设）。
    两种输出都先过 `xmp_writer.analysis_to_crs`，与 CLI `apply` 命令走的是
    同一条转换路径，产出的 crs 参数值理应逐字段相等。
    """
    name = ctx["params"]["name"]
    err = _validate_look_name(name)
    if err:
        return 400, {"error": err}

    body = ctx.get("body")
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        return 400, {"error": "请求体不是合法 JSON"}
    if not isinstance(payload, dict):
        return 400, {"error": "请求体必须是 JSON 对象"}

    looks_dir = config.looks_dir()
    analysis = lookstore.load(looks_dir, name)
    if analysis is None:
        return 404, {"error": f"风格库中找不到：{name}"}

    if payload.get("factor") is not None:
        factor, factor_err = _validate_factor(payload["factor"])
        if factor_err is not None:
            return factor_err
        analysis = intensity.scale_analysis(analysis, factor)

    sidecar = payload.get("sidecar")
    if sidecar:
        raw_path = Path(sidecar)
        if not raw_path.is_file():
            return 400, {"error": f"RAW 文件不存在：{sidecar}"}
        crs = xmp_writer.analysis_to_crs(analysis)
        out = xmp_writer.write_sidecar(crs, raw_path)
        return 200, {"sidecar": str(out.resolve())}

    out = lookstore.export_preset(looks_dir, name, analysis)
    return 200, {"preset": str(out.resolve())}


def _report(ctx: dict) -> "tuple[int, dict] | tuple[int, bytes, str]":
    """`GET /report/<name>`：独立报告页（U8）——直接是 `report.render_report`
    产出的自包含 HTML，不在 SPA 里重新实现一遍渲染逻辑（design.md 决策 3）。
    前端"打开报告"按钮用 `window.open` 打开这个路径：pywebview 窗口模式下
    WebView2 支持 `window.open` 弹出原生新窗口，browser 模式下就是普通新
    标签，两种模式前端写同一行代码，不必调用 Python 侧的
    `webview.create_window`（那样就要区分模式，维护两套前端逻辑）。

    `<name>` 段参数的路径穿越防御是两层的（详见 `_validate_look_name` 的
    docstring）：编码过的斜杠（`..%2f..%2f`）在 `server.py` 按 `/` 切分路径
    前就已经被 `unquote()` 展开，段数对不上单段占位符直接 404；同一段里
    的字面 `..`（如 `/report/..`）能匹配上路由，靠下面这行 `_validate_look_name`
    显式拒绝。
    """
    name = ctx["params"]["name"]
    err = _validate_look_name(name)
    if err:
        return 400, {"error": err}
    analysis = lookstore.load(config.looks_dir(), name)
    if analysis is None:
        return 404, {"error": f"风格库中找不到：{name}"}
    html = report.render_report(analysis, name)
    return 200, html.encode("utf-8"), "text/html; charset=utf-8"


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
    from ..preview import render_preview_jpeg

    return render_preview_jpeg(
        image_path,
        analysis,
        factor,
        max_edge=_PREVIEW_MAX_EDGE,
        quality=_PREVIEW_JPEG_QUALITY,
    )


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
    factor, err = _validate_factor(payload["factor"])
    if err is not None:
        return err

    jpeg_bytes = _render_preview(image_path, analysis, factor)
    return 200, jpeg_bytes, "image/jpeg"


def _json_body(ctx: dict) -> "tuple[dict, None] | tuple[None, tuple[int, dict]]":
    """读取 JSON 对象请求体，并统一输出稳定的中文 400。"""
    try:
        payload = json.loads(ctx.get("body") or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, (400, {"error": "请求体不是合法 JSON"})
    if not isinstance(payload, dict):
        return None, (400, {"error": "请求体必须是 JSON 对象"})
    return payload, None


def _validate_history(value: Any) -> str | None:
    if not isinstance(value, list):
        return "history 必须是消息数组"
    for item in value:
        if (
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
            or not item["content"].strip()
        ):
            return "history 中的消息必须包含有效 role 和 content"
    return None


def _chat_step(ctx: dict) -> tuple[int, dict]:
    payload, err = _json_body(ctx)
    if err is not None:
        return err
    image_path, err = _validate_image_path(payload.get("path"))
    if err is not None:
        return err
    analysis = payload.get("current_analysis")
    if not isinstance(analysis, dict):
        return 400, {"error": "current_analysis 必须是参数对象"}
    analysis_error = _validate_analysis(analysis)
    if analysis_error:
        return 400, {"error": f"current_analysis 无效：{analysis_error}"}
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return 400, {"error": "message 不能为空"}
    history = payload.get("history", [])
    history_error = _validate_history(history)
    if history_error:
        return 400, {"error": history_error}
    include_metadata = payload.get("include_metadata", False)
    if not isinstance(include_metadata, bool):
        return 400, {"error": "include_metadata 必须是布尔值"}
    if "factor" not in payload:
        return 400, {"error": "缺少 factor 字段"}
    factor, factor_error = _validate_factor(payload["factor"])
    if factor_error is not None:
        return factor_error
    try:
        result = chat.chat_step(
            image_path=image_path,
            current_analysis=analysis,
            factor=factor,
            message=message.strip(),
            history=history,
            include_metadata=include_metadata,
        )
    except chat.ChatStepError as exc:
        status = {"timeout": 504, "cancelled": 499, "image_error": 400}.get(exc.code, 502)
        return status, {"error": str(exc), "code": exc.code}
    return 200, asdict(result)


def _image_info(ctx: dict) -> tuple[int, dict]:
    payload, err = _json_body(ctx)
    if err is not None:
        return err
    image_path, err = _validate_image_path(payload.get("path"))
    if err is not None:
        return err
    try:
        return 200, ai_proxy.read_safe_image_info(image_path)
    except OSError:
        return 400, {"error": "无法读取拍摄信息"}


def _snapshot_payload(snapshot: SessionSnapshot) -> dict:
    return asdict(snapshot)


def _session_error(exc: Exception) -> tuple[int, dict]:
    if isinstance(exc, KeyError):
        return 404, {"error": "未找到指定会话"}
    if isinstance(exc, DatabaseRecoveryRequired):
        return 503, {"error": "会话数据库需要恢复，请先检查备份。"}
    if isinstance(exc, OSError):
        return 500, {"error": "会话数据库读写失败，请重试或检查存储位置。"}
    return 400, {"error": str(exc)}


def _create_session(ctx: dict) -> tuple[int, dict]:
    payload, err = _json_body(ctx)
    if err is not None:
        return err
    image_path, err = _validate_image_path(payload.get("path"))
    if err is not None:
        return err
    analysis = payload.get("initial_analysis")
    if not isinstance(analysis, dict):
        return 400, {"error": "initial_analysis 必须是参数对象"}
    analysis_error = _validate_analysis(analysis)
    if analysis_error:
        return 400, {"error": f"initial_analysis 无效：{analysis_error}"}
    try:
        snapshot = SessionStore().create_or_resume(str(image_path), analysis)
    except (ValueError, TypeError, OSError, DatabaseRecoveryRequired) as exc:
        return _session_error(exc)
    return 200, _snapshot_payload(snapshot)


def _get_session(ctx: dict) -> tuple[int, dict]:
    try:
        snapshot = SessionStore().load(ctx["params"]["id"])
    except (KeyError, OSError, DatabaseRecoveryRequired) as exc:
        return _session_error(exc)
    return 200, _snapshot_payload(snapshot)


def _get_sessions(ctx: dict) -> tuple[int, dict]:
    raw_limit = ctx.get("query", {}).get("limit", "8")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return 400, {"error": "limit 必须是 1 到 50 的整数"}
    try:
        sessions = SessionStore().list_recent(limit)
    except (ValueError, OSError, DatabaseRecoveryRequired) as exc:
        return _session_error(exc)
    return 200, {"sessions": [asdict(session) for session in sessions]}


def _commit_session(ctx: dict) -> tuple[int, dict]:
    payload, err = _json_body(ctx)
    if err is not None:
        return err
    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        return 400, {"error": "analysis 必须是参数对象"}
    analysis_error = _validate_analysis(analysis)
    if analysis_error:
        return 400, {"error": f"analysis 无效：{analysis_error}"}
    source = payload.get("source", "chat")
    if source not in {"chat", "manual", "library", "analysis"}:
        return 400, {"error": "source 必须是 chat、manual、library 或 analysis"}
    try:
        snapshot = SessionStore().commit_exchange(
            ctx["params"]["id"], payload.get("exchange"), analysis, source
        )
    except (KeyError, ValueError, TypeError, OSError, DatabaseRecoveryRequired) as exc:
        return _session_error(exc)
    return 200, _snapshot_payload(snapshot)


def _record_session_messages(ctx: dict) -> tuple[int, dict]:
    payload, err = _json_body(ctx)
    if err is not None:
        return err
    try:
        store = SessionStore()
        session_id = ctx["params"]["id"]
        store.record_failed_exchange(session_id, payload.get("exchange"))
        snapshot = store.load(session_id)
    except (KeyError, ValueError, TypeError, OSError, DatabaseRecoveryRequired) as exc:
        return _session_error(exc)
    return 200, _snapshot_payload(snapshot)


ROUTES: dict[tuple[str, str], Handler] = {
    ("GET", "/api/ping"): _ping,
    ("GET", "/api/param-contract"): _param_contract,
    ("GET", "/api/engine-probe"): _engine_probe,
    ("GET", "/api/config"): _get_config,
    ("POST", "/api/config"): _post_config,
    ("GET", "/api/tasks/<id>"): _get_task,
    ("POST", "/api/upload"): _upload,
    ("POST", "/api/analyze"): _analyze,
    ("POST", "/api/preview"): _preview,
    ("POST", "/api/chat/step"): _chat_step,
    ("POST", "/api/image-info"): _image_info,
    ("POST", "/api/sessions"): _create_session,
    ("GET", "/api/sessions"): _get_sessions,
    ("GET", "/api/sessions/<id>"): _get_session,
    ("POST", "/api/sessions/<id>/commit"): _commit_session,
    ("POST", "/api/sessions/<id>/messages"): _record_session_messages,
    ("POST", "/api/looks"): _post_looks,
    ("GET", "/api/looks"): _get_looks,
    ("GET", "/api/looks/<name>"): _get_look,
    ("POST", "/api/looks/<name>/export"): _export_look,
    ("GET", "/report/<name>"): _report,
}
