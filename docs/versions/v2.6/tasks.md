# v2.6 垂直修图 Agent Runtime 任务

## v2.6-A：Domain Pack 与 API Harness Spike

- [x] 固定 `PHOTO_EDITING.md`、StyleProfile、`SKILL.md`、Reference 与 Template 元数据协议。
- [x] 实现 Context Compiler 的来源、优先级、预算、快照和 Hash 契约测试。
- [x] 对 `pydantic-ai-slim` 完成许可、Windows/Tauri 打包、Anthropic、OpenAI-compatible、Ollama、图片、工具、流和取消门。
- [x] 可行性门通过后锁定 Pydantic AI 为唯一内嵌 Harness，不评估或并存 Pi。
- [x] 建立 Fake Harness 和统一 Adapter 最小接口，不接 UI。

## v2.6-B：最小候选 Agent Loop

- [x] 从现有参数契约生成 `render_candidate` 请求/响应 Schema 和 Pydantic Tool Binding。
- [x] 复用 Template 强度、Patch 校验和唯一引擎，建立不可变单线 Candidate Revision。
- [x] 将候选预览图、参数差异、基础指标、错误和剩余预算作为多模态 Tool Result 回灌模型。
- [x] 实现 `finish_candidate` 三种模型终态和独立用户确认边界。
- [x] 建立 Run/Attempt/Lease、取消、晚到和基线冲突的离线测试。
- [x] 用 API Harness 串通 Domain Pack → 候选 → 反馈 → 可选再修改 → 结构化结束。

自动化闭环已完成；真实 API、真实照片和主观效果验收仍属于后续显式人工 Spike，不据此宣称 v2.6 已发布。

## v2.6-C：本地 CLI Adapter

- [ ] 建立隔离 Workspace、Domain Pack 暂存、环境清理和一次性 Scoped MCP Token。
- [ ] 接入第一条已有基础最好的本地 CLI，固定探测、权限、图片反馈、事件、取消和进程回收。
- [ ] CLI 与 API 共用 Tool Schema、候选实现和终态，不复制业务逻辑。
- [ ] 用 Fake CLI 完成 Adapter Conformance Tests，再做真实 CLI 人工集成验收。
- [ ] 明确正式、实验性和不支持 CLI 的能力矩阵及 UI 风险说明。

## v2.6-D：首批 Skill、Template 与 Evals

- [ ] 完成自然人像、商品一致性和高光恢复三个内置 Skill 及必要 Reference。
- [ ] 为每个 Skill 准备少量带适用、禁用和风险元数据的官方候选 Template。
- [ ] 建立 12 个效果 Case 与 8 个安全/工程 Case，默认 CI 使用 Fake Harness 离线执行。
- [ ] 对每个 Skill 完成加载/不加载消融，对 Template 完成无/匹配/不匹配消融。
- [ ] 完成至少一次隐藏模型和配置的人工 Pairwise 盲测，记录已知失败而非只保留成功截图。

## v2.6-E：UI、恢复与收口

- [ ] UI 支持选择 Harness/模型、一个 Skill、一个 Template 和 StyleProfile，并展示实际数据接收方。
- [ ] 展示运行状态、工具事实、候选 before/after、参数差异、Template 强度、不确定项和能力限制。
- [ ] 实现取消、查看最后候选、继续新 Attempt、切换 Harness 和基线 stale 处理。
- [ ] 应用重启时收敛活动状态，基于 Domain Pack 快照和规范化事实恢复，不自动产生费用。
- [ ] 完成真实照片、CLI/API、取消恢复和隐私人工验收，回填架构实况与开发日志。
- [ ] 对成型代码 diff 做一次集中审查，核对文件职责、许可、日志脱敏和简历声明边界。

## 人工验收清单

- [ ] 逆光照片首候选出现可观察问题后，Agent 能依据真实图片/指标修正或正确停止。
- [ ] 同一任务在至少一个本地 CLI 和 API Harness 上均能产生可确认候选。
- [ ] 局部编辑目标在能力不足时明确降级，不用全局参数假装精确完成。
- [ ] 用户越权要求和图片文字注入不能触发正式提交、原图/路径读取或额外工具。
- [ ] 取消、强杀 CLI、渲染晚到、应用重启和正式基线变化均不污染正式版本。
- [ ] 三个内置 Skill 均有版本、消融、失败案例和人工盲测记录。

## 完成条件

五个阶段均有对应自动化或人工证据，且最终行为满足 `requirements.md`、`design.md`、`domain-pack.md` 与 `evals.md`；
文档和实现不把 Skill、Template、Workflow、Tool 或 Harness 混为同一概念。
