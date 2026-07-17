# AGENTS.md —— looklift 开发规范(所有 AI 编码助手必读)

> 本文件是 looklift 仓库对**任何 AI 编码助手**(Codex / Claude Code / 其他)的 binding 约束与文档地图。
> 开工前先读本文件 + 下方「权威文档」。规范约束**优先于**助手的默认行为。
> 维护于 2026-07-17(v2 一站式方向确立)。

## 项目是什么

looklift 是**开源一站式 AI 调色应用**(演进中):AI 逆向出**可解释白盒参数**(Lightroom 风格),
应用内三栏交互(左 AI 聊天调参 / 中画布看效果与原图 diff / 右 LR 风格滑杆面板)直接出成片,
也能导出 LR 预设 / RAW sidecar 给专业工作流。**核心红线:白盒**——AI 改的永远是可解释、可微调、
可学习的参数,不是黑盒像素。详见宪法 [docs/requirements.md](docs/requirements.md)。

## 权威文档地图(改代码前先对齐)

| 文档 | 作用 |
|---|---|
| [docs/requirements.md](docs/requirements.md) | **产品宪法**:定位、白盒双向、用户故事总表、路线图、非目标(锁死技术栈)。范围之争以它为准 |
| [docs/design.md](docs/design.md) | 只记**已实现**的架构实况(实现后回填,不写未来设计) |
| [docs/specs/README.md](docs/specs/README.md) | **迭代 spec 规范**:每迭代一个文件夹(需求/设计/任务三件套)+ 生命周期 + 待决清单 |
| `docs/specs/<版本>/` | 各迭代的详细 spec(当前:v0.5、v2.0-A、v2.0-B、v2.1) |
| `docs/plans/` | 由 spec 生成的**逐步 TDD 实施计划**(步骤级,含代码) |
| [docs/dev-log.md](docs/dev-log.md) | 开发踩坑记录 + 自主决策 + 待作者人工验收清单 |

## Binding 流程规范(不可绕过)

1. **spec 先行**:需求/设计变更**先改 spec 再改代码**。不在没有 spec 的情况下改动架构。
2. **spec → plan → 实现**:开工由 spec 生成 `docs/plans/` 的逐步计划,再按计划 TDD 执行。
3. **TDD**:先写失败测试 → 跑到失败 → 最小实现 → 跑到通过 → 提交。方向/正确性断言先行。
4. **测试离线**:测试**不触网、不调真实 AI/provider**;依赖 `tests/conftest.py` 的 autouse
   `_isolate_env` fixture(假 home / 假 config / 清 `LOOKLIFT_*`),任何测试不得碰真实 `~/.looklift`。
5. **频繁提交**:小步提交;commit message 用中文,**结尾空一行后**只跟实际参与模型的署名:
   `Co-Authored-By: <实际模型名> <该模型对应的 noreply 地址>`。
   **归属信息约束**:commit message、PR 标题/描述、发布说明中禁止写第三方工具生成声明,
   禁止写 Claude 或其他未实际参与者的共同作者/归属信息。Codex 提交只允许使用
   `Co-Authored-By: OpenAI Codex <noreply@openai.com>`;不得追加其他工具品牌宣传尾注。
6. **分支**:不在 main 上直接开发;每个迭代/功能开分支。破坏性 git 操作前先确认。

## Binding 技术栈(2026-07-17 锁定,不走回头路)

- **引擎**:Python(numpy + numba + pyvips),**不换 Rust/C**。可行性已 spike 实证(numba 融合
  代理 9.4ms / 40MP 导出 131ms)。GPU(moderngl/wgpu-py)是 v2.x 可选,非必需。
- **GUI 壳(v2)**:**Tauri + React + TS**,Python 引擎作 **sidecar**(本地 HTTP 复用现有 api.py)。
  v0.4 是 pywebview(将被 v2 React 取代)。
- **许可全程干净,不碰任何 GPL 代码**:参考开源产品(RapidRAW/AlcedoStudio 等)**只学架构不抄码**。
  依赖:numba(BSD)/ pyvips·libvips(LGPL 动态链接)/ rawpy(MIT,LibRaw 取 CDDL)/ Tauri(MIT/Apache)。
- **RAW 输入**:走内嵌 JPEG 预览(rawpy `extract_thumb`),不做全解码+每相机色彩匹配(见宪法非目标)。

## Binding 代码规范(作者硬要求)

- **层次清晰、单文件职责单一、不堆代码山**:每模块一个清晰职责;函数短小分层;新文件超 ~300 行警惕拆分。
  引擎按 operator 组织(参照 v2.0-A design)。code review 时把「文件是否臃肿、层次是否清晰」作显式检查项。
- **引擎是唯一实现**:业务逻辑全在核心模块,CLI 与 GUI 都只是入口/壳,永远共享同一实现。
- **中文**:docstring、注释、用户文案、文档、commit message 全中文(界面全中文,不做 i18n 到 v2.0)。
- **对外契约冻结**:`render.render(image, analysis)->Image`、`score` 等公开签名不随意改;改动需 spec 记录。

## 当前状态与构建次序

- **构建顺序**:v0.4 收尾合入 main → v0.5(供应商)→ v2.0-A(引擎重构)→ v2.0-B(Tauri 三栏)→ v2.1(聊天)。
- **参数模型**:`looklift/analyzer.py` 的 `ANALYSIS_SCHEMA` 是白盒参数单一真相源;v2.0-A 会加一个
  参数契约模块(路径枚举 + 机器可读范围),右面板与聊天 delta 都从它导出,**不手抄**。
- 测试基线:214 passed(v0.4);任何改动不得回归(线性光幅度阈值重标定是唯一例外,需 spec 记录)。

## 红线速查(最容易违反的)

- ❌ 不做黑盒生图/扩散像素改写;不驱动真 Adobe LR。✅ 只改可解释白盒参数。
- ❌ 不抄 GPL 代码(darktable/RawTherapee/RapidRAW/AlcedoStudio 的实现);✅ 只借鉴架构设计。
- ❌ 不在没有 spec 的情况下动架构;❌ 不写触网/调真实 AI 的测试;❌ 不在 main 直接开发。
