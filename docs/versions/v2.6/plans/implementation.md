# v2.6 垂直修图 Agent Runtime 实施计划

## 总原则

按 A–E 五个可独立验收的阶段推进，每阶段以一个可测完整单元提交。先证明内嵌 Harness 和最小候选闭环，再接本地
CLI；先用少量深 Skill 建评测，再扩数量。任何阶段都不得绕过现有参数契约、唯一渲染引擎、正式版本和离线测试隔离。

## v2.6-A：Domain Pack 与可行性门

1. 先写失败测试固定各内容来源、优先级、预算降级、快照和 Hash，再实现 Context Compiler。
2. 使用 Fake Harness 固定 `start/cancel/dispose` 和归一事件，不依赖真实 Provider。
3. 单独做 `pydantic-ai-slim` Spike，验证三类 Provider、代理图、Tool Result 图片、流、取消、打包和许可。
4. 通过则锁定依赖和 Adapter 边界；失败才评估 Pi，记录 go/no-go，不同时继续两套方案。

阶段门：Domain Pack 不能稳定复现，或 API Harness 不能把真实候选图片送回模型时，不进入 B。

### 2026-08-20 可行性门结果

`pydantic-ai-slim 2.32.x` 通过离线 FunctionModel、Mock HTTP 与 Windows PyInstaller 探针：Anthropic、
OpenAI-compatible/Ollama 可构造并序列化 JPEG 代理图，富图片 Tool Result 能进入下一次模型请求，类型化流和协作式
取消可用。冻结探针需显式复制 `genai-prices`、`pydantic-ai-slim` 和 `pydantic-graph` 发行元数据；基于 sidecar 已有
NumPy/Pillow 依赖的 onedir 增量为 21.74 MiB，低于 60 MiB 门限。结论为 GO，不评估或并存 Pi。

## v2.6-B：API 最小闭环

1. 先固定 Tool 请求/响应、稳定错误、Run/Attempt/Lease 和 Candidate Revision 测试。
2. 将现有 Patch、Template 强度和代理渲染组合到 `render_candidate`，不复制参数数学。
3. 完成 Pydantic Tool Binding 和 `finish_candidate`，用 Fake Provider 验证一轮与二轮候选。
4. 加入取消、晚到、预算、基线变化和用户确认边界，再做真实 API/照片人工 Spike。

阶段门：失败、取消和重启前置模拟不能证明正式版本不变时，不接 CLI。

### 2026-08-20 最小闭环结果

已实现内存 `CandidateRuntime`、不可变单线 Revision、相对 Template、严格参数 Patch、真实 JPEG 与基础指标回灌，
并通过 Pydantic AI 的 `render_candidate` 工具和结构化 `finish_candidate` 输出串通零修改、一轮候选和两轮修正。
Run/Attempt/Lease、预算、取消晚到、基线变化和重复终态均由离线测试覆盖；Adapter 对外只发归一事件，Provider
失败不泄漏原始载荷，也不跨 Provider 自动切换。当前完成的是不接 UI、SQLite 和本地 CLI 的 B 阶段自动化范围；
真实模型/照片观感仍待人工 Spike，正式版本入口未接入，因此候选不能保存或导出。

## v2.6-C：CLI Adapter

1. 先用 Fake CLI 固定进程、stdio/事件、取消和终态，再实现 Workspace 与 Scoped Tool Gateway。
2. 第一条真实 CLI 只开放两个 Tool，验证权限模式和候选图片反馈；无法满足最小权限则降为实验性。
3. 用同一 Adapter Conformance Suite 比较 CLI/API 的契约语义，不要求生成相同参数。
4. 完成强杀、超时、Token 撤销、进程回收和敏感环境检查。

阶段门：CLI 不能看到真实候选，或无法关闭内建高权限工具并限制业务工具权限时，不宣称正式 CLI Agent 支持。

### 2026-08-20 CLI 基础与 Pi candidate 结果

已完成随机隔离 Workspace、环境白名单、一次性 Scoped Token、双工具 Gateway、localhost 扩展传输和 Fake CLI/Pi
进程契约。Pi 0.84.x 可显式关闭内建工具、资源发现、项目上下文、会话持久化、遥测与版本检查，只加载 LookLift
随包只读扩展；扩展从同一 Pydantic Schema 注册两个工具，候选事实仍由 Python Runtime 产生。Fake Pi 已按其原生
JSON 事件串通图片反馈、结构化终态、取消和进程回收。当前等级为 `candidate`：尚未用真实 Pi 模型/订阅验证图片
Tool Result 和主观修正，不能勾选正式 CLI 支持或跨 Harness 人工验收。

## v2.6-D：领域内容与评测

1. 先建立 20 个核心 Case 和 rubric，再编写三个 Skill；不要先写大量 Skill 再补评测。
2. 每个 Skill 先跑离线契约和能力边界，再用固定真实任务做消融与盲测。
3. Template 从现有白盒资产补元数据，按无/匹配/不匹配对照验证是否减少修正而不压过用户目标。
4. 固化数据集、运行配置、来源 Hash、失败分类和人工结果；真实 Provider 结果不转成 CI 硬断言。

阶段门：Skill 只改变措辞而不改善结果、轨迹或风险判断时，不进入 builtin；Template 需频繁反向修正时不转官方。

## v2.6-E：UI、恢复和最终验收

1. 接入 Harness/Skill/Template/StyleProfile 选择和数据接收方提示。
2. 展示事实轨迹和候选证据，不展示隐藏思维链；正式提交继续复用现有版本入口。
3. 实现启动 Reconciliation、继续新 Attempt、切换 Harness、最后候选和 stale 处理。
4. 收口前一次运行后端与前端全量验证，再完成真实 CLI/API、照片、隐私、取消和恢复人工验收。
5. 回填 `product/architecture.md` 和 `history/dev-log.md`，根据实际完成证据更新简历表述。

## 验证分层

- 正确性核心：参数/工具、Run 状态、取消恢复、权限和快照按 TDD test-first。
- Provider、CLI 和渲染探索：先做隔离 Spike，再补契约测试锁定结论。
- UI 纯视觉：按实际渲染验收；状态和交互逻辑使用定向测试。
- 默认测试永远离线，真实 API/CLI 和主观观感只进入显式人工或可选集成流程。

## 停止条件

每阶段满足阶段门即停止扩写，进入下一阶段；只在发现职责冲突、安全边界无法实现或可行性门失败时重新讨论架构。
