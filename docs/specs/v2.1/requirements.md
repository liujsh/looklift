# v2.1 需求:左聊天调参

> 状态:草拟,待作者 review。
> 上游文档:[产品需求](../../requirements.md)(定位/路线图)、[头脑风暴与技术栈定案](../../../scratchpad/) → 见
> plan 文件 `fable-1-lr-ps-opendesign-ai-sleepy-pond.md`(一站式主线全部锁定决策、AI 调研、spike)。
> 同迭代:[设计](./design.md) · [任务](./tasks.md)。
> 前置迭代:[v0.5 供应商](../v0.5/requirements.md)(已成 spec)、[v2.0-A 引擎](../v2.0-A/requirements.md)(草拟)、[v2.0-B 三栏 GUI](../v2.0-B/requirements.md)(草拟)。

## 一句话目标

在三栏 GUI 的**左栏**加一层**对话式调参**:用户用自然语言说"想怎么调"(如"把天空调蓝一点、暗部再压一档"),
AI 输出的是**对当前可解释参数的增量修改(parameter delta)**、不是黑盒像素生成——delta 落到右面板绑定的
同一套参数模型上,引擎渲染、展示 diff,AI 再回看渲染结果自我修正(reflection 循环),直到达成用户意图。

**核心哲学(差异化)**:AI 改的是**参数不是像素**。每一步 AI 编辑都是一次可见的滑杆位移,用户能看、能改、能撤销。
这条路有顶会研究背书(JarvisArt/JarvisEvo 的 MLLM→LR 参数 + A2L 协议;**PhotoArtAgent 的 VLM→结构化
JSON 滑杆参数→渲染→reflection 循环,76% 需多轮**——几乎就是本迭代对话循环的概念孪生)。

## 范围边界(本迭代只做左栏对话层)

| 维度 | 本迭代做 | 本迭代不做 |
|---|---|---|
| 输入 | 多轮自然语言对话 + 当前渲染图 | 局部蒙版/框选的对话(bbox,归 v2.x) |
| AI 输出 | 相对当前 analysis 的**参数 delta**(白盒) | 全量重分析、黑盒生图/扩散像素 |
| 应用对象 | v2.0-A 引擎的全局 operator 参数(= 现 `ANALYSIS_SCHEMA` 分片) | 引擎内部实现、右面板 UI 控件、RAW、真 LR 驱动 |
| 循环 | render→diff→AI reflection 多轮自修正、收敛兜底 | 还原度评分闭环(那是 refine 图对图,非文字对话) |

## 用户故事

新增(建议登记进[产品宪法用户故事总表](../../requirements.md#用户故事总表),现有最大 U23):

| 编号 | 用户故事 | 本迭代范围 |
|---|---|---|
| U24 | 我不想逐个拖滑杆,想用大白话告诉 AI "天空更蓝、暗部压一点、整体暖一档",它就帮我把参数调好,而且我能看到它动了哪几个滑杆 | 核心交付:对话→参数 delta→应用→渲染→diff |
| U25 | AI 调完我一句"还是差点意思",它能自己看渲染结果、判断没到位、继续微调,不用我逐项纠正 | 核心交付:reflection 自修正循环 + 收敛兜底 |

依赖既有能力:U13(多供应商,delta 生成复用)、U10(本地渲染预览)、U12(GUI 壳)。

## 验收标准(可勾选)

**确定性闭环(mock provider,不触网,是本迭代 TDD 主线)**

- [ ] 给定 mock provider 返回一个固定 delta,输入一句用户请求 → 系统把 delta 应用到当前 analysis、
      产出新 analysis,新旧 analysis 的 diff 恰好等于该 delta 声明的字段变化,其余字段逐字节不变
- [ ] delta 是**相对当前值的增量**语义可验证:同一句"更蓝一点"连续应用两次,蓝色饱和度累加两次(而非覆盖为定值)
- [ ] 多轮对话:连续 3 轮 mock delta,历史被完整保留,第 N 轮的 delta 基于第 N-1 轮的 analysis,链路确定
- [ ] 一轮完整闭环可端到端断言:用户请求 → delta → 应用 → `render.render()` 产出图 → diff 数据结构生成,全程不触网
- [ ] reflection 收敛:mock evaluator 前两轮返回"未达成 + 修正 delta"、第三轮返回"已达成",循环在第三轮停止并返回最终 analysis;
      mock evaluator 永远返回"未达成"时,循环在硬上限轮次(默认 3)停止,兜底返回**最后一版可用 analysis**、不无限循环
- [ ] 参数校验:mock provider 返回越界值(如 exposure=99)/未知参数路径(如 `basic.nonexistent`)时,
      校验层裁剪/夹到 schema 合法域并丢弃未知路径,应用后 analysis 仍通过现有 `_validate_analysis`

**状态同步与可解释性**

- [ ] chat 应用一个 delta 后,右面板绑定的参数模型读到的就是同一份更新后的 analysis(单一数据源 =
      **前端 editorStore 当前 analysis**;chat_step 返回 delta,前端 applyDelta;chat 移动的就是右面板的滑杆)
- [ ] 反向:用户在右面板手动改了滑杆后再对话,AI 的 delta 基于**手改后的当前值**计算(前端把当前 analysis
      传入 chat_step;chat 与手动共用同一 analysis)
- [ ] 每一步 AI 编辑在对话流里可见(哪些参数、从多少改到多少),且可**撤销**:undo 后 analysis 回到上一版本、
      右面板与画布同步回退(**版本栈/undo 归前端 editorStore,chat 与手动编辑共用同一版本栈**——D2;
      chat 层不自建版本历史)

**多供应商与回归**

- [ ] 对话后端可切 Anthropic / OpenAI 兼容 / Ollama / 本地 claude·codex CLI(复用 [v0.5](../v0.5/requirements.md) provider 层),切换不改对话逻辑
- [ ] 现有 pytest 全部回归通过;对话层新增测试全部用 mock provider,不触网、不调真实 AI

## 非目标

- **不做黑盒生图/扩散**:AI 不直接产像素,只产参数 delta;这是与 ICEdit 这类文字→像素方案的根本分界
- **不做局部/蒙版对话**(bbox、"只调左上角天空")——JarvisArt 的 bbox 值得镜像,但归 v2.x,与全局 operator 一起等分割模型
- **不驱动真 LR/ACR**:JarvisArt 走真 LR 渲染,我们用自有 numpy/numba 引擎(v2.0-A),对话不写 LR
- **不做还原度评分闭环**:那是 `refine` 的图对图自动迭代(v0.3),本迭代是**文字驱动**的对话,收敛判据来自 AI reflection 而非相似度分数
- **不实现引擎内部**(operator/线性光/numba,归 v2.0-A)、**不实现右面板与画布 UI**(归 v2.0-B)——本迭代只做左栏对话层与其到参数模型的接线
- 不做对话记录的持久化/多会话管理/云同步(YAGNI,单张编辑会话即用即弃,未来再议)

## 对前置版本的依赖

| 依赖 | 提供什么 | 缺失时 |
|---|---|---|
| [v0.5 多供应商](../v0.5/requirements.md) | `OpenAICompatProvider`/`OllamaProvider` + 现有 `ClaudeCliProvider`/`AnthropicProvider`,统一 `VisionProvider.complete()`;多供应商是多轮对话 token 成本的缓解手段 | 只能跑 Anthropic 单供应商,多轮费用高;不阻塞对话逻辑本身 |
| v2.0-A 引擎(spec 草拟) | operator 化参数模型(现 `ANALYSIS_SCHEMA` 的分片)+ `render.render(img, analysis)→img` + **`contract.py`**(`param_paths`/`param_bounds`/`resolve_path`,D1:delta 的 path 枚举、clamp 域、落点解析单一来源) | 无渲染无法闭环;delta schema 从 contract 导出,**不再需要事后回填对齐**(D1 已定) |
| v2.0-B 三栏 GUI(spec 草拟) | 左栏容器、右面板绑定的参数模型单一数据源、**editorStore 版本栈 seam**(D2)、中画布 diff 展示位 | 无左栏落点;本迭代交付**纯函数对话引擎** + 到参数模型的接线,GUI 装配 + 版本栈 push/undo 随 v2.0-B |

> v2.0-A / v2.0-B 的 spec 已草拟并完成跨 spec 契约对齐:delta 的 path 枚举/clamp 域从 v2.0-A
> `contract.py` 单一来源导出(D1);状态同步的单一数据源与版本栈归前端 editorStore(D2);`chat_step`
> 为无状态纯函数、由前端 marshal 会话状态传入(D3)。**这些对齐点已在 spec 内敲定,无需再回填。**
