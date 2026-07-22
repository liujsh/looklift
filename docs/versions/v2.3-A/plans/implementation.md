# v2.3-A 实施计划

1. 先以离线测试固定图库仓库的幂等扫描、标签与缺失文件语义。
2. 实现 Python 数据库、扫描任务和缩略图服务；完成 API 契约测试。
3. 接入 React 图库页与 Studio 打开流程，补前端行为测试。
4. 收口前运行 `python -m pytest -q`、`pnpm test` 与 `pnpm build`，再做图库人工验收。
