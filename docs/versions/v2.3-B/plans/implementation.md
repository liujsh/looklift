# v2.3-B 实施计划

1. 先为 manifest、筛选、复制校验和取消状态写 Python 测试，确认失败。
2. 实现 `device_import.py` 的纯函数和后台任务。
3. 增加 API handler、路由和 TypeScript client 类型/方法。
4. 以 code-first 接入 ImportPage，补交互测试并运行定向检查。
5. 收口运行 `pytest`、`pnpm test`、`pnpm build`，检查 diff 后提交并创建中文 PR。
