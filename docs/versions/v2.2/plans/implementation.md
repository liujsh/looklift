# v2.2 平台外壳实施计划

> 执行方式：单智能体在 `v2.2-platform-shell` 分支线性实施，不派子代理；每个任务完成一次自审和聚焦验证。

**目标：** 将现有 AI Studio 迁入包含首页、全局导航和多 Studio 标签的桌面平台，并提供真实路径快速修图与最近正式会话恢复。

**架构：** 平台层只拥有导航、标签和 Studio 运行时注册表；每个 Studio 运行时独立拥有编辑 Store、会话协调器和聊天工作流。Python 只在现有 v2.1 会话表上增加只读最近列表，Tauri 只增加官方文件对话框能力。

**技术栈：** Python 3.10+、SQLite、stdlib HTTP；React 19、TypeScript、Vitest、Tauri 2、Rust。

## 全局约束

- 白盒参数仍由 Python 参数契约和现有渲染引擎唯一拥有；平台层不得复制调色业务。
- 首页固定存在；同一正式 session 最多打开一个 Studio 标签。
- 每个 Studio 的 analysis、强度、聊天、AI 请求、临时预览和派生界面状态互相隔离。
- 非活动 Studio 不响应窗口级拖放；已关闭运行时拒绝晚到异步结果。
- 重启只恢复 SQLite 中的正式状态，永不持久化 `pendingPreview` 或标签工作区。
- “添加文件夹”和“从设备导入”仅说明 v2.3 边界，不实现扫描、设备发现、复制或图库实体。
- 用户界面、注释、docstring、文档和提交摘要使用中文；对外品牌写作 **LookLift**。
- 测试离线，不调用真实 provider，不读取真实 `~/.looklift`。
- 迭代中只跑受影响测试和必要的 `pnpm exec tsc --noEmit`；纯样式只用 `pnpm dev` 人工检查。
- 全量 `pytest -q`、Ruff、`pnpm test && pnpm build` 只在 Task 8 收口运行一次；不在 build 后重复 tsc。
- 不推送、不创建 PR、不合并、不开始 v2.3。

---

## Task 1：最近正式会话只读投影

**文件：**

- 修改：`looklift/session_store.py`
- 修改：`looklift/gui/api.py`
- 修改：`tests/test_session_store.py`
- 修改：`tests/test_gui_sessions_api.py`
- 修改：`frontend/src/api/types.ts`
- 修改：`frontend/src/api/client.ts`
- 修改：`frontend/src/api/client.test.ts`

**接口契约：**

- `SessionStore.list_recent(limit)` 返回按 `edit_sessions.updated_at` 降序排列的不可变摘要集合。
- 摘要只投影 session ID、显示文件名、更新时间、当前正式版本 ID、正式摘要和 `source_available`。
- `GET /api/sessions?limit=<n>` 返回 `{sessions: [...]}`；缺省返回 8 条，允许范围为 1–50，范围外或非整数返回 400。
- 不返回完整 analysis、消息、版本栈、绝对路径或任何临时预览数据。
- 完整恢复继续使用现有 `GET /api/sessions/<id>`。

- [x] **Step 1：先写 SessionStore 失败测试**

  在临时数据库建立至少三个更新时间可区分的会话，断言排序、limit、当前正式摘要和存在/缺失文件状态；同时断言 schema version 不变化。

- [x] **Step 2：运行后端聚焦测试并确认失败**

  运行：`pytest tests/test_session_store.py -q`

  预期：因 `list_recent` 或摘要类型尚不存在而失败。

- [x] **Step 3：实现最小只读查询**

  使用现有表连接当前版本指针和当前版本记录；文件可用性在查询结果投影阶段判断，不写数据库、不触发迁移。

- [x] **Step 4：先写 API 和前端 client 失败测试**

  覆盖缺省查询、合法 limit、非法 limit、数据库错误脱敏，以及前端生成正确查询字符串并解析 `{sessions}`。

- [x] **Step 5：运行聚焦测试并确认失败**

  运行：`pytest tests/test_gui_sessions_api.py -q`

  在 `frontend/` 运行：`pnpm exec vitest run src/api/client.test.ts`

  预期：最近会话路由、类型或 client 方法尚不存在而失败。

- [x] **Step 6：接通 HTTP 与前端类型**

  复用 `_session_error` 的脱敏边界；路由只做 query 校验、调用仓库和序列化。前端新增只读摘要类型与列表方法，不改变现有单会话接口。

- [x] **Step 7：运行聚焦验证**

  运行：`pytest tests/test_session_store.py tests/test_gui_sessions_api.py -q`

  在 `frontend/` 运行：`pnpm exec vitest run src/api/client.test.ts`

  运行受影响 Ruff：`ruff check looklift/session_store.py looklift/gui/api.py tests/test_session_store.py tests/test_gui_sessions_api.py`

  预期：全部通过。

- [x] **Step 8：自审并提交**

  自审查询是否只读、是否泄露绝对路径、是否错误引入 v2.3 表；提交：`feat(v2.2): 添加最近会话查询`。

## Task 2：解除编辑界面的全局 Store 单例耦合

**文件：**

- 修改：`frontend/src/store/editorStore.ts`
- 修改：`frontend/src/app/EditorShell.tsx`
- 修改：`frontend/src/components/PanelPane.tsx`
- 修改：`frontend/src/components/GalleryPane.tsx`
- 修改：`frontend/src/components/CanvasPane.tsx`
- 修改：`frontend/src/app/EditorShell.test.tsx`
- 修改：`frontend/src/components/PanelPane.test.tsx`
- 修改：`frontend/src/components/GalleryPane.test.tsx`
- 修改：`frontend/src/components/CanvasPane.lifecycle.test.tsx`
- 修改：`frontend/src/store/editorStore.test.ts`

**接口契约：**

- `createEditorStore()` 继续是唯一 Store 构造入口。
- `useEditorState(store)` 明确订阅调用方传入的 Store；生产组件不再读取模块级 `editorStore`。
- `EditorShell`、`PanelPane` 和 `GalleryPane` 全部消费同一个显式 Store 实例。
- `EditorShell` 接收活动状态，Canvas 只有在所属 Studio 活动时注册窗口级拖放监听。
- 现有 analysis、pendingPreview、编辑锁、undo/redo 和渲染签名语义不改变。

- [x] **Step 1：写双 Store 隔离失败测试**

  使用两个 Store 渲染两个编辑壳或关键子组件，修改其中一个后断言另一个的参数、强度和禁用状态不变化；
  同时断言只有 active EditorShell 的 Canvas 注册窗口级拖放。

- [x] **Step 2：运行受影响前端测试并确认失败**

  在 `frontend/` 运行：`pnpm exec vitest run src/app/EditorShell.test.tsx src/components/PanelPane.test.tsx src/components/GalleryPane.test.tsx src/components/CanvasPane.lifecycle.test.tsx`

  预期：组件尚不能接收显式 Store，或仍读全局单例而失败。

- [x] **Step 3：最小化完成 Store 注入**

  参数面板、模板带和 EditorShell 的所有读写都改用传入实例。完成所有调用点迁移后删除生产路径中的模块级单例依赖，测试按需自行创建 Store；Canvas 的原生监听随 active 状态转移且不重置编辑状态。

- [x] **Step 4：运行聚焦测试与 TypeScript**

  在 `frontend/` 运行：`pnpm exec vitest run src/store/editorStore.test.ts src/app/EditorShell.test.tsx src/components/PanelPane.test.tsx src/components/GalleryPane.test.tsx src/components/CanvasPane.lifecycle.test.tsx src/features/sessions/sessionCoordinator.test.ts src/features/chat/chatWorkflow.test.ts`

  在 `frontend/` 运行：`pnpm exec tsc --noEmit`

  预期：全部通过。

- [x] **Step 5：自审并提交**

  用 `rg "editorStore" frontend/src` 确认没有组件偷偷回读模块级单例；提交：`refactor(v2.2): 隔离 Studio 编辑状态`。

## Task 3：平台标签 Store 与 Studio 运行时

**文件：**

- 新建：`frontend/src/platform/platformStore.ts`
- 新建：`frontend/src/platform/platformStore.test.ts`
- 新建：`frontend/src/platform/studioRuntime.ts`
- 新建：`frontend/src/platform/studioRuntime.test.ts`
- 修改：`frontend/src/features/chat/chatWorkflow.ts`
- 修改：`frontend/src/features/chat/chatWorkflow.test.ts`

**接口契约：**

- 平台标签只有 `home`、`platform`、`studio` 三类；home 唯一且不可关闭。
- 平台 Store 拥有标签顺序、活动标签、导航折叠偏好和“打开或聚焦”动作，不拥有 analysis。
- 导航折叠偏好通过可注入的本机 storage 适配器读写；测试不访问真实 localStorage。
- `StudioRuntime` 绑定 session ID、独立 editor Store、session coordinator、chat workflow、标题和存活状态。
- 运行时从完整 `SessionSnapshot` 恢复正式 analysis 与消息，不构造 pendingPreview。
- `dispose()` 幂等，取消 AI 并令后续异步结果失效；不删除正式 session。

- [ ] **Step 1：写平台状态失败测试**

  覆盖固定首页、导航偏好恢复、同一平台页去重、同一 session 聚焦、多个 session 并存、活动标签切换和关闭后回到邻近标签。

- [ ] **Step 2：写运行时失败测试**

  覆盖两个 runtime 的 Store/工作流不共享、snapshot 只恢复正式状态、dispose 幂等和关闭后晚到 AI 结果被拒绝。

- [ ] **Step 3：运行聚焦测试并确认失败**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/platformStore.test.ts src/platform/studioRuntime.test.ts`

  预期：平台 Store 与运行时模块尚不存在而失败。

- [ ] **Step 4：实现纯平台状态和运行时工厂**

  保持平台 Store 与 React 无关，方便确定性测试。给聊天工作流补最小销毁/存活门禁；不要复制已有 request ID、照片身份和编辑锁判断。

- [ ] **Step 5：运行聚焦验证**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/platformStore.test.ts src/platform/studioRuntime.test.ts src/features/chat/chatWorkflow.test.ts src/features/sessions/sessionCoordinator.test.ts`

  在 `frontend/` 运行：`pnpm exec tsc --noEmit`

  预期：全部通过。

- [ ] **Step 6：自审并提交**

  显式检查 runtime 是否独立、dispose 后是否仍有发布路径、平台 Store 是否误持 analysis；提交：`feat(v2.2): 添加平台标签运行时`。

## Task 4：首页、导航和顶部标签

**文件：**

- 新建：`frontend/src/platform/PlatformShell.tsx`
- 新建：`frontend/src/platform/PlatformShell.test.tsx`
- 新建：`frontend/src/platform/HomePage.tsx`
- 新建：`frontend/src/platform/HomePage.test.tsx`
- 新建：`frontend/src/platform/NavigationRail.tsx`
- 新建：`frontend/src/platform/WorkspaceTabs.tsx`
- 新建：`frontend/src/platform/ComingSoonPage.tsx`
- 修改：`frontend/src/App.tsx`
- 修改：`frontend/src/App.css`
- 修改：`frontend/src/theme/layout.css`
- 修改：`frontend/src/theme/components.css`

**接口契约：**

- `App` 的引擎 gate 保持不变；ready 后渲染 `PlatformShell`，不再直接渲染单个 EditorShell。
- 首页提供快速修图回调、最近会话加载/重试和未来入口说明。
- 标签栏 `＋` 复用首页三种动作来源，不维护独立业务分支。
- 最近会话卡片不显示绝对路径；`source_available=false` 时不可恢复。
- 导航包含最终六类入口，普通平台页记住展开偏好，Studio 默认使用窄图标轨。
- 未实施页面使用一个统一说明组件，不请求图库、设备、自动化或插件数据。

- [ ] **Step 1：写行为失败测试**

  覆盖启动进入首页、首页不可关闭、标签栏 `＋` 三入口、导航项完整、未来入口只显示版本说明、最近会话错误可重试、缺失文件禁用和点击 session 打开/聚焦 runtime。

- [ ] **Step 2：运行聚焦测试并确认失败**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/PlatformShell.test.tsx src/platform/HomePage.test.tsx src/app/EditorShell.test.tsx`

  预期：平台 React 组件尚不存在而失败。

- [ ] **Step 3：实现最小可用平台 UI**

  先完成语义结构、加载/空/错误状态和真实动作，再落基础布局。平台说明页只写已确认版本边界，不放原型假数据。

- [ ] **Step 4：接入多个 EditorShell**

  每个 studio 标签渲染所属 runtime 的 EditorShell；非活动项隐藏但保持挂载。标题使用文件显示名，AI 运行中提供非侵入状态提示。

- [ ] **Step 5：运行聚焦验证**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/PlatformShell.test.tsx src/platform/HomePage.test.tsx src/app/EditorShell.test.tsx`

  在 `frontend/` 运行：`pnpm exec tsc --noEmit`

  预期：全部通过。

- [ ] **Step 6：自审并提交**

  检查是否出现假图库/设备数据、是否重复 session、隐藏 Studio 是否仍保持组件状态；提交：`feat(v2.2): 搭建平台首页与导航`。

## Task 5：Tauri 原生快速修图选择

**文件：**

- 新建：`frontend/src/platform/quickEdit.ts`
- 新建：`frontend/src/platform/quickEdit.test.ts`
- 修改：`frontend/src/platform/HomePage.tsx`
- 修改：`frontend/package.json`
- 修改：`frontend/pnpm-lock.yaml`
- 修改：`frontend/src-tauri/Cargo.toml`
- 修改：`frontend/src-tauri/Cargo.lock`
- 修改：`frontend/src-tauri/src/lib.rs`
- 修改：`frontend/src-tauri/capabilities/default.json`

**接口契约：**

- 正式桌面只允许选择现有单个 JPEG、PNG、WebP 或 TIFF 文件，返回真实路径。
- 对话框取消返回正常空结果，不显示错误、不创建 session。
- 首页按钮和标签栏 `＋` 调用同一个 quick-edit 控制器。
- 非 Tauri 环境调用现有上传回退；上传成功后走与真实路径相同的 create/resume 和标签去重流程。
- 文件格式最终校验仍由现有后端负责，前端 accept/filter 只改善选择体验。
- Tauri 只增加官方 dialog 插件默认读取选择权限，不增加目录扫描或任意文件写权限。

- [ ] **Step 1：写控制器失败测试**

  通过依赖注入覆盖原生选择成功、取消、原生 API 不可用时浏览器回退、上传失败和 create/resume 失败；断言失败不会创建标签。

- [ ] **Step 2：运行聚焦测试并确认失败**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/quickEdit.test.ts src/platform/HomePage.test.tsx`

  预期：quick-edit 适配层或首页动作尚不存在而失败。

- [ ] **Step 3：安装并注册官方插件**

  前端与 Rust 插件均锁定 Tauri 2 同一主版本；更新 capability，只授予主窗口打开文件对话框所需权限。

- [ ] **Step 4：实现桌面选择与浏览器回退**

  平台控制器负责动作编排，HomePage 只负责触发和显示进度/错误；不要把 session 或标签业务塞进文件选择适配层。

- [ ] **Step 5：运行聚焦验证**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/quickEdit.test.ts src/platform/HomePage.test.tsx src/api/client.test.ts`

  在 `frontend/` 运行：`pnpm exec tsc --noEmit`

  在 `frontend/src-tauri/` 使用独立 target 目录运行：`cargo check`

  预期：全部通过。生产打包留到 Task 8，避免中途重复全量 build。

- [ ] **Step 6：自审并提交**

  检查 capability 最小化、取消是否无副作用、正式路径是否未经过临时上传；提交：`feat(v2.2): 接入原生快速修图选择`。

## Task 6：标签关闭门禁与资源释放

**文件：**

- 修改：`frontend/src/platform/platformStore.ts`
- 修改：`frontend/src/platform/platformStore.test.ts`
- 修改：`frontend/src/platform/studioRuntime.ts`
- 修改：`frontend/src/platform/studioRuntime.test.ts`
- 修改：`frontend/src/platform/PlatformShell.tsx`
- 修改：`frontend/src/platform/PlatformShell.test.tsx`
- 新建：`frontend/src/platform/CloseStudioDialog.tsx`
- 新建：`frontend/src/platform/CloseStudioDialog.test.tsx`

**接口契约：**

- AI 请求运行中关闭：仅提供停止并继续关闭或取消。
- pendingPreview 关闭：提供保留并关闭、放弃并关闭、取消。
- 保留必须等待现有 session 事务成功；失败时 runtime 和标签继续存在。
- 销毁顺序固定为停止新输入、解决候选/请求、取消派生任务、释放监听与 URL、移除标签。

- [ ] **Step 1：写关闭状态机失败测试**

  覆盖纯正式直接关闭、AI 请求取消关闭、停止后关闭、候选三选项、保留失败不关闭、重复点击幂等和晚到响应拒绝。

- [ ] **Step 2：运行聚焦测试并确认失败**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/platformStore.test.ts src/platform/studioRuntime.test.ts src/platform/CloseStudioDialog.test.tsx src/platform/PlatformShell.test.tsx`

  预期：活动归属或关闭门禁尚未实现而失败。

- [ ] **Step 3：实现关闭状态机和对话框**

  复用 SessionCoordinator 的 accept/discard 与 ChatWorkflow 的 cancel，不另写一套提交逻辑。对话框只驱动状态机并显示异步结果。

- [ ] **Step 4：运行聚焦验证**

  在 `frontend/` 运行：`pnpm exec vitest run src/platform/platformStore.test.ts src/platform/studioRuntime.test.ts src/platform/CloseStudioDialog.test.tsx src/platform/PlatformShell.test.tsx src/features/chat/chatWorkflow.test.ts`

  在 `frontend/` 运行：`pnpm exec tsc --noEmit`

  预期：全部通过。

- [ ] **Step 5：自审并提交**

  重点审查重复监听、未等待事务、关闭后 setState 和跨 runtime 污染；提交：`feat(v2.2): 完善标签关闭与资源清理`。

## Task 7：平台视觉与桌面响应式

**文件：**

- 修改：`frontend/src/App.css`
- 修改：`frontend/src/theme/tokens.css`
- 修改：`frontend/src/theme/layout.css`
- 修改：`frontend/src/theme/components.css`
- 修改：`frontend/src/platform/PlatformShell.tsx`
- 修改：`frontend/src/platform/HomePage.tsx`
- 修改：`frontend/src/platform/NavigationRail.tsx`
- 修改：`frontend/src/platform/WorkspaceTabs.tsx`
- 修改：`frontend/src/platform/ComingSoonPage.tsx`

**视觉基线：**

- 复用 `.superpowers/brainstorm/397-1784352572/content/design-section-1-information-architecture.html` 的平台层级。
- 复用 `design-section-2-home-import.html` 的首页主视觉，但移除假的最近图库、设备和推荐内容。
- 复用 `design-section-3-editing-studio.html` 的窄导航轨 + Studio 结构，保留当前已验收工作台细节。

- [ ] **Step 1：启动开发环境人工查看**

  在 `frontend/` 运行：`pnpm dev`

  检查首页、未来说明页、空 Studio、已有照片 Studio 和关闭对话框。

- [ ] **Step 2：调整平台视觉**

  完成标签选中/运行/关闭状态、导航展开/折叠、首页入口、最近会话卡片、错误与空状态；不加入与功能无关的大型动效或新设计系统。

- [ ] **Step 3：检查三个桌面宽度**

  人工检查约 1440px、1100px 和 900px。Studio 优先保住画布；低于最低宽度给出增大窗口提示，不设计手机布局。

- [ ] **Step 4：只在逻辑变化时跑聚焦测试**

  若仅 CSS 变化，不运行 Vitest。若修改条件渲染或折叠状态，在 `frontend/` 运行对应 `PlatformShell` / `EditorShell` 测试和 `pnpm exec tsc --noEmit`。

- [ ] **Step 5：自审并提交**

  以实际渲染为准检查层级、滚动、焦点、禁用态和画布空间；提交：`style(v2.2): 完成平台外壳响应式布局`。

## Task 8：集成、文档回填与版本收口

**文件：**

- 新建：`frontend/src/platform/PlatformShell.integration.test.tsx`
- 修改：`docs/versions/v2.2/tasks.md`
- 修改：`docs/product/architecture.md`
- 修改：`docs/history/dev-log.md`
- 修改：`docs/README.md`
- 修改：`docs/product/requirements.md`
- 修改：`pyproject.toml`
- 修改：`looklift/__init__.py`
- 修改：`frontend/package.json`
- 修改：`frontend/src-tauri/Cargo.toml`
- 修改：`frontend/src-tauri/tauri.conf.json`

**收口契约：**

- 流程测试使用假 client、假 AI 和临时文件，覆盖首页→快速修图→多标签→候选→关闭→最近会话恢复。
- 四处版本号统一为 2.2.0；实现完成后才把 architecture、路线图和任务状态改成实况。
- 人工验收记录真实 Windows/Tauri 的结果，不把未执行项目提前勾选。

- [ ] **Step 1：补端到端前端流程测试**

  覆盖新建与恢复去重、两个 Studio 隔离、后台 AI 归属、候选关闭三分支、缺失源文件和最近列表失败恢复。

- [ ] **Step 2：运行收口前聚焦测试**

  在 `frontend/` 运行新增集成测试及其直接依赖测试；失败时只修相关实现，不先跑全量。

- [ ] **Step 3：完成真实 Windows/Tauri 人工验收**

  使用两张真实照片验证原生路径、切换、后台 AI、关闭、重启、源文件缺失和三个窗口宽度。发现问题先修复并重跑受影响测试。

- [ ] **Step 4：回填文档与版本号**

  `architecture.md` 只记录已经实现的平台状态所有权和数据流；`dev-log.md` 记录验证事实与仍需作者确认项；任务清单只勾实际完成内容。

- [ ] **Step 5：执行唯一一次全量验证**

  仓库根运行：`pytest -q`

  仓库根运行：`ruff check .`

  在 `frontend/` 运行：`pnpm test && pnpm build`

  不额外运行 `tsc --noEmit`。记录通过数量、跳过数量和构建结果。

- [ ] **Step 6：批量代码 diff 自审**

  检查单文件职责、全局 Store 残留、跨标签异步竞态、Tauri 权限、错误脱敏、v2.3 越界和无关改动。只对成型代码 diff 做这一轮严格审查。

- [ ] **Step 7：提交版本收口**

  提交：`docs(v2.2): 收口平台外壳实现`。保持分支本地，不 push、不建 PR。

## 最终人工验收清单

- [ ] 启动进入首页，首页固定标签不可关闭。
- [ ] 添加文件夹和设备导入只显示 v2.3 说明，不触发系统扫描或设备访问。
- [ ] 原生文件选择成功打开真实路径；取消和失败不产生空标签。
- [ ] 两张照片分别手调、对话和生成候选，切换后 analysis、消息和直方图不串。
- [ ] AI 运行时切换标签，结果只回到原标签；非活动标签不接收拖放。
- [ ] 同一 session 从首页重复打开时只聚焦现有标签。
- [ ] 候选关闭的保留、放弃、取消三条路径均符合预期；保存失败不关闭。
- [ ] 重启后只恢复正式版本，未确认预览不出现。
- [ ] 源文件移走后首页标记不可用且不猜测路径。
- [ ] 约 1440px、1100px、900px 下平台导航、标签、画布和面板可用。

## 完成定义

Task 1–8 的自动化、人工验收、文档回填和版本号同步全部完成，全量验证一次通过，代码 diff 经一次批量自审，
且未实现 v2.3 或推送远端，v2.2 才算收口。
