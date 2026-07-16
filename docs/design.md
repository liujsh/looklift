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

- v0.3(provider 抽象、preview 渲染、auto-refine、LUT 导出):已实现,详见下方「v0.3 新增设计」(§10-15);
  原 spec:[specs/2026-07-16-v0.3-precision-loop.md](specs/2026-07-16-v0.3-precision-loop.md)
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

- `tests/`:pytest,不触网、不调 AI;`conftest.py` 的 autouse `_isolate_env` 夹具
  假 `Path.home()`、假 `config.CONFIG_PATH`、清空 `LOOKLIFT_*` 环境变量——任何测试
  都不可能碰到真实 `~/.looklift`(结构性隔离,而非逐用例手动 monkeypatch)
  - `test_xmp_writer.py`:analysis→crs 映射(符号前缀、HSL 字段、曲线 Seq)、
    预设/sidecar XML 合法性(minidom 解析)、往返(写出→xmp_reader 读回一致)
  - `test_xmp_reader.py`:属性式+元素式 crs 提取、无 XMP 返回 None
  - `test_analyzer.py`:`_normalize` 补全稀疏输出、`_extract_json` 容错(裸 JSON/
    代码块/前后杂文)、`resolve_backend` 三分支
  - `test_config.py`:TOML+env 覆盖优先级、`looks_dir()` 三级 fallback(cwd → config → 默认)
  - `test_providers.py`:CLI provider 的 Block→Read 指令拼装、
    `get_provider` 解析顺序(config → env key → which claude)
  - `test_render.py`:各调整项方向正确性(如 exposure>0 更亮)、HSV 往返、float32 契约
  - `test_autorefine.py`:收敛判定(提升<阈值提前停止)、最佳参数不一定是最后一轮
  - `test_lut.py`:.cube 格式(SIZE/DOMAIN/行数/取值范围)程序化校验
  - `test_cli.py`:`_resolve_template` 名字/路径解析、`_expand_raws` 通配符、
    `apply` 端到端(tmp_path 下生成文件)
  - 共 57 个用例
- `.github/workflows/ci.yml`:push/PR 触发,matrix = {ubuntu, windows, macos} × py3.12,
  `pip install -e . pytest` → `pytest -q`

---

## v0.3 新增设计

### 10. Provider 层(providers.py)

统一「发图+文字,按 schema 收 JSON」的传输层,analyzer.py 收窄为只负责
prompt/schema/normalize,组装 blocks 后交给 provider。

- **Block 约定**:`{"type": "text", "text": str}` / `{"type": "image", "path": Path,
  "label": str}`(label 如"原片"/"成片"/"效果图",两个后端各自决定怎么把图片发给模型)
- `VisionProvider` Protocol:`complete(system, blocks, schema) -> dict`
- `ClaudeCliProvider` / `AnthropicProvider`:即原 §1 的 cli/api 后端实现原样迁入,
  行为不变(cli 走 stdin 传 prompt;api 用 json_schema 结构化输出,图片长边压到
  `MAX_EDGE=1568`)
- `get_provider("auto")` 解析顺序:config.toml 显式指定 provider(cli/api)→
  有 API key(环境变量 `ANTHROPIC_API_KEY` 或 config 的 `api_key`)→
  `which("claude")` → 报错
- `_extract_json`:cli 后端输出无 schema 硬约束,容错提取(剥 markdown 代码块、
  取首尾大括号)

### 11. 配置(config.py)

- `load_config()`:读 `~/.looklift/config.toml`(`tomllib`),键
  `provider/model/api_key/base_url/looks_dir`;同名环境变量 `LOOKLIFT_*`
  非空时覆盖
- `looks_dir()`:cwd 下有 `looks/` 优先(兼容 v0.1/v0.2 项目内风格库)→
  配置项 `looks_dir` → 默认 `~/.looklift/looks/`
- `AnthropicProvider` 的 model 取 `config.load_config()["model"] or MODEL`
  (配置优先于内置默认模型)

### 12. 渲染管线(render.py)

定位是「方向正确的近似」,不承诺与 Lightroom 一致。输入假设 sRGB;内部统一用
float32 0-1 numpy 数组,在关键节点 clip 回 `[0,1]`(高光/阴影蒙版前、白/黑场后、函数末尾)。`_apply_color_ops` 只含全局色彩
映射(供 lut.py 的 3D 网格采样直接复用),空间效果单独在 `_apply_spatial_ops`。

`_apply_color_ops` 固定顺序:

| # | 步骤 | 实现要点 |
|---|---|---|
| 1 | 曝光 | `2^ev` 增益 |
| 2 | 白平衡 | temperature 反向增益 R/B 通道,tint 增益 G 通道 |
| 3 | 对比度 | 围绕 0.5 线性扩张 |
| 4 | 高光/阴影 | `luma²` / `(1-luma)²` 亮度蒙版加权提亮压暗 |
| 5 | 白/黑场 | 端点缩放,黑场只影响近黑区(`(1-arr)⁴` 权重) |
| 6 | 色调曲线 | 控制点排序后 `np.interp` 成 LUT |
| 7-8 | HSL 定向 + 饱和度/自然饱和度 | 转 HSV 域一次完成,8 通道中心±45° 三角权重 |
| 9 | 颜色分级 | 阴影/中间调/高光/全局四区按亮度权重叠加色相 tint 与明度 |

`_apply_spatial_ops`:暗角(径向 r² 衰减,`r` 归一化到画面对角线);颗粒未渲染
(标注但不实现像素噪声,避免影响评分判断)。`render(image, analysis)` 是唯一
对外入口:PIL Image → 两组 ops → PIL Image。

### 13. 还原度评分(render.score)

- `score(rendered, target) -> 0-100`:两图缩到 256px 后,亮度直方图(64 bins)
  余弦相似度(权重 0.6)+ 近似 Lab a/b 通道均值与标准差的接近度(权重 0.4)
- 仅用于同一目标下的迭代趋势判断(autorefine 每轮打分),不做跨风格绝对值比较

### 14. 自动校准闭环(autorefine.py)

- `auto_refine(analysis, source, target, rounds=3, min_gain=1.0, backend, on_round)
  -> (最佳参数, 评分历史)`
- 每轮:当前参数渲染 source → `score` 评分 → 效果图与 target 一起交给
  `analyzer.refine`(AI)修正参数 → 下一轮
- 收敛:相邻两轮评分提升 < `min_gain` 提前停止;最佳参数取全程评分最高的一版
  (AI 修正不保证单调变好,不是永远取最后一轮)
- 临时文件:一次性 `mkdtemp` 目录 + 按轮次编号命名,`try/finally` 整目录清理
  (Windows `mkstemp` 返回打开的 fd,PIL 再次以该路径写入会 `PermissionError`,
  故不用 `mkstemp`)

### 15. LUT 导出(lut.py)

- `export_cube(analysis, out, size=33)`:在 `[0,1]³` 网格采样,复用
  `_apply_color_ops` 做颜色映射,写 DaVinci Resolve `.cube` 规范
  (`TITLE`/`LUT_3D_SIZE`/`DOMAIN_MIN`/`DOMAIN_MAX` + 网格数据行)
- 行序 R 变化最快、G 次之、B 最慢(`.cube` 标准顺序)
- 暗角、颗粒是空间效果,LUT 是逐像素颜色映射表、无法承载,导出时按设计跳过
  (CLI 输出中会提示)
