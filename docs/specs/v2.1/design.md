# v2.1 设计:左聊天调参

> 状态:草拟,待作者 review。同迭代:[需求](./requirements.md) · [任务](./tasks.md)。
> 基线:[analyzer.py](../../../looklift/analyzer.py)(`ANALYSIS_SCHEMA`、`analyze`/`refine`/`_normalize`)、
> [providers.py](../../../looklift/providers.py)(`VisionProvider`、`ClaudeCliProvider`、`AnthropicProvider`)、
> [gui/api.py `_validate_analysis`](../../../looklift/gui/api.py)、[v0.5 多供应商](../v0.5/design.md)。
> 研究蓝本:PhotoArtAgent(arXiv 2505.23130,VLM→JSON 滑杆参数→渲染→reflection)、JarvisEvo(editor-evaluator loop)。

## 全局数据流(一句话)

```
用户自然语言 ──► AI 出 parameter delta(相对当前 analysis,非全量)
                     │
                     ▼  _validate_delta 校验+夹取+丢未知路径
              apply_delta(current_analysis, delta) ──► 新 analysis(单一数据源,右面板同读)
                     │
                     ▼  render.render(img, analysis)  →  中画布 diff
              reflection:AI 重看渲染结果 → 达成? ──否──► 出下一步 delta(回到 apply)
                     │是                                  (硬上限 N 轮兜底)
                     ▼
              返回最终 analysis + 对话流可见的逐步编辑记录(可 undo)
```

对照 PhotoArtAgent:`emit JSON params → render → reflect → iterate`。区别是我们的参数是**增量 delta**
(只发变化项,省 token、diff 天然)、且直接落到用户可见可改的滑杆上。

## 决策一览

| # | 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|---|
| 1 | AI 输出全量还是增量 | (a) 每轮重出完整 analysis(像 `refine`) (b) 只出 **delta**(变化字段) | **(b)** | "把天空调蓝一点"只该动 `hsl.blue.*`,重出全套会漂移未提及的参数、且 diff/undo 难界定。delta = 天然 diff、天然可解释、token 省。PhotoArtAgent 正是 function-calling 出结构化增量参数 |
| 2 | delta 表达形式 | (a) 嵌套偏 analysis 子树(partial dict) (b) **扁平 path-op 列表** | **(b)** | `[{"path":"hsl.blue.saturation","op":"add","value":15}]`:path 直接对应右面板一根滑杆,op 区分**增量**(`add`,"再蓝一点")与**定值**(`set`,"曝光设为 0")。列表即"这轮动了哪几根滑杆"的可见清单,映射 undo/diff 最直接 |
| 3 | 多轮对话如何喂给无状态 provider | (a) 给 provider 加有状态会话 API (b) **对话层每轮把 history+当前 analysis+当前渲染图组装进 blocks,无状态重放** | **(b)** | 现 `VisionProvider.complete(system, blocks, schema)` 是**无状态单发**。保持它不变,**前端持有 history、每轮传入 `chat_step`(纯函数,D3)**,`chat_step` 把传入的 history 组装进 blocks 无状态重放 → **四种 provider(Anthropic/OpenAI 兼容/Ollama/本地 CLI)零改动全部可用**;本地 `claude -p` 每轮新起进程也天然是无状态重放,无需管理 CLI 会话 |
| 4 | reflection 收敛判据 | — | AI evaluator 返回 `{done: bool, reason, next_delta?}`;`done` 或 `next_delta` 为空/可忽略 → 停;**硬上限 N 轮(默认 3,PhotoArtAgent 数据 76% 需>1 轮、少数需多轮)**;到顶未收敛 → 兜底返回最后一版可用 analysis,对话流提示"已尽力,可继续手动微调" | 类比 `refine --auto` 的收敛,但判据是**文字/视觉达成度**而非相似度分数;必须有硬上限防止本地模型抖动导致的无限循环 |
| 5 | delta 应用与右面板/画布同步 | — | **单一数据源 = 前端 editorStore 当前 analysis**(v2.0-B 右面板绑定的同一份)。chat_step 返回 delta → **前端 `applyDelta`** 应用 + push 前端版本栈(D2)→ 触发参数变更事件 → 右面板重读 + 画布防抖代理渲染。chat 编辑与手动拖滑杆走**同一条 apply→事件→渲染**通路,**共用前端版本栈**(chat 不自建历史,D2/D3) | 满足"chat 移动的就是右面板的滑杆";反向手改后对话,AI delta 基于手改后的当前值算,无需区分来源;undo 归前端 store |
| 6 | delta 校验层 | — | 新增 `_validate_delta`,复用 [`_validate_analysis`](../../../looklift/gui/api.py) 思路:path 必须在 **`contract.param_paths()`** 白名单内(否则丢弃)、value 必须数值、按 **`contract.param_bounds(path)`** 的范围**夹取(clamp)**;应用后整体再过一遍现有 `_normalize`/`_validate_analysis` | LLM(尤其本地模型)会出越界值/幻觉路径;白盒的好处是每个参数都有明确合法域(D1 契约),校验廉价且确定 |
| 7 | provider 复用范围 | — | **不新增 provider**;新增一个对话编排层 `chat.py` 调 `get_provider(backend).complete(...)`,schema 传 `DELTA_SCHEMA`(生成)与 `REFLECT_SCHEMA`(评估),不再传 `ANALYSIS_SCHEMA` | 复用 v0.5 全部多供应商能力;对话是"多轮 + 换 schema",不是新传输层 |

## delta schema(生成阶段结构化输出)

**path 枚举与 clamp 域的单一来源 = v2.0-A `contract.py`(D1),不手抄。** `_validate_delta` 的合法
path 白名单来自 `contract.param_paths()`、clamp 域来自 `contract.param_bounds(path)`,`apply_delta`
的落点用 `contract.resolve_path`(它封装 hsl 数组按 `color` 段定位/补零、`color_grading.global_`
下划线映射两个怪癖)。**v2.0-A 改字段名/范围时,delta 校验白名单与 clamp 域自动跟随**——删除任何
"两 spec 落定后回填对齐"的手抄措辞(现已由 contract 模块单一来源解决)。

```python
# path 枚举与范围均从 v2.0-A contract.py 导出(param_paths / param_bounds),非手抄
DELTA_SCHEMA = {
    "type": "object",
    "properties": {
        "note": {"type": "string", "description": "用中文一句话说明这次改了什么、为什么"},
        "ops": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "参数点路径,如 basic.exposure / hsl.blue.saturation / color_grading.shadows.hue"},
                    "op":   {"type": "string", "enum": ["add", "set"], "description": "add=在当前值上增量;set=设为定值"},
                    "value":{"type": "number"},
                },
                "required": ["path", "op", "value"], "additionalProperties": False,
            },
        },
    },
    "required": ["note", "ops"], "additionalProperties": False,
}
```

- **path 覆盖面**(= `contract.param_paths()`):`basic.*`(13 项)、`hsl.<color>.{hue,saturation,luminance}`
  (8 通道)、`color_grading.<zone>.{hue,saturation,luminance}` + `blending`/`balance`、`effects.*`;
  `tone_curve` 用整点数组、非单值滑杆,**v2.1 delta 不改曲线**(`contract.param_paths()` 本就不含
  `tone_curve`;曲线走右面板 ColorCurve 手调,见非目标)。
- `hsl` 在 analysis 里是**数组**(每项带 `color`):落点解析交给 `contract.resolve_path`——按 `path`
  的 color 段定位对应数组项、缺失的 color 通道按 `_normalize` 补零后再改;`color_grading.global_`
  的下划线怪癖同样由 `resolve_path` 处理,**apply_delta 不自己手写这两处解析**。
- 增量语义:`add` 在当前值上加,天然实现"再…一点"的累加;`set` 用于"把曝光设成 0"这类绝对指令。

## reflection 评估 schema

```python
REFLECT_SCHEMA = {
    "type": "object",
    "properties": {
        "done":   {"type": "boolean", "description": "当前渲染是否已达成用户本轮意图"},
        "reason": {"type": "string",  "description": "用中文说明判断依据(看到了什么)"},
        "next_delta": DELTA_SCHEMA,   # done=true 时 ops 应为空
    },
    "required": ["done", "reason", "next_delta"], "additionalProperties": False,
}
```

reflection 输入 blocks = 用户原始请求 + 已应用的 delta 摘要 + **当前渲染图**(可选带原图对照);
AI 判断达成度并给出 `next_delta`。这一步的 provider 调用与生成阶段同构,只是 schema 换成 `REFLECT_SCHEMA`。

### 渲染图如何喂给 provider:临时文件路径,`providers.py` 零改动(D7)

**决策:每轮 reflection 把渲染出的图写成临时文件,传路径给 `providers.complete`——不改 provider 接口。**

- 现有 `VisionProvider.complete(system, blocks, schema)` 的图片 block 走**文件路径**(analyzer/refine
  既有用法)。reflection 每轮渲染后,**渲染的是代理分辨率(proxy)**(非 40MP 全图),把该 proxy 写到
  一个 `tempfile.mkdtemp()` 目录下(**复用 [`autorefine.py`](../../../looklift/autorefine.py) 的
  mkdtemp + try/finally 清理模式**),按轮编号命名,把**路径**放进 blocks 传给 `complete`。
- 由此 **"provider 零改动复用"成立**——不需要给 provider 加"接受内存 bytes"的新入口,消除该歧义。
  生成阶段带的"当前渲染图"同理走临时文件路径。
- reflection **重渲染用 proxy 分辨率**(与右面板预览一致,交互级快),不在对话循环里渲 40MP;
  函数退出时 try/finally 清理临时目录。

## `chat_step` 是纯函数,sidecar 无状态(D3);会话状态与版本栈归前端(D2)

**决策(D3):对话层不在 sidecar 里持有有状态的 `ChatSession`。** `chat_step` 是一个**纯函数**,
会话状态(history、当前 analysis、版本栈)由**前端 editorStore** 拥有,每次调用由前端 marshal 传入——
与 v2.0-B「localhost-HTTP 无状态 sidecar」一致,sidecar 不在内存里跨请求存会话。

```python
# 纯函数:入参即全部状态,无跨调用的 in-memory session
def chat_step(
    history: list[Turn],          # 前端传入的对话历史(文字摘要,决策 3 无状态重放)
    current_analysis: dict,       # 前端 editorStore 的当前 analysis(单一数据源)
    image_path: str,              # 当前图路径(渲染代理用)
    user_text: str,
    backend: str,
    max_reflect: int = 3,
) -> tuple[Delta, ReflectionTrace]:
    # 1) 组装 blocks(history 摘要 + current_analysis + 当前渲染图 + user_text),complete(DELTA_SCHEMA)
    # 2) _validate_delta(delta)   —— 纯校验,不落库、不 push 版本
    # 3) reflection 循环(<= max_reflect):在一个 current_analysis 的**工作副本**上 apply+render+evaluate,
    #    complete(REFLECT_SCHEMA);未 done 且有 next_delta 则在工作副本上再 apply+render
    # 4) 返回:(合并后的 delta, reflection 轨迹)——**不返回版本栈,不 push 历史**
```

- **返回的是 delta + reflection 轨迹,不是新版本历史。** 前端 editorStore 拿到 delta 后
  `applyDelta` 到当前 analysis 并 **push 自己的版本栈**(v2.0-B D2 的 seam)——**版本历史的唯一
  owner 是前端 store**,chat 层不再自建 `analysis_versions`。
- **reflection 用工作副本,不产生对外版本。** reflection 内部多轮 apply/render 只在函数内的
  `current_analysis` 工作副本上进行(为了让 evaluator 看到"如果这样改会怎样");最终**只把收敛后的
  净 delta** 交回前端应用一次(或按"逐步可见编辑"把每步 delta 依次交给前端 push,见状态同步节)。
  chat 层自身**不持有**跨请求的版本栈。
- history 只需**文字摘要 + 当前 analysis 快照**重放,不必逐轮塞历史图片(省 token;当前渲染图只带最新一张)。
- `Turn` 只是数据结构(用户话 + 应用的 delta 列表 + note + reflection 轨迹),由前端持有并回传,
  **不是 sidecar 里的有状态对象**。

## 状态同步:chat = 移动右面板滑杆,共用前端版本栈(D2)

- **单一数据源 = 前端 editorStore 的当前 analysis**(v2.0-B 右面板绑定的同一份)。chat_step 返回的
  delta 由前端 `applyDelta` 应用 → 触发右面板重读 + 画布防抖代理渲染,**与手动拖滑杆走同一条
  apply→事件→渲染通路**。
- **undo 归前端**:editorStore 的版本栈(v2.0-B T7b seam)每次 apply(手动 or chat delta 的每一步)
  push 一版;undo = pop,右面板/画布随之同步。**v2.1 不再实现独立版本栈**——只产出 delta,交给前端 push。
- **反向**:用户手改滑杆后再对话,`current_analysis` 就是手改后的值(前端传入),AI delta 基于它计算,
  无需区分来源。

## 接口/文件变化(YAGNI,只列本迭代新增)

| 文件 | 变化 |
|---|---|
| `looklift/chat.py`(新) | **纯函数** `chat_step(history, current_analysis, image_path, ...)`、`apply_delta()`、`_validate_delta()`、`DELTA_SCHEMA`/`REFLECT_SCHEMA`;**不含有状态 `ChatSession`**(会话状态与版本栈归前端,D2/D3);对话编排,不含传输与渲染实现 |
| `looklift/providers.py` | **不改**;`complete()` 原样复用(schema 换成 delta/reflect;渲染图走临时文件路径,D7) |
| `looklift/analyzer.py` | **不改**;`_normalize` 复用于应用 delta 后的补全 |
| v2.0-A 引擎 | 提供 `render.render(img, analysis)` + **`contract.py`**(`param_paths`/`param_bounds`/`resolve_path`——delta 的 path 枚举、clamp 域、落点解析的单一来源,D1) |
| v2.0-B 前端 | editorStore 拥有当前 analysis + **版本栈**(D2);chat_step 返回的 delta 由前端 applyDelta + push;undo 归前端 |
| v2.0-B GUI | 左栏对话 UI + 把 `chat_step` 的输出接到右面板参数模型与中画布 diff(装配层,随 v2.0-B) |

## 风险

| 风险 | 缓解 |
|---|---|
| **LLM 出错参数**(越界/幻觉路径/非数值) | `_validate_delta` 复用 `_validate_analysis` 思路:白名单 path、clamp 到 schema 域、丢未知项;应用后再过 `_normalize`。白盒参数域明确,校验确定且廉价 |
| **多轮 token 消耗**:每轮重放 history + 带渲染图,单 Anthropic 供应商贵 | (1) history 只传文字摘要 + 当前 analysis 快照,图片只带最新一张;(2) **[v0.5](../v0.5/design.md) 多供应商缓解**——可切 OpenAI 兼容中转站(便宜)或本地 Ollama(免额度);(3) reflection 硬上限 N 轮封顶单次对话的调用数 |
| **reflection 不收敛**(本地模型抖动来回改) | 硬上限 `max_reflect`(默认 3,决策 4)+ 兜底返回最后一版可用 analysis + 对话流明示"未完全达成,可手动微调";evaluator 的 `done`/`next_delta` 空都算收敛信号 |
| **本地 CLI 多轮延迟**:`claude -p` 每轮新起进程,reflection ×N 轮串联,秒级累加 | 对话流做进度反馈(逐轮流式提示);reflection 轮次可配、默认小;延迟是本地 CLI 后端固有代价,文档如实标注,对时延敏感用户建议用 API 后端 |
| **delta path 枚举与 v2.0-A operator 契约漂移** | **已由 D1 解决**:path 集合、clamp 域、落点解析全部从 v2.0-A `contract.py`(`param_paths`/`param_bounds`/`resolve_path`)**单一来源导出**——不手抄、无需事后回填对齐;v2.0-A 改参数名/范围时 delta 校验自动跟随 |
| **曲线/局部不在 delta 里,用户却口头要求** | delta schema 不含 `tone_curve`/蒙版;对话层识别到这类请求时回中文提示"曲线请用右面板手动调 / 局部调整为后续版本",不静默失败 |

## 开放问题

- ~~v2.0-A 的 operator 参数模型是否 100% 沿用现 `ANALYSIS_SCHEMA` 的字段与范围?~~ **已定(D1)**:
  v2.0-A 只**实现**已有字段、不增删业务字段,并给数值字段补 `minimum`/`maximum` 元数据;delta 的
  path 枚举与 clamp 域从 `contract.py` 导出,不再是开放项。
- ~~v2.0-B 右面板参数模型的"单一数据源"对象形态与变更事件机制。~~ **已定(D2/D3)**:单一数据源 =
  前端 editorStore 当前 analysis;chat_step 纯函数返回 delta,前端 applyDelta + push 版本栈(chat 不自建历史)。
- reflection 是否需要把**原图**一起喂给 evaluator(判断"够不够蓝"可能需要参照系),还是只看当前渲染图——
  影响 token 与效果,建议实现期用真实对话实测定夺。(渲染图/原图均走临时文件路径传入,D7。)
