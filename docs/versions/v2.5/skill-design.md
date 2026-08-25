# v2.5 Skill 增量设计

## 加载模型

Agent 先读取 Skill 的 `name`/`description` 元数据，触发后再读取 `SKILL.md`，只有任务需要时才读取一层 `references/`。主文档只保留触发边界、工作流和输出契约，避免重复通用知识。

## 输出模型

Skill 输出面向 Agent 和用户的结构化 Markdown，包含目标、假设、步骤、参数建议、限制和验收项；不声称调用了 LookLift 渲染器，除非宿主实际提供并确认了对应工具结果。

## 兼容性

Skill 采用 Codex 官方目录约定；`agents/openai.yaml` 提供界面显示元数据。v2.6 接入 LookLift 时通过独立 Capability Registry 执行动作，不把当前文档包当成渲染执行器。

## 外部参考

GitHub 候选仅用于比较 Skill 组织和表达方式。许可证未确认前不复制任何代码、文本、素材或仓库结构；不把外部仓库作为运行时依赖。
