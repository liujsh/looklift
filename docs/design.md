# looklift 设计文档

> 产品定位、用户故事、路线图见 [requirements.md](requirements.md)。本文档记录**已实现**的技术架构与关键设计决策。
> 未实现迭代的详细设计写在 `docs/specs/`(每迭代一份 spec,实现后要点回填本文档)。当前:[v0.3 spec](specs/2026-07-16-v0.3-precision-loop.md)。

## 架构总览

```
                ┌─────────────┐
 用户 ──CLI──▶  │   cli.py    │  argparse 子命令: analyze / read / apply / list / refine / report
                └──────┬──────┘
        ┌──────────────┼───────────────┬──────────────┐
        ▼              ▼               ▼              ▼
  xmp_reader.py   analyzer.py     xmp_writer.py   report.py (v0.2)
  读 JPEG 内嵌     AI 视觉逆向      分析结果→crs      模版→HTML 报告
  XMP(crs 参数)   推断参数         →预设/sidecar
                       │
              ┌────────┴────────┐
              ▼                 ▼
        本地 claude CLI     Anthropic API
        (headless -p,      (结构化输出,
         走 CC 登录额度)     需 API key)
```

## 关键设计决策

### 1. 双后端(analyzer.py)

- `resolve_backend("auto")`:有 `ANTHROPIC_API_KEY` → api;否则找到 `claude` 命令 → cli
- **cli 后端**:`claude -p --output-format json --allowedTools Read`,prompt 从 **stdin**
  传入(Windows 上 claude 是 .CMD 包装,命令行参数约 8K 上限,带 schema 的 prompt 必超)。
  图片让 Claude 自己用 Read 工具看,省去 base64。
  输出无 schema 硬约束 → `_extract_json` 容错提取 + `_normalize` 补全缺失字段。
- **api 后端**:`output_config.format=json_schema` 结构化输出,图片用 Pillow 缩到
  长边 1568 再 base64(控制 token)。

### 2. 数据模型:analysis dict(ANALYSIS_SCHEMA)

所有流程围绕同一个 JSON 结构(模版文件即此结构的序列化):

```
summary: str            # 风格分析(中文)
steps: [str]            # 后期步骤讲解
basic: {13 项基本面板}   # temperature_shift/exposure/contrast/...
tone_curve: [{input, output}]      # 0-255 RGB 主曲线控制点
hsl: [{color, hue, saturation, luminance}]   # 8 通道
color_grading: {shadows/midtones/highlights/global_, blending, balance}
effects: {vignette_amount, grain_amount}
```

### 3. XMP 生成(xmp_writer.py)

- `analysis_to_crs()`:analysis dict → crs 参数字典(LR 字段名,正值带 `+` 前缀)
- 阴影/高光染色沿用 `SplitToning*` 字段(LR 保留的旧字段名),中间调/全局用 `ColorGrade*`
- 白平衡写 `IncrementalTemperature/Tint`(增量,对 JPEG/TIFF 精确;RAW 开尔文需微调)
- 同一份 crs 字典渲染成两种文件:预设(带 `crs:PresetType`/`crs:Name`/UUID)和
  sidecar(与 RAW 同名 .xmp)

### 4. 风格库(looks/)

- 约定目录 `looks/`(相对 cwd),每个风格 = `<名字>.json`(模版)+ `<名字>.xmp`(预设)
- `apply`/`refine`/`report` 的模版参数既接受路径也接受库内名字(`_resolve_template`)
- `refine` 更新模版前备份 `.json.bak`,并重新生成同名预设

---

## v0.2 新增设计

### 5. 多图合成风格(analyzer.analyze 扩展)

- `analyze(edited)` 的 `edited` 参数从单路径改为 `list[Path]`(CLI 层 `nargs="+"`,上限 5 张)
- 单张:行为不变。多张:prompt 改为"这些是同一风格的多张成片,请归纳它们**共同**的
  风格特征,忽略单张的题材差异;参数取能同时逼近各张的折中值"
- 多张时禁用 `--original`(对照关系不明确,CLI 层直接报错)
- 两个后端同构:cli 后端列出 N 个 Read 路径;api 后端塞 N 个 image block

### 6. HTML 报告(report.py,新模块)

- `render_report(analysis, name) -> str(html)`;`looklift report <名字>` 写
  `looks/<名字>.html`
- 自包含单文件:内联 CSS,零 JS 依赖、零外部请求
- 内容区块:标题 → 风格概述 → 后期步骤(有序列表)→ 基本面板表格(非零参数,
  带正负色标)→ 曲线图(纯 SVG:对角参考线 + Catmull-Rom→贝塞尔平滑曲线 + 控制点)
  → HSL 表(色名用对应颜色色块)→ 颜色分级(色轮值转 CSS hsl() 色块)→ 效果
- 曲线 SVG 坐标系:x=input(0-255→0-256px),y=256-output(SVG y 轴向下)

### 7. 打包(pyproject.toml)

- `[project]` name=looklift, requires-python >=3.10, deps: anthropic, Pillow
- `[project.scripts] looklift = "looklift.cli:main"`
- setuptools 后端;`pip install -e .` 开发安装

### 8. 未来迭代设计(已拆分至 specs/)

- v0.3(provider 抽象、preview 渲染、auto-refine、LUT 导出):
  详见 [specs/2026-07-16-v0.3-precision-loop.md](specs/2026-07-16-v0.3-precision-loop.md),实现后要点回填本文档
- v0.4 GUI 架构方向(已定形态,细节届时写 spec):
  - **形态(2026-07-16 敲定)**:同一套 HTML 界面,发布默认 **pywebview 独立窗口**
    (Windows 依赖 WebView2,Win11 自带),`--browser` 参数走本地 web + 浏览器,
    用于开发调试和兜底;**不引入 Electron/Node 栈**,保持 Python 单语言
  - **视觉基底(2026-07-16 敲定)**:vendored 的 Claude 风设计系统
    `assets/design-system/claude/`(取自 Open Design 仓库,Apache 2.0,纯 CSS 变量
    + 纯 HTML 组件配方,零框架依赖)。tokens.css 直接引入,组件优先照
    components.html 配方写;复杂控件(滑杆/对话框)如配方不够再引入
    Shoelace(Web Components,MIT,本地 vendored)
  - 原则:GUI 只是壳,所有逻辑留在核心模块,CLI 与 GUI 永远共享同一实现;
    零外部网络请求(字体/CSS/JS 全部本地)
  - 打包(v0.7):PyInstaller 单 exe

### 9. 测试与 CI

- `tests/`:pytest,不触网、不调 AI
  - `test_xmp_writer.py`:analysis→crs 映射(符号前缀、HSL 字段、曲线 Seq)、
    预设/sidecar XML 合法性(minidom 解析)、往返(写出→xmp_reader 读回一致)
  - `test_xmp_reader.py`:属性式+元素式 crs 提取、无 XMP 返回 None
  - `test_analyzer.py`:`_normalize` 补全稀疏输出、`_extract_json` 容错(裸 JSON/
    代码块/前后杂文)、`resolve_backend` 逻辑(monkeypatch 环境)
  - `test_cli.py`:`_resolve_template` 名字/路径解析、`_expand_raws` 通配符、
    `apply` 端到端(tmp_path 下生成文件)
- `.github/workflows/ci.yml`:push/PR 触发,matrix = {ubuntu, windows} × py3.12,
  `pip install -e . pytest` → `pytest -q`
