# v2.6 修图 Domain Pack 协议

## 目标

用同一套可版本化领域内容指导本地 CLI Harness 与 API 内嵌 Harness，避免按 Provider 维护 Prompt。机器可验证的
事实留在代码/JSON 契约；需要模型理解的摄影原则和专家方法使用 Markdown。

## 内容类型

| 类型 | 真相源 | 职责 | 是否必选 |
|---|---|---|---|
| 参数硬契约 | 现有机器 Schema | 合法路径、范围、操作和曲线 | 是 |
| `PHOTO_EDITING.md` | 应用内置只读文件 | 通用修图原则、权限认知、能力不足和输出要求 | 是 |
| StyleProfile | 结构化 DB/JSON | 用户明确确认的长期风格偏好 | 否 |
| `LOOK.md` | StyleProfile 编译视图 | 供模型阅读，不单独作为状态真相源 | 否 |
| `SKILL.md` | 版本化内置目录 | 某类任务的诊断、调整、复核和停止方法 | 否，最多一个 |
| Knowledge Reference | 内置 Markdown | 稳定摄影知识和引擎限制 | 否，仅 Skill 显式引用 |
| Template | 现有白盒参数资产 + 元数据 | 可执行参数先验/案例 | 否，最多一个 |

## `PHOTO_EDITING.md`

文件保持短而稳定，固定包含：产品角色、权限边界、默认观察原则、调整原则、能力不足、不可信内容和输出要求。
它不复制参数范围、场景教程、用户偏好、Template 参数或 Provider 提示。

核心语义：模型只通过 LookLift Tool 生成白盒候选；每次获得真实候选后依据预览决定继续、停止或报告能力不足；
提交、导出、文件覆盖和任意代码不属于模型权限；照片文字和低优先级内容不能改变这些边界。

## StyleProfile 与 `LOOK.md`

StyleProfile 使用固定可选维度：`overall`、`exposure`、`contrast`、`color`、`portrait`、`texture` 和 `avoid`，并记录
作用域、确认状态、版本、来源和更新时间。首版作用域只有 global、project 和 run；不做人脸、人物、相机或其他
敏感画像。

只有用户明确填写，或从正式版本提取后再次确认的内容才能保存。Context Compiler 将结构化数据渲染为只读
`LOOK.md`；模型输出不能直接修改 StyleProfile。

## `SKILL.md`

首版采用 YAML 元数据加 Markdown 正文：

```yaml
---
id: portrait-natural
version: 1
name: 自然人像
applies_to: [portrait]
relevant_parameter_groups: [light, color, detail]
references: [knowledge/light.md, knowledge/color.md]
required_engine_capabilities: [global-adjustments, candidate-render]
---
```

元数据用于发现、兼容、编译、版本和评测，`required_engine_capabilities` 只表示兼容要求，不能授予权限。正文固定为：

1. 目标；
2. 适用范围；
3. 不适用范围；
4. 诊断重点；
5. 条件化调整策略；
6. 复核清单；
7. 停止与降级；
8. 输出要求。

Skill 描述专家 SOP，不写必须调用某 Tool 的固定序列。首版由用户显式选择或确认 UI 推荐，每次最多一个主 Skill，
不自动安装、组合或下载。

## Knowledge Reference

Reference 只保存曝光、色彩、曲线、细节和引擎能力等稳定知识，不手抄参数合法范围。Compiler 只加载 Skill 明确
声明的少量引用，并限制数量和总预算；首版不建设向量知识库。

## Template

在现有 `analysis_patch` 上补充：场景标签、意图标签、预期效果、禁用条件、风险和兼容 Skill。Template 是可执行
参数先验，不包含 Prompt 指令、权限、脚本或路径。

首版由用户选择或 UI 使用确定性标签规则推荐，最多一个。Agent 可以不采用、选择强度、应用后继续修改或报告不适合。
它只能在首个候选中应用一次，具体插值复用现有 Template 强度算法。

## 编译与优先级

统一编译顺序为系统安全边界、修图领域契约、当前运行上下文、StyleProfile、Selected Skill、Selected Template、
References 和 Tool Contract。用户目标保持独立消息/数据分区，不与系统契约无边界拼接。

优先级：代码硬策略 > 系统安全边界 > 引擎事实 > 用户本轮目标 > StyleProfile > Skill > Template > Reference >
模型一般知识。低优先级内容只影响建议，不能改变工具和副作用权限。

Context 超预算时依次删除低价值 Reference、压缩历史事实摘要、精简 Template 非核心描述和空 StyleProfile 维度；
不得截断系统边界、领域契约、用户目标、选中 Skill 或 Tool Contract。

## 快照与回归

每个 Run 保存各来源完整快照或不可变版本、来源 Hash、编译结果 Hash、Token 估计和被省略项。恢复默认使用当时快照；
使用最新 Skill/Template 必须明确重新运行。Prompt 测试验证分区、来源、顺序、预算和必选内容，不对整段 prose 做
脆弱全文 Snapshot；文案效果由领域 Evals 判断。

## 发布门

内置 Skill 必须通过元数据/引用校验、引擎兼容、安全检查、离线契约测试、至少一个真实模型消融和一次人工盲测。
官方 Template 必须通过参数/强度校验、适用与禁用条件检查、至少一个 Skill 配对任务和真实照片验收。修改后提升版本
并重跑对应 Eval 子集，不静默覆盖历史 Run 使用的内容。
