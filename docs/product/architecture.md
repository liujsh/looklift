# looklift 设计文档

> 产品定位、用户故事、路线图见 [requirements.md](requirements.md)。本文档记录**已实现**的技术架构与关键设计决策。
> 未实现迭代的详细设计写在 `docs/versions/`(每迭代一个版本目录,实现后要点回填本文档)。最近完成:[RAW 可行性门](../versions/raw-gate/)。

> 未实现迭代的详细设计写在 `docs/versions/`(每迭代一个版本目录,实现后要点回填本文档)。当前:[v2.5](../versions/v2.5/)。

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

## v2.4 模板与教学架构实况

- `looklift/gui/template_catalog.py` 把既有官方/用户 look 投影为模板卡片；参数仍只存在于
  原 `analysis`，包内 `template_lessons.json` 只保存一级分类、适用场景、原理和关键参数路径。
- `GET /api/templates` 提供卡片目录，完整参数继续由 `GET /api/looks/<name>` 读取；用户
  look 文件无需迁移，缺少官方教学元数据时从摘要、步骤和非中性参数生成降级教学。
- 平台模板页采用“简洁暗房目录 → 独立暖纸详情”两级结构；来源、一级分类和搜索在目录页正交
  筛选，用户模板缺少元数据时投影到“未分类”。卡片无授权预览时显示参数指纹，不把原型占位图
  当照片效果，目录页不常驻教学和应用操作。
- 详情页读取完整 `analysis`，由现有 `ParamContract` 驱动只读滑杆，并把曲线、逐色 HSL 和颜色
  分级呈现为真实曲线图、三维度颜色滑杆和色轮；默认隐藏中性项，不建立第二套参数范围。
- 最近 Studio 存在时，详情页以可取消的 factor 0/1 预览请求
  生成当前照片 Before/After；预览不写 Store。详情页应用按钮才通过 Studio runtime 正式提交并
  持久化会话版本。聊天模板附件仍只在发送边界组合名称、摘要和白盒参数，不改变安全边界。

## v2.5 自动化技能架构实况

- `automation_store.py` 以应用数据目录中的独立 JSON 保存技能、冻结计划与运行清单；技能只引用
  既有 look，计划生成时冻结同一份白盒 `analysis`、强度和输出规则。
- `automation_render.py` 复用主渲染引擎生成完整尺寸 JPEG，在目标目录先写临时文件，再通过
  不覆盖既有路径的原子硬链接创建成片；原照片、既有输出和临时失败文件均受保护。
- `automation_tasks.py` 逐张隔离失败并在每项后持久化进度；协作式取消只阻止下一张开始，
  进程中断会恢复为可重试状态，重试只处理失败、中断或取消项。
- sidecar 提供技能、计划和运行 API；React 自动化页负责原生多选照片、输出目录、首张实际
  预览、逐文件计划确认、进度、取消与失败重试，不拥有渲染或路径安全逻辑。

## v2.3-A 本地文件夹图库架构实况

- `library.db` 保存索引根、文件项目、标签和导出操作摘要；schema 版本迁移会保留旧索引，
  原文件始终留在用户目录。文件项目以规范化路径保持稳定 ID，并记录大小、修改时间、尺寸、
  格式和安全拍摄信息，重复扫描只更新变化项。
- `library_tasks.py` 为每个根维护单一后台扫描任务，扫描逐项提交并通过任务 ID 暴露进度；取消
  保留已完成索引且不把尚未遍历的文件误标为缺失。完整扫描后才统一标记缺失文件，后续刷新
  可恢复同一项目。
- 缩略图以最长边 512px JPEG 写入应用数据缓存。普通图片和 Pillow 能解码的 RAW 嵌入预览
  共用同一路径；无法解码的 RAW 保留真实文件记录，由 React 显示格式占位卡。
- sidecar API 提供索引根管理、异步扫描状态/取消、关键词与标签组合分页、标签写入和按项目 ID
  调用 Windows Explorer。图库分页结果合并正式会话的当前版本摘要与 sidecar 导出次数，不把
  临时 AI 候选写入图库。
- React 图库页只消费上述显式契约，负责网格、筛选、分页、标签和缺失状态；进入 Studio 时复用
  `SessionStore.create_or_resume`，已有正式会话按源文件路径恢复，没有时才创建初始版本。

## RAW 可行性门架构实况

- `looklift.raw_gate` 是独立的离线诊断入口，不进入 Studio 运行时；`python -m looklift.raw_gate`
  接受作者提供的 manifest，只读本地 RAW 并输出原子替换的 JSON 报告和中文摘要。
- rawpy 通过可选依赖组 `raw` 与函数内可选导入接入，缺失或 DLL 不可用时报告结构化 `rawpy_unavailable` NO-GO，
  不让 GUI 在导入模块时崩溃。每个样本独立记录解码错误、RGB 形状/位深、方向、白平衡、耗时、
  峰值内存和现有图像管线兼容性。
- 决策要求样本/相机覆盖、全部样本成功、RGB/方向/白平衡契约、管线检查和性能测量同时通过；
  失败时明确锁定 v2.3-B 的“内嵌 JPEG 预览 + XMP sidecar”降级路径。真实相机样本门禁仍由作者执行。

## v2.2 平台外壳架构实况

- 平台 Store 只拥有全局导航折叠状态、标签顺序和活动标签；固定首页、说明页与 Studio
  共用标签模型，但平台层不复制调色参数、聊天或渲染状态。
- 每个 Studio 标签由独立运行时拥有 `editorStore`、会话协调器和聊天工作流。非活动运行时
  保持挂载以保留内存状态，但 Canvas 不注册窗口级拖放；关闭后统一取消请求、监听与预览资源，
  并拒绝晚到异步结果。
- 首页快速修图在 Tauri 中通过官方原生文件对话框取得稳定路径，普通浏览器开发模式继续使用
  上传回退。只有正式会话创建或恢复成功后才打开标签，取消或失败不会留下空运行时。
- 最近会话是 v2.1 SQLite 正式会话表的只读投影；列表不返回绝对路径或临时候选，完整恢复仍
  读取正式 analysis、消息和当前版本。缺失源文件只标记不可用，不搜索或替换路径。
- 关闭门禁先处理运行中的 AI，再对未确认候选提供保留、放弃和取消；保存失败保留运行时与候选。
  标签工作区、面板内存状态和未确认预览均不持久化，应用重启仍以正式会话为唯一恢复边界。
- 设备导入、自动化和插件页只说明目标版本，不创建对应数据实体或调用尚未存在的接口。

## v2.1 AI Studio 架构实况

- React 编辑 Store 同时暴露正式 `analysis` 与仅内存存在的 `pendingPreview`；画布和右侧
  面板统一读取 `displayAnalysis`，但候选只有在用户选择“保留此版本”后才成为正式状态。
- `chat_step` 保持无状态：每轮只接收安全代理图、最近消息、当前白盒参数和可选安全
  元数据；模型响应先经过本地参数白名单、范围和主曲线原子校验，不允许直接改像素、
  RGB 分通道曲线或局部蒙版。
- 本地 HTTP 层把候选计算与持久化拆成 `/api/chat/step`、`/api/sessions/*/commit` 和
  `messages` 三类操作。前端必须先确认候选渲染成功，再事务提交消息、版本和当前指针。
- `~/.looklift/looklift.db` 保存正式会话、消息、版本和当前指针；临时预览不入库。
  schema 升级前轮换三份备份，损坏时提供只读恢复入口而不覆盖原数据库。
- 普通消息固定调用一次；显式“AI 精修”最多追加两轮，每轮以上一候选为输入，并在
  达成、无变化、取消或轮数上限时确定停止。所有 provider 调用仍复用既有抽象。
- AI 请求冻结图片身份、当前 `analysis` 与强度；后端复用正式预览管线生成最长边 2048px、
  无 EXIF 的当前效果 JPEG。请求期间 Store 以活动 request ID 锁定编辑，停止立即解锁，
  切图或晚到响应不得建立候选。
- Canvas 把成功 after 预览的 blob 与签名交给前端 Web Worker，缩至约 512px 后统计 256 档
  RGB 与黑白场裁切比例。直方图是可失败的派生数据，不进入 analysis、版本或数据库；
  `/api/image-info` 只返回白名单拍摄信息供右侧独立展示。

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

### 8. 未来迭代设计(已拆分至 versions/)

- v0.3(provider 抽象、preview 渲染、auto-refine、LUT 导出):已实现,详见下方「v0.3 新增设计」(§10-15);
  原 spec:[v0.3/spec.md](../versions/v0.3/spec.md)
- v0.4(GUI alpha:pywebview 窗口/浏览器双模式、本地 HTTP server、强度滑杆、
  风格库面板、报告页):已实现,详见下方「v0.4 新增设计」(§16-19);
  原 spec:[v0.4/](../versions/v0.4/)
- v0.5(OpenAI-compatible/Ollama provider、可续跑目录批量分析、GUI 配置):已实现,
  详见下方「v0.5 新增设计」;原 spec:[v0.5/](../versions/v0.5/)
- v0.7 打包方向(PyInstaller 单 exe):已终止,历史细节见 [v0.7/](../versions/v0.7/)

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
  - v0.3 末共 71 个用例;v0.4 GUI alpha 新增 143 个(见下方「v0.4 测试」),
    当前共 **214 个**,全部离线(不触网、不调 AI、不碰真实 `~/.looklift`)
- `.github/workflows/ci.yml`:push/PR 触发,matrix = {ubuntu, windows, macos} × py3.12,
  `pip install -e . pytest` → `pytest -q`(不装 `[gui]` extra 也能跑;GUI 测试
  全部走 `create_server`/monkeypatch,不依赖真实 pywebview/WebView2)

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
- `OpenAICompatProvider` / `OllamaProvider`:分别翻译为标准 Chat Completions vision
  data URI 与 `/api/chat` 纯 base64；两者经 `_extract_json` 后仍由 analyzer 统一 normalize
- `get_provider("auto")` 解析顺序:config.toml 显式指定任一 provider→
  有 API key(环境变量 `ANTHROPIC_API_KEY` 或 config 的 `api_key`)→
  `which("claude")` → 报错
- `_extract_json`:cli 后端输出无 schema 硬约束,容错提取(剥 markdown 代码块、
  取首尾大括号)

### 11. 配置(config.py)

- `load_config()`:读 `~/.looklift/config.toml`(`tomllib`),键
  `provider/model/api_key/base_url/looks_dir/timeout`;同名环境变量 `LOOKLIFT_*`
  非空时覆盖
- `provider_timeout()`:校验正整数秒；空值按 cli/api/openai_compat/ollama 分别取
  600/120/120/300 秒
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

---

## v0.4 新增设计

> 原 spec:[v0.4/](../versions/v0.4/)(requirements.md / design.md / tasks.md)。
> 本节只回填**已实现**的架构要点,完整决策权衡见 spec 的 design.md。

### 16. GUI 架构(looklift/gui/)

```
looklift gui [--browser]
        │
   gui/app.py ── 起 gui/server.py(ThreadingHTTPServer,127.0.0.1:随机端口)
        │            → window 分支:webview.create_window + 注册原生拖放桥
        │              (import webview 失败 / 启动异常 → 自动降级到 browser 分支)
        │            → browser 分支:webbrowser.open,阻塞到 Ctrl-C
        ▼
   gui/server.py ── 显式路由白名单:/ 、/static/* 、/api/* 、/report/*(其余 404)
        ▼
   gui/api.py ── 薄粘合 handler 表:HTTP 参数校验 → 调核心模块 → JSON/二进制响应
        │
   ┌────┼──────────────┬────────────────┬───────────────┐
   ▼    ▼               ▼                ▼               ▼
 gui/tasks.py      gui/upload.py    gui/lookstore.py  intensity.py(新)
 后台线程任务表      multipart 落      风格库 json+xmp    scale_analysis
 status/message/    临时文件+文件名    文件 IO(不碰       (强度缩放纯函数,
 result/error        硬化清洗          HTTP 层)           §17)
```

- `app.py`:唯一入口,只做「起 server → 选窗口/浏览器分支」;两条分支退出前
  统一调 `_stop(srv)`(`shutdown()` + `server_close()`),不留残余监听线程/端口
- `server.py`:`ThreadingHTTPServer` + 显式前缀路由白名单;`/static/*` 额外做
  路径穿越防护(解析后的路径必须落在 `STATIC_DIR` 内才提供服务);handler 抛出
  的任何异常在 `_dispatch` 顶层统一兜底转 500 JSON,不吐 traceback
- `api.py`:`ROUTES: dict[(method, pattern), Handler]`,handler 只做「HTTP 参数
  校验 → 调核心模块(`analyzer`/`render`/`intensity`/`xmp_writer`/`report`/
  `config`)→ 响应」,业务逻辑一律留在核心模块——CLI 与 GUI 长期共享同一套实现
- `tasks.py`:内存态 `{task_id: {status, message, result, error}}`,后台
  daemon 线程跑耗时函数(`analyzer.analyze` 单次 30-120s),HTTP 请求处理线程
  立即拿 `task_id` 返回,前端轮询 `GET /api/tasks/<id>` 拿进度/结果
- `upload.py`:browser 模式专用(window 模式走 pywebview 原生拖放桥,零拷贝拿
  真实文件路径)——用 stdlib `email` 模块解析 multipart(`cgi.FieldStorage`
  在 Python 3.13 已移除),文件名清洗(剥路径分隔符只留末段、Windows 保留字符
  `< > : " | ? *` 与控制字符替换为 `_`、去首尾点/空格、清洗后为空回退固定名),
  50MB 上限,落 `tempfile.mkdtemp()` 惰性创建的进程级临时目录
- `lookstore.py`:风格库文件 IO(`<name>.json` + `<name>.xmp`),不碰 HTTP 层;
  与 CLI(`cli.cmd_analyze`/`cmd_list`)读写同一份 `config.looks_dir()` 目录,
  落盘形状必须与 CLI 一致,否则两边互相看不懂对方存的东西

### 17. 强度缩放语义(intensity.scale_analysis)

`scale_analysis(analysis, factor) -> dict`(纯函数,`factor∈[0,1]`,越界裁剪,
不改入参):

| 字段 | 缩放规则 |
|---|---|
| `basic` 13 项、`hsl[].{hue,saturation,luminance}`、`color_grading.{shadows,midtones,highlights,global_}.{saturation,luminance}`、`color_grading.balance`、`effects.*` | 乘 `factor`(全是相对中性基准的偏移量) |
| `color_grading.{...}.hue` | **不缩放**——色轮绝对角度(0-360),缩放角度没有物理意义 |
| `color_grading.blending` | **不缩放**——中间调过渡范围的技术参数,不代表强度 |
| `tone_curve[].output` | 向恒等线插值:`output' = input + factor*(output-input)`;`input` 不变 |
| `summary`/`steps` | 透传不变 |

`factor=1` 与原值完全一致(浮点误差内);`factor=0` 退化为"无调整"(曲线变对
角线)。GUI 侧滑杆变化 → `scale_analysis` → 同时喂 `render.render`(预览)和
`xmp_writer.analysis_to_crs`(导出),保证导出的预设/sidecar 是滑杆当前强度而
不是永远 100%。配套修了 `render.py` 一处曲线域外插值缺口:`_apply_color_ops`
第 6 步对超出控制点定义域的像素,原来是把 `np.interp` 直接夹到边界 y 值,改成
按斜率 1(恒等)外推——否则控制点不严格贴 0/255 时(如
`[(15,15),(128,128),(240,240)]`),`factor=0` 生成的"恒等曲线"渲染出来纯黑
会变成 15/255,不是真正的纯黑。

### 18. 双响应形态(server.py 分发)

`api.py` 的 handler 返回两种形状之一,`server.py` 按元组长度分发,不拆两套
Handler 签名:

| 返回值 | 分发方式 | 用例 |
|---|---|---|
| `(status, dict)` | `_send_json`:`json.dumps(ensure_ascii=False)` | 除下一行外的全部路由 |
| `(status, bytes, content_type)` | `_send_binary`:原样写字节 + 指定 Content-Type | `POST /api/preview`(JPEG 字节)、`GET /report/<name>`(HTML 字节) |

请求上下文同样统一成一个 dict:`{"params", "body": bytes | None, "content_type",
"query"}`——`body` 只有 `Content-Length` 头存在且 >0 才不是 `None`(区分"没有
body"和"空 body");需要读 body 的 handler(`/api/upload`/`/api/analyze`/...)
和只需要段参数的 handler(`/api/tasks/<id>`)用同一套签名,不必分裂成两种
Handler 类型。

### 19. 安全清单

| 项 | 问题 | 缓解 |
|---|---|---|
| XSS(双层) | `report.py` 对 `hsl[].color` 走 `_HSL_CN.get(color, color)` 原样回退进 HTML;早期 `POST /api/looks` 只检查 `analysis` 是不是 dict,任意内容都能落盘,`GET /report/<name>` 又原样把它吐回浏览器,构成存储型 XSS | `report.py` 补 `escape()`(第一层);`api.py` 新增 `_validate_analysis`,只挡"会被当受信任枚举/固定类型使用"的字段(如 `hsl[].color` 必须在 8 色枚举内),不重新实现一遍完整 `ANALYSIS_SCHEMA`(第二层) |
| `api_key` 回传 | 配置面板若原样回显密钥,浏览器 DevTools/日志可见 | `GET /api/config` 只回 `has_key: bool`,从不回传密钥原文;`POST /api/config` 里空字符串代表"保留原值"而非"清空" |
| 上传文件名 | 原始文件名可能带路径分隔符、Windows 保留字符(`< > : " \| ? *`)、控制字符——曾复现静默截断 / NTFS 备用数据流触发 / 未捕获 `OSError` 500 且响应体泄漏本机路径+用户名 | `upload.sanitize_filename`:剥路径分隔符只留末段 → 保留字符/控制字符替换为 `_` → 去首尾点/空格 → 清洗后为空回退固定名;写入失败统一转 400 通用中文文案,不回显 `str(exc)` |
| 风格库名 | 库名要在 UI 原样展示,不能像上传文件名一样静默清洗(会导致"存的名字"和"看到的名字"对不上) | `_validate_look_name` 拒绝式校验:空/纯空白、超长、含 `..`、含路径分隔符或 Windows 保留字符一律 400,不静默改写;路径穿越额外靠 `server.py` 对整条请求路径先 `unquote()` 再按 `/` 分段比较段数兜底(编码过的 `..%2f` 在匹配路由前就已展开,段数对不上直接 404) |
| 本地 server 暴露面 | 监听地址若误绑 `0.0.0.0` 会让局域网其他设备访问到分析接口 | 显式绑定 `127.0.0.1`,不做用户鉴权(同机单用户模型,鉴权对此场景过度设计),写进代码注释避免后续误改 |

---

## v0.5 新增设计

> 原 spec:[v0.5/](../versions/v0.5/)；本节只记录已实现实况。

### 20. 多供应商 HTTP 层

- `provider_http.py` 用标准库 `urllib.request` 发送 JSON；连接错误与 5xx 退避后重试
  一次，4xx 不重试；测试可替换 opener/sleeper，全程离线
- OpenAI-compatible 请求地址为 `base_url + /chat/completions`，图片是完整 data URI；
  Ollama 请求地址为 `base_url + /api/chat`，图片数组只含 base64
- provider 负责 wire 格式与中文错误映射；`analyzer.py` 仍是输出 normalize 的唯一入口

### 21. 可续跑批量分析

- `batch.py` 把根目录下每个含图片的一级子目录视为一组；图片按 mtime/文件名稳定排序，
  最多取 5 张
- 成功结果经同目录临时文件 + `os.replace` 原子写成 `.looklift-result.json`，同时作为
  断点；默认跳过已有结果，`--force` 删除旧断点后重算
- 单组异常只进入失败摘要，不中断其余组；任一失败时 CLI 最终退出码为 1

### 22. GUI 配置扩展

- 同一份设置表单增加 `openai_compat`/`ollama`、base_url/model/timeout；向导继续克隆复用
- provider 切换时隐藏无意义字段，Ollama 不显示 API key；配置 API 回显非敏感字段，
  密钥仍只返回 `has_key`

---

## v2.0-B 新增设计

> 原 spec：[v2.0-B/](../versions/v2.0-B/)；本节只记录已实现实况。

### 23. Tauri + React + Python sidecar

```
Tauri 原生窗口
  ├─ Rust 壳：spawn/reap sidecar、生成启动令牌、读取随机端口
  ├─ React 前端：三栏工作台、画布、参数面板、图库与导出交互
  └─ Python sidecar：localhost HTTP → gui/api.py → 核心分析/渲染/收藏/导出
```

- Rust 壳只管理窗口和进程。启动 `looklift-engine serve --port 0` 后，从 stdout 的
  `ready` JSON 取得端口，并把随机启动令牌通过 Tauri command 交给前端；应用退出时
  kill 并回收子进程。
- React 的 `LookliftClient` 为 `/api/*` 请求添加启动令牌；调色数学、参数范围、收藏和
  导出均留在 Python。报告页使用编码后的本地 `/report/<name>` URL 在新窗口打开。
- PyInstaller onedir sidecar 包含 numba、pyvips/libvips、ICC 和内置模板；numba cache
  位于 `%LOCALAPPDATA%/looklift/cache/numba`，不写安装目录。

### 24. 单一编辑状态与实时预览

- `editorStore` 是 `analysis`、全局强度、图片路径和版本栈唯一 owner。AI 整对象回填、
  面板分片修改和未来聊天 delta 都进入同一提交内核。
- 参数控件只消费 `/api/param-contract` 投影的范围和默认值；前端只维护分组、路径和中文
  标签，不复制 Python 参数范围表。
- 预览调度器以 160ms 防抖、单一 `AbortController` 和单调请求序号处理连续拖动；旧慢
  响应不会覆盖新画面。before/after 使用同尺寸 JPEG 与 CSS clipping，不引入 GPL 组件。

### 25. 内置模板与用户图库

- 三份原创通用模板由包内 `looklift/data/looks/*.json` 提供，只读加载；用户风格继续写
  `config.looks_dir()` 指向的可写目录。合并时用户历史同名条目优先且列表不重复。
- 收藏把当前 `analysis` 与全局强度交给既有 API，成功后局部刷新图库；只有刚收藏或载入、
  此后未修改的风格可从顶栏导出，避免当前画面与库内对象不一致。

### 26. Windows release 验证

- `packaging/stage_sidecar.ps1` 只把冻结 exe 与 `_internal` 复制到 Tauri `externalBin` 暂存区；
  Tauri bundler 生成 NSIS 安装包。
- `packaging/smoke_release.py` 在临时用户目录连续预热冻结引擎，启动随机 localhost 端口，
  校验内置模板只读、用户库可写、XMP 可导出，并回收 sidecar；全程不访问外网或 AI。

---

## v2.6-A–C 新增设计

> 原规格：[v2.6/](../versions/v2.6/)；这里只记录已实现的 API 候选闭环与首条受控 CLI Adapter。

### 27. Domain Pack 与统一 Adapter

- `domain_pack.py` 按固定优先级和预算编译领域契约、StyleProfile、单个 Skill、必要 Reference、可选 Template
  元数据和本轮目标，并生成内容 Hash；快照可在原始来源变化后复现同一 Attempt 输入。
- `agent_adapter.py` 把 Harness 收敛为 `start/cancel/dispose` 和八种有限事件。模型只接收编译文本与无 EXIF
  JPEG 代理图，不接收 Run、Attempt、Lease、正式版本 ID、原图路径或数据库信息。
- API 路径使用 `pydantic-ai-slim 2.32.x`；Anthropic、OpenAI-compatible 和 Ollama 只共享构造与事件适配层，
  一个 Attempt 内不自动切换 Provider。Fake/FunctionModel 测试全程离线。

### 28. 受控候选 Runtime

```
Domain Pack + 代理图 → Pydantic AI Agent
                         │ render_candidate（白盒 Patch）
                         ▼
Run/Attempt/Lease 守卫 → 唯一渲染引擎 → JPEG + 参数差异 + 指标
                         │ 真实结果回灌，可再修改
                         ▼
finish_candidate（模型终态）→ 内存候选，等待未来 UI 人工确认
```

- `agent_tool_contract.py` 是候选工具类型入口；标量路径和范围仍来自 `render.contract`，越界操作严格拒绝，
  不静默截断。Template 相对正式基线叠加，只能在首个成功候选决定一次。
- `CandidateRuntime` 默认最多渲染三次，保存不可变单线 Revision；每次渲染前和原子落候选时均复核权威状态，
  取消、Lease/Attempt 或正式基线变化使晚到结果成为 `cancelled/stale`。
- `render_candidate` 的富 Tool Result 同时包含结构化结果和真实 JPEG；`finish_candidate` 仅接受最新候选、
  无修改或明确能力不足三类终态。Finish 不保存、导出或修改正式版本。

### 29. CLI 隔离与 Pi Adapter

- 每个 CLI Attempt 使用随机 Workspace，只写编译后的 `DOMAIN_PACK.md`、代理图、传输无关 Tool Schema 和候选预览；
  目录名不含 Run/Attempt，环境按白名单重建并移除 Provider API Key、数据库和 LookLift 私有变量。
- `ScopedToolGateway` 以随机、可过期和可撤销 Token 私有绑定 `CandidateRuntime`，只接受 `render_candidate` 与
  `finish_candidate`。CLI 传入的参数不含运行身份、真实路径和正式版本；终态成功、取消或进程结束都会撤销 Token。
- Pi 使用其原生 RPC JSONL 事件和随应用只读 JavaScript Extension；启动参数关闭内建工具、其他 Extension、Skill、
  Prompt、Theme、项目上下文和 Session。Extension 经随机 localhost HTTP 端口调用同一 Gateway，并把 JPEG 作为图片
  Tool Result。RPC 初始消息直接携带冻结 Domain Pack 与安全代理图，不携带 Runtime 身份或私有路径。
- stdout 使用 8 MiB 硬上限容纳 Pi 回显的代理图片事件；Windows 可用直接 `node + cli.js` 前缀避免 npm `.cmd` 外壳
  妨碍进程回收。Fake 契约与真实 Pi 0.84.1/OpenRouter 候选、结构化终态和 0.028 秒取消均已验证，Pi 为当前唯一正式
  CLI Adapter；其他 CLI 不继承该等级。

### 30. v2.6-D 领域内容与离线评测

- `domain_skill.py` 注册三份版本化内置 Skill：`portrait-natural`、`product-consistency` 和
  `highlight-recovery`；正文与 Reference 均经固定章节、能力白名单、路径和 SHA-256 校验。
- `builtin_agent_templates.py` 提供六份只读官方相对白盒 Template，全部复用 `AgentTemplate`/`ScalarOperation`，
  不含脚本、路径、Prompt 或权限，也不复制候选渲染逻辑。
- `agent_eval.py` 固定 12 个效果 Case 与 8 个工程/安全 Case，使用确定性代理图和 Fake Harness 运行；结果记录终态、
  候选/工具调用数、失败码、正式副作用和敏感数据泄漏。消融配置已可表达 Skill、Template 与真实反馈对照，
  但真实模型结果和人工 Pairwise 仍不进入默认 CI。
### Context Compiler 2.0 与运行事实接线

`DomainPackRequest` 已支持冻结的 Capability/Permission、全局规则、Memory 和 Project Context 来源；编译顺序将权限与 Tool Contract 固定在领域和用户内容之前，所有来源进入稳定 Hash 与可恢复快照。`RunManifestStore.append_agent_event` 消费统一 `AgentEvent`，拒绝跨 Run/Attempt 事件，并在新 Attempt 开始时重置事件序号，避免 Harness 原生会话成为状态真相源。

### 声明式 Runtime 探测

`RuntimeDefinition` 已统一 API、CLI、Fake 的输入传输、流格式、Resume、MCP、能力和权限描述；`RuntimeDetectionEngine` 对注册项执行并行、限时、故障隔离的探测，输出脱敏的可用性、认证、版本和模型结果，单个 Runtime 失败不会阻断其他结果。

`RuntimeLifecycleEngine` 根据用户明确选择的 Definition 创建 Adapter，校验所需能力与事件身份/序号，统一附加 Runtime 能力快照并负责取消和回收。内置目录声明 Pydantic API、Pi CLI 和 Fake 三种 Runtime；`GET /api/runtimes` 只暴露选择器所需的安全字段，不返回命令、端点、环境或凭据。

### Plugin Registry、Scoped Token 与 Skill staging

Plugin Manifest 校验稳定语义版本、内容 SHA-256、类型、模式和能力红线；Registry 保留所有历史版本，卸载只禁用当前选择，不删除历史运行引用。`ScopedTokenStore` 将 Grant 绑定项目、版本和 Attempt，撤销主体后现有令牌立即失效。Skill staging 只接受 `SKILL.md` 和一层 Markdown Reference，将规范化内容冻结到项目私有 Hash 目录并阻断路径穿越。

### Connector Source Packet 与 Provider Gateway

Connector Manifest 固定协议、数据接收方和能力；外部事实先进入带来源摘要的 `SourcePacketStore`，再调用共享 Proposal Service 生成带 provenance 的提案。`ProviderGateway` 不接受文件路径，只接收内存 JPEG，并在发送前校验授权接收方、2048px 上限、真实 JPEG 格式和 EXIF 为空，输出既有 `AgentImage` 安全代理对象。

### Verifier、Critique 与 User Review Gate

`CandidateVerifier` 直接消费 CandidateRuntime 冻结的 changes、preview 和 metrics，不重新渲染或创建 Revision。Contract/Domain/Capability 硬失败阻止进入复核，裁切阈值产生可审阅软警告；每次结果包含覆盖候选差异、指标和预览摘要的 evidence hash。`UserReviewGate` 只冻结用户确认意图并复核正式基线，不承担正式版本提交。

### 版本化离线 Eval Runner

`agent_eval.py` 固定数据集版本 `v2.6-D-2026-08-25` 与 20 个确定性 Case。每次结果保存完整事件轨迹、失败分类、候选/工具计数、取消和晚到隔离状态、正式版本不变、候选版本单调、敏感数据检查及消融配置。`run_ablation_matrix()` 提供 Skill、Template、反馈三维对照；`build_eval_report()` 输出包含 Case 元数据、汇总、失败分类和四阶段门禁的 JSON 结构。真实模型消融和人工 Pairwise 没有数据时固定为 `pending_manual`，不生成产品通过结论。

### Run Manifest Repository 与恢复 API

每个 Run 使用独立 JSONL 事实日志和原子快照，Repository 以安全 Run ID 管理列表、详情和恢复。应用创建本地服务时执行一次启动收敛，将未完成状态标为 interrupted；普通查询不改变运行状态。`GET /api/agent/runs/recoverable` 和详情 API 暴露脱敏事实，恢复命令只在基线一致且状态为 interrupted/failed 时创建新 Attempt，可显式切换 Runtime，但不会自动启动模型调用。

恢复 API 不信任前端提交的基线：Manifest 绑定正式 `session_id`，服务端从 `SessionStore` 读取当前版本并计算 Hash。React 平台增加“运行恢复”页，展示状态、Harness/Provider/Model、最后候选 Revision 和基线摘要；stale Run 只读，中断/失败 Run 可明确选择 Runtime 并新建 Attempt。

### Global Rules、Memory 与 Project Context 设置

`ContextMemoryStore` 在独立应用数据目录保存受限 Markdown 条目、机器可读索引和默认关闭的自动提取配置；条目 ID 只接受安全 slug，用户直接编辑会形成已确认的新版本，停用保留正文和版本审计但不再进入新 Run 快照。Store 启动时从磁盘恢复，不依赖进程内存。

跨 Agent、Connector 和 Context 的写入统一由持久化 `ProposalService` 管理，状态固定为 preview、confirmed、rejected、applied、expired 或 conflict。确认与应用分离，`base_hash` 冲突不会覆盖正式内容，重复确认、拒绝和应用保持幂等；Proposal 保留 Source Packet ID，不把来源正文写进日志。

冻结给 Harness 的 Context 快照只包含 enabled 且 confirmed 的条目，并在不改写本地原文的前提下清除 Home/原图路径、密钥和 EXIF 明细。Global Rule、Memory 与 Project Context 进入 Domain Pack 时转义分区边界，不能伪造 Tool Contract。Python API 提供配置、条目、规则和 Proposal Query/Command；React 设置页展示来源、版本、确认状态、Hash、项目上下文及提案审核，不接触存储路径。

运行详情的 `RunManifest` 额外冻结脱敏 `context_sources` 摘要，只包含来源 ID、版本、内容 Hash、使用/省略状态和省略原因；旧 Manifest 缺少该字段时按空摘要兼容。恢复页据此展示本次上下文依据，不返回上下文正文、原图路径或密钥。
