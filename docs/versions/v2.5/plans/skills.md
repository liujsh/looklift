# v2.5 Skill 首批实施计划

1. 使用官方 `skill-creator` 的 `init_skill.py` 生成三个标准目录。
2. 编写精简 `SKILL.md`、一层参考资料和 `agents/openai.yaml`。
3. 运行 `quick_validate.py`，检查 frontmatter、命名、引用和元数据。
4. 用离线文本案例检查三个 Skill 的触发边界、结构化输出要求和禁止事项。
5. 记录本期只新增文档 Skill，不改渲染、自动化、插件、MCP 或前端。

完成条件：三个 Skill 可被 Codex 发现并加载，契约无矛盾即停止；后续执行能力进入 [v2.6 Agent Runtime](../../v2.6/plans/implementation.md)。
