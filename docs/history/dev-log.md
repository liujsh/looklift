# 开发日志(坑、决策、待作者处理)

> 自主开发期间(2026-07-16 起)的问题记录与自主决策,供作者回来后快速过目。
> 早期待作者决策记录见 [legacy-spec-process.md](legacy-spec-process.md)；当前文档规范见 [文档中心](../README.md)。

## 需要你人工处理的事项

- [ ] **删除一个测试遗留文件**:`C:\Users\刘金山\.looklift\looks\MyLook.xmp`。
  v0.3 Task 2 的 TDD 红灯阶段,老测试曾意外写到真实用户目录(根因已修,见下)。
  按你"不碰项目外文件"的指令,安全分类器拦截了我的清理,需要你手动删一下。
- [ ] **准备 v0.3 验收素材**:3-5 组「LR 原片+成片」JPEG,放 `test-assets/`(已 gitignore),
  用于 auto-refine 端到端人工验收(spec Task 8)。
- [ ] **装剪映**:验证导出的 .cube LUT 能加载(程序化格式校验已由单元测试覆盖)。
- [ ] **review 历史 specs**:v0.4-v0.7 的三文档已归档到 `docs/versions/v0.X/`；
  待决问题清单见 [legacy-spec-process.md](legacy-spec-process.md)。
- [ ] **v0.4 人工验收(9 项)**:视觉核对、两种模式的拖拽体验、强度滑杆手感、
  首次配置向导两条路径、WebView2 缺失兜底、长任务体验、U1/U4/U8 全流程复核、
  视觉 token 合规抽查——清单见 [v0.4/tasks.md](../versions/v0.4/tasks.md)
  「人工验收」一节,逐项过一遍后勾选。
- [x] **v2.0-B T1 最后人工门禁**:作者于 2026-07-18 确认手测通过。在一台未安装 Python/Rust 的干净 Windows 上
  双击 `looklift_0.5.0_x64-setup.exe`，确认安装、启动、页面显示「T1 真实引擎往返已通过」，
  关闭后任务管理器无 `looklift-engine.exe`。本机 Defender 自定义扫描已无威胁，
  但干净机 SmartScreen/Defender 仍需此步验收。
- [x] **v2.0-B T11 集中人工验收（M1–M8）**：作者于 2026-07-18 使用最终安装包完成正式验收，M1–M8 全部通过；v2.0-B 与 2.0.0 收口完成。
  拖图→分析→调参→diff→收藏→导出、三栏视觉与手感、真实路径拖拽、连续预览、三份
  内置模板观感和 40MP 稳定性。逐项判据见 [v2.0-B/tasks.md](../versions/v2.0-B/tasks.md)。
- [ ] **v2.1 AI Studio 人工验收**：实现与自动化收口已完成。请按
  [v2.1/tasks.md](../versions/v2.1/tasks.md) 末尾清单，用真实供应商和照片验证单轮建议、
  主曲线、保留/撤销/继续手调、最多两轮精修、重启恢复、元数据关闭与超范围操作说明。

## v2.1 AI Studio 自动化收口（2026-07-18）

- 新增安全代理图、白盒参数操作契约、无状态 `chat_step`、本地 SQLite 正式版本仓库与
  五条会话/对话 API；候选计算和正式提交严格分离。
- React 编辑 Store 增加 pending、undo/redo 和过期请求拒绝；普通消息单轮、显式精修
  最多两轮，保存失败会保留候选供重试。
- 左侧 AI Studio 默认启用且可折叠，展示供应商/代理图/元数据摘要、显影记录、能力限制、
  近似方案和右侧手调步骤；视觉继续复用 v2.0-B 暗房 token。
- 新增离线全链路测试，覆盖消息→候选→真实渲染→确认/撤销→重启恢复，以及超时、鉴权、
  回滚、取消和渲染错误不污染正式版本。版本字段统一为 `2.1.0`。

## v2.0-B T1 打包 gate 实证(2026-07-18)

| 项目 | 结果 |
|---|---|
| 构建链 | Node 22.19.0 / pnpm 11.5.3 / rustc 1.97.1 / VS 2022 Build Tools 17.14.36 |
| 真实引擎 | numba 0.66.0 + pyvips 3.1.1 + libvips 8.18.4，冻结后真实渲染通过 |
| onedir | 约 222 MB；冷 probe 19.7s，cache 命中后 1.63s；可写 cache 落盘 2 文件 |
| Tauri 往返 | release 应用自动拉起 sidecar；带启动 token 的 ping/engine-probe 均通过 |
| 生命周期 | 正常关闭主窗口后主进程与 sidecar 同时退出，无孤儿进程 |
| 安装器 | NSIS `looklift_0.5.0_x64-setup.exe`，65.1 MB；本机 Defender 扫描无威胁 |
| 自动测试 | Python `394 passed, 1 skipped`；TypeScript/Vite build、Vitest `21 passed` 和 Rust `cargo check` 通过 |

门禁判定为 **GO（2026-07-18 作者确认）**：技术链路与干净 Windows
安装/SmartScreen 人工验收均已通过，可以进入 T2。

## v2.0-B T6 参数控件实证(2026-07-18)

- 参数路径、范围、默认值和复位值均从 `/api/param-contract` 获取；前端只保留路径与中文标签映射。
- `ColorCurve` 仓库虽附 MIT LICENSE，但 README 明确声明 JavaScript 基于 GIMP curves code，按项目“不碰 GPL”红线弃用，未引用其代码；曲线采用独立实现的极简单调 Hermite 编辑器。
- 四区颜色分级采用 MIT 许可的 `react-colorful 5.8.0`，已核对安装包 LICENSE 和 ACKNOWLEDGMENTS；业务范围与组件标准坐标通过参数契约双向映射。
- 自动验证：前端 `38 passed`、TypeScript/Vite production build 通过；Python `394 passed, 1 skipped`。

## v2.0-B T7 实时预览与版本栈(2026-07-18)

- 参数在本地即时乐观更新，静止 160ms 后发预览；新变化同时清定时器、abort 在途请求，并以请求序号拒绝旧慢响应。
- 图片切换使用可复用 `cancel()`，取消旧图请求但不销毁调度器；首帧同步使用新图的中性 analysis，避免短暂套用上一张图参数。
- `editorStore` 在连续拖动期间不堆历史，防抖定格时只 push 一份拖动前快照；`applyDelta` 与分片提交共用同一版本 owner，未添加 undo UI。

## v2.0-B T8 内置模板与图库(2026-07-18)

- 首批内置模板采用三个通用原创参数组合：青橙经典、柔和胶片、清透日系；不复制商业预设，也不引用外部实现。
- 内置名称保留且源目录只读；历史用户同名条目优先显示和载入，避免升级后遮蔽已有数据，同时合并列表不产生重复卡片。
- API 列表增加 `source`/`readonly`，前端按内置/用户 tab 展示；卡片载入完整 analysis 到同一 `editorStore`，复用 T7 自动预览。

## v2.0-B T9 统一视觉收口(2026-07-18)

- 视觉模型统一为桌面暗房工作台：暖纸色应用框架、近黑灯箱画布、氧化陶土色高信号操作；全程使用系统离线字体。
- tokens 独立为颜色/字体/间距/阴影单一入口；组件样式不再散落十六进制色值，并补键盘 focus 与 reduced-motion。
- 图库接触印样带是唯一视觉签名；其余区域保持克制。1100px/820px 两级窗口边界已有结构回归，真机截图与比例手感留 M3/M4 集中验收。

## v2.0-B T10 收藏、报告与导出闭环(2026-07-18)

- 当前 `analysis` 与全局强度一起收藏；后端 409 重名中文错误原样展示，成功后只重拉图库并切到“我的风格”。
- 报告通过本地编码 URL 在新窗口打开；预设与 RAW sidecar 均复用既有导出 API，并展示后端返回的实际文件路径。
- 顶栏导出只对刚收藏或载入、且此后未继续修改的风格开放，避免把当前画面与库内导出对象混为一谈。
- 离线流程测试锁定手调、before/after、收藏与导出共用同一份 `analysis` 和 `factor`。

## v2.0-B T11 最终打包与自动验收(2026-07-18)

- 用 Python 3.12.13 / PyInstaller 6.21.0 重建 onedir sidecar；最终 Tauri release 已包含
  T8 的三份内置模板、T9 最终 UI 与 T10 收藏/报告/导出闭环。
- release sidecar 连续两次真实预热均成功：numba 0.66.0、pyvips 3.1.1、libvips 8.18.4；
  随机 localhost API 返回 3 份只读内置模板，临时用户库收藏和 XMP 导出成功，进程已回收。
- Tauri 2.11.5 release + NSIS 构建成功；安装包
  `frontend/src-tauri/target/release/bundle/nsis/looklift_0.5.0_x64-setup.exe`，65,128,699 字节。
- 自动化基线：Python `398 passed, 1 skipped`；前端 Vitest `55 passed`；TypeScript/Vite
  production build 与 Tauri release build 通过。后续作者已在真机完成 M1–M8 集中验收，结果全部通过。

## v2.0-B PR 前审查修正(2026-07-18)

- 修复 WebView 原生 `fetch` 被作为对象方法调用时丢失 `Window` 接收者、导致
  `Illegal invocation` 的启动错误；默认请求函数现在始终经 `globalThis.fetch` 调用。
- 补齐此前只有 API client、没有界面入口的 AI 分析闭环：画布可提交当前图片、轮询任务、
  取消旧图任务，并把完整 `analysis`、`summary`、`steps` 回填面板和预览。
- 修复风格强度一致性：载入图库、AI 新结果和重置均回到 100%；已激活风格同时绑定
  `analysis` 与 `factor`，任一变化都会禁用旧风格导出，避免预览与导出强度不一致。
- PR 前自动验证：Python `398 passed, 1 skipped`；前端 Vitest `62 passed`；TypeScript/Vite
  production build、Rust `cargo test`、本分支改动 Python 文件的 Ruff 检查均通过。
- M2 开始验收时发现聊天 feature flag 关闭后，隐藏的 `ChatPane` 退出 CSS Grid 自动排布，导致
  `CanvasPane` 落入 0px 预留列，界面只剩参数面板且看不到拖图入口。改用显式命名区域
  `chat / canvas / controls`，820px 断点固定为 `canvas / controls`；作者已在 `tauri dev` 中确认
  画布、选择照片和真实拖图恢复。新增布局回归后前端 `63 passed`，最终安装包已重新生成；
  作者随后已用该新安装包正式执行 M1–M8，结果全部通过；v2.1 对话栏不属于 v2.0-B 验收范围。

## v0.4 开发中踩的坑(已解决)

| # | 坑 | 解决 |
|---|---|---|
| 1 | 配置向导用 `cloneNode(true)` 克隆隐藏设置面板表单生成向导表单,`id`/`label[for]` 原样复制,向导(首屏可见)和隐藏设置面板出现重复 id,点向导里的 label 有概率把焦点带去隐藏面板的同名 input | `showWizard` 插入前先 `_dedupeClonedIds(clone)`:遍历克隆节点内所有 `[id]` 元素改写成不冲突的新 id(`settings-` 前缀换 `wizard-`),同步改写引用它们的 `label[for]` |
| 2 | `index.html` 静态资源写成相对路径(如 `vendor/claude/tokens.css`),在 `/` 之外的路径下 404;第一次修复尝试在 `server.py` 加了"未匹配的 GET 都当静态文件"的隐式兜底分支,把显式路由白名单变成了隐式的,被 code review 打回 | 改用 reviewer 建议方案:`server.py` 路由表恢复成显式前缀白名单(`/`、`/static/*`、`/api/*`、`/report/*`);`index.html` 全部改成 `/static/...` 绝对路径;新增测试从 `index.html` 正则提取本地引用,断言全部以 `/static/` 开头且实际起 server 能 200 |
| 3 | CSS 裸 hex 合规扫描两处盲区:(a) 排除范围最初只排除 `tokens.css` 本身,没排除整个 `vendor/claude/**`,而 `components.css` 是从上游 `components.html` 原样摘录、自带 2 处合法 hex,被误判违规;(b) "每行找第一个 `:`" 的逐行启发式漏检换行的多值声明(如 `box-shadow` 续行,hex 出现在没有 `:` 的续行开头) | (a) 排除判断改成整个 `vendor/claude/**` 路径前缀;(b) 改成 block/declaration 级扫描——先剥注释,取每条规则 `{}` 内的声明体,按 `;` 切出单条声明再各自定位 `:` 之后的值部分;两处各配一条反向测试锁定排除范围/扫描能力不被意外收窄 |
| 4 | 上传文件名清洗最初只处理了 `/`、`\` 两个路径分隔符,复现出:`a"b.jpg` 静默截断、`a:b.jpg` 触发 NTFS 备用数据流、`a<b>.jpg`/`a\|b.jpg` 直接抛未捕获 `OSError` → 500,响应体里带着本机用户名在内的完整临时文件路径 | `upload.sanitize_filename` 改成完整 Windows 保留字符集(`< > : " \| ? *`)+ 所有控制字符统一替换、去首尾点/空格、清洗后为空回退固定名;`api.py` 把落盘异常包进 `try/except OSError`,统一转 400 通用中文文案,绝不回显 `str(exc)` |
| 5 | `POST /api/looks` 早期只校验 `analysis` 是不是 dict,任意内容都能落盘;`report.py` 对 `hsl[].color` 用 `_HSL_CN.get(color, color)` 原样回退进 HTML——两者叠加构成存储型 XSS(收藏一份 `hsl[].color` 塞 `<script>` 的 analysis,打开报告页即执行) | 双层修复:`report.py` 补 `escape()`;`api.py` 新增 `_validate_analysis`,只挡"会被当受信任枚举/固定类型使用"的字段(如 `hsl[].color` 必须在 8 色枚举内),不重新实现一遍完整 schema |
| 6(v0.4 收尾 fold-in) | `lookstore.save` 先落 `<name>.json`,再算 `xmp_writer.analysis_to_crs`/`write_preset`;若 `analysis` 混进非数值(如 `basic.exposure="x"`),`analysis_to_crs` 在 json 已落盘之后才报 `ValueError`,留下只有 `.json` 没有 `.xmp` 的孤儿条目——这个名字被 `lookstore.exists()` 永久判定"已占用",带修正值重试同一个名字会被 `POST /api/looks` 的 409 挡死,没有恢复手段 | `save` 把 `analysis_to_crs(analysis)` 提前到任何落盘动作之前调用,非法值在这一步就报错、两个文件都还没写;`json`/`xmp` 落盘顺序不再重要 |

## v0.3 开发中踩的坑(已解决)

| # | 坑 | 解决 |
|---|---|---|
| 1 | 测试红灯阶段污染真实用户目录:`_resolve_template` 改走 `config.looks_dir()` 后,无 cwd looks/ 的测试会落到真实 `~/.looklift`,一度写入了文件 | tests/conftest.py 加 autouse `_isolate_env` 夹具:假 home、假 CONFIG_PATH、清 `LOOKLIFT_*` 环境变量——结构性根治,任何未来测试都不可能再碰真实 home |
| 2 | render 管线 float64 泄漏:`_apply_color_grading` 的 tint 数组把整条管线提升成 float64,违反 LUT 依赖的 float32 契约,且默认 fixture 恰好触发 | tint 构造显式 float32 + `_apply_color_ops` 返回处加 astype 双保险,配 dtype 回归测试 |
| 3 | 计划自带缺陷:`if not s: continue` 使纯 luminance 颜色分级(saturation=0)静默失效 | 拆成独立分支(s 控染色、lum 控明度),配方向回归测试;此为计划骨架的 bug,已作为计划作者授权修复 |
| 4 | Windows `tempfile.mkstemp` 返回打开的 fd,PIL 往该路径写文件会 PermissionError | autorefine 改用 `mkdtemp` + 轮次编号文件 + try/finally 清理 |
| 5 | 审查者误报一例:Task 3 审查(只看本任务 diff)认为四个测试未隔离 CONFIG_PATH,实际 Task 2 的 autouse 夹具已全局隔离 | 控制器仲裁为误报,不改代码;跨任务上下文由控制器把关 |

## 过程备注

- Task 7 实现者的报告 TDD 叙述自相矛盾(声称"实现已存在"又列了 RED/GREEN 过程)。
  审查者独立手推了收敛/最优语义并复跑测试(57 通过),**代码本身确认正确**;
  报告可信度问题已记录,不影响交付质量。
- 每任务均经 spec 合规+代码质量双审查;发现的 Minor 级问题(文案/风格/覆盖盲区)
  统一记在 `.superpowers/sdd/progress.md`,由最终全分支 review 统一裁量。

## 自主决策记录(按你的授权,按推荐执行)

| 决策 | 内容 |
|---|---|
| U23 归属 | 「原片→正向推荐风格」记为 v0.6 候选,RAW 走内嵌 JPEG 预览方案(不引 rawpy) |
| v0.4 GUI 后端 | stdlib ThreadingHTTPServer(窗口/浏览器两模式共用)+ 轮询进度;不引入 FastAPI |
| v0.4 组件 | 纯 tokens.css + components.html 配方即可,Shoelace 暂不需要 |
| 强度滑杆语义 | 偏移类参数按比例缩、曲线向恒等线插值;color_grading 的 hue 与 blending 不缩放 |
| Task 7 计划缺陷 | 以计划作者身份授权修复(见坑 3) |
| 导出需先收藏 | 分析结果区的"导出预设/sidecar"按钮要求先成功 `POST /api/looks` 收藏(`savedLookName` 非空才启用),不提供"未收藏也能导出"的路径——`/api/looks/<name>/export` 是按库里存的 analysis 走的,不是按浏览器内存里的当前状态;这是 design.md「API 路由一览」五条 `/api/looks*` 路由表的忠实实现,也让 U20"滑杆强度带入导出"这条验收标准有一个无歧义的落地点(收藏那一刻的强度)。**但 requirements.md 原始措辞("分析面板能导出预设")读起来像是分析完就能直接导出、不必先收藏,存在歧义,该历史决策记录见 [legacy-spec-process.md](legacy-spec-process.md)** |
| 报告页打开方式统一 | window 模式(WebView2 支持)和 browser 模式都用前端 `window.open('/report/'+name)`,不额外调用 Python 侧 `webview.create_window`——两种模式前端写同一行代码,不用区分模式维护两套打开逻辑 |
