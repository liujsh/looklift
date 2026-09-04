# 实施计划

> 对照时间：2026-09-04。以当前工作区实现为准，不把半成品或人工门禁标成完成。

## 1. 契约与状态

- [x] 梳理现有 RuntimeSummary、ProviderSettings 和 Agent Run 接口，补充启停状态与默认选择的持久化契约。 _需求：需求 1、需求 4_
- [x] 为 CLI 启停、默认入口/模型失效和 API 编辑草稿编写离线失败测试。 _需求：需求 1、需求 2_

## 2. 后端与 API

- [x] 在不绕过 Runtime Registry 的前提下提供 CLI 启停与默认选择读写接口或等价本地状态服务。 _需求：需求 1_
- [x] 确认 API 配置列表/编辑复用 ProviderConfigStore，补齐脱敏响应和错误分类测试。 _需求：需求 2_
- [x] 验证选择的 `runtime_id + model` 能创建并启动 CLI/API Agent Run；补充 fake harness 契约测试。 _需求：需求 4_

说明：`/api/chat/step` 已接收并校验 `execution_mode + runtime_id + model`，停用入口返回 409。真正的无 CLI BYOK Attempt 仍走第 8 节，不经现有 `chat.chat_step()` / `get_provider()`。

## 3. 前端设置页

- [x] 重构 CLI 条目：扫描、状态、模型数量、启用开关、模型弹窗和默认选择。 _需求：需求 1_
- [x] 重构 API 区域为配置摘要列表与编辑弹窗，保持草稿隔离和 Key 脱敏。 _需求：需求 2_
- [x] 按范围收敛左侧设置导航，仅保留已实现页面并完成窄屏交互。 _需求：需求 5_

## 4. 对话框选择器

- [x] 在加号右侧增加当前 CLI/API 图标与模型摘要。 _需求：需求 3_
- [x] 实现入口→模型两级选择器，过滤停用/不可用入口并更新当前会话运行上下文。 _需求：需求 3、需求 4_
- [x] 增加未选择、模型失效和入口不可用时的阻止发送提示。 _需求：需求 3、需求 4_

现状：发送按钮在未选择入口/模型时禁用，并给出中文提示，不再静默回退。

## 5. 验证与人工门禁

- [x] 运行受影响 Vitest、TypeScript 检查和 Python 离线测试；修复回归。 _需求：需求 1–5_
- [ ] 完成桌面浅色、窄屏和深色设置页视觉检查。 _需求：需求 5_
- [ ] 在用户环境分别人工验证一个可用 CLI 和一个 API 配置的真实调用、取消与候选确认链路。 _需求：需求 4_

## 6. OpenDesign 对齐交互

- [x] 将“本机 CLI / API 提供商”分段按钮实现为即时模式切换，并保持两套草稿和默认选择隔离。 _需求：需求 6_
- [x] 重做输入框入口按钮：显示当前模式图标/模型，弹窗提供当前模式模型选择和“设置”跳转。 _需求：需求 7_
- [x] 为模式切换、弹窗选择、设置跳转补充前端交互测试。 _需求：需求 6、需求 7_

现状：入口按钮显示当前摘要或“未配置”；弹窗按本机 CLI / API 提供商过滤；“设置”跳转平台设置页。

## 7. BYOK API Loop

- [x] 冻结 `ExecutionSelection`、Provider-specific 请求和 SSE 事件契约，明确无 CLI 时不启动任何 CLI。 _需求：需求 8_
- [ ] 实现受限 Tool Loop：允许列表、Schema/路径校验、3 轮硬上限、取消和超时，并覆盖达到 `tool_loop_limit` 的终态。 _需求：需求 8_
- [x] 实现上下文预算管理：旧轮次摘要、工具结果压缩、单条硬截断和 `ContextCompactionEvent` 审计。 _需求：需求 8_
- [x] 将 BYOK 输出归一为 LookLift 白盒 Candidate，接入 CandidateRuntime/Verifier；禁止 artifact 直接写正式版本。 _需求：需求 8_
- [ ] 使用 fake Provider 离线覆盖压缩、截断、工具轮数上限、预算不足和取消边界。 _需求：需求 8_

现状：`OpenAiApiAdapter` 已跑 3 轮工具循环并走 `ScopedToolGateway` + Verifier；达到上限时发出的是 `missing_terminal`，不是 `tool_loop_limit`。适配器测试目前只有成功路径。上下文预算已截断/丢弃旧消息，尚未做“旧轮次摘要”。

## 8. 无 CLI BYOK Harness 实施

- [x] 抽取并冻结 `ByokApiHarness`、`ProviderTransport`、`ToolGuard`、`ContextBudget`、`CandidateNormalizer` 接口及 Attempt 状态机。 _需求：需求 9_
- [x] 实现 API 模式下的无 CLI 选择算法：CLI 缺失/不可用时直接进入 BYOK Harness，禁止 CLI fallback、安装和进程启动。 _需求：需求 9_
- [x] 将 Provider 快照、凭据引用、SSE Parser 和取消令牌接入 Harness；实现唯一终态和迟到事件丢弃。 _需求：需求 9_
- [x] 将 `ScopedToolGateway` 包装为 ToolGuard，补齐工具允许列表、Schema/路径/大小校验及稳定错误码。 _需求：需求 9_
- [x] 实现上下文预算、旧历史摘要、工具结果摘要/硬截断和 `ContextCompactionEvent` 审计；原始上下文仅保存在本地受控日志。 _需求：需求 9_
- [x] 将工具终态归一化为 LookLift CandidateDraft，接入 CandidateRuntime/Verifier，拒绝 HTML/artifact/未验证参数写入正式版本。 _需求：需求 9_
- [ ] 使用 fake SSE Provider 覆盖 3 轮工具调用上限、未知工具、非法参数、超时、取消、断线、重复终态、预算不足和迟到 chunk。 _需求：需求 9_
- [ ] 将 Harness 事件映射到 Daemon SSE 与前端对话状态，完成无 CLI API Key 模式人工验收。 _需求：需求 9_

说明：当前执行器是 `OpenAiApiAdapter` + `HarnessManager`，没有独立类名 `ByokApiHarness` / `ToolGuard` / `CandidateNormalizer`。`chat.py` 仍按 `runtime_id` 映射到 `get_provider()`，`auto` 可能落到 CLI。

### 8.1 运行输入与选择解析

- [x] 从会话/请求构造冻结的 `AgentRunInput`，绑定 `ExecutionSelection`、Provider 快照、代理图和 Domain Pack。 _需求：需求 9_
- [x] API 模式下检测本机 CLI；无可用 CLI 时选择 `OpenAiApiAdapter`，禁止 CLI fallback。 _需求：需求 9_

现状：新增 `looklift/agent_run_input_codec.py`（`AgentRunInputCodec`/`ProtectedAttempt`，
`create`/`decode`，只存凭据引用与图片哈希，哈希不符或基线/身份不一致抛
`StaleAttemptError`）与 `looklift/agent_assembly.py`（`build_candidate_runtime` /
`make_openai_adapter_factory` / `wire_openai_adapter_factory`，装配候选 Runtime、
快照/凭据解析器与 OpenAiApiAdapter 工厂）；`gui/agent_stream` 新增
`register_openai_adapter_factory` 与按请求显式工厂的 `make_streamer(factories=...)`。
`api.py` 的 stream 路由对 `openai-api` 从会话解析 `image_path` / 基线分析 /
`current_version_id`，经 `wire_openai_adapter_factory` 绑定 ProviderConfigStore 装配
真实工厂（显式传入避免并发覆盖全局表）。新增 `execution_selection.resolve_runtime_id`：
API 模式固定选 `openai-api`，CLI 缺失不是错误，也不回退到 CLI；模式与 Runtime 不一致
直接拒绝。离线测试覆盖 codec、stream 会话装配、API 模式拒绝 CLI fallback。

### 8.2 Daemon 流式出口

- [x] 为 Agent Attempt 增加异步生命周期管理，接入 `RuntimeLifecycleEngine` 和 API Harness。 _需求：需求 9_
- [x] 新增受令牌保护的 SSE stream/cancel 路由，转发统一 Harness 事件并保证唯一终态。 _需求：需求 9_

现状：已新增 `looklift/gui/agent_stream.py`（`build_run_input` / `make_streamer` /
可注入的 Adapter Factory 注册表 / 线程安全取消令牌），`POST /api/agent/runs/<id>/stream`
（`text/event-stream`，逐帧写出、唯一终态、取消/异常补发失败终态帧）与
`POST /api/agent/runs/<id>/cancel`（202，设置同一 manager 的取消令牌）已接入 `ROUTES`；
`server.py` 增加 SSE 流式出口。离线测试覆盖成功流、坏 body 400、阻塞取消与真实 HTTP
流式响应。真实 `openai-api` 路径已在 stream 路由按会话装配工厂并显式传入
（8.1 的 `wire_openai_adapter_factory`），可真实调用。

### 8.3 前端消费与验证

- [x] 前端 Client 增加 Harness SSE 订阅和取消 API（`parseSseBlock` / `streamAgentRun` / `cancelAgentRunStream`）。 _需求：需求 9_
- [ ] 将文本、工具、压缩、候选和错误事件映射到对话状态；使用 fake Adapter/Transport 离线覆盖启动、事件顺序、取消、终态和断线；完成一次 API 模式人工验收。 _需求：需求 9_

现状：`client.ts` 新增 `parseSseBlock`（纯函数，离线可测）、`streamAgentRun`（SSE 订阅，
逐帧映射为统一 Harness 事件）与 `cancelAgentRunStream`；vitest 覆盖事件解析、跨 chunk
重组与终态停止。对话仍走 `/api/chat/step`，尚未把 Harness 事件接到聊天状态机；断线
与 API 模式人工验收待补。
