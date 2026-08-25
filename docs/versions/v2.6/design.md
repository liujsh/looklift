# v2.6 垂直修图 Agent Runtime 设计

## 设计结论

LookLift 采用薄 Domain Runtime，不在成熟 Harness 上重复实现通用 Agent Loop：

```text
React / Tauri
      ↓
Run Coordinator + Context Compiler
      ↓
┌──────────────────────┬────────────────────────┐
│ Local CLI Adapter    │ Embedded API Adapter   │
│ CLI 原生 Harness      │ pydantic-ai-slim       │
└──────────────────────┴────────────────────────┘
      ↓ 同一 Tool Contract
Scoped Tool Gateway
      ↓
白盒参数契约、Template、渲染、版本引擎
```

Harness 负责模型调用、消息上下文、工具循环、流式输出和当前 Turn 取消；LookLift 负责领域上下文、参数与副作用
校验、候选状态、用户确认、持久化、恢复和评测。Harness 可替换，领域状态和安全终态不可委托。

## 双执行路径

### 本地 CLI

Claude/Codex/OpenCode/Pi 等 CLI 使用自身 Harness。Adapter 只描述探测、启动参数、上下文交付、受限工具注入、事件
解析、取消和可选 Session Resume，不再包一层模型—工具循环。

正式支持的 CLI 必须能：

- 接收组合后的 Domain Pack 和安全代理图；
- 调用 Scoped Tool Gateway；有原生 MCP 时使用 MCP，没有原生 MCP 但能关闭内建工具时可使用随应用只读、经审计的扩展桥；
- 消费 MCP 图片结果或隔离 Workspace 中的候选图片；
- 输出可归一化的运行和终态事件；
- 使用自身 Sandbox/Permission 限制工作目录和内建工具；
- 响应取消并可回收进程。

第三方 CLI 是用户主动安装并信任的外部程序。LookLift 最小化提供给它的数据和业务能力，但不宣称能把任意本地
二进制变成绝对安全沙箱。无法限制高权限内建工具的 CLI 只能列为实验性 Runtime，并在 UI 明示风险。

### 模型 API

API 路径首选 `pydantic-ai-slim` 作为唯一内嵌 Harness，在现有 Python sidecar 内运行。它只承担模型—工具循环、
消息/图片转换、工具参数解析、流事件、用量限制和取消；不引入其通用文件、代码执行或多智能体能力。

实现前通过可行性门验证 MIT 许可、Windows/Tauri 打包、Anthropic、OpenAI-compatible、Ollama、图片 Tool Result、
取消和依赖体积。只有该门失败才用同一用例评估 `pi-agent-core`；不得长期并存两套内嵌 Harness。OpenCode 可以作为
外部 CLI/BYOK Runtime，不作为无 CLI 用户的隐式依赖。

### 统一 Adapter ABI

Adapter 最小接口只有：

```text
start(run_input) → AgentEvent stream
cancel(run_id)
dispose(run_id)
```

运行事件收敛为 `run_started`、`text_delta`、`tool_started`、`tool_completed`、`candidate_created`、`usage_updated`、
`run_finished` 和 `run_failed`。Tool Gateway 的调用记录才是业务事实；CLI 文本流只用于 UI，不作为候选和权限依据。

## Domain Pack

Context Compiler 每次运行解析并快照：

```text
ResolvedDomainPack
├─ PHOTO_EDITING.md       必选、内置领域契约
├─ StyleProfile/LOOK.md   可选、用户确认的风格偏好
├─ SKILL.md               可选、最多一个主 Skill
├─ Template               可选、最多一个白盒参数起点
├─ References             Skill 显式引用的少量稳定知识
├─ Run Context            用户目标、当前参数、代理图和基础指标
└─ Tool Contract          当前可用工具和输出协议
```

具体内容协议见 [`domain-pack.md`](domain-pack.md)。编译结果记录每个来源的 ID、版本、Hash、优先级、实际省略项和
总预算；CLI 与 API 必须消费语义相同的编译结果，不分别维护 Provider Prompt。

冲突优先级固定为：

```text
代码硬策略
> 系统安全边界
> 当前引擎能力事实
> 用户本轮明确目标
> 用户确认的 StyleProfile
> Selected Skill
> Selected Template
> Knowledge Reference
> 模型一般知识
```

## 最小执行工具

### Scoped Binding

`run_id`、`photo_id`、真实路径、正式基线和 Workspace 不进入模型参数。Runtime 在绑定工具或签发一次性 MCP Token
时固定这些事实；每次调用重新检查 Run、Attempt、Lease、基线、预算和权限。

Python 请求/响应类型是 Tool Schema 单一真相源，并生成 Pydantic Tool、MCP JSON Schema、前端类型和 Fake Harness
数据。不得手写两套 CLI/API Tool 契约。

### `render_candidate`

模型只提交现有白盒 Patch 操作、简短目的和首轮可选 Template 强度。Runtime 按顺序完成：

```text
运行与预算校验
→ Template 使用状态
→ Patch Schema、路径、范围和曲线校验
→ 基于当前活动候选生成完整参数副本
→ 唯一引擎渲染
→ 计算当前可可靠生成的基础指标
→ 保存不可变 Candidate Revision
→ 返回 JSON + 候选预览图
```

首轮从正式基线开始，可一次性应用所选 Template 强度；后续候选沿唯一活动链继续修改，不做模型自动分叉。返回
参数差异、亮度/裁切等确定性事实、警告和剩余预算。肤色、主体分割和审美分数等当前无法可靠计算的内容不伪装
成本地指标，由 VLM 查看 before/after 并交给用户判断。

领域错误以结构化 `ok=false` 返回，包含稳定错误码、是否可修正和安全提示；内部状态损坏、数据库或协议异常才结束
Attempt。渲染失败不创建活动候选，上一候选继续有效。

### `finish_candidate`

模型只能结构化结束为：

- `candidate_ready`：引用当前 Run 的最新成功候选，并提供参数目的、复核项、不确定项和限制；
- `no_change_needed`：当前照片已经满足目标；
- `insufficient_capability`：目标超出全局白盒参数能力。

`cancelled`、`interrupted`、`provider_failed`、`tool_failed`、`budget_exhausted`、`policy_rejected` 和 `stale` 由 Runtime
产生，不能被模型包装为成功。`finish_candidate` 永远不提交正式版本、导出或保存长期偏好。

### 用户确认

`candidate_ready` 后 UI 展示 before/after、参数差异、Skill、Template 强度、摘要、不确定项和能力限制。用户可选择
保留版本、继续手调、重新运行或放弃。正式提交继续调用现有版本服务；用户手调归属于用户操作，不伪装成 Agent
决策。

## Agent Run、Attempt 与候选

一个用户目标对应一个 `AgentRun`，每次具体 Harness 执行对应一个 `Attempt`。切换模型、切换 CLI/API、恢复中断
或使用最新 Skill 都创建新 Attempt 或新 Run，不伪造模型 Session 连续性。

Run 冻结照片、正式版本和参数 Hash；Candidate 是不可变 Revision，首版只有单线活动链。每个调用绑定
`run_id + attempt_id + call_seq + run_lease + base_version_id`。任何晚到结果不匹配当前 Lease，只能记录为过期事件，
不能更新活动候选或 UI 状态。

状态收敛为：

```text
created → starting → running → finishing
                    ├→ candidate_ready / no_change_needed / insufficient_capability
                    ├→ cancelling → cancelled
                    └→ interrupted / failed / budget_exhausted / stale
```

## 隔离与隐私

CLI 每次 Attempt 使用独立 Workspace，只包含编译后的领域文件、安全代理图、候选预览和脱敏上下文。Workspace 不含
原图、EXIF、真实图库路径、API key、SQLite、用户 Home、其他照片、未选择 Skill 或可执行脚本。

外部 Provider 继续只接收最长边 2048px、无 EXIF 的代理图。API key 只进入对应 Provider 客户端；CLI 使用自己的
认证，LookLift 不把 API key 注入 CLI 环境。日志不保存图片 Base64、密钥、完整环境、原始路径或隐藏思维链。

一次性 Scoped Tool Token 绑定 Run、Attempt、工具权限和过期时间，只暴露 `render_candidate` 与 `finish_candidate`；运行
完成、取消、超时、基线变化或 Attempt 替换时立即失效。

传输层不是业务真相源：CLI 原生支持 MCP 时优先注入临时 MCP Server；像 Pi 这类明确不内置 MCP、但支持
`--no-builtin-tools` 和自定义 Tool Extension 的 Harness，可加载 LookLift 随包只读扩展，把同一 Pydantic Schema 和
Scoped Token 转发给 Gateway。扩展不得位于可写 Workspace、不得注册第三个工具，也不得复制参数校验或候选逻辑。
无法关闭文件、Shell、代码执行等内建工具的 CLI 只能标为实验性。

## 取消、恢复与冲突

取消先原子写入 `cancelling` 并更新 Lease，再中止内嵌 Harness 或向 CLI 发送原生取消；宽限期后仍未退出则终止
子进程。无法中断的底层渲染可以完成临时文件，但 Lease 不匹配时不得创建候选。

应用启动时把 `starting/running/cancelling` 统一收敛为 `interrupted`，不自动恢复模型或产生费用。用户点击继续后，
校验照片、正式基线、Domain Pack 快照、候选参数和 Harness 可用性，再创建新 Attempt。

恢复基于原目标、Domain Pack 快照、正式基线、最后候选、已应用操作、候选预览和事实摘要；CLI 原生 Session Resume
只是可选优化，不是状态真相源。正式基线变化时 Run 进入 `stale`，撤销 Token 并要求从新版本重新运行，不自动合并
Agent 候选与用户新版本。

Provider 或 Harness 失败后不自动把照片发给另一个服务。用户明确选择切换后创建新 Attempt，并显示新的数据接收方、
模型和可能成本。

## 跨 Harness 一致性

一致性指相同 Domain Pack 语义、Tool Schema、参数校验、候选渲染、正式副作用边界、终态、取消恢复和用户确认
流程；不要求不同模型产生相同参数、轨迹、文本、Token 或成本。

每个 Adapter 使用 Fake CLI/Provider 通过同一契约集：上下文与图片交付、MCP Tool、候选图片回灌、流事件、终态、
取消、超时、非法参数、基线变化和敏感信息脱敏。真实 CLI/API 测试为可选集成或人工测试，不进入默认离线 CI。

## 领域评测

评测协议见 [`evals.md`](evals.md)。结果、轨迹、安全、可靠性和效率分别报告；Skill 与 Template 必须做消融，真实
观感至少包含一次隐藏模型和配置的人工 Pairwise 盲测。模型自评不能单独决定任务成功。

## 停止条件

本文只固定职责、数据流、安全不变量和跨 Harness 语义。具体预算默认值、超时、宽限期、数据库字段和参数 Path
由 Spike 与 TDD 固定，不在 Markdown 穷举。上述契约无矛盾即停止继续架构发散。
