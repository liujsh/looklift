# v2.0-B Spec:三栏 GUI 壳(Tauri)—— 设计

> 状态:已确认(2026-07-18,作者授权开工)。
> 上游:[requirements.md](requirements.md)(本迭代做什么);技术栈定案见根 [plan](../../plans/)。
> 约定:本文件定"怎么做、为什么";选项均给推荐 + 理由。YAGNI:不写引擎内部/聊天/RAW。

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│  Tauri 原生窗口 (Rust 壳, ~10MB, 仅构建期需 Rust 工具链)         │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  React + TS + Vite 前端 (WebView 内渲染)                  │  │
│  │  ┌──────────┬──────────────────────┬──────────────────┐ │  │
│  │  │ [左:聊天] │      中画布           │   右 全局调色面板   │ │  │
│  │  │ v2.1 预留 │  image + diff slider │  operator 分组滑杆  │ │  │
│  │  │ (seam)   │                      │  + 曲线 + 强度      │ │  │
│  │  ├──────────┴──────────────────────┴──────────────────┤ │  │
│  │  │              下/侧 图库 (lookstore + 内置模板)         │ │  │
│  │  └────────────────────────────────────────────────────┘ │  │
│  └──────────────┬─────────────────────────────────────────┘  │
│                 │ localhost HTTP (复用现有 api.py 路由)         │
│                 │  (Tauri sidecar 生命周期管理 + 端口注入)      │
│  ┌──────────────▼─────────────────────────────────────────┐  │
│  │  Python 引擎 sidecar (PyInstaller 单/onedir exe)          │  │
│  │  server.py + api.py(路由) → analyzer/render/intensity/   │  │
│  │  lookstore/xmp_writer/lut/config/providers  (v2.0-A 引擎) │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

三层职责:**Tauri 壳**管窗口/进程生命周期/打包;**React 前端**管三栏 UI 与状态;
**Python sidecar** 管分析与渲染(引擎)。前端不含任何调色逻辑,渲染一律回引擎。

## 2. T1:打包 spike 的 go/no-go 设计(最先做,决策门)

这是"双语言 + sidecar + 双重打包"的分发架构,不是单纯换前端框架;spike B 已发现本机
**cargo/rustc 未装**(构建期成本,用户无感),真正未知是 **Tauri 打包 PyInstaller sidecar**
的平台摩擦。**先证实打包链路,再建任何 UI。**

> **D4 关键修正:T1 冻结的是「真实引擎 sidecar」,不是 `/api/ping` stub。** 本迭代最真实的分发
> 风险不是「能不能起个 HTTP server」,而是 **numba + pyvips(libvips DLL)能不能被 PyInstaller
> 冻结、且冻结后 numba 不是每次启动都重编译**。故 T1 必须打包一个**真正 import numba + pyvips、
> 启动时 JIT 编译一次并跑一帧真实渲染**的 sidecar(可复用 v2.0-A 引擎;v2.0-A 未就位时至少用一段
> 真实 `@njit(cache=True)` 内核 + `pyvips.Image` 调用触发两库的冻结与 JIT 路径,而非 stub)。
> 这把原本压在 T11 的「真实引擎打包」提前到决策门——**在建任何 UI 前,先证实 numba+libvips 冻结可行**。

### 门禁目标(通过=GO 才进 T2+)

| 验证点 | 通过判据 |
|---|---|
| 脚手架 | Tauri + React+TS+Vite 能 `dev` 起窗口、`build` 出安装包 |
| **真实引擎 sidecar 打包** | sidecar **真正 import numba + pyvips**、PyInstaller **onedir** 成功成 exe,能跑一帧真实渲染(非 `/api/ping` stub) |
| **numba cache 可写** | 冻结应用里 numba cache 目录**可写**——否则每次启动多秒重编译。落实:可写 cache 位置 / 构建期预热 / 随包预编译产物之一 |
| **冷启动耗时** | 测量冷启动(含首帧 JIT/加载)耗时并记录;评估是否需预热/预编译 |
| **Defender 不误报** | 干净 Windows 上 onedir 产物不被 Defender 拦截/隔离(呼应 v0.7 免签名路线) |
| externalBin 声明 | 该 exe 声明为 Tauri `externalBin`,随安装包一并分发 |
| 生命周期 | 应用启动**自动拉起** sidecar,关闭时**回收**(无孤儿进程) |
| IPC 往返 | 前端 → sidecar `/api/ping` 与一次**真实渲染**往返成功,端口协商可靠 |
| 真机双击 | 构建出的安装包在干净环境**双击运行**,以上全部成立 |

### go / no-go 与回退

| 结果 | 动作 |
|---|---|
| **GO** | 全部通过 → 锁定 Tauri 架构,进 T2 起 UI |
| **NO-GO**(打包链路无法在可接受成本内打通) | **回退保留 pywebview**(v0.4 已工作),React 前端改由 pywebview 托管其静态产物、仍复用 api.py;放弃 Tauri 轻分发优势但不阻塞三栏 UI 交付 |

> 回退成本可控的关键:**前后端通信选 localhost HTTP + 复用 api.py**(见 §4),
> 使前端与"壳是谁"解耦——Tauri 或 pywebview 都只是把同一套前端 + 同一个 Python server 装起来。

## 3. 前端组件结构

参照 **Onlook**(三栏状态绑定)+ **ART**(右面板按工具分组)。

```
src/
  App.tsx                     三栏布局骨架 (grid: [chat-seam] canvas panel / gallery)
  state/
    editorStore.ts            当前图 + analysis(operator 参数对象)+ factor + 渲染态 + 版本栈 seam(D2:每次应用变更 push,chat 与手动共用;undo UI 本期不做)
    galleryStore.ts           库列表 + 内置模板 + 当前载入项
  panes/
    ChatPane.tsx              v2.1 占位 (feature-flag 关闭, 保留 seam)
    CanvasPane.tsx            <img-comparison-slider> 包一层 + 加载/错误态
    PanelPane.tsx             右面板容器, 渲染 operator 分组
    GalleryPane.tsx           卡片网格 (用户库 + 内置模板 tab)
  panel/
    groups.ts                 operator → 分组映射 (见 §3.1)
    SliderControl.tsx         单参数滑杆 (label + range + 数值输入 + 复位)
    ToneCurve.tsx             曲线控件 (包 vaguilera/ColorCurve)
    HslMixer.tsx              8 通道 HSL
    ColorGradingWheels.tsx    4 区色轮
    StrengthSlider.tsx        全局强度 (factor)
  api/client.ts               fetch 封装 (对 sidecar localhost HTTP)
  theme/tokens.css            由 assets/design-system/claude/tokens.css 移植 (§6)
```

### 3.1 面板分组(按 operator,分组参照 ART)

| 分组 | 绑定的 `ANALYSIS_SCHEMA` 分片 | 控件 |
|---|---|---|
| 基础 | `basic`(温度/色调/曝光/对比/高光/阴影/白/黑/纹理/清晰/去朦胧/自然饱和/饱和,13 项) | 滑杆 ×13 |
| 色彩 HSL | `hsl`(8 通道 × 色相/饱和/明度) | HslMixer |
| 曲线 | `tone_curve`(控制点) | ToneCurve(ColorCurve) |
| 分级 | `color_grading`(阴影/中间调/高光/全局 4 色轮 + blending/balance) | ColorGradingWheels |
| 效果 | `effects`(暗角/颗粒) | 滑杆 ×2 |
| (顶部) | 全局 `factor` | StrengthSlider |

> 每个分组是薄组件,读写同一个 `analysis` 状态对象的对应分片——**参数模型即状态对象,
> 不发明新结构**(与引擎 `ANALYSIS_SCHEMA` 同构,回填/收藏/导出全用同一份)。
>
> **滑杆 min/max/复位默认来自 v2.0-A 参数契约(D1),前端不手抄范围表**:每根 `SliderControl`
> 的上下界与复位值从 `looklift/render/contract.py` 的 `param_bounds(path)` 导出——经 api.py 暴露一个
> 「参数契约」端点(如 `GET /api/param-contract` 返回 `{path: {min, max, default}}`),前端启动时取一次
> 缓存。v2.0-A 改字段范围时前端自动跟随,**杜绝前端与引擎各存一份范围而漂移**(这是 review C1/C2 的
> 前端侧落点;后端侧由 v2.0-A `contract.py` 保证单一真相源)。

### 3.2 复用组件清单 + 许可(需在 T2 逐个核对后锁定)

| 组件 | 用途 | 体积 | 声明许可 | 本期动作 |
|---|---|---|---|---|
| **sneas/img-comparison-slider** | 中画布 before/after diff | <12KB | 待核(README 标 MIT) | 核 LICENSE → 若 MIT 直接用;框架无关 web component,React 里包一层 |
| **vaguilera/ColorCurve** | 曲线编辑(改 canvas 通道) | 小 | **待核(仓库可能未标明许可)** | **风险项**:若无明确宽松许可 → 自研极简曲线控件(单调 Hermite 插值,数学参考 AlcedoStudio,不抄码) |
| react-colorful(可选) | HSL/色轮基元 | 小 | MIT | 仅当自研色轮成本高时引入 |

> 硬规则:**不碰任何 GPL 代码**。ART/AlcedoStudio/RapidRAW 均为 GPL/受限许可——**只学设计不抄码**。
> 组件许可未核实前不得写进 package.json;许可不明的一律按"自研兜底"排期。

## 4. 前后通信选型

| 选项 | 机制 | 优点 | 缺点 |
|---|---|---|---|
| **A. localhost HTTP(推荐)** | 前端 `fetch` 打 Python sidecar 的 HTTP server(**现有 `server.py`+`api.py` 直接复用**) | v0.4 已证实(211 测试通过);零重写;壳无关(Tauri/pywebview 都能用);二进制响应(JPEG 预览)天然支持 | 需端口协商;localhost 暴露面(单用户本地模型可接受,v0.4 已论证) |
| B. Tauri IPC(`invoke`) | 前端经 Rust `command` 转调 sidecar | Tauri 原生;无开放端口 | Rust 侧要写转发层;把渲染字节经 Rust 中转;**绑死 Tauri**,回退 pywebview 时整层作废;api.py 路由白重写 |

**推荐 A(localhost HTTP + 复用 api.py)**。理由:
1. **最大化 carry-forward**——api.py 的 12 条路由(`/api/analyze`/`/api/preview`/`/api/looks*`/
   `/report/*` 等)设计成熟、已测,直接迁移,本期前端只写 client。
2. **与壳解耦**——是 T1 回退方案成立的前提(§2):Tauri 或 pywebview 只负责"把 server 起起来"。
3. **二进制预览友好**——`/api/preview` 已返回 JPEG 字节流,HTTP 直取,不必经 Rust 编解码中转。

Tauri 的角色收窄为:**管 sidecar 生命周期 + 把协商到的端口注入前端**(而非承载业务 IPC)。
安全:仅绑 `127.0.0.1` + 随机端口 + 启动令牌;沿用 v0.4"localhost 单用户威胁模型"论证。

## 5. 打包架构

```
[Python 引擎 + server]  --PyInstaller-->  looklift-engine(.exe / onedir)
        │                                         │
        │                              声明为 Tauri externalBin
        ▼                                         ▼
   sidecar 二进制  ───────────────────►  Tauri bundler  ──►  安装包(.msi/.dmg/.AppImage)
                                                              双击 → 壳启动 → spawn sidecar
```

| 维度 | 说明 |
|---|---|
| 平台 | Windows(.msi/NSIS,主目标)· macOS(.dmg)· Linux(.AppImage);本期以 **Windows 优先**验收 |
| 体积 | Tauri 壳 ~10MB + PyInstaller sidecar(numpy/numba/pyvips 会偏大,~数十–上百 MB);numba 若含 LLVM 需实测 |
| Rust 工具链 | **构建期**需 cargo/rustc(本机未装,spike B 已记);用户运行期**无感**;CI/开发机需装 |
| PyInstaller 模式 | 优先 **onedir**(启动快、易排错、利于 Defender 白名单——呼应 v0.7 免签名路线);单文件仅在分发洁癖时选 |
| **numba cache 可写(D4)** | 冻结应用里 numba JIT cache 必须落在**可写目录**(用户数据目录 / 显式 `NUMBA_CACHE_DIR`),否则每次启动重编译多秒。可选:构建期预热生成 cache 随包 / 预编译 AOT 产物。**T1 gate 显式验证** |
| 库目录 | 打包后 `config.looks_dir()` 需定位到用户可写目录(非安装目录);内置模板随包只读、用户库可写,二者合并展示 |
| 许可打包义务 | pyvips=libvips(LGPL 动态链接需守义务)、rawpy(本期不引入);全程不嵌 GPL 二进制 |

> **风险已列为 T1 gate**:PyInstaller 打包 numba/pyvips 的平台摩擦是本迭代最大未知,先证再建。

## 6. 状态管理:React state ↔ 引擎参数 ↔ 实时渲染

```
用户拖滑杆
   │ setState(analysis.basic.exposure = v)   (乐观更新: 滑杆/数值立即动)
   ▼
editorStore  ──debounce(~120–200ms)──►  POST /api/preview {path, analysis, factor}
   │                                              │ (sidecar: intensity.scale → render → JPEG)
   │                                              ▼
   └──────────────  中画布 <img> after 源更新  ◄──  JPEG 字节
```

要点:
- **单一状态对象**:`analysis`(= `ANALYSIS_SCHEMA` 结构)是唯一真相;面板控件、收藏、导出、
  渲染请求全读它。参照 RapidRAW/AlcedoStudio"一个扁平参数对象驱动 UI + 渲染 + 导出"。
- **乐观 UI + 防抖渲染**:滑杆数值即时响应(本地 state),预览渲染防抖后发一次,避免每像素抖动打爆 sidecar。
- **串行渲染防叠加**(风险,见 §8):同一时刻只允许一个在途预览请求;新请求就绪时**丢弃/取消**
  过期的在途请求(`AbortController` + 请求序号),防止慢响应覆盖新参数的画面。
- **before/after 对齐**:`factor=0`(或空 analysis)走同一条渲染管线取 before 图,与 after 同尺寸对齐
  (api.py `_render_preview` 已是此设计)。
- **v2.1 seam**:聊天将来产出"参数 delta"叠加到同一个 `analysis` 对象——现在只需保证状态层
  以"整对象替换/分片更新"为接口,不为聊天预实现任何逻辑。
- **版本栈 seam = editorStore 单一 owner(D2)**:`editorStore` 内建一个**版本栈**,**每次应用变更**
  (手动拖滑杆定格 **或** 未来 v2.1 chat delta)都 push 一版当前 `analysis` 快照。**编辑历史的唯一
  拥有者是前端 store**——不是 sidecar、也不是 v2.1 的聊天层。本期 **undo UI 不做**(不加时间线/快捷键),
  但这条 seam 本期就建好:chat 与手动编辑**共用同一个版本栈**,v2.1 只需调 store 的 `applyDelta`(内部
  push),不自建第二个历史(见 v2.1 design.md §对话会话状态与状态同步)。这样「chat 移动的就是右面板
  滑杆、且和手动编辑同一条撤销历史」在架构上从一开始就成立,避免 v2.1 再补大改。

## 7. 设计 token → React 主题

直接移植 [`assets/design-system/claude/tokens.css`](../../../assets/design-system/claude/tokens.css)
为前端 `theme/tokens.css`(CSS 变量原样搬,React 组件用 `var(--*)`)。关键保真:
暖米底(`--bg #f5f4ed`,永不纯白)、赤陶单一强调色(`--accent #c96442`)、暖调中性灰、
标题衬线(Anthropic Serif)、环形描边深度(`--elev-ring`)。三栏面板用 `--surface`/`--surface-warm`
分层,滑杆/曲线沿用现有 `.form`/`.field`/原生 `range` 配方观感(v0.4 已验证零额外前端依赖可覆盖)。

## 8. 从 v0.4 的 carry-forward 清单

| 组件 | 去/留 | 说明 |
|---|---|---|
| Python 引擎(analyzer/render/intensity/lut/xmp/report/lookstore/config/providers/tasks) | **留 100%** | 本期只调用;render 由 v2.0-A 升级 |
| `gui/api.py` 路由设计(12 条) | **留** | 打包进 sidecar,前端 fetch 复用;localhost HTTP 通信基石 |
| `gui/server.py`(stdlib server + 路由分发) | **留(可能小改)** | sidecar 内继续作 HTTP server;端口/令牌注入适配 Tauri |
| `gui/lookstore.py` | **留 + 扩展** | 新增"内置模板只读源"与用户库合并列出 |
| `gui/upload.py` | **视情况** | Tauri 拖拽能拿真实路径 → 可能不再需要 multipart 上传兜底;保留供 browser 回退 |
| 设计 tokens(`assets/design-system/claude/tokens.css`) | **留** | 移植为 React 主题 |
| 安全加固经验(文件名/库名/XSS/路径穿越) | **留(理念)** | React 天然转义;库名/路径校验规则沿用 api.py |
| **pywebview 壳(`gui/app.py`)** | **弃**(除非 T1 NO-GO 回退) | 被 Tauri 取代 |
| **vanilla-JS SPA(`gui/static/js/*`,index.html,app.css)** | **弃** | 被 React 前端取代;v0.4 终审里"纯前端 UI 类"缺陷随之自然消解 |

## 9. 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Tauri+Python 打包平台摩擦** | 阻断分发 | **已定为 T1 gated 任务**;NO-GO 回退 pywebview(§2) |
| 大图内存 | sidecar OOM / 卡顿 | 预览统一缩到 2048px 长边(api.py `_PREVIEW_MAX_EDGE` 已有);原分辨率只在导出走 |
| 实时渲染串行请求叠加 | 慢响应覆盖新画面 / 请求堆积 | 防抖 + 单一在途 + `AbortController` 取消过期(§6);引擎融合后单帧 <50ms 进一步缓解 |
| 复用组件许可不明(尤其 ColorCurve) | 法务/商业化风险 | T2 逐个核 LICENSE;不明则自研兜底;不碰 GPL |
| Rust 工具链构建期成本 | 开发/CI 门槛 | 一次性装 cargo/rustc;用户运行期无感;文档写清环境要求 |
| sidecar 孤儿进程 | 资源泄漏 | Tauri 生命周期钩子回收;T1 门禁显式验证 |
| v2.0-A 未先行 | 手感验收无法达标 | 先对接现有 `render.render`(~1-2s),打包 gate 与 UI 骨架可先行;融合后复测手感 |
| 库目录打包后定位错 | 收藏/内置模板读写失败 | 打包产物里 `looks_dir` 指向用户可写目录;内置模板只读合并;T1/T2 验证 |
