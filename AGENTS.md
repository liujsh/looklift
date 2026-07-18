# AGENTS.md —— looklift 开发规范(所有 AI 编码助手必读)

> 本文件是 looklift 仓库对**任何 AI 编码助手**(Codex / Claude Code / 其他)的 binding 约束与文档地图。
> 开工前先读本文件 + 下方「权威文档」。规范约束**优先于**助手的默认行为。
> 维护于 2026-07-18(v2 平台化路线确立)。

## 项目是什么

looklift 是**开源一站式 AI 调色应用**(演进中):AI 逆向出**可解释白盒参数**(Lightroom 风格),
应用内三栏交互(左 AI 聊天调参 / 中画布看效果与原图 diff / 右 LR 风格滑杆面板)直接出成片,
也能导出 LR 预设 / RAW sidecar 给专业工作流。**核心红线:白盒**——AI 改的永远是可解释、可微调、
可学习的参数,不是黑盒像素。详见宪法 [docs/product/requirements.md](docs/product/requirements.md)。

## 权威文档地图(改代码前先对齐)

| 文档 | 作用 |
|---|---|
| [docs/README.md](docs/README.md) | **唯一文档导航与存放规范** |
| [docs/product/requirements.md](docs/product/requirements.md) | **产品宪法**:定位、白盒双向、用户故事总表、路线图、非目标。范围之争以它为准 |
| [docs/product/architecture.md](docs/product/architecture.md) | 只记**已实现**的架构实况(实现后回填,不写未来设计) |
| [docs/versions/](docs/versions/) | 各版本需求、设计、任务与同版本实施计划 |
| [docs/history/dev-log.md](docs/history/dev-log.md) | 开发踩坑记录 + 自主决策 + 待作者人工验收清单 |

## Binding 流程规范(不可绕过)

1. **spec 先行**:需求/设计变更**先改 spec 再改代码**。不在没有 spec 的情况下改动架构。
2. **spec → plan → 实现**:开工由版本三文档生成同版本 `docs/versions/<版本>/plans/` 计划,再按计划 TDD 执行。禁止新建 `docs/specs/`、根 `docs/plans/` 或 `docs/superpowers/`。
3. **TDD**:先写失败测试 → 跑到失败 → 最小实现 → 跑到通过 → 提交。方向/正确性断言先行。
4. **测试离线**:测试**不触网、不调真实 AI/provider**;依赖 `tests/conftest.py` 的 autouse
   `_isolate_env` fixture(假 home / 假 config / 清 `LOOKLIFT_*`),任何测试不得碰真实 `~/.looklift`。
5. **分支**:不在 main 上直接开发;每个迭代/功能开分支。破坏性 git 操作前先确认。
6. **计划=契约,不是代码**:`docs/versions/<版本>/` 的三文档与 `plans/` 定的是**架构契约与不变量**
   (接口、数据形态约定、阶段顺序、ABI 边界、许可/技术栈红线),**不预写代码级细节**
   (精确 dtype/shape/字段偏移/nopython 签名/默认值等)。这些细节在**测试里用 TDD 钉死**,
   不在 markdown 里用文字穷举。判断"文档够不够"的标准:**契约清晰、无相互矛盾**即可,
   不追求 prose 覆盖每个实现细节。
7. **文档只审一轮,重型审查只对代码**:计划/spec 文档做**一次一致性检查**即停;
   **对抗式/多视角严格审查只对代码 diff 跑**,不对 markdown 反复 hardening。
   每个文档修订给一句明确的完成条件(如"契约无矛盾即停"),避免无限精化。
8. **纯文档改动不跑全量测试、不建审查包**:全量 `pytest`、review 包只在**有代码改动**时跑;
   对纯 markdown 提交跑全量测试是浪费。
9. **小步、聚焦、勤提交**:优先小而聚焦的任务(单请求上下文小),而非在一个大任务里
   反复扩写。超大上下文 + 超长输出会拖累速度、并增加与模型 API 的连接中断/重连。
   遇到真·架构矛盾(不是"精度不够")才停下问协调层,其余按 spec/plan 直接实现。
10. **执行方式(TDD 分场景 / 单智能体不派子代理 / 批量审查)** —— 流程按活的性质瘦身,不套死:
   - **TDD 分场景**:正确性核心(数学方向、契约解析、numba↔numpy 等价、安全校验——错了会**静默出错**)
     **test-first**;探索性代码(numba 内核等,形状未定)、纯粘合/接线/搬运/UI **code-first**,
     写通一个连贯块后末尾补几个特征测试锁行为。**不逐 5 行红-绿**,那是把 TDD 降级成 ceremony。
   - **单智能体直接实现**:一个能干的智能体做**线性顺序**任务时,**直接在自身上下文实现,不为每任务派新子代理**
     (派子代理要重建上下文、费 token)。不要使用子智能体功能，包括pr pre review等。
   - **批量审查**:在有意义的边界(一组 operator / 内核跑通 / 契约模块完成)自审一次即可;
     对抗式/多视角严格审查只对**成型的代码 diff**,不对半成品、不对每个微任务。
   - **提交粒度**:以"一个可测的完整单元"为单位,不为每 5 行提交。
   - 注:版本 `plans/` 里若出现 `REQUIRED SUB-SKILL: subagent-driven-development` 等字样,那是
     Claude Code 的 superpowers 工作法,**对其他助手(Codex 等)不适用,忽略之**,按本条执行。
11. **视觉类改动流程瘦身(前端样式/布局/UI)** —— "正确"能否被断言决定要不要测:
   - **判据**:改动的"对不对"只能靠**眼睛看渲染**(间距/对齐/颜色/圆角/字号/阴影/响应式手感)→
     **不写测试、不 brainstorm、不生成 plan**,直接改代码,然后**跑起来看效果**(必要时多断点/多主题看)。
   - **带逻辑的才测**:表单校验、状态机、数据流、交互边界、条件渲染分支等——"正确"可用断言表达的部分,
     按 rule 3/10 该 test-first 就 test-first,只测逻辑不测像素(禁止 `expect(margin).toBe('16px')` 这类脆断言)。
   - **反例**:给"把按钮改圆角""调整间距"这种纯视觉任务套 brainstorming→plan→红绿 TDD 全流程,
     是把流程当 ceremony,负收益。superpowers 的"1% 相关就调 skill"不适用于纯视觉改动——
     视觉的反馈闭环是渲染结果,不是测试红绿灯。
   - **成片验收**:样式改完以"截图/实际渲染"为准,不以单测通过为准。


## Binding 技术栈(2026-07-17 锁定,不走回头路)

- **引擎**:Python(numpy + numba + pyvips),**不换 Rust/C**。可行性已 spike 实证(numba 融合
  代理 9.4ms / 40MP 导出 131ms)。GPU(moderngl/wgpu-py)是 v2.x 可选,非必需。
- **GUI 壳(v2)**:**Tauri + React + TS**,Python 引擎作 **sidecar**(本地 HTTP 复用现有 api.py)。
  v0.4 是 pywebview(将被 v2 React 取代)。
- **许可全程干净,不碰任何 GPL 代码**:参考开源产品(RapidRAW/AlcedoStudio 等)**只学架构不抄码**。
  依赖:numba(BSD)/ pyvips·libvips(LGPL 动态链接)/ rawpy(MIT,LibRaw 取 CDDL)/ Tauri(MIT/Apache)。
- **RAW 输入**:v2.3-B 前先过 rawpy 可行性门；通过则全解码进入 float32 管线，未通过则内嵌 JPEG
  预览 + XMP sidecar。外部 AI 永远只接收 2048px 无 EXIF 代理图（见宪法非目标）。

## Binding 代码规范(作者硬要求)

- **层次清晰、单文件职责单一、不堆代码山**:每模块一个清晰职责;函数短小分层;新文件超 ~300 行警惕拆分。
  引擎按 operator 组织(参照 v2.0-A design)。code review 时把「文件是否臃肿、层次是否清晰」作显式检查项。
- **引擎是唯一实现**:业务逻辑全在核心模块,CLI 与 GUI 都只是入口/壳,永远共享同一实现。
- **中文**:docstring、注释、用户文案、文档、commit message 全中文(界面全中文,不做 i18n 到 v2.0)。
- **对外契约冻结**:`render.render(image, analysis)->Image`、`score` 等公开签名不随意改;改动需 spec 记录。

## 当前状态与构建次序

- **构建顺序**:v2.0-A/B 已实现 → 完成 M1-M8 并收口 2.0.0 → v2.1 AI Studio → v2.2 平台外壳 →
  v2.3-A 本地图库 → RAW 门 → v2.3-B 设备导入 → v2.4 模板教学 → v2.5 自动化 → v2.6 插件。
- **参数模型**:`looklift/analyzer.py` 的 `ANALYSIS_SCHEMA` 是白盒参数单一真相源;v2.0-A 会加一个
  参数契约模块(路径枚举 + 机器可读范围),右面板与聊天 delta 都从它导出,**不手抄**。
- 测试基线以最近一次 `docs/dev-log.md` 记录为准；任何改动不得回归（纯文档改动不跑全量测试）。

## 红线速查(最容易违反的)

- ❌ 不做黑盒生图/扩散像素改写;不驱动真 Adobe LR。✅ 只改可解释白盒参数。
- ❌ 不抄 GPL 代码(darktable/RawTherapee/RapidRAW/AlcedoStudio 的实现);✅ 只借鉴架构设计。
- ❌ 不在没有 spec 的情况下动架构;❌ 不写触网/调真实 AI 的测试;❌ 不在 main 直接开发。

## Git 操作与提交信息

**Git 操作策略：**
- **无需许可**: 只读操作如 `git status`, `git diff`, `git log`, `git show` 等
- **需要用户明确指示**: 写操作如 `git add`, `git commit`, `git push`, `git merge`, `git rebase` 等
- 不要自动执行任何 git 写操作
- GitHub PR 描述使用 `gh pr create/edit --body-file`（或 heredoc）而非 `--body "...\n..."`，避免换行符转义问题
- 如果 PR 对应某个 issue，在 PR 描述开头加 `Closes #<issue号>`，PR 合并时 GitHub 会自动关闭该 issue
- 开发过程中发现 bug 或问题但不便立刻修复时，通过 `gh issue create` 提 issue 记录，不要忽略

**提交信息格式：**
- 以下列前缀之一开头，后跟冒号: build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test
- **提交信息主体采用中文**，前缀保持英文
- **PR 标题和描述同样使用中文**
- 首字母小写
- **完成功能/任务时，自动生成提交信息（仅生成文本，不要执行 git commit 命令）**
- **提交描述规则：**
  - 小改动不写描述，避免描述变更细节
  - 仅当摘要行不足以传达完整上下文时才添加描述
  - **禁止在描述中包含 "Generated with Claude Code"、"Co-Authored-By: Claude" 或类似归属信息**
- 可选择在前缀后的括号中包含 scope
- 示例：
  - `feat: 添加语义搜索支持`
  - `fix(executor): 修复 agent loop 中的内存泄漏`
  - `refactor(planner): 将规划逻辑拆分为独立模块`
  - `docs: 更新安装说明`
  - `test(tasks): 添加任务追踪单元测试`
  - `chore: 更新依赖`
