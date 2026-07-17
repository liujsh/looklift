# v0.4 Spec:GUI alpha —— 设计

> 状态:已确认(2026-07-17,作者授权自主推进;人工验收项后置)。
> 需求见同目录 [requirements.md](requirements.md);任务分解见同目录 [tasks.md](tasks.md);
> 当前已实现架构见 [../../design.md](../../design.md)(§8 已记录本迭代的形态/视觉基底决策,
> 本文档是它的展开)。

## 目标回顾

GUI 只是壳:所有业务逻辑留在核心模块(`analyzer`/`render`/`xmp_writer`/`report`/`config`,
均为 v0.1-v0.3 已交付或已定的 API),CLI 与 GUI 共享同一实现,GUI 代码全部放
`looklift/gui/` 包。发布默认 pywebview 独立窗口,`looklift gui --browser` 走本地
web + 系统浏览器兜底。视觉必须用 `assets/design-system/claude/tokens.css`。

## 架构总览

```
                    ┌─────────────────────────────┐
        用户 ──▶    │  looklift gui [--browser]     │   cli.py 新增子命令
                    └───────────────┬───────────────┘
                                    ▼
                    ┌─────────────────────────────┐
                    │     looklift/gui/app.py       │  启动器:起本地 server → 开窗口 or 开浏览器
                    └───────────────┬───────────────┘
                    ┌────────────────┴─────────────────┐
                    ▼                                    ▼
       window 模式(默认发布)                   browser 模式(--browser)
       webview.create_window(url=本地 URL)      webbrowser.open(本地 URL)
       Windows: WebView2(Win11 自带)             系统默认浏览器
       WebView2 缺失 → 捕获异常自动降级 ↴                 │
                    └────────────────┬───────────────────┘
                                     ▼
                    looklift/gui/server.py
                    ThreadingHTTPServer,绑定 127.0.0.1:<OS 随机分配端口>
                    路由:静态资源(static/)/ /api/* JSON / /report/<name>
                                     ▼
                    looklift/gui/api.py   (路由 handler,只做入参校验 + 调核心模块 + 序列化)
                    looklift/gui/tasks.py (长任务:后台线程 + 内存态 task 表,供轮询)
        ┌──────────────┬──────────────┬────────────────┬────────────────┬────────────────┐
        ▼               ▼              ▼                 ▼                ▼                ▼
  analyzer.py      render.py     intensity.py       xmp_writer.py      report.py        config.py
  (v0.3 已定)      (v0.3 已定)    (v0.4 新增)         (已有)             (已有)           (已有,补写)
  analyze/refine   render/score  scale_analysis      analysis_to_crs    render_report    load_config/
                                                      write_preset/                      save_config(新)/
                                                      write_sidecar                      looks_dir
```

关键点:`api.py` 不写业务逻辑,只是"HTTP 参数 → 核心函数调用 → JSON 响应"的粘合层;
真正做事的仍是已有/已定的核心模块,保证 CLI 与 GUI 长期同构。

## 目录/文件结构规划

```
looklift/
  gui/
    __init__.py
    app.py            # looklift gui 入口:解析 --browser/--port,起 server,选窗口/浏览器分支;
                       # pywebview 不可用(未装/WebView2 缺失)时捕获异常自动降级为 browser 模式
    server.py          # ThreadingHTTPServer + 路由分发(静态资源 / /api/* / /report/<name>)
    api.py             # 业务路由 handler,见下文"API 路由一览"
    tasks.py           # 长任务表:{task_id: {status, message, result, error}},后台线程跑耗时函数
    static/
      index.html       # SPA 壳:导航 + 分析/风格库/设置三个面板容器(报告页不在这里)
      css/app.css       # 页面样式,只用 vendor/claude/tokens.css 里的变量,不写裸 hex
      js/app.js          # 面板切换、fetch 调用、轮询、拖拽处理(区分 window/browser 取路径方式)、
                          # 强度滑杆联动 before/after 对比条
      vendor/
        claude/
          tokens.css     # 从 assets/design-system/claude/tokens.css 同步而来(见"依赖与打包")
          components.css # 从 components.html 摘录整理的可复用配方(按钮/卡片/表单/徽标)
looklift/
  intensity.py         # 新增:scale_analysis(analysis, factor) —— 强度缩放纯函数,GUI 和未来 CLI 都能调用
  config.py             # 补一个 save_config(data: dict) 供配置向导写 ~/.looklift/config.toml(load_config 已有)
```

## 设计决策

### 决策 1:GUI 后端形态

| 方案 | 说明 | 优劣 |
|---|---|---|
| A. pywebview js_api 直连 | `create_window(..., js_api=Api())`,JS 通过 `pywebview.api.xxx()` 直接调 Python 方法,不起 HTTP server | window 模式最省事;但 `--browser` 模式**无论如何**需要一个真正的 HTTP server(浏览器标签页没有 js_api 桥),等于要维护两套后端实现,行为容易漂移 |
| B. 本地 HTTP server(stdlib `http.server`)+ 两种模式统一指向 localhost | window 模式的 `webview.create_window(url=...)` 和 browser 模式的 `webbrowser.open(...)` 指向同一个本地 server,前端只用标准 `fetch`,不区分模式 | 单一实现,零新增第三方依赖(`http.server`/`socketserver` 是标准库);长任务轮询天然是标准 HTTP 语义;代价是要自己写最小路由分发(参数校验、404 等) |
| C. FastAPI/uvicorn 本地 server | 路由/校验/自动文档更省事 | 新增 4 个依赖(fastapi/uvicorn/starlette/pydantic),与项目现有"仅 anthropic + Pillow"的轻依赖取向冲突;对本项目路由数量(个位数)是过度设计 |

**推荐:B。** 理由:`--browser` 模式硬性要求 HTTP server,方案 A 无法避免维护两套实现;
方案 C 的重量级依赖对当前路由规模不成比例。stdlib 的 `http.server.ThreadingHTTPServer`
配合手写的十来条路由完全够用,且窗口模式下 pywebview 本身也支持"entrypoint 是 URL"
的用法,天然兼容这套方案。

实现要点:

- 绑定 `127.0.0.1` + 端口号传 `0`(交给 OS 分配空闲端口),避免重复启动/端口占用冲突,
  也避免监听所有网卡带来的本机其他进程可访问风险
- `pywebview` 只作为 **可选依赖**(`pip install looklift[gui]` 的 extra),CLI-only 用户
  (P3)不需要装它;`--browser` 模式完全不依赖 pywebview,只用标准库 `webbrowser`

### 决策 2:长任务进度反馈

`analyze` 单次 30-120 秒,`auto-refine`(核心 API 已就绪,但 v0.4 暂不建 UI)更久。

| 方案 | 说明 | 优劣 |
|---|---|---|
| 轮询 | `POST /api/analyze` 立即返回 `task_id`,任务在后台线程跑;前端每 ~800ms `GET /api/tasks/<id>` 查状态 | 实现最简单,天然兼容 stdlib `http.server`(每次都是短连接请求-响应);对分钟级任务而言亚秒级延迟无感 |
| SSE(Server-Sent Events) | server 保持连接、持续 push 进度 | 需要 chunked/流式响应,`http.server` 手写起来容易踩坑(缓冲、连接不主动关闭导致线程占用);WebView2 对长连接 SSE 也有零星兼容性问题报告 |
| WebSocket | 双向实时 | 本场景不需要双向;stdlib 没有内建 WebSocket,要么手撸协议要么加 `websockets` 依赖,收益(更平滑的进度条)配不上成本 |

**推荐:轮询。** 理由:任务时长是分钟级,不是需要毫秒级反馈的场景;轮询在两种运行模式
(window/browser)下代码完全一致,不需要额外依赖,出错时也最容易调试(每次都是一次
普通 HTTP 请求)。

实现要点:

- `tasks.py` 维护内存态 `{task_id: {status: "running"|"done"|"error", message, result, error}}`
- 提交分析请求的 handler 只负责起线程 + 生成 `task_id` + 立即返回,真正的 `analyzer.analyze(...)`
  调用在后台线程里跑,不阻塞 HTTP server 的请求处理线程
- server 用 `ThreadingHTTPServer`(而非单线程 `HTTPServer`):静态资源加载、轮询请求、
  配置读写等短请求需要在长任务运行期间也能被及时处理

### 决策 3:页面结构

| 方案 | 说明 | 优劣 |
|---|---|---|
| A. 纯 SPA | 一个 `index.html`,JS 切换全部面板(含报告页) | 应用感强、状态好管理;但报告页目前是`report.render_report` 产出的**自包含单文件**(专门设计成可直接分享的独立 HTML),硬塞进 SPA 组件要么破坏"自包含可分享"的定位,要么重复实现一遍渲染逻辑 |
| B. 纯多页 | 分析/风格库/报告/设置各是独立整页,服务端每次整页渲染 | 简单直接;但"当前分析结果""选中的风格""滑杆强度"这些跨面板共享的状态要在页面间传递(query string / 服务端 session),徒增复杂度;pywebview 窗口里多次整页刷新观感像浏览网页而不是桌面应用 |
| C. 混合:SPA 壳 + 报告页独立 | 分析/风格库/设置三个面板在同一 `index.html` shell 里用 JS 切换(DOM 常驻、状态共享);报告页直接是 `/report/<name>` 返回的独立 HTML,通过新窗口(window 模式:`webview.create_window`)/新标签(browser 模式:`window.open`)打开 | 兼顾两者:强关联状态(分析结果、选中风格、强度滑杆)留在 SPA 内存里;报告页保持它本来的"自包含可分享"定位,不用改造 `report.py` |

**推荐:C。** 报告本来就要能"存成文件发朋友/发论坛",不应该被拆碎成 SPA 里的一个
组件再拼回去;分析/库/设置三个面板则确实需要共享状态,适合单页应用式管理。

### 决策 4:拖拽文件的实现路径

两种模式下"往同一个 drop zone 拖一张图"的视觉体验一致,但底层拿文件路径的方式不同:

**window 模式(pywebview)**

- pywebview 的 DOM 事件桥支持监听原生拖放:`window.dom.document.events.drop += on_drop`,
  Python 侧收到的 `event['dataTransfer']['files'][i]` 会额外带一个 `pywebviewFullPath`
  字段——**这是 pywebview 专门为拖放场景加的扩展,只在 Python 侧可见**(标准浏览器
  JS 侧的 `File` 对象出于安全限制没有真实文件系统路径)
- 流程:`app.py` 建窗口后注册这个 drop 监听 → 拿到 `pywebviewFullPath` 绝对路径 →
  用 `window.evaluate_js(...)` 把路径回推给前端,触发和"点击选择文件"一样的 JS 流程
- 优点:零拷贝,直接把原图路径交给 `analyzer.analyze`,不用复制大文件

**browser 模式(`--browser`)**

- 标准浏览器标签页里,`ondrop`/`<input type="file">` 拿到的只是 `File` Blob,没有
  文件系统路径(这是浏览器的安全设计,不是 pywebview 的限制,拿不到绕不过去)
- 流程:JS 用 `fetch` 把文件内容以 `multipart/form-data` `POST /api/upload`,本地
  HTTP server 落一份临时文件,返回临时路径给前端,后续分析请求带这个临时路径
- 代价:大文件要经过一次本地回环 HTTP 上传,比 window 模式慢——这是可接受的
  trade-off,因为 `--browser` 定位本来就是"开发调试 / WebView2 缺失兜底",不追求
  与默认发布形态同等性能

### 决策 5:是否引入 Shoelace

`components.manifest.json` 盘点过 `assets/design-system/claude/components.html` 现有配方:
按钮(`.btn`/`.btn-primary`/`.btn-secondary`)、卡片(`.card`)、表单(`.form`/`.field`/
`.field-help`)、徽标(`.badge`)、排版/布局工具类——**没有滑杆、没有对话框**。

逐项核对本迭代要用到的复杂控件:

- **强度滑杆**:原生 `<input type="range">` + CSS 可以满足——轨道/滑块用
  `--accent`/`--radius-pill`/`--border` 等 token 上色,`accent-color: var(--accent)`
  覆盖大部分浏览器/WebView2 默认外观,不需要 Shoelace 的 `sl-range`
- **首次配置向导**:内容是"选 provider + 填 key"的表单,直接复用 `.form`/`.field`
  配方做成 SPA 里的一个全屏面板即可,不需要模态对话框
- **before/after 对比条**:两张 `<img>` 叠放 + `clip-path` 由一个 `<input type="range">`
  驱动,同样是原生控件

**结论:v0.4 不 vendor Shoelace**,零新增前端依赖,完全落在现有配方 + 原生表单控件
能覆盖的范围内。如果后续迭代真的需要模态对话框(比如风格删除二次确认)或更复杂的
双滑块控件,再按 [../../design.md](../../design.md) 里定的"配方不够才引入 Shoelace,
本地 vendored、禁止 CDN"的原则单独决策。

## 强度缩放语义(`intensity.scale_analysis`)

U20 的"预设只套 70% 强度"落地为一个纯函数:`scale_analysis(analysis: dict, factor: float) -> dict`,
`factor` 定义域 `[0.0, 1.0]`(对应滑杆 0%-100%),返回新 dict(不修改入参)。核心问题是
"analysis 里哪些字段是可以线性缩放的偏移量,哪些不是"——逐字段过一遍
`analyzer.ANALYSIS_SCHEMA`:

| 分区 | 字段 | 缩放规则 | 理由 |
|---|---|---|---|
| `basic`(13 项) | `temperature_shift`/`tint_shift`/`exposure`/`contrast`/`highlights`/`shadows`/`whites`/`blacks`/`texture`/`clarity`/`dehaze`/`vibrance`/`saturation` | 乘 `factor` | 全部是"相对中性基准的偏移量",0 = 无调整,线性缩放即"调整力度打折" |
| `hsl`(8 通道) | `hue`/`saturation`/`luminance` | 乘 `factor` | schema 里这三项都是 -100~100 的**偏移量**(不是绝对色相角),不是色轮位置 |
| `color_grading.{shadows,midtones,highlights,global_}` | `saturation`、`luminance` | 乘 `factor` | 染色力度/明暗偏移,0 = 该区不染色 |
| `color_grading.{...}` | `hue` | **不缩放** | 这是色轮上的绝对角度(0-360),缩放角度本身没有物理意义;`saturation` 降到 0 时颜色本来就不可见,hue 是否缩放不影响观感 |
| `color_grading` | `balance` | 乘 `factor` | 阴影/高光染色力度的对称偏移量,0 = 对称 |
| `color_grading` | `blending` | **不缩放** | 默认 50,是中间调过渡范围的技术参数,不代表"强度";缩放它会改变染色分布形状而不是力度,语义上不对 |
| `effects` | `vignette_amount`、`grain_amount` | 乘 `factor` | 0 = 无效果的偏移量 |
| `tone_curve` | 每个控制点的 `output`(`input` 不变) | `output' = input + factor * (output - input)` | 向恒等线(`output == input`,即"不调整")插值:`factor=0` 时曲线退化成对角线,`factor=1` 时等于原曲线;这与"曲线是一种相对于恒等映射的调整"的语义一致 |
| `summary`/`steps` | — | 透传不变 | 纯文本讲解,与数值强度无关 |

`factor=1.0` 时输出应与不缩放的原始 `analysis` 在数值上完全一致(浮点误差内),
`factor=0.0` 时输出应等价于"完全不调整"(所有偏移量归零、曲线是对角线)。该函数
不做任何 I/O,可以直接用固定 dict 写单元测试(边界值 + 单调性),符合项目"测试不
触网、不调 AI"的原则。

GUI 侧用法:滑杆变化 → `scale_analysis(analysis, factor)` → 同时喂给
`render.render`(刷新 before/after 预览)和最终导出时的 `xmp_writer.analysis_to_crs`
(确保导出的预设/sidecar 是缩放后的参数,不是永远 100% 强度)。

## API 路由一览

| 方法 | 路径 | 作用 | 对应核心 API |
|---|---|---|---|
| GET | `/` | SPA 首页 | 静态文件 |
| GET | `/api/config` | 读取当前配置状态(provider 是否已配好) | `config.load_config` |
| POST | `/api/config` | 写入首次配置向导结果 | `config.save_config`(新增) |
| POST | `/api/upload` | (仅 browser 模式)接收拖拽/选择的图片字节,落临时文件 | 无(纯 IO) |
| POST | `/api/analyze` | 提交分析任务(图片路径 + 可选 original/hint/backend),立即返回 `task_id` | `analyzer.analyze`(后台线程) |
| GET | `/api/tasks/<id>` | 查询任务状态/结果 | `tasks.py` 内存态 |
| POST | `/api/preview` | 按当前 `factor` 渲染 before/after 预览图 | `intensity.scale_analysis` + `render.render` |
| POST | `/api/looks` | 收藏当前分析结果到风格库 | `xmp_writer.*` + `config.looks_dir` |
| GET | `/api/looks` | 列出风格库 | 遍历 `config.looks_dir()` |
| GET | `/api/looks/<name>` | 读取某风格的完整 analysis | 读 `looks_dir` 下的 json |
| POST | `/api/looks/<name>/export` | 按当前 `factor` 导出预设/sidecar | `intensity.scale_analysis` + `xmp_writer.write_preset`/`write_sidecar` |
| GET | `/report/<name>` | 独立报告页(新窗口/标签打开) | `report.render_report` |

## 依赖与打包

- `pyproject.toml` 新增 `[project.optional-dependencies] gui = ["pywebview>=5,<6"]`——
  CLI-only 用户不需要装它;`looklift gui`(非 `--browser`)在 `import webview` 失败时
  给出清晰的 `pip install looklift[gui]` 提示并自动降级为 `--browser` 模式,而不是崩溃
- pywebview 在 Windows 走内置的 EdgeChromium(WebView2)后端,`pip install pywebview`
  即可,不需要额外声明 `pythonnet`(那是 WinForms 后端才需要,本项目不用)
- `looklift/gui/static/vendor/claude/` 下的 `tokens.css`/`components.css` 是从
  `assets/design-system/claude/` 复制而来的**构建期产物**,不是运行期动态读取——
  因为 `assets/` 在仓库根目录,`pip install` 打包后不会自动带上;需要在
  `pyproject.toml` 的 `[tool.setuptools.package-data]` 里把 `gui/static/**` 声明为包数据,
  确保 wheel 里真的有这些文件(否则装完之后打开是白屏)

## 风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| WebView2 Runtime 缺失或版本过旧 | Win11 理论自带,但精简版系统镜像/企业镜像可能没装,或版本太旧不兼容 pywebview 要求的最低版本 | `app.py` 捕获 pywebview 启动异常,打印中文提示并自动降级为 `--browser` 模式,而不是直接崩溃退出 |
| 长任务卡 UI | `analyze` 30-120s、auto-refine 更久,如果同步阻塞会让 pywebview 窗口"未响应" | 分析任务在独立后台线程跑,HTTP 请求处理线程立即返回 `task_id`;前端轮询展示进度文案,不阻塞事件循环(见决策 2) |
| 大图内存占用 | 现代相机 JPEG 常见 4000 万像素起,`render.render` 生成 before/after 预览、加上分析用的缩略图,同时在内存里可能有好几份大图数组,导致卡顿甚至 OOM | GUI 侧统一把预览用途的图先缩到一个上限(如长边 2048px)再喂给 `render.render`,不用原始分辨率做"仅用于观感"的预览;导出预设/sidecar 时不受此限制(那条路径不经过 GUI 的预览缩放,直接用原图参数) |
| 本地端口冲突/多开 | 用户重复启动多个 `looklift gui` 实例,固定端口会冲突 | 端口传 `0` 交给 OS 分配空闲端口,不写死端口号 |
| 本地 HTTP server 暴露面 | 监听 127.0.0.1 本身风险有限(同机用户模型),但如果不小心绑定到 `0.0.0.0` 或局域网可达,同网络其他设备可能访问到分析接口 | 显式绑定 `127.0.0.1`,不监听所有网卡;不做用户鉴权(同机场景下过度设计),但把"只信任本机"写进代码注释和本文档,避免后续误改 |
| 首次配置向导卡死 | 如果向导强制要求填完 provider 才能进主界面,而用户当下只想看看界面/库面板,会被卡住 | 向导允许"稍后配置"跳过,只有触发"分析"时才真正需要 provider;库面板/报告页浏览不依赖 provider 是否配置 |
| window/browser 两种模式行为不一致被漏测 | 决策 4 里两种模式拿文件路径的机制完全不同,只测一种模式很容易让另一种模式的拖拽路径在发布前才发现是坏的 | 人工验收(见 [tasks.md](tasks.md) 最后一节)明确要求两种模式都单独走一遍拖拽流程 |
