# v2.6 垂直修图 Agent Runtime 需求

## 定位

把 v2.1 的“单次白盒建议 + 用户触发精修”升级为真正基于渲染反馈的垂直修图 Agent。LookLift 不建设通用
Agent 平台：本地 Claude/Codex/OpenCode/Pi 等 CLI 继续使用其原生 Harness；只有模型 API 时使用应用内嵌
Harness。两条路径接收同一份修图 Domain Pack、调用同一候选工具，并最终停在用户确认点。

本版本的领域壁垒来自可版本化的修图契约、摄影 Skill、用户风格配置、白盒 Template 和真实照片评测，而不是
支持更多 Provider、增加工具数量或在 Harness 之上再写一层固定 Workflow。

## 核心用户故事

| 编号 | 用户故事 | 本期交付 |
|---|---|---|
| U35 | 我只描述修图目标，希望 AI 查看照片、调整参数并依据真实预览决定是否继续 | Harness 自主调用候选渲染工具，结果重新回灌模型 |
| U36 | 我希望本地 Agent CLI 和模型 API 都能使用相同修图能力 | CLI 原生 Harness 与 API 内嵌 Harness 共用 Domain Pack、Tool 和终态 |
| U37 | 我希望选择适合任务的摄影方法，而不是每次使用一段通用 Prompt | 显式选择一个可版本化内置 Skill，或不选 Skill 使用通用契约 |
| U38 | 我希望 AI 遵守我确认的长期风格，但本轮明确要求仍然优先 | 结构化 StyleProfile 编译为只读风格契约 |
| U39 | 我希望已有模板作为可调整起点，而不是覆盖照片的固定答案 | 可选一个白盒 Template，由 Agent 决定是否采用和使用强度 |
| U40 | 我需要知道 AI 实际改了什么、依据什么停止以及有什么限制 | 候选参数差异、预览、摘要、不确定项和能力限制可见 |
| U41 | 取消、崩溃、重启或切换 Harness 不能污染正式版本 | Run/Attempt 持久化、晚到隔离和基于规范化事实恢复 |
| U42 | 我希望 Skill 和 Template 的效果有证据，而不是凭演示判断 | 消融、真实照片、盲测、安全和恢复评测 |

## 产品验收标准

- [ ] Runtime 能把相同版本的领域契约、StyleProfile、Skill、Template、References 和运行上下文编译为可追踪 Domain Pack。
- [ ] 本地 CLI 使用自身 Harness；API 使用唯一内嵌 Harness。两者共享候选工具 Schema、参数校验、终态和用户确认语义。
- [ ] 至少一条 API 路径和一条本地 CLI 路径能查看安全代理图、调用候选工具、获得真实候选预览并完成运行。
- [ ] Agent 可以根据候选图与确定性指标再次修改；Runtime 不强制固定的观察—渲染—评估工具顺序。
- [ ] 首版机器动作收敛为 `render_candidate`，结构化终止收敛为 `finish_candidate`；提交、导出和批量执行不作为 Agent Tool。
- [ ] `render_candidate` 复用现有白盒 Patch ABI、模板强度算法、参数契约和唯一渲染引擎，不产生第二套调色实现。
- [ ] 每个 Run 绑定正式基线，每个候选是不可变 Revision；任何失败、取消、晚到响应和重启都不能移动正式版本。
- [ ] 首版每次最多一个主 Skill 和一个可选 Template；Skill、Template、References 均不能授予工具权限。
- [ ] StyleProfile 只保存用户明确确认的固定维度偏好；本轮明确目标优先于 StyleProfile、Skill 和 Template。
- [ ] 外部模型继续只接收最长边 2048px、无 EXIF 的代理图；CLI Workspace 不含原图、真实图库路径、密钥和数据库。
- [ ] 不满足图片反馈、结构化事件或最小权限要求的 CLI 不列为正式支持 Runtime。
- [ ] 同一评测集同时覆盖任务结果、Skill/Template 增益、真实反馈利用、安全、取消恢复、延迟和成本。

## 首批领域内容

- 通用 `PHOTO_EDITING.md` 修图契约。
- 一个用户可确认的结构化 StyleProfile，并可编译为 `LOOK.md` 视图。
- `portrait-natural` 自然人像 Skill。
- `product-consistency` 商品一致性 Skill。
- `highlight-recovery` 高光与曝光恢复 Skill。
- 每个 Skill 配少量带适用条件、禁用条件和风险说明的官方候选 Template。

首版不以数量为目标；每个内置 Skill 必须完成加载/不加载消融和至少一次人工盲测。

## 非目标

- 不实现多智能体、角色辩论、后台无限反思或通用 Workflow 编排平台。
- 不把本地 CLI 再包进第二个 Agent Loop；不同时维护两套 API 内嵌 Harness。
- 不允许任意 Shell、Python、JavaScript、文件读写或模型直接操作图库。
- 不实现局部蒙版、生成式擦除、内容重绘、人物身份修改或黑盒像素生成。
- 不自动安装、组合或下载第三方 Skill；第三方扩展等待 v2.7 Plugin 权限与签名。
- 不根据未确认对话或照片隐式建立人物、相机或敏感长期画像。
- 不自动跨 Provider 降级；切换 CLI/API、模型或服务必须由用户确认并创建新 Attempt。
- 不以向量数据库、Template 数量或 Prompt 长度作为本版本完成指标。

## 版本完成条件

API 与至少一个本地 CLI 均完成“Domain Pack → 候选渲染 → 真实反馈 → 结构化结束 → 用户确认”闭环；三类首批
Skill 具备版本、失败边界和评测证据；取消、恢复、基线冲突和隐私边界通过自动化与人工验收。未满足时不得在
简历中宣称已完成双 Harness、Skill 消融或生产级 Agent Runtime。
