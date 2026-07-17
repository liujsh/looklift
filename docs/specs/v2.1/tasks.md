# v2.1 任务:左聊天调参

> 状态:草拟,待作者 review。同迭代:[需求](./requirements.md) · [设计](./design.md)。
> 任务按依赖顺序排列;**TDD:mock provider 的确定性闭环测试先行**;人工验收项集中放最后「人工验收」区。
> 前置门槛:v2.0-A 引擎(`render.render` + operator 参数模型 + **`contract.py`** 参数契约,D1)、
> v2.0-B 左栏容器 + 右面板单一数据源 + **editorStore 版本栈 seam**(D2)须先就位(见 [requirements.md 依赖表](./requirements.md#对前置版本的依赖))。

## T1 delta schema 与校验(纯函数,最先做)

- [ ] `chat.py` 定义 `DELTA_SCHEMA`、`REFLECT_SCHEMA`([design.md](./design.md#delta-schema生成阶段结构化输出))
- [ ] path 枚举与范围**从 v2.0-A `contract.py` 导出(D1,不手抄)**:白名单 = `contract.param_paths()`、
      clamp 域 = `contract.param_bounds(path)`;覆盖 `basic.*`/`hsl.<color>.*`/`color_grading.*`/`effects.*`;
      **不含 `tone_curve`**(`param_paths()` 本就不含)
- [ ] `_validate_delta(delta)`:复用 [`_validate_analysis`](../../../looklift/gui/api.py) 思路——
      白名单 path(`param_paths()`)、value 必数值、按 `param_bounds()` clamp、丢弃未知 path
- 验收:单测覆盖合法 delta 通过、越界值被夹取(到 `param_bounds`)、未知 path 被丢弃、非数值被拒;
      曲线 path(如 `tone_curve.*`)不在白名单;不触网

## T2 apply_delta(纯函数)

- [ ] `apply_delta(analysis, delta) -> new_analysis`:`add` 增量 / `set` 定值;**落点解析用
      `contract.resolve_path`(D1)**——封装 hsl 数组按 color 段定位/补零、`color_grading.global_`
      下划线映射,apply_delta 不自己手写这两处;应用后过 `_normalize`
- [ ] 输入 analysis 不被就地篡改(返回新对象),便于前端版本栈与 undo(版本栈归前端,D2)
- 验收:单测——`add` 累加语义("更蓝一点"连用两次饱和度加两次)、`set` 覆盖、未提及字段逐字节不变、
      新旧 diff 恰等于 delta 声明;`hsl.blue.saturation` 命中数组项、`color_grading.global.hue` 落到 `global_` 键

## T3 无状态会话 marshal(D3;版本栈/undo 归前端,D2)

- [ ] **`chat_step` 设计为纯函数**:入参 `(history, current_analysis, image_path, user_text, backend, max_reflect)`,
      **不在 sidecar 里持有有状态 `ChatSession`**;会话状态(history、当前 analysis、版本栈)由前端 editorStore 拥有、每轮传入
- [ ] `Turn` 只作**数据结构**(用户话 + 应用的 delta 列表 + note + reflection 轨迹),前端持有并回传;
      history 摘要派生(文字 + 当前 analysis 快照,供无状态重放)
- [ ] **不实现独立版本栈/undo**:chat_step 只返回 delta + 轨迹;push 版本与 undo 由前端 editorStore 负责(D2)
- 验收:单测——同一 `(history, current_analysis)` 输入两次 chat_step 结果确定(无跨调用隐藏状态);
      history 摘要按输入组装;**无 sidecar 内 `analysis_versions` 版本栈**(版本栈断言归 v2.0-B T7b)

## T4 provider 接线(无状态重放,复用 v0.5 多供应商)

- [ ] 组装生成阶段 blocks(history 摘要 + 当前 analysis + 当前渲染图 + user_text),调 `get_provider(backend).complete(system, blocks, DELTA_SCHEMA)`
- [ ] **渲染图走临时文件路径(D7)**:当前渲染图写到 `mkdtemp` 临时目录(复用 [`autorefine`](../../../looklift/autorefine.py) 的 mkdtemp+try/finally 清理模式),把**路径**放进 blocks;**`providers.py` 零改动**(不新增"接受内存 bytes"入口)
- [ ] provider 层**零改动**;backend 可取 `auto|cli|api|openai_compat|ollama`([v0.5](../v0.5/design.md))
- 验收:mock provider 返回固定 delta,断言 blocks 组装正确(图为文件路径)、schema 传入正确、解析出 delta;四种 backend 走同一路径(参数化测试);临时文件用后清理;不触网

## T5 一轮闭环:请求→delta→应用→渲染→diff

- [ ] `chat_step` 串起 T1-T4 + `render.render()`(v2.0-A)+ diff 数据结构生成
- [ ] delta 生成后经 `_validate_delta` → `apply_delta` → push 版本 → 渲染 → diff
- 验收:mock provider 下端到端断言一轮完整闭环(请求→delta→新 analysis→渲染图→diff),全程不触网

## T6 reflection 自修正循环(工作副本 + 临时文件,D3/D7)

- [ ] reflection 在 `current_analysis` 的**工作副本**上迭代(不产生对外版本栈,D3);每轮**重渲染 proxy 分辨率**、
      写临时文件、路径传 `complete(..., REFLECT_SCHEMA)` 拿 `{done, reason, next_delta}`;未 done 且 next_delta 非空则再 apply+render
- [ ] 硬上限 `max_reflect`(默认 3);到顶未收敛兜底返回**最后一版可用 analysis(净 delta)** + 明示提示
- [ ] reflection 重渲染用 **proxy(非 40MP)**;临时目录用后 try/finally 清理(D7)
- 验收:mock evaluator 脚本化——前两轮"未达成+delta"、第三轮"达成"→ 第三轮停;永远"未达成"→ 上限停且兜底返回最后版本;
      reflection 每步在工作副本上进行、最终只把净 delta 交回(不在 sidecar 持有版本栈);不无限循环、不触网

## T7 状态同步接线(chat = 移动右面板滑杆;版本栈归前端,D2)

- [ ] `chat_step` 返回的 delta 由**前端 editorStore `applyDelta`** 应用到**同一 analysis 单一数据源**
      + push **前端版本栈**(v2.0-B T7b seam)+ 同一变更事件(触发右面板重读 + 中画布防抖代理渲染);
      **chat 与手动编辑共用这一个版本栈**(D2),chat 层不自建历史
- [ ] 反向:手改滑杆后对话,前端把当前(手改后)analysis 传入 chat_step,delta 基于它计算
- 验收:集成测——chat 应用 delta 后右面板参数模型读到同一份;手改后再 chat 的 delta 基于手改值;
      undo(前端版本栈 pop)后右面板与画布同步回退;chat 与手动编辑在同一条撤销历史上

## T8 边界与错误处理

- [ ] 用户口头要求曲线/局部调整时,回中文提示(曲线走右面板、局部归后续版本),不静默失败
- [ ] provider 常见错误(鉴权/超时/服务未启)沿用 v0.5 中文提示,不抛原始堆栈
- [ ] 本地 CLI 多轮延迟:对话流逐轮进度反馈
- 验收:单测覆盖越界/未知 path 已在 T1;曲线请求提示路径的单测;错误提示中文化

## T9 收尾

- [ ] 对话层新增测试全绿、现有 pytest 全回归通过(全部 mock,不触网)
- [ ] README / `docs/design.md` 回填对话调参架构要点(delta→apply→render→reflection、多供应商复用)
- [ ] 版本号对齐 v2.1,CI 绿,推送

## 人工验收(作者,后置,真实体验)

- [ ] 用真实照片在左栏做几组自然语言调色("天空更蓝""暗部压一档""整体日系一点"),确认 AI 改的确实是可解释参数、右面板滑杆随之移动、diff 直观
- [ ] reflection 效果:说一句模糊需求("还差点意思"),观察 AI 自修正是否朝对的方向收敛、收敛轮数是否合理
- [ ] 三种后端各跑一遍对话(API / OpenAI 兼容中转 / 本地 CLI 或 Ollama),对比响应质量、延迟、token 成本,记录供 README 参考
- [ ] 每步 AI 编辑可见可撤销的实机体验;undo 后画布与面板是否同步无残留
- [ ] 极端/刁难请求(要求改曲线、要求局部)是否给出合理提示而非乱改或崩溃
