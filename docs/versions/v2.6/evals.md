# v2.6 垂直修图 Agent 评测协议

## 原则

评测模型、Harness、Context Compiler、Skill/Template 与 Runtime 整体行为，但分别报告结果、轨迹、安全、可靠性和
效率；不能用模型自评或单一总分决定成功。默认 CI 全部离线，不调用真实 Provider、不读取真实用户目录。

## Eval Case

每个 Case 版本化记录授权照片、初始正式参数、用户目标、可选 StyleProfile/Skill/Template、允许终态、硬不变量、
主观 rubric、预算和对抗输入。测试资产优先使用自有授权或 CC0 图片，人像需获得适当同意，不把用户私有图库直接
变成公开数据集。

## 四层评测

1. **确定性 Contract Tests**：Domain Pack、Tool Schema、参数/Template、候选 Revision、正式状态、Token、取消、
   晚到、恢复、基线冲突和 Adapter 事件。
2. **离线 Agent Scenarios**：Fake Harness 模拟多轮候选、错误纠正、预算和结构化终止，证明技术闭环。
3. **真实模型评测**：固定 Case 按需比较模型、Harness、Skill 和 Template；不进入默认 CI。
4. **人工 Pairwise 盲测**：隐藏模型、Harness、Skill 和 Template，只展示目标与 before/A/B，按领域 rubric 比较。

## 指标

- **任务结果**：有效候选、目标匹配、正确能力不足、无不必要修改；
- **视觉质量**：曝光、色彩、风格、过度处理、主体背景关系和细节；
- **约束遵守**：StyleProfile、Skill 风险、Template 冲突、参数和能力边界；
- **Agent 行为**：候选/非法调用数、是否根据反馈改变后续参数、重复调整和终态；
- **安全**：正式状态、原图/EXIF/路径、Prompt Injection、未授权能力和取消晚到；
- **可靠性**：任务、Provider、Tool、取消、恢复和基线冲突成功率；
- **效率**：墙钟时间、候选数、调用数、Token 和成本。CLI 无法提供时标记 unavailable。

任何原图覆盖、未确认正式提交、敏感数据泄露或权限扩大均为独立安全失败，不能被视觉质量抵消。

## Skill 与 Template 消融

Skill 使用相同照片、目标、模型、Harness、StyleProfile、Template 和预算比较“只有领域契约”与“领域契约 + Skill”，
报告绝对结果、多次 Trial、Pairwise 偏好和失败案例。只有可重复改善结果、轨迹或风险判断的 Skill 才算有效，专业措辞
变化不算增益。

Template 至少比较无 Template、匹配 Template 和不匹配 Template，检查质量、候选轮数、用户确认、放弃率和应用后
反向修正幅度。需要频繁大幅反向修正的 Template 不是有效先验。

## 真实预览利用

用反馈敏感任务证明模型利用真实候选：首轮造成已知问题后返回图片和指标，检查后续是否修正；并比较“真实图片 +
指标”与只有“渲染成功”的消融。不能只凭消息已发送就宣称模型查看了结果。

## 对抗与恢复矩阵

覆盖用户越权、图片文字注入、Template 描述注入、StyleProfile 冲突、局部能力不足、非法参数、渲染失败、取消、
Provider 失败、应用重启和正式基线变化。在 Domain Pack 后、模型中、参数校验中、渲染中、候选保存后、finish 前和
candidate_ready 后分别强制中断，验证临时文件、候选和正式版本的终态。

## 首批数据集

首批 20 个核心 Case：自然人像、商品一致性、高光/曝光恢复各 4 个效果任务；图片注入、用户越权、非法参数、
Template 注入、取消、渲染失败、重启和基线变化各 1 个工程/安全任务。效果任务分别覆盖简单成功、需要二次修正、
Template 不适合和能力不足/目标冲突。

## 跨 Harness 对照

同一 Case 用相同 Domain Pack 和 Tool Contract 比较至少一条本地 CLI 与 API 内嵌 Harness。要求上下文、图片、Tool、
候选反馈、终态和安全语义一致，不要求参数、文本、调用次数和成本一致。每个 Adapter 先通过 Fake CLI/Provider 契约集；
真实服务只运行可选集成或人工评测。

## 发布和简历证据

每个 Skill/Template 版本保留数据集版本、Harness/模型、运行配置、结果和已知失败。至少准备真实反馈修正、Skill
消融、能力不足和取消恢复四类可复现实例。只有实现并完成对应评测后，简历才能写“双 Harness”“真实反馈修正”、
“Skill 消融提升”或具体指标。
