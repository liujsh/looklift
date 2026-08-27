# 需求文档

## 简介

将 LookLift 的 Agent 接入层统一调整为声明式 Runtime Adapter 架构：由 Runtime Definition 描述不同 Agent/Provider 的探测、启动、输入、流式输出和能力，由通用引擎负责生命周期与事件归一。首批支持 Claude Code（cc）、Codex、Pi、DeepSeek Harness，以及使用 OpenAI API Key 的 API Harness。

本规格同时定义“模型与提供商”设置页的产品行为、状态和视觉对齐目标。所有模型输出仍必须进入 LookLift 的白盒候选校验、预览和用户确认闭环。

## 范围与归属

本规格是 `260825-runtime-registry` 与 `260825-settings-plugin-run-ui` 的增量扩展，不新增第二个 Runtime Registry 或 UI 真相源。它迁移 v2.6 中 OpenAI-compatible/Ollama API Harness 的实现层（保留 `AgentEvent`、CandidateRuntime、Verifier、Run Manifest 与 Provider 能力契约），并规定迁移、兼容和验收边界。迁移收口后删除不可选择的 `pydantic-api` 兼容 Runtime 与 Pydantic-AI 依赖；既有 Anthropic 官方 SDK Provider 不属于该兼容 Runtime，继续独立保留。

## 需求

### 需求 1 - 统一 Runtime Definition

**用户故事：** 作为平台维护者，我想用统一清单描述 CLI 和 API Runtime，以便新增模型入口时不重复实现 Agent 生命周期。

#### 验收标准

1. 当系统加载 Runtime Registry 时，如果 Runtime ID 重复、入口类型非法或能力声明不完整，那么系统应该拒绝加载并返回脱敏错误。
2. 当注册五类 Runtime 时，系统应该为每个 Runtime 声明版本探测、模型探测、输入传输、流格式、能力、取消、恢复和 MCP 支持情况。
3. 当新增 Runtime 复用已有流格式时，系统应该只新增 Definition 和 Registry 条目，不要求修改通用生命周期引擎。
4. 当 Runtime Definition 声明的权限超过独立 Capability/Permission Gate 时，系统应该拒绝启动，不得由 Definition 扩大权限。

### 需求 2 - CLI Harness

**用户故事：** 作为用户，我想使用本机已安装的 Agent CLI，以便复用自己的登录态、模型和本地工作环境。

#### 验收标准

1. 当用户选择 Claude Code、Codex、Pi 或 DeepSeek Harness 时，系统应该探测可执行文件、版本、认证状态和可用模型，并在不可用时显示安装或配置原因。
2. 当 CLI Runtime 启动时，系统应该通过隔离 Workspace、受限环境和声明式参数传入 Domain Pack、Skill、Reference 与脱敏代理图。
3. 当 CLI 输出声明的 JSONL、JSON-RPC、RPC 或其他流格式时，系统应该由对应 Stream Parser 归一为统一 `AgentEvent`。
4. 当 CLI 被取消、超时、异常退出或产生晚到事件时，系统应该回收进程、撤销令牌并隔离晚到结果，不得污染当前 Run 或正式版本。
5. 当用户选择恢复运行时，如果基线、上下文和权限快照一致，系统应该基于 LookLift 事实日志创建新的 Attempt；Runtime 无原生 Resume 时也不得失去事实恢复能力。原生会话续接仅作为可选优化。

### 需求 3 - OpenAI API Harness

**用户故事：** 作为不想安装 CLI 的用户，我想使用自己的 OpenAI API Key 和模型，以便直接运行 LookLift Agent。

#### 验收标准

1. 当用户填写 OpenAI API Key、Base URL 和模型时，系统应该只在本地安全存储凭据引用或受控密钥，不得将 Key 返回前端查询、模型上下文或普通日志。
2. 当 API Harness 发起请求时，系统应该构造 OpenAI Chat Completions 或 Responses 兼容请求，支持结构化 Tool Call、图片代理图和流式响应。
3. 当 API 返回 SSE、工具调用、错误或限流事件时，系统应该由协议解析器转换为统一 `AgentEvent`，并保留错误分类、取消和超时语义。
4. 当 API Provider 不可用时，系统不得自动切换其他 Provider；只有用户明确选择其他 Runtime 后才能重新启动。
5. 当 API Harness 请求 `render_candidate` 或 `finish_candidate` 时，工具执行必须进入 ScopedToolGateway 和 CandidateRuntime；仅成功产生候选且终态为 `candidate_ready` 时进入 Verifier，无候选终态不得进入 User Review Gate，不得由适配层直接修改正式版本。

### 需求 4 - 统一 Agent Workflow 与候选校验

**用户故事：** 作为摄影用户，我想让不同模型入口共享同一套安全和结果语义，以便更换模型不会绕过保护边界。

#### 验收标准

1. 当任一 CLI 或 API Runtime 接收修图任务时，系统应该共享上下文快照、工具权限、候选状态、错误分类、终态和正式版本边界；模型内部轮次、观察与工具调用顺序由对应 Harness 自主负责，系统不得强制固定 Agent Loop 顺序。
2. 当模型调用未知工具、提交非法 Patch、越过参数范围或引用未授权路径时，系统应该拒绝调用并返回结构化错误。
3. 当候选渲染成功时，系统应该记录预览、参数差异、亮度/裁切指标、不可变 Revision 和事件轨迹。
4. 当用户未确认候选时，系统不得修改正式版本、导出文件或启动批量执行。
5. 当取消、失败、重启或基线变化发生时，系统应该保证正式版本不变，并在 Run Manifest 中保留可审计事实。

### 需求 5 - 模型与提供商设置页

**用户故事：** 作为用户，我想在一个设置页中管理本机 CLI 和 API 提供商，以便清楚选择模型入口并检查是否可用。

#### 验收标准

1. 当用户打开“模型与提供商”页时，系统应该提供“本机 CLI”和“API 提供商”两个顶层模式，并明确当前选择。
2. 当用户打开“本机 CLI”模式时，系统应该展示已检测 Runtime、版本、认证状态、模型列表、能力标签、安装提示和重新扫描操作。
3. 当用户打开“API 提供商”模式时，系统应该展示 Provider 选择、Base URL、模型、最大 Token、连通性检测和保存状态；OpenAI/OpenAI-compatible Provider 显示 API Key，明确选择本地 Ollama 时隐藏 API Key 且不要求填写。
4. 当 API Key 输入框获得焦点、失焦、保存或删除时，系统应该显示本地存储和隐私说明，不得在回显接口中返回完整密钥。
5. 当 Provider 或模型配置无效、检测超时或认证失败时，系统应该显示可操作的中文错误，不得静默保存为可用状态。
6. 当用户切换模式或 Provider 时，系统应该保留未提交表单的隔离状态，不得覆盖另一模式的配置。
7. 当页面以“本机 CLI”或“API 提供商”模式在桌面宽屏、窄屏、浅色和深色主题下渲染时，系统应该分别保持清晰的布局层级、间距、分段切换、Provider 胶囊选择、表单卡片、字体层级和状态提示；桌面浅色模式以已确认的对应状态参考界面为基准进行视觉对齐，并使用 LookLift 自有设计 Token、图标和资源实现。

### 需求 6 - 兼容性与安全

**用户故事：** 作为维护者，我想让不同 Runtime 的行为可测试、可恢复和可审计，以便扩展不会破坏现有候选安全边界。

#### 验收标准

1. 当运行 Fake Runtime Conformance Suite 时，五类 Runtime 的共用契约应该均可离线验证。
2. 当测试涉及 Provider、CLI、取消、晚到、恢复或权限时，测试应该不触网、不调用真实模型、不读取真实用户目录。
3. 当上下文、Skill、Connector 或模型输出包含 Prompt 注入、原图路径、Home 路径、EXIF 或密钥时，系统应该在进入模型或日志前脱敏或拒绝。
4. 当升级 Runtime Definition 或 Provider 配置格式时，系统应该保留旧 Run Manifest 的读取能力，并拒绝不兼容的隐式迁移。
5. 当 Runtime Harness 迁移完成时，系统应该删除 Pydantic-AI Adapter、模型构造、隐藏 Runtime、打包元数据和专属测试；历史 Run 中的旧 Runtime ID 仍作为普通字符串可读取。

### 需求 7 - Runtime 支持等级

**用户故事：** 作为维护者，我想区分正式与实验性 Runtime，以便未完成真实验收的入口不会被误认为稳定能力。

#### 验收标准

1. 当系统展示 Runtime 时，Pi 应标记为正式；Claude Code、Codex、DeepSeek Harness 和 OpenAI API 初始标记为实验性。
2. 当 Runtime 同时通过结构化事件、代理图输入、工具限制、取消回收、事实恢复、Fake Conformance 及真实人工验收门禁时，系统才允许升级为正式。

### 需求 8 - Provider 网络与凭据安全

#### 验收标准

1. 当配置远程 Base URL 时，系统应该要求 HTTPS，解析后重新校验 IP，拒绝 loopback、私网、link-local、CGNAT，并默认禁止重定向。
2. 当接收响应时，系统应该限制响应体与解压后大小，超限即终止并分类报错。
3. 当安全存储不可用或凭据保存失败时，系统不得显示为已配置或可用。
4. 当用户明确选择本地 Ollama 时，系统可受控允许 loopback；请求只在本机处理且不得经外部代理。

### 需求 9 - 设置页视觉基准

#### 验收标准

1. 当进行桌面浅色视觉验收时，系统应该分别以 `references/provider-settings-cli.jpg` 和 `references/provider-settings-api.jpg`（均为 1264×861）作为“本机 CLI”与“API 提供商”状态基准，在 DPR 1 下完成截图对比。
2. 当进行窄屏或深色主题验收时，系统应该以 LookLift 自有设计 Token 验证响应式重排、内容可读性、控件可操作性和主题对比度，不得把桌面浅色参考图误作不存在的窄屏或深色像素基准。
