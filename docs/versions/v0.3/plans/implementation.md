# looklift v0.3「像——精度闭环」实施计划

**Goal:** 实现本地近似渲染 preview + 还原度评分 + refine 自动闭环 + .cube LUT 导出,并完成 provider 抽象与配置体系(spec: `docs/versions/v0.3/spec.md`)。

**Architecture:** 新增 `config.py`(配置/目录解析)、`providers.py`(VisionProvider 接口,现有 cli/api 后端迁入)、`render.py`(渲染管线+评分)、`lut.py`(cube 导出)、`autorefine.py`(闭环);`analyzer.py` 瘦身为 prompt 组装 + 调 provider;`cli.py` 加 `preview`/`export-lut` 子命令和 `refine --auto`。

**Tech Stack:** Python ≥3.11(tomllib)、Pillow、numpy(新依赖)、pytest。

## Global Constraints

- 测试不触网、不调 AI(现有原则,pytest 全部离线可跑)
- preview/评分/LUT 假设 sRGB JPEG/PNG 输入;不承诺与 LR 渲染一致
- 行为兼容:现有 23 个测试必须全程保持绿色;cwd 下有 `looks/` 时优先用它
- 中文用户文案;代码注释风格与现有模块一致
- 迭代中只运行当前 Task 涉及的测试文件；全量套件仅在 Task 9 收口时运行一次

---

### Task 1: 配置体系 config.py

**Files:**
- Create: `looklift/config.py`
- Modify: `pyproject.toml`(requires-python ">=3.11")
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_config() -> dict[str, Any]`(键:`provider/model/api_key/base_url/looks_dir`,env `LOOKLIFT_*` 覆盖文件);`looks_dir() -> Path`(优先级:cwd `looks/` 存在 → 用它;否则 config `looks_dir`;否则 `~/.looklift/looks/`);`CONFIG_PATH: Path`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config.py
import os
from pathlib import Path
from looklift import config


def test_load_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nonexistent.toml")
    for k in list(os.environ):
        if k.startswith("LOOKLIFT_"):
            monkeypatch.delenv(k)
    cfg = config.load_config()
    assert cfg["provider"] == "auto"
    assert cfg["api_key"] == ""


def test_load_config_file_and_env_override(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('provider = "api"\nmodel = "m1"\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    monkeypatch.setenv("LOOKLIFT_MODEL", "m2")
    cfg = config.load_config()
    assert cfg["provider"] == "api"   # 来自文件
    assert cfg["model"] == "m2"       # env 覆盖文件


def test_looks_dir_prefers_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.delenv("LOOKLIFT_LOOKS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "looks").mkdir()
    assert config.looks_dir() == Path("looks")


def test_looks_dir_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.delenv("LOOKLIFT_LOOKS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # 无 looks/
    assert config.looks_dir() == Path.home() / ".looklift" / "looks"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_config.py -q`
Expected: FAIL(`No module named 'looklift.config'`)

- [ ] **Step 3: 最小实现**

```python
# looklift/config.py
"""配置体系:~/.looklift/config.toml,环境变量 LOOKLIFT_* 覆盖。"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".looklift" / "config.toml"

_DEFAULTS = {"provider": "auto", "model": "", "api_key": "", "base_url": "", "looks_dir": ""}


def load_config() -> dict[str, Any]:
    cfg = dict(_DEFAULTS)
    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open("rb") as f:
            data = tomllib.load(f)
        cfg.update({k: v for k, v in data.items() if k in _DEFAULTS})
    for key in _DEFAULTS:
        env = os.environ.get(f"LOOKLIFT_{key.upper()}")
        if env:
            cfg[key] = env
    return cfg


def looks_dir() -> Path:
    """风格库目录:cwd 下有 looks/ 优先(向后兼容),否则配置项,否则 ~/.looklift/looks/。"""
    local = Path("looks")
    if local.is_dir():
        return local
    configured = load_config()["looks_dir"]
    if configured:
        return Path(configured)
    return Path.home() / ".looklift" / "looks"
```

并把 `pyproject.toml` 的 `requires-python = ">=3.10"` 改为 `">=3.11"`(tomllib 需要)。

- [ ] **Step 4: 跑测试确认通过**

Run: `pytest tests/test_config.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add looklift/config.py tests/test_config.py pyproject.toml
git commit -m "feat: add config module (~/.looklift/config.toml, env override, looks_dir resolution)"
```

---

### Task 2: 风格库目录迁移(cli.py 接入 config)

**Files:**
- Modify: `looklift/cli.py`(删除 `LOOKS_DIR = Path("looks")` 常量,全部改调 `config.looks_dir()`)
- Test: `tests/test_cli.py`(追加)

**Interfaces:**
- Consumes: `config.looks_dir() -> Path`
- Produces: cli 内部函数 `_looks_dir() -> Path`(等价转发,便于测试 monkeypatch);`_resolve_template`/`cmd_list`/`_emit_outputs`/`cmd_analyze` 行为不变但目录来源变化

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli.py 追加
def test_resolve_template_uses_global_looks(monkeypatch, tmp_path, sample_analysis):
    """cwd 无 looks/ 时,模版名字应在全局库(config.looks_dir())中解析。"""
    import json
    from looklift import cli, config
    globaldir = tmp_path / "globallooks"
    globaldir.mkdir()
    (globaldir / "mystyle.json").write_text(json.dumps(sample_analysis), encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # cwd 无 looks/
    monkeypatch.setattr(config, "looks_dir", lambda: globaldir)
    assert cli._resolve_template("mystyle") == globaldir / "mystyle.json"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `pytest tests/test_cli.py -q`
Expected: 新测试 FAIL(cli 仍用模块常量 `LOOKS_DIR`,找不到模版)

- [ ] **Step 3: 实现**

`cli.py` 中:删除 `LOOKS_DIR = Path("looks")`;新增

```python
from . import analyzer, config, report, xmp_reader, xmp_writer

def _looks_dir() -> Path:
    return config.looks_dir()
```

把 `_resolve_template`、`cmd_list`、`_emit_outputs`、`cmd_analyze` 中所有 `LOOKS_DIR` 替换为 `_looks_dir()` 调用(`mkdir(exist_ok=True)` 处改 `d = _looks_dir(); d.mkdir(parents=True, exist_ok=True)`,全局目录父级可能不存在)。报错与提示文案中的 `looks/` 改为动态 `f"{_looks_dir()}"`。

- [ ] **Step 4: 跑相关测试** — `pytest tests/test_cli.py tests/test_config.py -q` 全绿（覆盖 cwd 优先与配置目录回退）

- [ ] **Step 5: Commit**

```bash
git add looklift/cli.py tests/test_cli.py
git commit -m "feat: style library resolves via config.looks_dir (cwd looks/ wins, else ~/.looklift/looks)"
```

---

### Task 3: Provider 抽象(providers.py,analyzer 重构)

**Files:**
- Create: `looklift/providers.py`
- Modify: `looklift/analyzer.py`(prompt 组装保留,传输层迁出)
- Test: `tests/test_providers.py`;`tests/test_analyzer.py` 保持全绿

**Interfaces:**
- Consumes: `config.load_config()`
- Produces:
  - Block 约定:`{"type": "text", "text": str}` 或 `{"type": "image", "path": Path, "label": str}`
  - `class VisionProvider(Protocol): def complete(self, system: str, blocks: list[dict], schema: dict) -> dict`
  - `class ClaudeCliProvider` / `class AnthropicProvider`(实现 complete)
  - `def get_provider(backend: str = "auto") -> VisionProvider`(auto 逻辑 = 现 `resolve_backend`,并先看 config 的 provider 项)
  - `analyzer.resolve_backend` 保留(转发,兼容现有测试);`analyzer._extract_json`/`_normalize` 不动

- [ ] **Step 1: 写失败测试**

```python
# tests/test_providers.py
import json
from pathlib import Path
from looklift import providers


def test_cli_provider_builds_read_instructions(monkeypatch):
    """image block 应转成 Read 工具指令;text block 原样;schema 拼在结尾。"""
    captured = {}

    def fake_run(cmd, input, **kw):
        captured["prompt"] = input
        class P:
            returncode = 0
            stdout = json.dumps({"result": json.dumps({"summary": "ok"})})
            stderr = ""
        return P()

    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    monkeypatch.setattr(providers.shutil, "which", lambda _: "claude")
    p = providers.ClaudeCliProvider()
    out = p.complete(
        "SYS",
        [
            {"type": "text", "text": "任务说明"},
            {"type": "image", "path": Path("a.jpg"), "label": "成片"},
        ],
        {"type": "object"},
    )
    assert out == {"summary": "ok"}
    assert "SYS" in captured["prompt"]
    assert "任务说明" in captured["prompt"]
    assert "Read 工具" in captured["prompt"] and "a.jpg" in captured["prompt"]
    assert "JSON Schema" in captured["prompt"]


def test_get_provider_auto(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert isinstance(providers.get_provider("auto"), providers.AnthropicProvider)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr(providers.shutil, "which", lambda _: "claude")
    assert isinstance(providers.get_provider("auto"), providers.ClaudeCliProvider)


def test_get_provider_none_available(monkeypatch, tmp_path):
    from looklift import config
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(providers.shutil, "which", lambda _: None)
    import pytest
    with pytest.raises(RuntimeError):
        providers.get_provider("auto")
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_providers.py -q` → FAIL(模块不存在)

- [ ] **Step 3: 实现 providers.py**

把 `analyzer.py` 的 `_run_cli`、`_extract_json`(复制引用)、`_encode_image`、`_image_block`、`_run_api`、`MODEL`、`MAX_EDGE` 迁入:

```python
# looklift/providers.py
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
MAX_EDGE = 1568


class VisionProvider(Protocol):
    def complete(self, system: str, blocks: list[dict], schema: dict) -> dict: ...


def _extract_json(text: str) -> dict[str, Any]:
    # ……(原 analyzer._extract_json 逐字迁入)
    ...


class ClaudeCliProvider:
    """走本地 Claude Code CLI(claude -p),prompt 从 stdin 传(Windows 8K 参数上限)。"""

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
        proc = subprocess.run(
            [claude, "-p", "--output-format", "json", "--allowedTools", "Read"],
            input="\n".join(parts), capture_output=True, text=True,
            encoding="utf-8", timeout=600,
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

    def complete(self, system: str, blocks: list[dict], schema: dict) -> dict:
        import anthropic

        content: list[dict[str, Any]] = []
        for b in blocks:
            if b["type"] == "text":
                content.append({"type": "text", "text": b["text"]})
            else:
                content.append({"type": "text", "text": f"这是{b['label']}:"})
                content.append(_image_block(b["path"]))
        client = anthropic.Anthropic()
        model = config.load_config()["model"] or MODEL
        with client.messages.stream(
            model=model, max_tokens=16000, system=system,
            output_config={"format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            raise RuntimeError("模型拒绝了本次请求,请换一张照片重试。")
        return json.loads(next(b.text for b in response.content if b.type == "text"))


def _encode_image(path):  # 原 analyzer._encode_image 逐字迁入
    ...

def _image_block(path):   # 原 analyzer._image_block 逐字迁入
    ...


def get_provider(backend: str = "auto") -> VisionProvider:
    if backend == "auto":
        configured = config.load_config()["provider"]
        if configured in ("cli", "api"):
            backend = configured
    if backend == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            backend = "api"
        elif shutil.which("claude"):
            backend = "cli"
        else:
            raise RuntimeError(
                "未找到可用后端:请设置 ANTHROPIC_API_KEY,或安装 Claude Code CLI(claude 命令)。"
            )
    return AnthropicProvider() if backend == "api" else ClaudeCliProvider()
```

- [ ] **Step 4: 重构 analyzer.py 调 provider**

`analyzer.py` 保留:`ANALYSIS_SCHEMA`、`SYSTEM_PROMPT`、`_MULTI_TASK`、`_REFINE_TASK`、`_normalize`、`MAX_IMAGES`、`analyze()`、`refine()`。删除传输层函数,`analyze`/`refine` 改为组装 blocks:

```python
from . import providers
from .providers import MODEL, MAX_EDGE  # 兼容旧引用

def resolve_backend(backend: str = "auto") -> str:
    """兼容入口:返回 auto 解析后的后端名(测试与 cli 打印用)。"""
    p = providers.get_provider(backend)
    return "api" if isinstance(p, providers.AnthropicProvider) else "cli"

def analyze(edited, original=None, style_hint=None, backend="auto"):
    images = [edited] if isinstance(edited, (str, Path)) else list(edited)
    if len(images) > MAX_IMAGES:
        raise ValueError(f"一次最多分析 {MAX_IMAGES} 张成片(收到 {len(images)} 张)。")
    if len(images) > 1 and original is not None:
        raise ValueError("多张成片模式下不支持 --original 原片对照。")
    blocks: list[dict] = []
    if original is not None:
        blocks += [{"type": "image", "path": Path(original), "label": "修图前的原片"},
                   {"type": "image", "path": Path(images[0]), "label": "后期完成的成片"},
                   {"type": "text", "text": "请精确对比原片和成片,推断出从原片调到成片所用的 Lightroom 参数。"}]
    elif len(images) == 1:
        blocks += [{"type": "image", "path": Path(images[0]), "label": "后期完成的照片"},
                   {"type": "text", "text": "请分析这张后期完成的照片,推断出复现这种色调风格所需的 Lightroom 参数。"}]
    else:
        blocks += [{"type": "image", "path": Path(p), "label": f"成片 {i}"} for i, p in enumerate(images, 1)]
        blocks.append({"type": "text", "text": _MULTI_TASK})
    if style_hint:
        blocks.append({"type": "text", "text": f"补充信息:{style_hint}"})
    result = providers.get_provider(backend).complete(SYSTEM_PROMPT, blocks, ANALYSIS_SCHEMA)
    return _normalize(result)

def refine(current_params, attempt, target, backend="auto"):
    blocks = [
        {"type": "text", "text": _REFINE_TASK},
        {"type": "text", "text": f"当前参数模版:\n{json.dumps(current_params, ensure_ascii=False)}"},
        {"type": "image", "path": Path(attempt), "label": "套用当前参数后导出的效果图"},
        {"type": "image", "path": Path(target), "label": "想要达到的目标成片"},
    ]
    result = providers.get_provider(backend).complete(SYSTEM_PROMPT, blocks, ANALYSIS_SCHEMA)
    return _normalize(result)
```

`tests/test_analyzer.py` 中 `resolve_backend`/`_extract_json` 的既有测试:`_extract_json` 在 analyzer 保留一个 `from .providers import _extract_json` 转发;若测试 monkeypatch 的对象路径失效,**修测试指向新家,不改断言语义**。

- [ ] **Step 5: 跑相关测试** — `pytest tests/test_providers.py tests/test_analyzer.py -q` 全绿

- [ ] **Step 6: Commit**

```bash
git add looklift/providers.py looklift/analyzer.py tests/
git commit -m "refactor: extract VisionProvider layer; analyzer keeps prompts, providers own transport"
```

---

### Task 4: 渲染管线 render.py(preview 核心)

**Files:**
- Create: `looklift/render.py`
- Modify: `pyproject.toml`(dependencies 加 `"numpy>=1.26"`)
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: analysis dict(ANALYSIS_SCHEMA 结构)
- Produces:
  - `render(image: Image.Image, analysis: dict) -> Image.Image`(全管线:色彩 ops + 空间 ops)
  - `_apply_color_ops(arr: np.ndarray, analysis: dict) -> np.ndarray`(float32 0-1、shape (...,3);**只含全局色彩映射**,Task 6 LUT 复用:曝光→白平衡→对比→高光/阴影→白/黑场→曲线→HSL→饱和度→颜色分级)
  - `_apply_spatial_ops(arr, analysis) -> np.ndarray`(暗角;颗粒 v0.3 不渲染)

- [ ] **Step 1: 写失败测试(方向正确性)**

```python
# tests/test_render.py
import numpy as np
from PIL import Image
from looklift import render


def _flat_gray(v=0.5, size=(32, 32)):
    return np.full((*size, 3), v, dtype=np.float32)


def _zero_analysis(sample_analysis):
    """把 fixture 里的所有调整清零,便于单项测试。"""
    import copy, json
    a = copy.deepcopy(sample_analysis)
    a["basic"] = {k: 0 for k in a["basic"]}
    a["tone_curve"] = []
    a["hsl"] = []
    for zone in ("shadows", "midtones", "highlights", "global_"):
        a["color_grading"][zone] = {"hue": 0, "saturation": 0, "luminance": 0}
    a["effects"] = {"vignette_amount": 0, "grain_amount": 0}
    return a


def test_identity_analysis_is_noop(sample_analysis):
    a = _zero_analysis(sample_analysis)
    arr = _flat_gray()
    out = render._apply_color_ops(arr.copy(), a)
    assert np.allclose(out, arr, atol=1e-3)


def test_exposure_positive_brightens(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["exposure"] = 1.0
    out = render._apply_color_ops(_flat_gray(0.25), a)
    assert out.mean() > 0.4  # 2^1 增益


def test_temperature_warm_lifts_red_over_blue(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["temperature_shift"] = 50
    out = render._apply_color_ops(_flat_gray(), a)
    assert out[..., 0].mean() > out[..., 2].mean()


def test_contrast_spreads_histogram(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["contrast"] = 50
    arr = np.stack([_flat_gray(0.3), _flat_gray(0.7)]).reshape(-1, 2, 3)
    out = render._apply_color_ops(arr, a)
    assert out[..., 0].max() - out[..., 0].min() > 0.4  # 原本 0.4 差距被拉大


def test_shadows_positive_lifts_dark_pixels_only(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["shadows"] = 80
    dark = render._apply_color_ops(_flat_gray(0.15), a).mean()
    bright = render._apply_color_ops(_flat_gray(0.85), a).mean()
    assert dark > 0.15 + 0.03           # 暗部被抬
    assert abs(bright - 0.85) < 0.03    # 亮部基本不动


def test_tone_curve_lifted_black(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["tone_curve"] = [{"input": 0, "output": 40}, {"input": 255, "output": 255}]
    out = render._apply_color_ops(_flat_gray(0.0), a)
    assert out.mean() > 0.1  # 40/255 ≈ 0.157


def test_saturation_negative_desaturates(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["basic"]["saturation"] = -100
    arr = np.zeros((4, 4, 3), dtype=np.float32); arr[..., 0] = 0.8  # 纯红
    out = render._apply_color_ops(arr, a)
    assert out.std(axis=-1).mean() < 0.05  # 通道间差异消失=去饱和


def test_vignette_darkens_corners_not_center(sample_analysis):
    a = _zero_analysis(sample_analysis)
    a["effects"]["vignette_amount"] = -80
    out = render._apply_spatial_ops(_flat_gray(0.5, (64, 64)), a)
    assert out[0, 0].mean() < out[32, 32].mean() - 0.05


def test_render_returns_image(sample_analysis):
    img = Image.new("RGB", (48, 32), (128, 128, 128))
    out = render.render(img, sample_analysis)
    assert isinstance(out, Image.Image) and out.size == (48, 32)
```

- [ ] **Step 2: 跑测试确认失败** — `pytest tests/test_render.py -q` → FAIL(模块不存在)

- [ ] **Step 3: 实现 render.py**

```python
# looklift/render.py
"""本地近似渲染:把 analysis 参数应用到图片上。

定位是「方向正确的近似」,不承诺与 Lightroom 渲染一致(见 v0.3 spec)。
输入假设 sRGB;内部用 float32 0-1 numpy 数组。
_apply_color_ops 只含全局色彩映射(LUT 导出复用);暗角等空间效果在 _apply_spatial_ops。
"""
from __future__ import annotations

import numpy as np
from PIL import Image

_HSL_CENTERS = {  # 8 通道中心色相(度)
    "red": 0, "orange": 30, "yellow": 60, "green": 120,
    "aqua": 180, "blue": 240, "purple": 280, "magenta": 320,
}


def _luminance(arr: np.ndarray) -> np.ndarray:
    return arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722


def _rgb_to_hsv(arr):
    ...  # 向量化 RGB→HSV(np.max/np.min 实现,h 单位度 0-360)

def _hsv_to_rgb(arr):
    ...  # 逆变换


def _apply_color_ops(arr: np.ndarray, analysis: dict) -> np.ndarray:
    b = analysis.get("basic", {})
    arr = arr.astype(np.float32)

    # 1) 曝光:2^ev 增益
    ev = b.get("exposure", 0)
    if ev:
        arr = arr * (2.0 ** ev)

    # 2) 白平衡:温/色调通道增益(±100 → ±20% 通道差)
    t, tint = b.get("temperature_shift", 0), b.get("tint_shift", 0)
    if t:
        arr[..., 0] *= 1 + 0.2 * t / 100
        arr[..., 2] *= 1 - 0.2 * t / 100
    if tint:
        arr[..., 1] *= 1 - 0.15 * tint / 100  # 品红=压绿

    # 3) 对比度:围绕 0.5 的线性扩张(±100 → ±60%)
    c = b.get("contrast", 0)
    if c:
        arr = 0.5 + (arr - 0.5) * (1 + 0.6 * c / 100)

    # 4) 高光/阴影:亮度蒙版加权提亮/压暗
    arr = np.clip(arr, 0, 1)
    luma = _luminance(arr)[..., None]
    hi, sh = b.get("highlights", 0), b.get("shadows", 0)
    if hi:
        arr = arr + (hi / 100) * 0.25 * (luma ** 2) * np.sign(1)  # 亮区权重 luma²
    if sh:
        arr = arr + (sh / 100) * 0.25 * ((1 - luma) ** 2)

    # 5) 白/黑场:端点缩放
    wh, bl = b.get("whites", 0), b.get("blacks", 0)
    if wh:
        arr = arr * (1 + 0.15 * wh / 100)
    if bl:
        arr = arr + 0.15 * bl / 100 * (1 - np.clip(arr, 0, 1))**4  # 只影响近黑

    arr = np.clip(arr, 0, 1)

    # 6) 色调曲线:0-255 控制点 → np.interp LUT
    curve = sorted(
        ((p["input"], p["output"]) for p in analysis.get("tone_curve", [])),
    )
    if len(curve) >= 2:
        xs = np.array([p[0] for p in curve]) / 255.0
        ys = np.array([p[1] for p in curve]) / 255.0
        arr = np.interp(arr, xs, ys).astype(np.float32)

    # 7) HSL 定向 + 8) 饱和度/自然饱和度 + 9) 颜色分级:HSV 域一次完成
    hsv = _rgb_to_hsv(arr)
    for entry in analysis.get("hsl", []):
        center = _HSL_CENTERS.get(entry.get("color", ""), None)
        if center is None:
            continue
        dist = np.abs((hsv[..., 0] - center + 180) % 360 - 180)
        mask = np.clip(1 - dist / 45, 0, 1)  # 中心±45° 三角权重
        hsv[..., 0] = (hsv[..., 0] + mask * entry.get("hue", 0) * 0.3) % 360
        hsv[..., 1] *= 1 + mask * entry.get("saturation", 0) / 100 * 0.5
        hsv[..., 2] *= 1 + mask * entry.get("luminance", 0) / 100 * 0.3

    sat, vib = b.get("saturation", 0), b.get("vibrance", 0)
    if sat:
        hsv[..., 1] *= 1 + sat / 100
    if vib:  # 自然饱和度:低饱和像素受益更多
        hsv[..., 1] += (vib / 100) * 0.5 * hsv[..., 1] * (1 - hsv[..., 1])
    hsv[..., 1] = np.clip(hsv[..., 1], 0, 1)
    arr = _hsv_to_rgb(hsv)

    # 9) 颜色分级:亮度加权叠色(shadows/midtones/highlights/global_)
    arr = _apply_color_grading(arr, analysis.get("color_grading", {}))
    return np.clip(arr, 0, 1)


def _apply_color_grading(arr, cg):
    luma = _luminance(arr)[..., None]
    weights = {
        "shadows": (1 - luma) ** 2, "midtones": 4 * luma * (1 - luma),
        "highlights": luma ** 2, "global_": np.ones_like(luma),
    }
    for zone, w in weights.items():
        z = cg.get(zone, {})
        s = z.get("saturation", 0)
        if not s:
            continue
        hue = np.deg2rad(z.get("hue", 0))
        tint = np.array([np.cos(hue), np.cos(hue - 2.0944), np.cos(hue - 4.1888)]) * 0.5 + 0.5
        arr = arr + w * (s / 100) * 0.3 * (tint - arr)
        lum = z.get("luminance", 0)
        if lum:
            arr = arr + w * lum / 100 * 0.2
    return arr


def _apply_spatial_ops(arr: np.ndarray, analysis: dict) -> np.ndarray:
    v = analysis.get("effects", {}).get("vignette_amount", 0)
    if v:
        h, w = arr.shape[:2]
        y, x = np.mgrid[0:h, 0:w]
        r = np.sqrt(((x / w - 0.5) * 2) ** 2 + ((y / h - 0.5) * 2) ** 2) / np.sqrt(2)
        arr = arr * (1 + (v / 100) * 0.6 * (r ** 2))[..., None]
    return np.clip(arr, 0, 1)


def render(image: Image.Image, analysis: dict) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")
    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = _apply_color_ops(arr, analysis)
    arr = _apply_spatial_ops(arr, analysis)
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGB")
```

`_rgb_to_hsv`/`_hsv_to_rgb` 写完整向量化实现(实现时若断言精度不达标,微调系数,**方向断言不许改**)。`pyproject.toml` dependencies 加 `"numpy>=1.26"`。

- [ ] **Step 4: 跑测试** — `pytest tests/test_render.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add looklift/render.py tests/test_render.py pyproject.toml
git commit -m "feat: local approximate render pipeline (color ops + vignette), numpy dep"
```

---

### Task 5: 还原度评分 score()

**Files:**
- Modify: `looklift/render.py`(追加)
- Test: `tests/test_render.py`(追加)

**Interfaces:**
- Produces: `score(rendered: Image.Image, target: Image.Image) -> float`(0-100;缩到 256 缩略图;亮度直方图相关性 60% + ab 通道均值/方差接近度 40%;只用于趋势判断)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_render.py 追加
def _noise_img(seed, size=(64, 64)):
    rng = np.random.default_rng(seed)
    return Image.fromarray((rng.random((*size, 3)) * 255).astype(np.uint8), "RGB")


def test_score_identical_is_high():
    img = _noise_img(1)
    assert render.score(img, img) > 95


def test_score_monotonic_under_known_perturbation(sample_analysis):
    """扰动越大分越低——评分单调性,auto-refine 的可用性前提。"""
    base = _noise_img(2)
    import copy
    def perturbed(ev):
        a = copy.deepcopy(sample_analysis)
        a["basic"] = {k: 0 for k in a["basic"]}
        a["tone_curve"] = []; a["hsl"] = []
        for z in ("shadows", "midtones", "highlights", "global_"):
            a["color_grading"][z] = {"hue": 0, "saturation": 0, "luminance": 0}
        a["effects"] = {"vignette_amount": 0, "grain_amount": 0}
        a["basic"]["exposure"] = ev
        return render.render(base, a)
    s_small = render.score(perturbed(0.3), base)
    s_big = render.score(perturbed(1.5), base)
    assert s_small > s_big
    assert render.score(base, base) > s_small
```

- [ ] **Step 2: 跑测试确认失败** — FAIL(`score` 不存在)

- [ ] **Step 3: 实现**

```python
# render.py 追加
def _ab_stats(arr):
    """近似 Lab 的 a/b 通道均值与标准差(色彩倾向指纹)。"""
    a = arr[..., 0] - arr[..., 1]          # 红绿轴
    b_ = arr[..., 1] - arr[..., 2]         # 黄蓝轴
    return np.array([a.mean(), b_.mean(), a.std(), b_.std()])


def score(rendered: Image.Image, target: Image.Image) -> float:
    """还原度 0-100。只用于同一目标的迭代趋势判断,不做跨风格比较。"""
    def prep(im):
        im = im.convert("RGB"); im.thumbnail((256, 256))
        return np.asarray(im, dtype=np.float32) / 255.0
    r, t = prep(rendered), prep(target)

    hr, _ = np.histogram(_luminance(r), bins=64, range=(0, 1), density=True)
    ht, _ = np.histogram(_luminance(t), bins=64, range=(0, 1), density=True)
    denom = np.linalg.norm(hr) * np.linalg.norm(ht)
    hist_sim = float(hr @ ht / denom) if denom else 0.0   # 余弦相似度 0-1

    d = np.abs(_ab_stats(r) - _ab_stats(t))
    color_sim = float(np.clip(1 - d.mean() / 0.15, 0, 1))

    return round(100 * (0.6 * hist_sim + 0.4 * color_sim), 1)
```

- [ ] **Step 4: 跑相关测试** — `pytest tests/test_render.py -q` → PASS

- [ ] **Step 5: Commit**

```bash
git add looklift/render.py tests/test_render.py
git commit -m "feat: similarity score (luma histogram + ab-channel stats), monotonic under perturbation"
```

---

### Task 6: LUT 导出 lut.py + preview/export-lut 子命令

**Files:**
- Create: `looklift/lut.py`
- Modify: `looklift/cli.py`(新增 `cmd_preview`、`cmd_export_lut` 与两个子命令注册)
- Test: `tests/test_lut.py`、`tests/test_cli.py`(追加)

**Interfaces:**
- Consumes: `render._apply_color_ops`(**不含**暗角/颗粒——LUT 只承载全局色彩映射)
- Produces: `lut.export_cube(analysis: dict, out: Path, size: int = 33) -> Path`;CLI `looklift preview <模版> <照片> [-o]`、`looklift export-lut <模版> [-o x.cube] [--size 33]`

- [ ] **Step 1: 写失败测试(程序化 .cube 校验——即 T4 验收第 1 条)**

```python
# tests/test_lut.py
import numpy as np
from looklift import lut


def _parse_cube(path):
    size, data = None, []
    for line in path.read_text(encoding="ascii").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("TITLE"):
            continue
        if line.startswith("LUT_3D_SIZE"):
            size = int(line.split()[1]); continue
        if line.startswith("DOMAIN_"):
            continue
        data.append([float(x) for x in line.split()])
    return size, np.array(data)


def test_cube_format_valid(sample_analysis, tmp_path):
    out = lut.export_cube(sample_analysis, tmp_path / "t.cube", size=17)
    size, data = _parse_cube(out)
    assert size == 17
    assert data.shape == (17 ** 3, 3)          # size³ 行、每行 RGB
    assert data.min() >= 0.0 and data.max() <= 1.0


def test_identity_analysis_gives_identity_lut(sample_analysis, tmp_path):
    import copy
    a = copy.deepcopy(sample_analysis)
    a["basic"] = {k: 0 for k in a["basic"]}
    a["tone_curve"] = []; a["hsl"] = []
    for z in ("shadows", "midtones", "highlights", "global_"):
        a["color_grading"][z] = {"hue": 0, "saturation": 0, "luminance": 0}
    a["effects"] = {"vignette_amount": 0, "grain_amount": 0}
    _, data = _parse_cube(lut.export_cube(a, tmp_path / "i.cube", size=9))
    # 第一行应是 (0,0,0),最后一行 (1,1,1);R 变化最快(Resolve 约定)
    assert np.allclose(data[0], [0, 0, 0], atol=0.01)
    assert np.allclose(data[-1], [1, 1, 1], atol=0.01)
    assert data[1][0] > data[0][0] and abs(data[1][1] - data[0][1]) < 0.01
```

- [ ] **Step 2: 跑测试确认失败** — FAIL(模块不存在)

- [ ] **Step 3: 实现 lut.py**

```python
# looklift/lut.py
"""把 analysis 的全局色彩映射采样成 3D LUT(.cube,Resolve 规范)。

暗角/颗粒是空间效果,LUT 无法承载,导出时跳过(CLI 层提示)。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .render import _apply_color_ops


def export_cube(analysis: dict, out: str | Path, size: int = 33) -> Path:
    ax = np.linspace(0.0, 1.0, size, dtype=np.float32)
    # .cube 行序:R 变化最快,然后 G,最后 B
    b, g, r = np.meshgrid(ax, ax, ax, indexing="ij")
    grid = np.stack([r, g, b], axis=-1).reshape(-1, 1, 3)  # (N,1,3) 伪图像
    mapped = _apply_color_ops(grid, analysis).reshape(-1, 3)

    lines = [
        f'TITLE "looklift"',
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    lines += [f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}" for p in mapped]
    out = Path(out)
    out.write_text("\n".join(lines) + "\n", encoding="ascii")
    return out
```

- [ ] **Step 4: 跑 lut 测试** — PASS

- [ ] **Step 5: 写 CLI 测试(失败)**

```python
# tests/test_cli.py 追加
def test_cmd_preview_writes_image(tmp_path, sample_analysis, monkeypatch):
    import json
    from PIL import Image
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    photo = tmp_path / "in.jpg"
    Image.new("RGB", (32, 32), (100, 100, 100)).save(photo)
    rc = cli.main(["preview", str(t), str(photo), "-o", str(tmp_path / "out.jpg")])
    assert rc == 0 and (tmp_path / "out.jpg").exists()


def test_cmd_export_lut(tmp_path, sample_analysis, monkeypatch):
    import json
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    rc = cli.main(["export-lut", str(t), "-o", str(tmp_path / "o.cube"), "--size", "9"])
    assert rc == 0 and (tmp_path / "o.cube").read_text(encoding="ascii").startswith("TITLE")
```

- [ ] **Step 6: 实现 CLI 命令**

```python
# cli.py 新增(import 处加 from . import lut, render)
def cmd_preview(args) -> int:
    from PIL import Image
    template = _resolve_template(args.template)
    analysis = json.loads(template.read_text(encoding="utf-8"))
    img = Image.open(args.photo)
    out = Path(args.out) if args.out else Path(args.photo).with_stem(Path(args.photo).stem + "_preview")
    render.render(img, analysis).save(out, quality=92)
    print(f"[preview] 已生成: {out}  (本地近似渲染,方向参考,不等于 LR 效果)")
    if args.target:
        from PIL import Image as I
        s = render.score(I.open(out), I.open(args.target))
        print(f"[评分] 与目标图相似度: {s}/100")
    return 0


def cmd_export_lut(args) -> int:
    template = _resolve_template(args.template)
    analysis = json.loads(template.read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else template.with_suffix(".cube")
    lut.export_cube(analysis, out, size=args.size)
    print(f"[LUT] 已生成: {out}  (达芬奇/剪映导入;曝光等全局色彩已包含,暗角/颗粒不进 LUT)")
    return 0
```

子命令注册(`main()` 里,report 之后):

```python
    p = sub.add_parser("preview", help="本地近似渲染:预览模版套用效果(不开 LR)")
    p.add_argument("template", help="模版文件路径,或风格库中的名字")
    p.add_argument("photo", help="要套用的照片(sRGB JPEG/PNG)")
    p.add_argument("-o", "--out", help="输出路径,默认 <照片>_preview.jpg")
    p.add_argument("--target", help="可选:目标成片,输出相似度评分")
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser("export-lut", help="导出 .cube 3D LUT(达芬奇/剪映给视频调色)")
    p.add_argument("template", help="模版文件路径,或风格库中的名字")
    p.add_argument("-o", "--out", help="输出路径,默认与模版同名 .cube")
    p.add_argument("--size", type=int, default=33, help="LUT 网格大小,默认 33")
    p.set_defaults(func=cmd_export_lut)
```

- [ ] **Step 7: 跑相关测试** — `pytest tests/test_lut.py tests/test_cli.py -q` 全绿

- [ ] **Step 8: Commit**

```bash
git add looklift/lut.py looklift/cli.py tests/test_lut.py tests/test_cli.py
git commit -m "feat: .cube LUT export + preview/export-lut CLI commands"
```

---

### Task 7: refine 自动闭环 autorefine.py

**Files:**
- Create: `looklift/autorefine.py`
- Modify: `looklift/cli.py`(refine 子命令加 `--auto [N]`、`--source`;`--attempt` 变为条件必需)
- Test: `tests/test_autorefine.py`

**Interfaces:**
- Consumes: `render.render`、`render.score`、`analyzer.refine(current, attempt, target, backend)`
- Produces: `auto_refine(analysis: dict, source: Path, target: Path, rounds: int = 3, min_gain: float = 1.0, backend: str = "auto", on_round=None) -> tuple[dict, list[float]]` — 返回 (最佳参数, 每轮评分历史);`on_round(i, score)` 回调供 CLI 打印

- [ ] **Step 1: 写失败测试(monkeypatch 掉 AI,不触网)**

```python
# tests/test_autorefine.py
import copy
from PIL import Image
from looklift import autorefine


def test_auto_refine_keeps_best_and_stops_on_convergence(tmp_path, sample_analysis, monkeypatch):
    src = tmp_path / "src.jpg"; tgt = tmp_path / "tgt.jpg"
    Image.new("RGB", (32, 32), (90, 90, 90)).save(src)
    Image.new("RGB", (32, 32), (140, 140, 140)).save(tgt)

    scores = iter([50.0, 70.0, 70.5, 70.6])  # 第 3 轮起提升 < min_gain
    monkeypatch.setattr(autorefine.render, "score", lambda r, t: next(scores))

    calls = {"n": 0}
    def fake_refine(current, attempt, target, backend="auto"):
        calls["n"] += 1
        out = copy.deepcopy(current)
        out["basic"]["exposure"] = calls["n"] * 0.1
        return out
    monkeypatch.setattr(autorefine.analyzer, "refine", fake_refine)

    best, history = autorefine.auto_refine(
        sample_analysis, src, tgt, rounds=5, min_gain=1.0)
    assert history == [50.0, 70.0, 70.5]      # 第 3 轮提升 0.5 < 1.0,停
    assert best["basic"]["exposure"] == 0.2   # 评分 70.5 那轮之前的最优=第 2 轮修正版?
    # ↑ 语义:history[i] 是「第 i 版参数」的评分;最佳=评分最高那版参数
    assert calls["n"] == 2                    # 收敛后不再调 AI


def test_auto_refine_respects_rounds_limit(tmp_path, sample_analysis, monkeypatch):
    src = tmp_path / "s.jpg"; tgt = tmp_path / "t.jpg"
    Image.new("RGB", (16, 16)).save(src); Image.new("RGB", (16, 16)).save(tgt)
    it = iter([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    monkeypatch.setattr(autorefine.render, "score", lambda r, t: next(it))
    monkeypatch.setattr(autorefine.analyzer, "refine",
                        lambda c, a, t, backend="auto": copy.deepcopy(c))
    best, history = autorefine.auto_refine(sample_analysis, src, tgt, rounds=3, min_gain=1.0)
    assert len(history) == 4  # 初始评分 + 3 轮
```

- [ ] **Step 2: 跑测试确认失败** — FAIL(模块不存在)

- [ ] **Step 3: 实现**

```python
# looklift/autorefine.py
"""refine 自动闭环:渲染 → 评分 → AI 修正 → 再渲染,直到收敛或到轮数上限。"""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path

from PIL import Image

from . import analyzer, render


def auto_refine(
    analysis: dict,
    source: str | Path,
    target: str | Path,
    rounds: int = 3,
    min_gain: float = 1.0,
    backend: str = "auto",
    on_round=None,
) -> tuple[dict, list[float]]:
    """返回 (最佳参数, 评分历史)。history[0] 是初始参数的评分,之后每轮一项。"""
    src = Image.open(source)
    tgt = Image.open(target)
    current = copy.deepcopy(analysis)

    def evaluate(params) -> tuple[float, Path]:
        rendered = render.render(src, params)
        tmp = Path(tempfile.mkstemp(suffix=".jpg")[1])
        rendered.save(tmp, quality=92)
        return render.score(rendered, tgt), tmp

    s, attempt = evaluate(current)
    history = [s]
    best, best_score = current, s
    if on_round:
        on_round(0, s)

    for i in range(1, rounds + 1):
        current = analyzer.refine(current, attempt, target, backend=backend)
        s, attempt = evaluate(current)
        history.append(s)
        if on_round:
            on_round(i, s)
        if s > best_score:
            best, best_score = current, s
        if s - history[-2] < min_gain:
            break
    return best, history
```

- [ ] **Step 4: 校对测试语义并跑通**

第一个测试断言 `best["basic"]["exposure"] == 0.2`:history=[50, 70, 70.5],评分最高的是第 2 轮(70.5)对应 `exposure=0.2`。确认实现与断言一致后 `pytest tests/test_autorefine.py -q` → PASS

- [ ] **Step 5: CLI 接入 --auto**

`cmd_refine` 开头改为:

```python
def cmd_refine(args) -> int:
    template = _resolve_template(args.template)
    current = json.loads(template.read_text(encoding="utf-8"))
    if args.auto is not None:
        if not args.source:
            print("错误: --auto 需要同时提供 --source 原片。", file=sys.stderr)
            return 1
        from . import autorefine
        print(f"自动校准 {template.stem}(最多 {args.auto} 轮,后端: {analyzer.resolve_backend(args.backend)})")
        updated, history = autorefine.auto_refine(
            current, args.source, args.target, rounds=args.auto, backend=args.backend,
            on_round=lambda i, s: print(f"  第 {i} 轮评分: {s}/100"))
        print(f"评分曲线: {' → '.join(f'{s:g}' for s in history)}")
    else:
        if not args.attempt:
            print("错误: 手动模式需要 --attempt 效果图(或改用 --auto N --source 原片)。", file=sys.stderr)
            return 1
        print(f"正在校准 {template.stem} ...(后端: {analyzer.resolve_backend(args.backend)})")
        updated = analyzer.refine(current, args.attempt, args.target, backend=args.backend)
    _print_analysis(updated)
    # ……以下备份/写模版/重生成预设逻辑不变
```

参数定义:`--attempt` 去掉 `required=True`;新增

```python
    p.add_argument("--auto", type=int, nargs="?", const=3, default=None, metavar="N",
                   help="自动闭环:渲染→评分→AI 修正,最多 N 轮(默认 3),需配 --source")
    p.add_argument("--source", help="原片(--auto 模式渲染起点)")
```

CLI 测试追加:

```python
def test_refine_auto_requires_source(tmp_path, sample_analysis, monkeypatch):
    import json
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    rc = cli.main(["refine", str(t), "--target", "x.jpg", "--auto"])
    assert rc == 1
```

- [ ] **Step 6: 跑相关测试** — `pytest tests/test_autorefine.py tests/test_cli.py -q` 全绿

- [ ] **Step 7: Commit**

```bash
git add looklift/autorefine.py looklift/cli.py tests/
git commit -m "feat: refine --auto closed loop (render, score, AI-correct, keep best)"
```

---

### Task 8: 真实照片端到端验证(人工,T3 验收)

**Files:**
- Create: `test-assets/`(gitignored,作者放入 3-5 组原片+成片)

- [ ] **Step 1:** 请作者把 LR 修过的照片按组导出到 `test-assets/`:`组名_原片.jpg` + `组名_成片.jpg`
- [ ] **Step 2:** 对每组跑:

```bash
looklift analyze test-assets/组名_成片.jpg --original test-assets/组名_原片.jpg --name e2e-组名
looklift refine e2e-组名 --target test-assets/组名_成片.jpg --source test-assets/组名_原片.jpg --auto 3
```

Expected: 每组评分曲线 3 轮内净上升;preview 出图肉眼方向正确
- [ ] **Step 3:** `looklift export-lut e2e-组名`,剪映导入 .cube,肉眼确认色调方向正确(T4 验收第 2 条)
- [ ] **Step 4:** 结果(评分曲线数字)记入 `docs/tasks.md` 历史区;发现的渲染系数问题开进下轮迭代,不阻塞发布

---

### Task 9: 收尾(T5)

**Files:**
- Modify: `.github/workflows/ci.yml`、`pyproject.toml`(version)、`README.md`、`docs/design.md`、`docs/tasks.md`

- [ ] **Step 1:** ci.yml 矩阵改 `os: [ubuntu-latest, windows-latest, macos-latest]`
- [ ] **Step 2:** `pyproject.toml` version → `0.3.0`
- [ ] **Step 3:** README 新增 preview/export-lut/refine --auto 用法示例(与 cli.py docstring 同步)
- [ ] **Step 4:** v0.3 spec 要点回填 `docs/design.md`(新章节:provider 层、render 管线、评分、autorefine、lut——按「已实现」时态写);`docs/tasks.md` v0.3 任务打勾并移入历史
- [ ] **Step 5:** `pytest -q` 全绿 → Commit:

```bash
git add -A
git commit -m "chore: v0.3.0 — docs sync, CI adds macOS, version bump"
git push
```

- [ ] **Step 6:** 推送后确认 GitHub Actions 三平台全绿

---

## Self-Review 记录

- **Spec 覆盖**:T1 provider+config(Task 1,3)、looks 迁移(Task 2)、T2 preview+评分(Task 4,5,6 preview 命令)、T3 auto(Task 7,8)、T4 LUT(Task 6,8)、T5(Task 9)、sRGB 边界(render docstring+preview help)——全覆盖。
- **占位符**:`_rgb_to_hsv`/`_hsv_to_rgb`/`_encode_image` 等标注「逐字迁入/完整实现」的,来源代码在现有 analyzer.py 中,执行者可直接搬——不算 TBD。
- **类型一致性**:`_apply_color_ops(arr, analysis)` 在 Task 4 定义、Task 6 lut.py 引用一致;`auto_refine` 返回 `(dict, list[float])` 与 CLI 解包一致;`config.looks_dir()` 与 cli `_looks_dir()` 一致。
