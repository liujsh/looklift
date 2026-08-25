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
- [x] **v2.1 AI Studio 人工验收**：作者于 2026-07-20 完成验收，最后一个 PR 为 #6，
  已合入 `main`。
- [ ] **v2.2 平台外壳人工验收**：实现与自动化收口已完成。请按
  [v2.2/tasks.md](../versions/v2.2/tasks.md) 末尾清单，用真实照片验证多 Studio 隔离、后台 AI
  归属、关闭门禁、重启恢复与缺失源文件。当前冻结 sidecar 烟测通过，真实 Tauri 首页已加载，
  原生文件选择器可打开；照片选择后的完整功能链路尚未代替作者勾选。
- [ ] **v2.4 模板与教学人工验收**：用真实照片核对三份官方模板观感与教学文案；从模板页
  直接套用后确认画布、参数面板和会话版本同步；在 AI 输入框附加模板，确认 provider 返回的是
  针对当前照片的自适应参数而非机械覆盖。自动化不调用真实 provider。
- [ ] **v2.6-A/B API Agent 人工 Spike**：用真实 API 和真实照片验证首候选观感、依据 JPEG
  反馈继续精修和正确停止；确认代理图无 EXIF、取消在 1 秒内终止且候选不进入正式版本。当前只完成
  离线 FunctionModel/Mock HTTP 与冻结自动化，不接 UI、SQLite、本地 CLI 或正式保存入口。

## v2.6-A/B Domain Pack 与最小 API 候选闭环（2026-08-20）

- Pydantic AI 可行性门通过：三类 Provider 离线序列化、JPEG Tool Result 回灌、类型化流、取消与
  Windows PyInstaller 探针均通过；相对已有 NumPy/Pillow sidecar 增量 21.74 MiB，低于 60 MiB 门限。
- Domain Pack 编译器固定来源优先级、预算降级、Hash 和快照恢复；内置修图领域契约与自然人像 Skill
  已版本化，但尚未通过真实模型消融，因此不把 Skill 效果写成已验证结论。
- 受控 Runtime 串通白盒 Patch → 唯一引擎 → JPEG/差异/指标反馈 → 可选再修改 → 三类结构化终态。
  候选只存在内存，不会保存、导出或修改正式版本；Run/Attempt/Lease、预算、取消晚到和基线冲突有离线测试。
- API Adapter 归一八类单调事件，重复 Attempt 被拒绝；Provider 错误转稳定文案且不自动跨供应商切换。
  自动化完成不等于 v2.6 发布，CLI、UI、恢复、三领域 Skill/Eval 与真实照片验收仍在 C–E 阶段。
- 收口证据：Python 全量 `595 passed, 1 skipped`；本批 Python 文件 Ruff 通过。更新后的真实 sidecar onedir
  冻结构建成功，冷/热预热、随机 localhost API、3 份内置模板、临时用户预设导出和进程回收 smoke 全部通过。
  全仓 Ruff 仍有 25 个既有问题，位于本批未修改的设备导入、GUI API 和图库测试文件，未借本批越界清理。

## v2.6-C CLI 基础与 Pi Adapter（2026-08-20）

- 实测本机 Pi 0.84.1：支持 JSON/RPC 事件、`--no-builtin-tools`、单扩展加载、无 Session 和资源发现禁用；同时其
  随包文档明确不内置 MCP。规格据此把传输收敛为 Scoped Tool Gateway：有原生 MCP 就用 MCP，Pi 使用随应用只读
  扩展桥；两者仍共享 Token、Pydantic Schema 和 Python Runtime，不额外复制一套候选逻辑。
- Fake CLI/Pi 自动化覆盖随机 Workspace、敏感环境清理、双工具白名单、Token 过期/撤销、真实 localhost HTTP、JPEG
  图片结果、原生事件归一、协议错误脱敏、取消和强制进程回收。Pi 启动封套还关闭遥测与版本检查，避免模型服务之外
  的隐式数据接收方。
- 真实 Pi 0.84.1 + OpenRouter Gemini 2.5 Flash Lite 已确认初始安全代理图进入模型上下文。一次运行调用
  `render_candidate`，取得 JPEG、亮度与裁切指标后以 `candidate_ready` 停止；实际 Patch 仅把
  `basic.shadows: 0 → 0.08`。另一次运行在 `run_started` 后取消，0.028 秒退出、无候选、无正式副作用。
- 真实门暴露并修复两项只在 Windows/图片输入出现的问题：npm `.cmd` 只回收外壳，现支持直接 `node + cli.js` 命令
  前缀；RPC 会回显 base64 图片事件，stdout 从默认 64 KiB 改为 8 MiB 硬上限。第一次失败遗留的精确临时 Attempt 目录
  已删除，后续 Workspace 均自动回收。
- Pi 达到 v2.6-C 正式 Adapter 支持标准，但真实 API、单张照片主观观感、Skill 消融、UI 与重启恢复仍未完成；当前仍
  不能写“v2.6 已发布”或“完整双 Harness 产品落地”。
- 收口证据：Python 全量 `620 passed, 1 skipped`，本批 Ruff 与 Pi Extension Node 语法检查通过；更新后的 Windows
  sidecar 冻结构建成功，随包包含只读 `pi-looklift-tools.js`，冷/热预热和既有发布 smoke 全部通过；本机 Pi 0.84.1
  的 `--offline --help` 也能加载该扩展封套且不调用模型。

## v2.6-D 领域 Skill、Template 与离线评测骨架（2026-08-25）

- 新增商品一致性与高光/曝光恢复内置 Skill，与自然人像共同通过 frontmatter、固定章节、引擎能力和内容 Hash 校验；
  两者复用已登记的曝光/色彩 Reference，不授予工具权限。
- 新增六份只读官方 Agent Template，覆盖三类 Skill 的匹配场景、禁用条件和风险说明；参数全部复用统一白盒
  `ScalarOperation` 契约，不能携带脚本、路径或权限。
- 新增 20 个确定性离线 Eval Case（12 个效果、8 个工程/安全）及 Fake Harness Runner，覆盖终态、候选数量、工具调用、
  正式副作用和敏感数据泄漏断言；Skill/Template/反馈消融配置仅作为可复用执行维度。
- 当前未纳入真实照片、真实 Provider 或人工盲测，因此不把离线通过写成视觉增益或 v2.6 发布证据。
- 收口证据：新增与既有 Domain Skill/Agent 契约测试共 `19 passed`；完整 Agent 定向测试和全量测试待收口验证。

## v2.4 模板与教学自动化收口（2026-07-23）

- 新增模板目录投影与 `GET /api/templates`，官方教学元数据不复制参数值，用户模板无需迁移即可
  生成摘要、步骤和关键非中性参数教学。
- “大师模板”平台页支持官方/我的模板筛选、适用场景、白盒参数课及向最近 Studio 正式套用；
  没有 Studio 时明确引导先打开照片。
- AI 输入框可选择、移除模板附件；发送时携带模板白盒参数与自适应约束，不选择时保持旧消息。
- 定向验证：Python 模板/looks API `34 passed`；前端相关 `27 passed`；TypeScript 检查通过。

## v2.4 大师模板最终原型迁移（2026-08-11）

- 根据验收反馈把常驻两栏改为“简洁暗房目录 → 独立暖纸详情”：目录卡片只负责识别和选择，
  Before/After、教学、参数和应用按钮进入第二级详情，返回后保留来源、分类与搜索状态。
- 模板目录增加一级分类投影；来源、分类、名称/摘要/场景搜索正交工作，用户模板不迁移原文件且
  默认进入“未分类”。只使用三条真实官方模板，未导入原型的 30 条布局占位。
- 仓库没有已确认授权的官方样片，卡片与无照片详情明确回退白盒参数指纹；有当前 Studio 时由
  本地引擎生成选中模板的真实 Before/After 临时预览，预览可取消且不提交正式版本。
- 详情读取完整 look `analysis`；参数展示由抽象表格改为 ParamContract 驱动的只读滑杆、真实
  曲线图、HSL 三维度八色滑杆与颜色分级色轮，默认只显示有调整项，可切换显示全部。
- 自动化验证：Python 模板目录/API `34 passed`；前端 `157 passed`；production build 成功。
  当前环境无可用浏览器实例，1440/1100/900 实际截图与手感继续保留给作者人工验收。

- [ ] **v2.5 自动化技能人工验收**：用一组真实照片检查技能创建、首张效果与逐文件计划；
  确认批量输出不覆盖原图或既有文件；执行中取消后已完成成片保留；制造一张损坏输入并在重启
  后只重试失败项。页面布局与交互手感由作者检查。

## v2.5 自动化技能自动化收口（2026-07-24）

- 新增已有风格自动化技能，冻结 look analysis、强度、后缀和 JPEG 质量；输入照片与输出目录
  显式选择，计划阶段检查缺失、格式、同批重名和已有输出冲突。
- 完整尺寸成片复用主渲染引擎，以同目录临时文件和不覆盖硬链接保护原图及既有输出；单张失败
  不阻塞后续照片。
- 运行清单逐项持久化，支持协作式取消、进程中断恢复和只重试失败/中断/取消项。
- 平台“自动化技能”占位页替换为真实技能、首张预览、计划确认、运行进度和失败重试页面。
- 定向验证：Python 相关 `68 passed`；前端 API/页面/平台相关 `23 passed`；Ruff 与
  TypeScript 检查通过。收口全量验证：Python `494 passed, 1 skipped`，前端 `143 passed`，
  production build 成功。真实照片观感、页面布局和批量交互保留给作者人工验收。

## v2.3-A 本地文件夹图库 T1–T4 完成（2026-07-22）

- `library.db` 增加保留旧索引的 schema 迁移、稳定文件项目、大小/mtime、尺寸/格式、
  安全拍摄信息、标签和导出操作摘要；更新版本数据库会拒绝降级，重叠索引根在扫描前拒绝。
- 扫描改为每根单一后台任务，支持进度轮询和协作式取消；文件逐项提交，取消时不误标尚未
  遍历的文件为缺失。普通图片与可解码 RAW 生成受控 JPEG 缩略图，其余 RAW 显示占位卡。
- sidecar API 补齐分页搜索、扫描状态/取消、标签与按项目 ID 的 Explorer 定位；结果合并
  最近正式会话版本和 RAW sidecar 导出摘要。从图库打开继续复用正式 SessionStore。
- React 图库页补齐根管理、搜索、标签、分页、扫描进度/停止、缺失状态和 Studio 入口；
  桌面宽度与 900px 窗口实际渲染通过，卡片操作在窄卡片中保持可读。
- 定向验证：Ruff 通过；Python `70 passed`；前端 `18 passed`；TypeScript 检查通过。
  按作者本轮指示，T5 的全量 Python/前端测试、production build 和约 5000 条数据人工验收
  均未执行，任务保持未勾选。

## v2.3-A 真机手测回归修复（2026-07-24）

- 真机发现缩略图使用未启用的 Tauri 本地文件协议，改为经带启动令牌的 sidecar 二进制接口读取，
  并限制只能访问应用缩略图目录。
- 标签保存与移除索引分别使用 PUT、DELETE，但 HTTP server 未实现对应方法，CORS 预检也只放行
  GET/POST；现已补齐真实分发与预检方法。
- 图库项目与正式会话路径的只读核对确认关联数据存在；空版本摘要不再展示随机版本 ID，统一显示
  “已建立 Studio 会话”。
- 定向验证：GUI server／图库 API `41 passed`，前端相关测试 `17 passed`，TypeScript 检查与
  Ruff 通过；真实 Tauri 复验需重建并暂存 sidecar 后执行。

## RAW 可行性门 T1–T5 完成（2026-07-27）

- 新增 `looklift.raw_gate` 离线探针与 `python -m looklift.raw_gate` 入口：manifest、逐样本
  解码隔离、RGB/位深/方向/白平衡检查、性能/内存测量、JSON 报告和中文 GO/NO-GO 摘要。
- rawpy 采用可选导入；缺失或 DLL 不可用会输出结构化 `rawpy_unavailable`，失败时明确建议
  v2.3-B 使用内嵌 JPEG 预览 + XMP sidecar，不把 rawpy 硬依赖带入 GUI。
- 真实门禁使用 8 种相机、24–61MP 的 CC0 RAW；全部成功解码为 `uint16 RGB` 并进入 float32
  渲染边界，解码耗时 1.17–6.02 秒，进程峰值内存最高 1.04 GB，方向和色彩人工检查通过。
- 真机发现 Pillow 会误拒绝三通道 `uint16`，探针改为归一化 float32 代理并走生产数组管线；
  同时修正失败原因优先级和非 Windows `ru_maxrss` 单位。最终结论 **GO**，v2.3-B 采用 RAW
  全解码路径。验证：RAW 门测试 `8 passed`，全量 Python `502 passed, 1 skipped`，Ruff 通过。

## v2.2 平台外壳自动化收口（2026-07-20）

- 新增最近正式会话只读投影、固定首页、全局导航、顶部标签与未来能力说明页；快速修图在
  Tauri 使用官方原生文件选择器，浏览器开发模式保留上传回退。
- 每个 Studio 运行时独立拥有编辑 Store、会话协调器和聊天工作流；非活动 Canvas 不接收全局
  拖放，后台 AI 结果只回到发起标签，关闭后取消资源并拒绝晚到结果。
- 临时候选关闭支持保留、放弃和取消，运行中的 AI 必须先停止；保存失败不销毁候选或标签。
- 平台未引入图库、设备、模板教学、自动化或插件实体；标签布局和未确认候选不持久化。
- 版本字段统一为 `2.2.0`。收口验证：Ruff 通过；Python `462 passed, 1 skipped`；前端
  `129 passed`，production build 成功。完整 Windows/Tauri 功能验收保留给作者手动执行。

## v2.1 AI Studio 自动化收口（2026-07-18）

- 新增安全代理图、白盒参数操作契约、无状态 `chat_step`、本地 SQLite 正式版本仓库与
  五条会话/对话 API；候选计算和正式提交严格分离。
- React 编辑 Store 增加 pending、undo/redo 和过期请求拒绝；普通消息单轮、显式精修
  最多两轮，保存失败会保留候选供重试。
- 左侧 AI Studio 默认启用且可折叠，展示供应商/代理图/元数据摘要、显影记录、能力限制、
  近似方案和右侧手调步骤；视觉继续复用 v2.0-B 暗房 token。
- 新增离线全链路测试，覆盖消息→候选→真实渲染→确认/撤销→重启恢复，以及超时、鉴权、
  回滚、取消和渲染错误不污染正式版本。版本字段统一为 `2.1.0`。

## v2.1 当前效果上下文与直方图（2026-07-18）

- AI 不再把原片代理当作当前编辑效果：`preview.py` 统一 GUI 与 AI 的渲染入口，聊天请求把
  `current_analysis`、factor 与同一快照渲染出的 2048px 无 EXIF JPEG 一并提交。
- 编辑 Store 增加活动 AI request ID 锁。请求中右侧参数、模板、强度、重置和历史修改被阻止；
  停止立即解锁，切图和供应商晚到响应不会生成候选。
- 右侧新增当前 after 预览的 RGB 直方图、黑白场裁切提示和安全拍摄信息。直方图由独立 Worker
  缩图计算，签名不匹配的旧结果被丢弃，计算失败不影响画布与调参。
- 自动收口：Ruff 通过；Python `456 passed, 1 skipped`；前端 `100 passed`，production build
  成功并产出独立 `histogramWorker` chunk。真实照片效果与交互仍保留给作者人工验收。

## v2.1 人工验收预览回归修复（2026-07-18）

- 人工验收发现模板、右侧手调和 AI 候选只更新参数、画布不更新；WebView Network 实证
  `/api/preview` 排队 3.5 分钟，同时产生约 90 个 `plugin:event` listen/unlisten 请求。
- 根因是 Canvas 原生拖图 effect 依赖随 analysis/factor 重建的 `loadPath`。改为每个
  Canvas/client 只注册一次监听，通过 ref 调用最新回调，消除事件请求风暴。
- 所有改变显示 analysis 的入口立即使旧预览失效；AI 候选只有在对应预览 ready 后才能保留、
  继续手调或精修，渲染失败仍保留候选以便撤销或重试。
- AI 精修从“一次点击自动连跑两轮”改为“一次点击一轮、累计最多两轮”，并在 workflow 层拦截
  未渲染候选、并发重复点击和第三轮调用。
- 自动验证：前端 `89 passed`、TypeScript 与 Vite production build 通过；Python
  `452 passed, 1 skipped`、Ruff 与 Rust `cargo check` 通过。人工复验项目保留在
  [v2.1/tasks.md](../versions/v2.1/tasks.md)，未提前勾选。

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
## 2026-08-25：Context Compiler 2.0 与 Run Manifest 事件接线

- Domain Pack 新增 Capability/Permission、Global Rules、Memory、Project Context 的不可变来源和快照恢复。
- 固定安全编译顺序：系统边界 → Capability Gate → Tool Contract → 摄影领域契约 → 已确认上下文 → Skill/Template/Reference。
- Run Manifest 接入规范化 AgentEvent，并修复不同 Attempt 的 sequence 必须独立计数。
- 定向测试 `34 passed`，受影响文件 Ruff 通过；真实 Provider 和重启 UI 不在本单元验收范围。

## 2026-08-25：Runtime Registry 通用探测骨架

- Runtime Definition 补齐输入传输、事件流格式、Resume 和 MCP 声明字段。
- 通用探测引擎并行执行注入式 Probe，隔离超时和异常，不向调用方泄漏底层错误正文。
- 新增可用性、认证、版本和模型发现契约测试；通用启动/取消生命周期仍留在下一完整单元。

## 2026-08-25：Runtime 通用生命周期与目录 API

- 新增通用启动、能力门控、事件身份/序号校验、取消和回收引擎，禁止隐式 Runtime/Provider 回退。
- Pydantic API、Pi CLI、Fake 进入内置声明式目录；新增 `/api/runtimes` 安全选择数据。
- Runtime、Adapter 与 GUI 定向回归 `65 passed`；受影响 Ruff 与 diff check 通过。

## 2026-08-25：Plugin 版本、令牌与 Skill staging

- Plugin Registry 使用语义版本选择，校验内容 SHA-256 和高风险能力；禁用版本仍保留用于历史回放。
- Scoped Token 绑定项目、插件版本和 Attempt，撤销后即时失效。
- Skill 内容冻结到项目私有 staging，仅允许入口和一层 Markdown Reference；契约测试 `12 passed`。

## 2026-08-25：Connector 来源提案与代理图门禁

- Connector Manifest 固定协议、接收方和能力；Source Packet 以内容摘要保证 ID 幂等。
- Connector 复用唯一 Proposal Service，ProjectContext 等目标保留完整 Source Packet 来源链。
- Provider Gateway 仅接受授权接收方的 2048px 无 EXIF JPEG 内存代理图；定向契约测试 `11 passed`。

## 2026-08-25：Verifier、Critique 与用户复核门

- Verifier 复用 CandidateRevision 的白盒差异、真实预览和指标，未复制渲染或 Patch 校验。
- 固定 Contract/Domain/Capability/Render 失败分类、硬失败与软警告语义，并生成 evidence hash。
- User Review Gate 复核正式基线且不直接提交；Verifier/Candidate/Eval 定向测试 `23 passed`。

## 2026-08-25：Run Manifest Repository 与恢复 API

- 每个 Run 使用独立事实日志/原子快照，Repository 阻断不安全 ID 并提供可恢复列表和详情。
- 本地服务启动时只执行一次 interrupted 收敛；列表请求不会改变活跃 Run。
- 恢复仅创建新 Attempt，可显式切换 Runtime，不复用序号、不自动产生模型费用；后端定向回归 `62 passed`。

## 2026-08-25：运行恢复 UI 与服务端基线权威

- 恢复 API 改为根据 Manifest 的 session_id 从 SessionStore 读取正式版本，忽略客户端伪造的 baseline_hash。
- 平台新增运行恢复导航、可恢复列表、运行事实详情、Runtime 选择和新 Attempt 操作；stale 状态不提供恢复按钮。
- 后端基线/恢复测试 `18 passed`，前端定向测试 `21 passed` 且 TypeScript 通过；当前环境无浏览器控制入口，实际截图视觉验收待人工完成。
