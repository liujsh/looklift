# 实施计划

- [x] 1a. 更新既有规格归属与迁移说明
  - 标注本规格对 `260825-runtime-registry`、`260825-settings-plugin-run-ui` 的增量关系
  - 同步更新 `docs/versions/v2.6/` 权威规格与 `docs/product/architecture.md`，记录 Pydantic-AI 迁移理由、迁移门及 Anthropic/OpenAI-compatible/Ollama 的保留或去留
  - 冻结共享 Capability/Permission 与 Proposal owner，避免重复实现
  - 未完成该文档迁移任务前，不开始 API Harness 代码迁移
  - _需求：需求 1、需求 6_

- [x] 1. 冻结统一 Runtime 与 Harness 契约
  - 定义 Runtime Definition、Provider Snapshot、AgentEvent、Parser 和 Capability 字段
  - 明确 CLI Harness、API Harness、Workflow、CandidateRuntime 的职责边界
  - _需求：需求 1、需求 4、需求 6_

- [ ] 2. 扩展现有 Runtime 生命周期引擎并完成兼容迁移
  - 统一探测、启动、输入、事件归一、超时、取消、回收和错误脱敏
  - 保留旧 Adapter 的兼容工厂，完成生命周期迁移
  - _需求：需求 1、需求 2、需求 6_

- [ ] 3. 接入 Claude Code、Codex、Pi 与 DeepSeek Harness Definition
  - 注册可执行文件、版本探测、模型探测、能力、流格式和 Resume 声明
  - 复用或补齐对应 Stream Parser 与 Fake CLI Fixture
  - 标注 Pi 为正式，其余 Runtime 未通过门禁前保持实验性
  - _需求：需求 2、需求 6、需求 7_

- [ ] 4. 实现 OpenAI API Harness
  - 实现 OpenAI/兼容协议请求构造、SSE/JSON 解析和结构化工具调用
  - 实现 API Key 引用、Provider 配置快照、超时、取消、错误分类和显式重试
  - 增加 HTTPS、DNS 重绑定、重定向、响应/解压大小和凭据保存失败处理；Ollama 仅允许用户明确选择的 loopback 例外
  - _需求：需求 3、需求 4、需求 6、需求 8_

- [ ] 5. 强制接入统一候选 Workflow
  - 让 API/CLI 所有工具调用进入 ScopedToolGateway 与 CandidateRuntime，仅成功的 `candidate_ready` 候选进入 Verifier
  - 覆盖非法 Patch、未知工具、能力不足、晚到结果和正式版本不变
  - _需求：需求 4、需求 6_

- [ ] 6. 实现“模型与提供商”设置页
  - 增加“本机 CLI / API 提供商”双模式和 Query/Command ViewModel
  - 实现 Provider 胶囊选择、API Key/URL/Model 表单、检测、保存和删除
  - 按参考界面实现卡片、分段控件、状态提示、窄屏和主题适配
  - _需求：需求 5_

- [ ] 7. 完成 Fake Runtime Conformance 与安全测试
  - 覆盖五类 Runtime 的探测、启动、事件、工具、取消、超时、恢复和回收契约
  - 覆盖密钥、路径、EXIF、Prompt 注入、权限越权、Provider 降级和晚到隔离
  - 增加 Base URL SSRF、DNS 重绑定、重定向、响应/解压大小及凭据不落日志断言
  - _需求：需求 2、需求 3、需求 4、需求 6、需求 7、需求 8_

- [ ] 8. 完成设置页交互与视觉验收
  - 测试模式切换、表单隔离、密钥不回显、检测失败、刷新和取消
  - 使用 `references/provider-settings-wide.png`（1280×832）和 `references/provider-settings-narrow.png`（390×844），DPR 1，完成浅色/深色主题人工截图验收
  - _需求：需求 5、需求 6、需求 9_

- [ ] 9. 文档与迁移收口
  - 更新架构实况、任务状态、运行时兼容矩阵和离线测试证据
  - 记录未进入默认 CI 的真实 Provider/CLI 和人工视觉验收边界
  - _需求：需求 1 至需求 9_
