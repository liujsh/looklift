# 实施计划

- [x] 1. 定义 VerifierResult、FailureClass 与 CritiquePolicy
  - 固定硬门禁、证据和指标字段
  - _需求：需求 1、需求 2_
- [x] 2. 实现 Contract、Domain、Render Verifier
  - 接入参数、权限、Skill 和渲染指标校验
  - _需求：需求 1、需求 2_
- [x] 3. 实现 Critique 与 User Review Gate
  - 生成解释、预览和用户确认事件
  - _需求：需求 2、需求 5_
- [x] 4. 实现版本化 Eval Dataset 与 Runner
  - 支持 20 个离线 Case 和三组消融开关
  - _需求：需求 3_
- [x] 5. 实现多阶段评测报告
  - 区分自动化、真实模型和人工盲测状态
  - _需求：需求 4_
- [x] 6. 编写安全与回归测试
  - 覆盖取消、晚到、越权和正式版本不变
  - _需求：需求 1-5_
