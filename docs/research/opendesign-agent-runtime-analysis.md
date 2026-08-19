# OpenDesign Agent Runtime 源码分析与 LookLift 借鉴边界

> 调研对象：[`nexu-io/open-design`](https://github.com/nexu-io/open-design)。调研日期：2026-08-19。
> 本文只提炼公开源码的架构思想，不复制其代码或文本；正式产品契约见 `versions/v2.6/`。

## 结论

OpenDesign 最值得借鉴的不是“用 AI 生成网页”，而是它没有再造一套通用 Agent。Claude Code、Codex、
OpenCode、Pi 等现成 CLI/Harness 负责模型调用、工具循环、上下文、权限、恢复与取消；本地 daemon 负责运行时
探测和适配、领域上下文组装、工作区、统一事件流、预览、产物和持久化。

它的设计垂域优化主要发生在 Harness 上下两侧：用 `DESIGN.md`、functional skill、craft 规则、模板与插件管线
约束生成过程，再用真实 HTML/CSS/JS、沙箱预览和 critique/evaluator 形成反馈。公开源码中未见专用设计模型
训练或微调；这是模型无关的上下文工程、工具工程和评测工程。

LookLift 应借鉴“委托通用循环 + 做厚领域层”，但不能照搬代码 Agent 的文件系统权限。修图运行时只应向
Harness 暴露类型化 Capability 和不透明资源句柄，原图路径、Shell、任意文件写入和正式提交不能交给模型。

## Runtime 源码分析

### 完整循环委托给已有 Harness

OpenDesign 的 [Agent adapters 文档](https://github.com/nexu-io/open-design/blob/main/docs/agent-adapters.md)
明确把模型调用、工具使用、上下文管理、权限处理、恢复和取消委托给用户已有的代码 Agent CLI。OpenDesign
只探测 CLI，提供 skill、prompt 与受管工作目录，并把输出转为 UI 可消费的事件。

### Adapter 是数据定义，执行引擎共用

每个 CLI 主要由一份 `RuntimeAgentDef` 描述：可执行文件、版本参数、启动参数、输入方式、流格式、事件解析器、
图片支持、认证探测和模型枚举等。通用引擎负责探测、启动、调用、取消与终态收敛。源码可见
[runtime 共用模块](https://github.com/nexu-io/open-design/tree/main/apps/daemon/src/runtimes) 与
[CLI 定义](https://github.com/nexu-io/open-design/tree/main/apps/daemon/src/runtimes/defs)。

Claude stream JSON、JSON event stream、ACP JSON-RPC、Pi RPC 等协议最终归一为 thinking、tool-call、
tool-result、text-delta、file-write、error、done 等事件，上层 UI 和存储不依赖某个 CLI 的私有格式。

### API/BYOK 也走 Harness 语义

BYOK 路径会把 API 凭据和模型配置交给 OpenCode 兼容运行时，由 OpenCode 承担模型—工具循环；退化到 plain
stream 时只接受受约束的完整 artifact 块。“CLI 模式”和“API 模式”因此不应维护两套行为不同的 Agent。

### Skill 有运行生命周期

根据 [Skills 协议](https://github.com/nexu-io/open-design/blob/main/docs/skills-protocol.md)，运行前解析主 Skill、
被提及的 Skill 与插件 Skill，把必要正文组成上下文，并把 Skill 目录复制到项目 `.od-skills/` 暂存区。
references 和 assets 不全部内联，Agent 需要时再读；复制而非软链接也避免 Agent 修改 Skill 源。

这比“仓库里放 Markdown”多了发现、选择、隔离、注入、引用解析和轨迹。但 Skill 文本不能授权工具；部分旧
`capabilities_required` 元数据并不负责运行时权限，真正授权仍属于插件/Runtime 层。

## 原型设计垂域优化

1. [Design systems](https://github.com/nexu-io/open-design/tree/main/design-systems) 用 `DESIGN.md` 固定品牌与视觉
   语言契约，配合 tokens、组件、资产和来源证据，减少跨轮漂移。
2. [`design-brief` Skill](https://github.com/nexu-io/open-design/blob/main/skills/design-brief/SKILL.md) 把模糊意图
   压缩为 palette、accent、typography、display、layout、mood、density、constraints 八个维度，并定义受限词表、
   默认值与 token 解析。这类“领域状态空间 + 缺省策略 + 可验收输出”才是高含金量 Skill。
3. functional skills、rendering templates、design systems 和 plugins 相互分离。插件能组装 discovery、plan、
   generate、critique 阶段与有硬上限的 dev loop，见 [Plugins 规格](https://github.com/nexu-io/open-design/blob/main/docs/plugins-spec.md)。
4. CLI 写真实前端文件，daemon 管 artifact 与沙箱预览，领域反馈来自可运行产物，不只是模型自评。
5. 优化深度并不均匀：Runtime 和 `design-brief` 扎实，但也有正文较薄、主要指向上游安装包的 Skill；部分视觉
   diff、响应式、无障碍与品牌 evaluator 仍是后续项。Skill 数量不能等于垂域深度。

## LookLift 借鉴映射

| OpenDesign 方法 | LookLift 对应设计 | 修图域差异 |
|---|---|---|
| 通用循环委托 CLI/Harness | 外部 CLI Harness + 内嵌 Harness | 两者共享事件与 Capability ABI |
| 数据化 runtime definition | 数据化 Harness 能力描述与探测 | 不透传通用 Bash/文件写入 |
| 归一化事件流 | 统一计划、调用、结果、候选与终态 | 不保存隐藏思维链 |
| `DESIGN.md` | 用户明确确认的长期风格契约 | 不隐式推断敏感偏好 |
| functional skill | 摄影场景 Skill/SOP | 带触发、观察、允许能力、风险与 rubric |
| design template | 参数模板/Look | 模板是数据，不冒充 Skill |
| sandbox preview | 白盒引擎候选渲染 | 候选不得自动提交 |
| critique/dev loop | 指标 + 领域 rubric + 有界复核 | 模型自评不能是唯一 grader |

## 无本地 CLI 时的 Harness 选型

| 方案 | 优点 | 对 LookLift 的主要问题 | 结论 |
|---|---|---|---|
| `pydantic-ai-slim` | Python 同进程、类型化工具、模型无关循环、流事件、用量限制、审批/延期工具、多模态 | 需要把现有 provider 与事件迁移到统一适配层，并自行保有产品持久化 | **首选内嵌 Harness** |
| OpenCode | provider、Session、MCP、SDK/Server 完整；OpenDesign 已验证 BYOK 路径 | 代码 Agent 和独立服务偏重，需禁用大量文件/Shell 能力，增加进程与配置面 | 作为外部 CLI/BYOK Runtime，不默认捆绑 |
| `pi-agent-core` | MIT、轻量、工具循环和事件流清楚，provider 与图片支持较全 | TypeScript/Node 给 Python sidecar 增加运行时和打包复杂度 | Python 方案可行性门失败时的备选 |
| 自研循环 | 完全可控、依赖少 | 会重复处理 provider 差异、工具协议、部分响应、取消、上下文和边界错误 | 不选，除非第三方方案均无法通过门 |

选择依据不是功能数量，而是最小权限、同进程领域工具调用、Windows 桌面打包和维护成本。最终依赖在实现前通过
离线可行性门锁定；LookLift 自己的 Capability、策略、运行记录和恢复语义不委托给任何第三方 Harness。

## “AI Native”的判断

当前最准确的定位是：**AI-first 的垂直修图应用，具备受控 agentic editing loop**。

它不是浅层 AI 集成：AI 已进入核心编辑流程，能把意图变成参数并读取真实预览后精修。但移除 AI 后，白盒引擎、
滑杆、模板、导出和批处理仍是可用产品；当前 `chat_step` 也缺少统一 Harness、工具选择、持久运行、Skill 生命周期
和领域 Agent 评测。因此现在直接称“成熟 AI Native Agent”会被追问击穿。

完成 v2.6 后，满足下列证据才适合称 **AI-native vertical photo-editing agent**：

1. 自然语言目标成为主要任务入口，Runtime 能在受控能力内选择观察与动作；
2. CLI 与 API 模型通过统一 Harness ABI 运行，可取消、恢复、审计和降级；
3. Skill、风格契约、模板和 Capability 分层，并能证明它们改变任务结果；
4. 用摄影师参与定义的任务集评测结果、轨迹、安全、成本和恢复；
5. 手动滑杆是人在回路与精修出口，而不是另一套割裂产品。

## 对其他垂域的可迁移价值

真正可迁移的不是“会调色”，而是领域状态与动作本体、专家 Skill/SOP 编译、副作用分级治理和领域评测。
[Sierra Agent SDK](https://sierra.ai/product/agent-sdk) 与 [Decagon AOP](https://decagon.ai/modules/aops)
也强调目标/guardrail、可组合 Skill 或操作流程、上下文、工具与人工升级；Anthropic 的
[Agent 评测方法](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) 强调模型和 Harness 整体评测，
任务应由领域专家参与定义。共同壁垒是受控执行环境、专家流程和持续评测，不是更长的系统提示词。

## 停止条件

源码事实、借鉴边界与 v2.6 决策能够互相解释且无矛盾即停止；不继续按 Skill 数量做表面竞品盘点。
