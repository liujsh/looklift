# v2.5 Skill 增量需求

## 目标

在仓库内建立首批可按需加载的 Codex 兼容 AgentSkill，先验证摄影领域知识工作流，再接入 Looklift 的执行能力。

## 术语与边界

- **AgentSkill**：以 `SKILL.md` 为入口的指令、参考资料和工作流包，供 Agent 按需加载。
- **Capability**：由 LookLift 引擎执行并校验的机器能力；本期不实现，统一进入 v2.6 Agent Runtime。
- **Template**：风格、版式或输出规格的内容资产；本期只作为 Skill 参考资料。
- **Workflow/Automation**：未来编排 Skill/Capability 的执行计划；不改变现有 v2.5 自动化数据结构。
- **Plugin**：未来分发 Skill、Template、Integration Provider 或 MCP Server 的安装包；本期不实现。
- **Integration/MCP**：未来的外部连接实例及工具协议；本期不实现。

首批 Skill 只输出知识、计划和验收清单，不执行任意 Python、Shell 或 JavaScript，不生成像素，不绕过白盒参数和渲染边界。

## 首批 Skill

| Skill | 职责 |
|---|---|
| `skill-editor` | 通过对话创建、检查、拆分和修改 Skill 草案；保存前要求宿主确认 |
| `photo-abstract-editorial` | 抽象摄影/编辑风格的意图拆解、诊断、编辑计划和预览评审 |
| `zine` | Zine 主题、照片顺序、页数、网格、留白、出血和输出检查计划 |

## 目录契约

每个 Skill 位于仓库根目录 `skills/<name>/`，包含 `SKILL.md`、`agents/openai.yaml`，以及按需加载的一层 `references/` 文件。`SKILL.md` frontmatter 必须包含与目录一致的 `name` 和明确触发场景的 `description`。

## 验收标准

- 三个 Skill 均通过官方 `quick_validate.py`。
- frontmatter、目录名、引用路径和 `agents/openai.yaml` 一致。
- Skill 主文档保持精简，细节放在一层 references 中。
- `skill-editor` 输出结构化草案，不直接写入用户目录。
- `photo-abstract-editorial` 输出“诊断 → 计划 → 参数建议 → 预览评审”，不虚构已完成渲染。
- `zine` 输出主题、照片选择、页数/版式、排序和输出检查清单。
- 三个 Skill 均明确禁止任意代码、黑盒像素修改和越过 LookLift 白盒参数契约。
- 验证过程不触网、不调用真实模型、不读取真实用户目录。

## 非目标

本期不做应用内 Skill Registry、机器可读 Capability contract、Skill 执行器、Skill Editor UI、插件安装、MCP Server、外部 Integration、Zine PDF 排版引擎或 React 导航调整。Skill 的受控执行边界见 [v2.6 设计](../v2.6/design.md)。
