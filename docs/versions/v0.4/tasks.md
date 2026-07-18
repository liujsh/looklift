# v0.4 Spec:GUI alpha —— 任务清单

> 状态:已确认(2026-07-17,作者授权自主推进;人工验收项后置)。
> 需求见同目录 [requirements.md](requirements.md);技术方案见同目录 [design.md](design.md)。
> 任务按依赖顺序排列,每条只写一句验收;需要真人操作的验证集中放在最后
> 「人工验收」一节,不混在自动化任务里。

## T1 依赖与打包骨架

`pyproject.toml` 新增 `[project.optional-dependencies] gui = ["pywebview>=5,<6"]` 和
`[tool.setuptools.package-data]` 声明 `gui/static/**`;创建 `looklift/gui/` 包骨架
(`__init__.py`/`app.py`/`server.py`/`api.py`/`tasks.py`/`static/index.html` 占位);
把 `assets/design-system/claude/tokens.css` 复制到
`looklift/gui/static/vendor/claude/tokens.css`,从 `components.html` 摘录出
`components.css`(按钮/卡片/表单/徽标配方)。

**验收**:`pip install -e ".[gui]"` 成功;`python -c "import looklift.gui"` 不报错。

## T2 `config.save_config`

`config.py` 新增 `save_config(data: dict) -> None`,手写简单 TOML 序列化写入
`~/.looklift/config.toml`(字段都是纯字符串/简单值,不引入 `tomli-w` 等新依赖)。

**验收**:pytest 覆盖往返(`save_config` 写入后 `load_config` 能读回同样的值)。

## T3 强度缩放 `intensity.scale_analysis`

新模块 `looklift/intensity.py`,按 [design.md](design.md)「强度缩放语义」一节的字段表实现
`scale_analysis(analysis: dict, factor: float) -> dict`(纯函数,不改入参)。

**验收**:pytest 覆盖 `factor=0`(所有偏移量归零、曲线退化为对角线)、`factor=1`
(与原值完全一致)、`0<factor<1`(单调性:数值介于 0 和原值之间,`hue`/`blending`
保持不变)。

## T4 本地 HTTP server 骨架

`looklift/gui/server.py`:`ThreadingHTTPServer` 绑定 `127.0.0.1:0`,路由分发到
`api.py` 的 handler(静态资源 `/`、`/api/*` JSON、`/report/<name>`);统一 404/500
JSON 错误格式。

**验收**:pytest 起 server 后 `GET /` 返回 200 且是 `index.html` 内容,`GET /nonexistent`
返回 404。

## T5 长任务框架

`looklift/gui/tasks.py`:`submit(fn, *args) -> task_id` 在后台线程跑 `fn`,内存态
`{task_id: {status, message, result, error}}`;`server.py` 接入
`GET /api/tasks/<id>`。

**验收**:pytest 用一个 sleep 一下再返回值的 mock 函数验证 `running → done` 状态迁移,
且最终能读到 `result`;mock 一个抛异常的函数验证状态变成 `error` 且带错误信息。

## T6 CLI 入口 `looklift gui`

`cli.py` 新增 `gui` 子命令,参数 `--browser`(走浏览器模式)、`--port`(默认 `0`,
主要供测试/调试指定固定端口);调用 `looklift.gui.app.main(browser=..., port=...)`。

**验收**:`looklift gui --help` 能看到新子命令和两个参数的说明。

## T7 pywebview 窗口模式

`looklift/gui/app.py` 窗口分支:起 T4 的 server → `webview.create_window(url=本地 URL)`
→ `webview.start()`;`import webview` 失败或启动异常时捕获、打印中文提示、自动走
T8 的 browser 分支(而不是崩溃退出)。

**验收**:Windows 下 `looklift gui` 弹出原生窗口且首页能加载;用 monkeypatch 模拟
`import webview` 失败,验证会走到 browser 分支(不需要真的在无 WebView2 环境测试,
那部分留给人工验收)。

## T8 browser 模式

`app.py` 的 `--browser` 分支:起 T4 的 server → `webbrowser.open(本地 URL)` →
阻塞运行直到 Ctrl-C / 进程退出。

**验收**:pytest 验证 `--browser` 路径下 `webbrowser.open` 被调用且参数是本地
server 的 URL(mock 掉 `webbrowser.open`,不依赖真实浏览器)。

## T9 拖拽文件路径两种实现

按 [design.md](design.md)「决策 4」实现:window 模式在 `app.py` 里注册
`window.dom.document.events.drop`,取 `pywebviewFullPath` 后用
`window.evaluate_js` 回推给前端;browser 模式实现 `POST /api/upload`(接收
`multipart/form-data`,落临时文件,返回临时路径)。

**验收**:`POST /api/upload` 有 pytest(mock 一次 multipart 上传,确认临时文件落地、
返回路径可读);window 模式的 drop 监听走人工验收(pywebview 事件桥依赖真实窗口,
无法在无头环境单测)。

## T10 首次配置向导

前端页面复用 `.form`/`.field` 配方做成 SPA 里的全屏面板;`GET/POST /api/config`
接入 T2 的 `config.load_config`/`save_config`;支持"稍后配置"跳过,不阻塞库面板/
报告页浏览。

**验收**:pytest 覆盖 `GET /api/config` 在未配置 provider 时返回"未配置"状态,
`POST` 后能通过 `config.load_config` 读到写入的值。

## T11 分析面板(U1)

前端:选图(拖拽走 T9,或点选走 `<input type=file>`)→ `POST /api/analyze` 提交任务
(带 T5 的 `task_id`)→ 轮询 `GET /api/tasks/<id>` → 网页排版展示
`summary`/`steps`/`basic` 参数(不是终端文本转发)。

**验收**:U1 端到端——不碰命令行,从拖入一张照片到看到 AI 分析结果(风格概述+
后期步骤+基本面板参数)。

## T12 强度滑杆 + before/after 对比条(U20)

前端滑杆(原生 `<input type=range>`,token 上色)变化时调用
`POST /api/preview`(内部走 T3 的 `intensity.scale_analysis` + `render.render`),
两张图叠放 + `clip-path` 展示对比。

**验收**:U20 端到端——滑杆从 0% 拖到 100%,对比条随之平滑变化;0% 时预览应与
原图基本一致(肉眼);滑杆调整后的强度会带入后续导出(T13)。

## T13 收藏 + 导出(U4 一半)

`POST /api/looks`(收藏当前分析结果到风格库,调 `xmp_writer.write_preset`/
`config.looks_dir`)、`POST /api/looks/<name>/export`(按当前 factor 导出预设/
sidecar,先过 T3 的 `scale_analysis` 再过 `xmp_writer`)。

**验收**:分析结果能存进 `looks_dir`;导出的预设文件内容与 CLI `apply` 命令用
同一份(缩放后的)参数生成的文件等价(复用 `test_xmp_writer.py` 的断言思路)。

## T14 风格库面板 + 报告页(U4 另一半 + U8)

`GET /api/looks`(列表)、`GET /api/looks/<name>`(详情)接入前端库面板;
`GET /report/<name>` 直接返回 `report.render_report` 的 HTML,前端"打开报告"按钮
在 window 模式开新窗口 / browser 模式开新标签。

**验收**:U4 端到端——风格库面板能看到 T13 收藏的风格并展示概述;U8 端到端——
从库里打开报告页,内容与 `looklift report` 命令生成的 HTML 在同一份 analysis
输入下等价。

## T15 视觉 token 合规扫描

pytest 扫描 `looklift/gui/static/**/*.css`(排除 `vendor/claude/tokens.css` 本身),
用正则 `#[0-9a-fA-F]{3,6}` 检查不应出现 token 块之外的裸 hex。

**验收**:扫描测试通过;之后任何人加/改样式,裸 hex 会被这条测试挡住。

## T16 文档收尾

README 加"GUI 使用"小节(启动命令、`--browser` 用法、首次配置向导说明);
`docs/tasks.md` 补 v0.4 历史记录;版本号提到 `0.4.0`;`docs/design.md` 按 v0.3 的
惯例,在实现完成后回填本迭代的架构要点(§8 从"未来迭代设计"移到"已实现");
CI 绿。

**收口验收**:README/`docs/tasks.md` 更新，版本收口时运行一次 `pytest -q` 并全绿。

---

## 人工验收

以下项目需要真人在真实环境里操作确认,不追加到上面的自动化任务里。

- [ ] **视觉核对**:pywebview 窗口下界面配色/字体与 `assets/design-system/claude`
      预期一致(暖色调色板、衬线标题字体等),肉眼比对,不止靠 T15 的自动扫描
- [ ] **拖拽体验(window 模式)**:从文件管理器拖一张 jpg 到分析面板,确认能直接
      触发分析、没有先复制文件的明显等待(应该接近瞬间进入"分析中"状态)
- [ ] **拖拽体验(browser 模式)**:同样拖拽,确认上传+触发分析成功(允许有肉眼
      可见的上传等待,这是决策 4 里认可的 trade-off)
- [ ] **强度滑杆手感**:拖动滑杆从 0% 到 100%,对比条应平滑变化;0% 时预览应与
      原图基本一致,100% 时应与不缩放的分析结果输出图一致
- [ ] **首次启动配置向导**:临时改名/删除 `~/.looklift/config.toml` 模拟全新环境,
      启动 `looklift gui`,确认弹出向导;分别测试"填写完成"和"稍后配置跳过"两条
      路径都能正常进入主界面
- [ ] **WebView2 缺失兜底**:在没有 WebView2 Runtime 的机器或虚拟机上启动
      `looklift gui`,确认能自动降级到浏览器模式并有清晰中文提示,而不是崩溃或
      无提示卡死
- [ ] **长任务体验**:分析一张较大的照片,观察窗口在等待期间是否仍可拖动/缩放
      (不是系统提示"未响应"),等待完成后能看到结果
- [ ] **U1/U4/U8 全流程复核**:从头到尾不碰命令行,完整走一遍"拖拽照片 → 看到
      分析结果 → 调整强度滑杆 → 收藏进风格库 → 打开报告页 → 导出预设/sidecar",
      对照 [requirements.md](requirements.md) 的验收标准逐条确认
- [ ] **视觉 token 合规抽查**:除 T15 的自动化扫描外,人工再翻一遍关键页面的
      DevTools 计算样式,确认没有绕过 token 直接写内联裸 hex 的情况(比如从别处
      粘贴的三方 HTML 片段漏改)
