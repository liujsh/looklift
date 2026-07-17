# v2.0-A Spec:引擎重构(operator 化 + 线性光 + numba 融合)—— 需求

> 状态:已确认(2026-07-17,作者授权开工;性能口径见下方「性能验收口径」)。同迭代:[设计](./design.md) · [任务](./tasks.md)。
> 上游:[产品宪法 requirements.md](../../requirements.md)(v2 一站式定位)、
> [当前架构 design.md](../../design.md)(§12 现渲染管线、§15 LUT、§17 强度缩放)、
> [specs 规范](../README.md)。完整调研/决策/spike 实证见开发计划文档(scratchpad 的 v2 plan)。
> 约定:本文件定「做什么、做到什么程度、不做什么」;技术方案见 [design.md](./design.md);
> 任务分解见 [tasks.md](./tasks.md)。

## 一句话目标

把 `render.py` 的单函数管线重构为 **operator 化、分阶段的渲染引擎**——每个调整是一个
职责单一、可独测的 operator;曝光/白平衡/混合搬进**线性光**做物理正确运算;整条管线用
**numba 融合成单遍内核**打进交互延迟;补齐 texture/clarity/dehaze/grain 的像素实现;导出
嵌 sRGB ICC(Display-P3 输出留 v2.x)。这是从「方向正确的近似」到「应用内成品渲染」的画质与架构跃迁,是 v2
一站式新线的引擎地基。

## 背景

v2 一站式的中画布(实时预览)+ 右调色面板(逐参数滑杆)都建在渲染引擎上,而现引擎有三个
硬缺口:① 曝光/白平衡在 sRGB gamma 域做,物理不正确(「muddy/发暗」的根源,1 档曝光≠2×);
② `_apply_color_ops` 是一个大函数,9 步耦合,难独测、难扩展,违背作者「层次清晰、单一职责、
不堆代码山」的分层规范;③ texture/clarity/dehaze/grain 已进 `ANALYSIS_SCHEMA` 且被
`intensity.scale_analysis` 缩放,但 render 里**无像素实现**——右面板拉这四个滑杆无反应。

六路调研(RapidRAW/AlcedoStudio/darktable/RawTherapee/JarvisArt)一致确认:**没有「输 LR
滑杆出成片」的现成引擎,只能手搓提升现有 numpy 管线**;可行性 spike 已实证 Python+numba
+线性光可达成品级(见验收基线)。本迭代**只重构引擎**,不碰 GUI/聊天/RAW/GPU(那是 v2.0-B
及之后)。

## 覆盖的能力

以现有用户故事编号为锚,本迭代是它们的**引擎底座升级**,不新增交互面:

| # | 用户故事 | 本迭代如何服务 |
|---|---|---|
| U10 | 不开 LR 就能预览参数套用后的效果 | 从「方向近似」升级为**线性光成品渲染 + 应用内导出成片**(嵌 ICC 的 JPEG/TIFF),这是 U10 的画质跃迁,也是 v2「不用打开 LR/PS 就能出成片」定位的引擎实现 |
| U19 | 风格导出成 .cube LUT | `lut.export_cube` 迁移到复用同一 operator 管线的采样入口,行为不回归 |
| U20 | 预设只套 N% 强度 | `intensity.scale_analysis` 的输出契约保持不变,新引擎照常消费缩放后参数 |
| U16 | 预置经典 look 库(青橙/胶片/日系) | 这些 look 依赖 texture/clarity/dehaze/grain/色调曲线的**真实像素表现**,本迭代补齐像素实现后它们才渲染得对 |

**新增能力(v2 定位新引入)**:

- **应用内成品渲染**:sRGB→linear 入口、物理运算在线性光、导出编码回并**嵌 sRGB ICC**,
  产出可跨设备正确显示的成片(不再是「仅用于观感的近似预览」)。Display-P3 输出留 v2.x(见非目标)。
- **交互级延迟**:2048px 代理单帧 <50ms,支撑右面板拉滑杆的实时反馈(v2.0-B 依赖)。
- **texture/clarity/dehaze/grain 像素实现**:四个此前只在 schema、无渲染的参数落地为真实效果。
- **参数契约模块(单一真相源)**:新增一个 `looklift/render/contract.py`,导出「可调参数点路径枚举 +
  每字段机器可读 (min,max) 范围 + hsl 数组 / `global_` 解析规则」。这是 v2.0-B 右面板(min/max/复位)
  与 v2.1 delta(path 枚举 + clamp 域)的**共同单一来源**——两者从本模块导出,不各自手抄/回填(见下 D1)。

## 验收标准

对齐开发计划文档「验证方式(v2.0-A)」口径。**每条可勾选、可自动化(除末尾人工验收区)。**

**架构/正确性**

- [ ] 每个 operator 有独立单测:给定其 params 分片,`apply_numpy`(或 `apply_px`)方向断言成立
      (如 exposure>0 更亮、单通道白平衡朝预期方向、clarity>0 中频对比增强)
- [ ] **线性光正确性**:纯曝光 +1.0 EV 使线性光亮度精确 ×2(误差 <1%),+2.0 EV ×4;
      而非现 sRGB 域的 ≈2.3×/≈4.6×(用已知输入构造断言,不依赖肉眼)
- [ ] 白平衡/混合类物理运算在线性光域执行,单测验证其在 linear 而非 gamma 域(如两倍叠加
      符合线性叠加而非 gamma 叠加)
- [ ] **numba 融合前后一致**:同一 analysis 下,融合内核输出与「逐 operator numpy 参考实现」
      逐像素一致(容差 ≤ 1/255,因 `fastmath`+`parallel` 改变浮点结合序,用容差非严格相等)

**参数契约(D1,单一真相源)**

- [ ] `looklift/render/contract.py` 提供 `param_paths()`(枚举所有可调数值参数的点路径,含
      `basic.*` / `hsl.<color>.{hue,saturation,luminance}` / `color_grading.<zone>.{...}` +
      `blending`/`balance` / `effects.*`,**不含 `tone_curve`**——曲线是整点数组非单值滑杆)
      与 `param_bounds(path)->(min,max)`;每条 path 都能解析到 analysis 里的落点(hsl 数组按
      `color` 段定位对应 `{color:...}` 项、`color_grading.global_` 的下划线尾巴正确映射),
      每个数值字段都有 (min,max)
- [ ] 范围以**机器可读**形式存在:在 `ANALYSIS_SCHEMA` 各数值字段补 `minimum`/`maximum`
      (单一 schema 仍是唯一真相源,不新建平行范围表),`param_bounds` 从 schema 读取

**画质/色彩管理**

- [ ] 导出图嵌入 sRGB ICC,能被标准查看器(如系统图片查看器 / exiftool)识别
      到 ICC profile 字段;不嵌 profile 的旧路径不再是默认(Display-P3 输出留 v2.x)
- [ ] texture/clarity/dehaze/grain 四项各有像素实现:非零值产生可测的方向性变化(如
      grain_amount>0 使局部方差增大、dehaze>0 使低对比雾区对比与饱和上升),0 值等价恒等

**性能验收口径(2026-07-17 作者确认,取代此前含糊的「全 op <50ms」表述)**

分层计量,不把两类性质不同的运算混算一个阈值:

- [ ] **融合内核(pointwise 色彩 op 全开)代理帧 <50ms** —— 2048px、warmup 后、单机;作回归软门槛
      (超阈告警)。依据:numba spike 已证实 pointwise 全开可达此区间(代理子集 9.4ms)。
- [ ] **S2 预处理(大半径高斯模糊等空间辅助:texture/clarity/dehaze 用)独立预算 <200ms** ——
      代理路径;S2 非 pointwise、内存带宽重,单独设阈、单独 benchmark(必要时更低分辨率估辅助缓冲)。
- [ ] **同时记录「完整帧(融合内核 + S2)总耗时」为观测项**(不硬失败,记入 benchmark 与风险);
      交互手感以「拖滑杆只重跑融合内核、S2 结果缓存复用」为设计前提,故完整帧偶发 >50ms 不阻塞交互。
- [ ] 全分辨率 40MP 导出记录实测(S2 大半径 blur 可使其高于 <1s,导出非交互、可接受);不达标记入风险。
- [ ] 同一融合内核同时服务 2048px 代理与全分辨率导出(不维护两套渲染实现)。

**兼容/不回归**

- [ ] `test_render.py` 的**方向断言保持**(exposure>0 更亮、HSV 往返、float32 契约等),但
      **幅度标定阈值须审计并重新标定**(D5):线性光会改变幅度——如 `test_exposure_positive_brightens`
      现断言均值 >0.4,而线性光下 +1EV @0.25 得约 0.352,方向仍变亮但阈值须调低。方向不变、
      **阈值可变**;不存在被打破的逐像素 golden(本项目本就无 golden 值测试)
- [ ] 对外契约 `render.render(image, analysis) -> Image`、`render.score(rendered, target) -> float`
      签名与语义不变,调用方(CLI/GUI/autorefine)零改动
- [ ] `test_lut.py` 全绿:`.cube` 的 SIZE/DOMAIN/行数/取值范围不回归(结构层面)
- [ ] **LUT 与应用渲染观感一致(D6)**:`.cube` 采样一个 display-referred [0,1]³ 立方体、
      走**与应用相同的完整色彩管线**(内部 linearize 做曝光/WB、再 delinearize 回 display),
      使 sRGB 入→sRGB 出与应用画面一致;取若干 RGB 采样点断言 `.cube` 输出 ≈ `render` 输出
      (容差内)。此改动会使 `.cube` 数值不同于旧 LUT(旧的不烘 linearize/delinearize 往返),
      但**更正确、且与应用两条出口一致**
- [ ] CLI 的 `preview` / `export-lut` / `apply` 行为不回归:同一 analysis 输入下,产物在
      「方向/格式」层面与重构前等价(允许因线性光带来的**数值**改进,不允许方向或格式破坏)
- [ ] `intensity.scale_analysis` 与新引擎联调:factor=0 渲染 ≈ 原图、factor=1 = 满调,语义不变

## 非目标(v2.0-A 明确不做)

| 不做 | 归属 |
|---|---|
| **局部调整 / 蒙版 / 渐变**的像素实现 | 产品级非目标(仍以文字讲解代替);未来 backlog |
| **RAW 解码 / 高光重建** | v2.x(`rawpy`);本迭代守 sRGB(含 JPEG/TIFF)输入契约 |
| **GPU 后端**(moderngl/wgpu-py/cupy) | v2.x 可选,仅当全分辨率导出仍慢时;本迭代纯 CPU(numba) |
| **Display-P3 输出导出** | v2.x;本迭代输出侧只嵌 **sRGB** ICC(色管转换基元/包结构为 P3 留位,但不作为本期交付) |
| **三栏 GUI 壳 / 中画布 / 右面板控件 / diff 对比条** | v2.0-B(引擎只提供 `render`/`preview` 入口,不碰前端) |
| **左聊天调参 / 参数 delta 循环** | v2.1 |
| **AI 分析引擎 / provider 层改动** | 不动 `analyzer`/`providers`;引擎只消费 `ANALYSIS_SCHEMA` |
| **ANALYSIS_SCHEMA 业务字段增删** | 引擎只**实现**已有字段(含此前未渲染的四项),**不增删业务字段**;但本迭代**拥有参数契约**(D1):枚举可调路径 + 机器可读范围 + hsl 数组/`global_` 解析规则,并允许给 schema 数值字段补 `minimum`/`maximum` **元数据**(非业务字段) |
| **显示器 ICC 感知(输入侧色管)** | 锦上添花,留后;本迭代只做**输出侧**嵌 profile |

## 对现有代码的兼容要求(硬约束)

- **对外 API 不破**:`render.render` / `render.score` 签名、返回类型、语义保持;`render._apply_color_ops`
  作为 LUT 采样入口的**兼容点**必须保留或提供等价替代(见 [design.md](./design.md) 迁移策略),
  使 `lut.py` 无需理解内部重构即可复用同一色彩管线。
- **CLI 不回归**:`preview` / `export-lut` / `apply` 三条命令的行为在「格式合法性、方向正确性」
  层面与重构前等价。允许线性光带来的画质**数值**变化(更亮更干净),不允许破坏格式或方向。
- **intensity 契约不变**:`scale_analysis(analysis, factor)` 的输入/输出形状不动,新引擎按现语义消费。
- **测试迁移全绿**:现有离线测试(`test_render.py`/`test_lut.py`/`test_autorefine.py` 等)迁移后
  全部通过;方向断言保持;新增的是线性光正确性、operator 单测、融合一致性、性能软门槛等**增量**断言。
- **依赖新增许可干净**:`numba`(BSD)、`pyvips`/libvips(MIT 壳 / LGPL 动态链接);**不引入任何 GPL 代码**。
  pyvips 作为可选依赖,缺失时核心数学(sRGB↔linear、增益运算)用纯 numpy 兜底(见 [design.md](./design.md))。
- **numba 缺失可运行(纯 numpy 渲染兜底)**:`numba` 缺失/JIT 不可用时,引擎走**纯 numpy 渲染路径**——
  把各 operator 的 `apply_numpy` 串成一条运行时兜底管线(不仅用于测试/LUT,而是一条**可出图的降级渲染**)。
  该路径慢但结果与融合内核方向一致(容差内);保证核心「拖图→出成片」在无 numba 环境仍可用。
