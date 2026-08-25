# 实施计划

> 前置依赖：先冻结共享 Proposal、Capability/Grant、AgentEvent、Run Manifest 和 VerifierResult 契约，再实现本阶段 UI。实现顺序为 Context/Memory → Manifest → Runtime/Plugin/Connector → Verifier → UI；UI ViewModel 必须携带契约版本并支持向后兼容。

- [ ] 1. 定义 UI Query/Command ViewModel 契约
  - 固定设置、插件、运行和恢复数据形态
  - _需求：需求 1-4_
- [ ] 2. 实现设置页上下文管理
  - 全局规则、记忆、项目上下文及 Proposal 差异审阅
  - _需求：需求 1_
- [ ] 3. 实现插件页与能力授权
  - Registry 浏览、安装状态、版本历史和 Grant/Revoke
  - _需求：需求 2_
- [ ] 4. 实现运行详情页
  - 轨迹、候选预览、参数差异、指标和 Critique 展示
  - _需求：需求 3_
- [ ] 5. 实现恢复中心与新 Attempt 流程
  - interrupted/stale/failed 状态、基线对比和恢复操作
  - _需求：需求 4_
- [ ] 6. 完成隐私提示、可访问性与交互测试
  - 覆盖取消、拒绝、刷新、晚到和正式版本不变
  - _需求：需求 5_
