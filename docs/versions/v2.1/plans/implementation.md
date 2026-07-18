# v2.1 AI Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to implement this plan task-by-task. 本仓库禁止派子代理，固定由当前会话内联执行；每个任务遵循 TDD，先观察红灯再写生产代码。

**Goal:** 在现有三栏修图工作台中开放可折叠 AI 对话栏，让模型通过受控参数契约提出修图建议，用户可在临时预览中保留、撤销、继续手调或主动执行最多两轮 AI 精修，并在重启后只恢复已确认状态。

**Architecture:** React `editorStore` 继续是编辑状态唯一拥有者；后端 `chat_step` 是无状态纯流程，负责准备安全代理图、调用现有 provider、校验结构化操作并返回候选 analysis。AI 候选先进入内存 `pendingPreview`，仅在用户保留或继续手调时通过 SQLite 事务写入正式消息、版本与当前指针。照片原文件、代理图和临时预览不进入数据库。

**Tech Stack:** Python 3.11+、Pillow、标准库 `sqlite3`、现有 VisionProvider、React 19、TypeScript、Vitest、Tauri 2。

## Global Constraints

- 参数白名单与范围只来自 `looklift/render/contract.py`；不得在聊天层手抄第二套范围。
- 首版仅支持标量 `delta/set` 与主明度曲线整组替换；不支持 RGB 分通道、蒙版、局部修复或生成式编辑。
- 普通消息只调用模型一次；只有明确点击“AI 精修”才允许额外调用，最多两次，可取消。
- 所有外部 provider 只接触最长边不超过 2048px、重新编码且无 EXIF 的代理图；安全元数据独立作为文本块发送。
- `pendingPreview` 只在内存；任何异常都不得移动数据库当前版本指针。
- 保留 v2.0-B 手调、模板、分析、预览、收藏与导出路径，不顺带实现 v2.2 平台外壳或 v2.3 图库。
- 不执行 Git add/commit/push，除非作者另行明确授权。

---

### Task 0: 固化 2.0.0 收口基线

**Files:**
- Modify: `pyproject.toml`
- Modify: `looklift/__init__.py`
- Modify: `frontend/package.json`
- Modify: `frontend/src-tauri/Cargo.toml`
- Modify: `frontend/src-tauri/Cargo.lock`
- Modify: `frontend/src-tauri/tauri.conf.json`
- Modify: `README.md`
- Modify: `docs/requirements.md`
- Modify: `docs/dev-log.md`
- Modify: `docs/versions/v2.0-A/{requirements,design,tasks}.md`
- Modify: `docs/versions/v2.0-B/{requirements,design,tasks}.md`
- Modify: `frontend/.gitignore`

- [x] 将所有应用正式版本字段统一为 `2.0.0`，历史日志与第三方依赖版本保持原样。
- [x] 将 v2.0-A、v2.0-B 和根路线图标记为已完成，并记录 M1-M8 作者验收全部通过。
- [x] 忽略并清理 Vite 临时缓存 `frontend/.vite/`，确保源码管理只显示真实改动。
- [x] 运行版本与工作树校验。

Run: `.venv\Scripts\python.exe -c "import looklift; print(looklift.__version__)"`

Expected: `2.0.0`。

Run: `pnpm build`

Expected: production build 成功，package 版本不影响现有前端行为。

Run: `cargo check`

Expected: Rust/Tauri 配置与 lockfile 一致。

Run: `git diff --check`

Expected: 无空白错误；Cargo.lock 中仍出现的 `0.5.0` 仅属于第三方依赖。

---

### Task 1: 参数操作契约与原子应用

**Files:**
- Create: `looklift/chat_contract.py`
- Create: `tests/test_chat_contract.py`
- Modify: `looklift/render/contract.py`

**Interfaces:**

```python
def apply_chat_operations(analysis: dict, operations: list[dict]) -> ChatApplyResult: ...

@dataclass(frozen=True)
class ChatApplyResult:
    analysis: dict
    changes: tuple[dict, ...]
    rejected: tuple[dict, ...]
```

标量操作格式为 `{"type":"scalar","path":"basic.exposure","mode":"delta|set","value":0.3,"reason":"..."}`；曲线格式为 `{"type":"tone_curve","points":[...],"reason":"..."}`。

- [x] 先写失败测试：合法 delta/set、clamp、未知路径、非法 mode、布尔冒充数字、空变更及输入对象不被修改。
- [x] 写曲线失败测试：端点、范围、输入严格递增、重复 input、非数值、整组原子拒绝和其余 analysis 字段不变。
- [x] 在参数契约中导出 AI 可写标量路径；在 `chat_contract.py` 深拷贝后按统一范围落点。
- [x] 标量非法项可逐项拒绝；一条曲线只允许整组接受或整组拒绝；最终无合法变化时不制造版本。

Run: `.venv\Scripts\python.exe -m pytest tests/test_chat_contract.py -q`

Expected: PASS。

---

### Task 2: 安全代理图与元数据白名单

**Files:**
- Create: `looklift/ai_proxy.py`
- Create: `tests/test_ai_proxy.py`
- Modify: `looklift/providers.py`

**Interfaces:**

```python
@dataclass(frozen=True)
class AiProxy:
    path: Path
    metadata: dict[str, str | int | float]

@contextmanager
def prepare_ai_proxy(source: Path, *, include_metadata: bool) -> Iterator[AiProxy]: ...
```

- [x] 先写带 EXIF 的 JPEG 测试，断言代理图最长边 ≤2048、RGB JPEG、重新编码且 `getexif()` 为空。
- [x] 测试安全字段仅含 ISO、快门、光圈、焦距、曝光补偿、白平衡和色彩空间；GPS、机身序列号、作者、版权和自由文本永不返回。
- [x] 测试关闭元数据后返回空对象；临时代理在上下文退出后删除。
- [x] 实现 Pillow 读取、缩放和无 EXIF 重编码；provider 仍只接收代理路径，不能自己退回原图路径。
- [x] 给 provider 图像编码补回归测试，证明二次缩放仍满足 ≤2048 且不会重新附加元数据。

Run: `.venv\Scripts\python.exe -m pytest tests/test_ai_proxy.py tests/test_providers.py -q`

Expected: PASS。

---

### Task 3: 无状态 AI 对话核心

**Files:**
- Create: `looklift/chat.py`
- Create: `tests/test_chat.py`
- Modify: `looklift/providers.py`

**Interfaces:**

```python
def chat_step(
    *, image_path: Path, current_analysis: dict, message: str,
    history: list[dict], include_metadata: bool,
    provider: VisionProvider | None = None,
) -> ChatStepResult: ...
```

响应包含 `analysis`、规范化 `changes`、中文 `explanation`、`limitations`、`manual_steps`、`provider`、`proxy_count` 和 `metadata_sent`；provider 原始 JSON 不直接透传前端。

- [x] 先用捕获 blocks/schema 的 mock provider 写失败测试：单轮成功、最近上下文裁剪、代理图路径、元数据开关与 provider 名称。
- [x] 写 provider 超时/鉴权/取消、非法 JSON 结构、全部操作非法和只有能力说明的测试。
- [x] 定义严格输出 schema 与中文 system prompt，明确禁止把局部请求偷换成无关全局参数。
- [x] 调用 `apply_chat_operations` 规范化结果；同一 mock 输入必须得到确定性结果。
- [x] 将底层 provider 异常映射成稳定错误类别，保留中文可执行提示，不包含 API key、原始响应或本机临时路径。

Run: `.venv\Scripts\python.exe -m pytest tests/test_chat.py tests/test_providers.py -q`

Expected: PASS，全程不触网。

---

### Task 4: SQLite 正式会话与版本仓库

**Files:**
- Create: `looklift/session_store.py`
- Create: `tests/test_session_store.py`
- Modify: `looklift/config.py`

**Schema:**

- `schema_version(version)`
- `edit_sessions(id, image_path, created_at, updated_at)`
- `messages(id, session_id, role, body, provider, status, created_at)`
- `edit_versions(id, session_id, parent_id, analysis_json, source, summary, created_at)`
- `session_current_versions(session_id, version_id)`

**Interfaces:**

```python
class SessionStore:
    def create_or_resume(self, image_path: str, initial_analysis: dict) -> SessionSnapshot: ...
    def commit_exchange(self, session_id: str, exchange: list[dict], analysis: dict, source: str) -> SessionSnapshot: ...
    def record_failed_exchange(self, session_id: str, exchange: list[dict]) -> None: ...
    def load(self, session_id: str) -> SessionSnapshot: ...
```

- [x] 先写 schema 建立、创建/恢复、父版本链、当前指针、消息顺序和 JSON 往返测试。
- [x] 用故障注入写事务中途失败测试，断言消息、版本和当前指针全部回滚。
- [x] 写重启测试，断言只恢复最后确认版本，任何未提交候选都不存在。
- [x] 写迁移前 `.bak.1`～`.bak.3` 轮换与损坏库只读诊断测试；不得自动覆盖损坏原库。
- [x] 数据库默认放在 `CONFIG_PATH.parent / "looklift.db"`，测试必须注入临时路径，不写真实用户目录。

Run: `.venv\Scripts\python.exe -m pytest tests/test_session_store.py -q`

Expected: PASS。

---

### Task 5: 本地 HTTP API 与前端类型客户端

**Files:**
- Modify: `looklift/gui/api.py`
- Create: `tests/test_gui_chat_api.py`
- Create: `tests/test_gui_sessions_api.py`
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

**Routes:**

- `POST /api/chat/step`：只计算候选，不持久化预览。
- `POST /api/sessions`：按照片创建或恢复会话与初始正式版本。
- `GET /api/sessions/<id>`：读取正式消息、版本和当前指针。
- `POST /api/sessions/<id>/commit`：事务提交本轮消息与候选版本。
- `POST /api/sessions/<id>/messages`：仅记录无参数结果、失败或取消状态，不移动版本指针。

- [x] 先写 handler 级红灯测试：请求体类型、路径/analysis/message/history 校验、元数据布尔值、稳定状态码与中文错误。
- [x] 注入 mock `chat_step`/临时数据库，证明 chat 路由不写版本，commit 才移动指针。
- [x] 写真实 HTTP token/CORS 回归，确保新路由不绕过本机启动令牌。
- [x] 在前端定义 `ChatStepRequest/Response`、`SessionSnapshot`、`CommitSessionRequest`，实现对应 client 方法和 AbortSignal。
- [x] 测试 fetch URL、body、令牌、取消与后端中文错误透传。

Run: `.venv\Scripts\python.exe -m pytest tests/test_gui_chat_api.py tests/test_gui_sessions_api.py -q`

Run: `pnpm vitest run src/api/client.test.ts`

Expected: 全部 PASS。

---

### Task 6: 编辑 Store 临时预览状态机

**Files:**
- Modify: `frontend/src/store/editorStore.ts`
- Modify: `frontend/src/store/editorStore.test.ts`

**State additions:**

```ts
type PendingPreview = Readonly<{
  baseAnalysis: Analysis;
  candidate: Analysis;
  changes: readonly ChatChange[];
  exchange: readonly ChatMessage[];
  requestId: number;
  createdAt: string;
}>;
```

Store 对外提供 `displayAnalysis`（候选存在时为 candidate，否则为正式 analysis）、`beginPendingPreview`、`acceptPendingPreview`、`discardPendingPreview`、`beginManualFromPending`、`undo`、`redo` 和 `restoreSession`。

- [x] 先写状态转移红灯测试：AI 候选不进 versions、保留只进一次、撤销还原、切图丢弃、重启只恢复正式状态。
- [x] 写继续手调测试：第一次手调以候选为基线，不回跳旧正式参数；返回待持久化 exchange，供协调层提交。
- [x] 写 undo/redo、正式新提交清空 redo、旧异步 requestId 被拒绝、渲染失败不展示候选测试。
- [x] 实现不可变状态；既有 `previewFragment/finalizePreview` 连续拖动只压一份历史的语义保持不变。

Run: `pnpm vitest run src/store/editorStore.test.ts`

Expected: PASS。

---

### Task 7: 对话工作流、有界 AI 精修与持久化协调

**Files:**
- Create: `frontend/src/features/chat/chatWorkflow.ts`
- Create: `frontend/src/features/chat/chatWorkflow.test.ts`
- Create: `frontend/src/features/sessions/sessionCoordinator.ts`
- Create: `frontend/src/features/sessions/sessionCoordinator.test.ts`
- Modify: `frontend/src/app/EditorShell.tsx`
- Modify: `frontend/src/components/CanvasPane.tsx`
- Modify: `frontend/src/components/PanelPane.tsx`

- [x] 先写普通消息测试，断言恰好一次 `chatStep`，成功后只建立 pending，不调用 commit。
- [x] 写“保留”测试：先确认候选渲染成功，再调用 session commit，成功后才清 pending；失败保留 pending 供重试。
- [x] 写“撤销”测试：不调用 commit，恢复正式 analysis；无变更解释通过 messages 路由保存但不造版本。
- [x] 写继续手调协调测试：候选作为基线，首个手调值不丢失；提交失败时明确错误并保留可重试状态。
- [x] 写 AI 精修测试：最多两次额外调用；每轮以最新 candidate 为 current_analysis；done、无变化、取消和第二轮后都停止。
- [x] `CanvasPane` 和 `PanelPane` 统一消费 `displayAnalysis`，继续复用现有 160ms 预览调度与旧响应拒绝机制。
- [x] 打开照片时创建/恢复 session；应用启动恢复最后正式 analysis 与消息，不恢复 pending。

Run: `pnpm vitest run src/features/chat/chatWorkflow.test.ts src/features/sessions/sessionCoordinator.test.ts src/store/editorStore.test.ts`

Expected: PASS。

---

### Task 8: 可折叠 AI 对话界面与能力边界

**Files:**
- Modify: `frontend/src/components/ChatPane.tsx`
- Create: `frontend/src/components/ChatPane.test.tsx`
- Create: `frontend/src/components/ChatMessageList.tsx`
- Create: `frontend/src/components/ChatChangeCard.tsx`
- Modify: `frontend/src/app/featureFlags.ts`
- Modify: `frontend/src/app/EditorShell.tsx`
- Modify: `frontend/src/app/EditorShell.test.tsx`
- Modify: `frontend/src/theme/layout.css`
- Modify: `frontend/src/theme/components.css`

- [x] 先写 UI 红灯测试：空态、消息流、输入提交、附件加号 seam、发送中/取消、变化卡片、错误与操作按钮。
- [x] 实现聊天栏常驻可折叠；折叠后画布扩展但右侧调参和底部照片带不跳位，窄窗口仍可操作。
- [x] 显示调用前隐私摘要：供应商、代理图数量、元数据开关；关闭开关后后续请求立即生效。
- [x] pending 状态显示“保留此版本”“撤销”“AI 精修”；精修中显示 `第 1/2 轮`、取消和停止原因。
- [x] limitations 卡片明确显示“当前不能自动完成”“可用近似方案”“右侧面板手动步骤”，局部调整/RGB 曲线不得伪装成功。
- [x] 启用 `FEATURES.chatPane`，删除 v2.1 占位文案但保留 feature seam，便于故障回退。
- [x] 样式复用现有 token，不引入在线字体、外链图标或新视觉体系。

Run: `pnpm vitest run src/components/ChatPane.test.tsx src/app/EditorShell.test.tsx`

Run: `pnpm build`

Expected: 测试与 production build 成功。

---

### Task 9: 全链路验证、文档回填与 2.1.0 候选

**Files:**
- Create: `tests/test_v21_chat_integration.py`
- Modify: `docs/product/architecture.md`
- Modify: `docs/history/dev-log.md`
- Modify: `docs/versions/v2.1/tasks.md`
- Modify: `README.md`
- Modify: `pyproject.toml`
- Modify: `looklift/__init__.py`
- Modify: `frontend/package.json`
- Modify: `frontend/src-tauri/Cargo.toml`
- Modify: `frontend/src-tauri/Cargo.lock`
- Modify: `frontend/src-tauri/tauri.conf.json`

- [ ] 用 mock provider + 临时 SQLite 写离线集成测试：消息→候选→预览→保留/撤销→重启恢复。
- [ ] 增加失败矩阵：鉴权、超时、服务未启动、取消、非法响应、渲染失败、数据库回滚；每项都断言正式版本不变且有重试/撤销/手调出口。
- [ ] 跑 Python、前端、Rust 全量回归，确认现有手调、模板、渲染、导出与 provider 不回退。
- [ ] 回填架构实况、迁移版本、人工验收清单和已知限制；实现完成后才把版本字段从 2.0.0 对齐到 `2.1.0`。

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: 全部 PASS（保留仓库既有平台条件 skip）。

Run: `pnpm vitest run`

Run: `pnpm build`

Run: `cargo test`

Run: `cargo check`

Expected: 全部 PASS。

Run: `.venv\Scripts\python.exe -m ruff check looklift tests`

Run: `git diff --check`

Expected: 无 lint 或空白错误。

## 作者后置人工验收

- 用真实照片验证单轮建议、变化解释、主曲线、保留、撤销和继续手调。
- 主动运行 AI 精修，确认最多两轮、每轮可取消且无后台无限调用。
- 重启应用，确认正式消息与版本恢复，未确认临时预览不恢复。
- 对比元数据开关开/关时的调用摘要，确认外部 provider 不接触原图与敏感 EXIF。
- 请求局部提亮、RGB 曲线等超范围动作，确认系统诚实说明限制并给出可执行手调路径。

## Stop Conditions

- 若代理图不能覆盖当前允许导入的某种格式，只添加明确降级提示，不在 v2.1 引入完整 RAW 解码器。
- 若真实 provider 不支持所需 JSON schema，适配层可退回“提示词约束 + 本地严格校验”，不得放宽本地契约。
- 若 SQLite 迁移或恢复检测到损坏，停止写入并进入只读诊断，不自动覆盖用户数据库。
