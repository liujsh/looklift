# v2.0-A Spec:引擎重构 —— 设计

> 状态:已确认(2026-07-17,作者授权开工)。同迭代:[需求](./requirements.md) · [任务](./tasks.md)。
> 基线:[当前架构 design.md §12/§15/§17](../../design.md)(现渲染管线/LUT/强度缩放)、
> [产品宪法](../../requirements.md)。参考架构(设计非代码,均不抄码):**AlcedoStudio**
> (operator + per-op JSON 参数 + 分阶段管线,GPL-3 仅借结构)。spike 数据引自开发计划文档。

## 目标回顾

把现 `_apply_color_ops`(9 步耦合的大函数)+ `_apply_spatial_ops` 重构为 **operator 化、
分阶段、线性光、numba 融合**的引擎,对外仍是 `render.render(image, analysis) -> Image`。
四个正交的改造:① operator 架构(单一职责、可独测);② 线性光(物理正确);③ numba 融合
(交互延迟);④ 补四个像素 op + 输出 ICC(成品化)。**引擎是唯一实现,CLI/GUI 共享**。

---

## 一、Operator 架构

### 1.1 为什么 operator 化

现 `_apply_color_ops` 把 9 步塞进一个函数,曝光的 bug 要通读全函数、texture 想加没有挂点、
LUT 复用靠 `from .render import _apply_color_ops` 硬耦合。AlcedoStudio 的经验:**每个调整 =
一个 operator**,各带 `GetParams()/SetParams()` 的 JSON 契约,上层一个**扁平全局参数结构**
带 per-op enable 标志喂渲染。这比大函数**层次清晰、单一职责、可独立单测、可独立补新 op**,
正契合作者「不堆代码山」的分层规范。

### 1.2 operator 基类接口(`base.py`)

每个 operator 是一个轻对象/模块,承担四件事——**参数契约、解析、逐像素数学(numba)、
参考实现(numpy,供测试与兜底)**:

```python
class Operator(Protocol):
    name: str                        # "exposure" / "white_balance" / ...
    stage: Stage                     # 所属阶段(见 §四),决定固定顺序
    domain: Domain                   # LINEAR 或 DISPLAY,决定在哪个光域执行

    def resolve(self, analysis: dict) -> tuple:
        """从 analysis 切出本 op 的参数分片,预计算成一组标量/小数组;
        返回值写进扁平全局结构。若本 op 无效(全 0),返回 None → enable=False。"""

    # 逐像素数学:被融合内核 inline 调用(numba 可跨模块 inline njit device 函数)
    #   @njit(inline='always')
    #   def apply_px(r, g, b, *params, aux) -> (r, g, b)

    def apply_numpy(self, arr: np.ndarray, params: tuple, aux=None) -> np.ndarray:
        """整数组参考实现:op 级单测、LUT 采样、numba 不可用时的兜底路径。
        与 apply_px 是同一数学的两种写法,一致性由「融合前后一致」测试守护。"""
```

- **单一数学、两处形态**:`apply_px`(numba device 函数,生产路径,被融合内核 inline)与
  `apply_numpy`(向量化参考,测试/LUT/兜底)。二者数值一致性是一条**验收断言**(容差 ≤1/255)。
- **per-op enable**:`resolve` 返回 `None` 即该 op 在本次渲染跳过(enable 位=0),融合内核里是
  一个 `if` 短路——0 值 op 不产生数值改变也不浪费算力。

### 1.3 operator 清单(映射现有 ANALYSIS_SCHEMA)

每个 op 的 params 契约就是 `ANALYSIS_SCHEMA` 的一个**分片**(不发明新字段):

| operator | 参数分片(schema 来源) | 光域 | 现状 |
|---|---|---|---|
| `exposure` | `basic.exposure` | **linear** | 有(现在错在 gamma 域) |
| `white_balance` | `basic.temperature_shift`, `tint_shift` | **linear** | 有(迁到 linear) |
| `contrast` | `basic.contrast` | display | 有 |
| `highlights_shadows` | `basic.highlights`, `shadows` | display | 有 |
| `whites_blacks` | `basic.whites`, `blacks` | display | 有 |
| `tone_curve` | `tone_curve[]` | display | 有(含域外恒等外推,§17 已修) |
| `hsl` | `hsl[]`(8 通道 hue/sat/lum) | display(HSV) | 有 |
| `saturation` | `basic.saturation`, `vibrance` | display(HSV) | 有 |
| `color_grading` | `color_grading.{shadows,midtones,highlights,global_}` | **display**(艺术染色) | 有 |
| `color_grading.blending/balance` | 同名字段 | contract-only,本期无像素效果 | 无 |
| `texture` | `basic.texture` | display(亮度/细节) | **新增像素实现** |
| `clarity` | `basic.clarity` | display(亮度/细节) | **新增像素实现** |
| `dehaze` | `basic.dehaze` | display | **新增像素实现** |
| `vignette` | `effects.vignette_amount` | display(位置相关) | 有(现在 spatial) |
| `grain` | `effects.grain_amount` | 输出前(display,噪声场) | **新增像素实现** |

### 1.4 扁平全局参数结构(`RenderParams`)

镜像 AlcedoStudio 的「扁平 `OperatorParams` + per-op enable」:pipeline 遍历 operator 注册表,
逐个 `resolve(analysis)` 把预计算标量写进**一个扁平结构**(numba `NamedTuple` / 定长 record,
无嵌套,便于 marshal 进内核),外加一个 enable 位掩码。融合内核只吃这一个结构 + 辅助缓冲,
不吃 Python dict。曲线这类「小数组参数」预计算成定长 LUT(如 1024 项)一并放入。

**关键:operator 是组织/契约/测试层,融合内核是执行层。** operator 不在每像素上被当 Python
对象调用(那会慢),而是它的 `apply_px` 被 numba **inline 进单个内核**——既拿到单一职责的
代码组织,又拿到融合的性能。

### 1.5 参数契约模块 `contract.py`(D1,跨 spec 单一真相源)

review 发现的 #1 缺口:v2.0-B 右面板要每根滑杆的 (min,max) 与复位默认、v2.1 delta 要「合法
path 枚举 + clamp 域」,若各自**手抄**一份路径/范围表,三处一改就漂移。**解法:v2.0-A 拥有一个
参数契约模块作为唯一来源**,B/C 只从它导出,不回填、不手抄。

- **范围机器可读化**:现 `ANALYSIS_SCHEMA` 的范围只写在中文 `description` 里(如「-100 到 100」),
  机器读不到。本迭代给 schema 各**数值字段**补 `minimum`/`maximum` 字段(标准 JSON-Schema 关键字,
  单一 schema 仍是唯一真相源,**不新建平行范围表**、不增删业务字段)。
- **导出的 API**:
  - `param_paths() -> list[str]`:枚举所有可调数值参数的点路径——`basic.*`(13)、
    `hsl.<color>.{hue,saturation,luminance}`(8 通道)、`color_grading.<zone>.{hue,saturation,luminance}`
    + `blending`/`balance`、`effects.{vignette_amount,grain_amount}`。**不含 `tone_curve`**(整点数组,
    非单值滑杆;曲线由右面板 ColorCurve / 手调,不进 delta——见 v2.1 非目标)。
  - `param_bounds(path) -> (min, max)`:从 schema 的 `minimum`/`maximum` 读该 path 的范围。
  - `resolve_path(analysis, path)`:把点路径解析到 analysis 里的**落点**,封装两个结构怪癖——
    ① **hsl 是数组**(每项 `{color, hue, saturation, luminance}`):`hsl.blue.saturation` 要在数组里
    find `{color:"blue"}` 项,缺失则按 `_normalize` 补零后 insert;② **`color_grading.global_`
    带下划线尾巴**(避 Python 关键字):`color_grading.global.hue` 的 `global` 段映射到 dict 键 `global_`。
- **消费方**:v2.0-B 面板控件的 min/max/复位从 `param_bounds`/schema 默认取;v2.1 `_validate_delta`
  的白名单来自 `param_paths()`、clamp 域来自 `param_bounds()`,`apply_delta` 的落点用 `resolve_path`。
  三处**同一来源**,v2.0-A 改字段名/范围时 B/C 自动跟随。

> 落位在 `render` 包内(`looklift/render/contract.py`),因为它是渲染引擎的参数契约;若担心 v2.1
> 对话层引入 render 包的重依赖,可将 `param_paths/param_bounds` 设计为**不 import numba/pyvips**
> 的轻量纯 Python 模块(只读 `analyzer.ANALYSIS_SCHEMA`),使 chat 层导入它不触发引擎重编译。

---

## 二、线性光空间

### 2.1 现状缺口与修法

现引擎全程在 sRGB gamma 域(0-1 编码值)做运算:曝光 `arr * 2^ev` 在 gamma 域使 +1EV 只亮
≈2.3× 而非物理的 2×,是「muddy/发暗」的根源(调研结论 D 列为**最大正确性缺口**)。修法:
**入口 sRGB→linear,物理运算在线性光,末尾编码回 + 嵌 ICC**。

### 2.2 哪些 op 在 linear、哪些在 display

不是所有 op 都该在 linear——**物理性合并运算**在 linear,**LR 滑杆语义**按其定义域(display):

| 光域 | operator | 理由 |
|---|---|---|
| **linear(scene-referred)** | exposure、white_balance | 光的加/乘性合并,物理上就在线性辐射域;「1 档=2×」只有在 linear 才成立(仅这两个是无歧义的物理运算) |
| **display-referred(sRGB OETF 编码后)** | contrast、highlights_shadows、whites_blacks、tone_curve、hsl、saturation、**color_grading**、texture、clarity、dehaze、vignette | 这些是相对 display 码值定义的**创作滑杆**;color_grading(色轮染色)是艺术操作非物理合光,与对比度/HSL 同域,整体留 display——见 §2.5 #2 |
| **输出前(display)** | grain | 胶片颗粒是 display 域的感知噪声,末尾叠加 |

### 2.3 单管线内的光域切换

融合内核内部只切换**一次**(scene-linear → display),不来回横跳:

```
[Stage 1 已是 linear]
  → exposure (×2^ev, linear)
  → white_balance (通道增益, linear)
  → 编码 linear→display (sRGB OETF)               ← 唯一一次切换(仅 exposure/WB 在 linear)
  → contrast → highlights_shadows → whites_blacks
  → tone_curve → hsl → saturation → color_grading
  → texture → clarity → dehaze → vignette          ← LR 滑杆语义(含 color_grading)全在 display 段
  → [Stage 4 输出:display 即成品;本期嵌 sRGB ICC(P3 输出留 v2.x)]
```

> 注(2026-07-17 修订,见 §2.5 缺口 #2):color_grading **整体留在 display 段**,不拆 linear/display。

### 2.4 线性段内不提前 clip(D5)

线性光是 **scene-referred**:曝光提亮后线性值**可以 >1**(高光超出显示范围但仍是有效场景亮度)。
**关键约束:linear 段内的中间结果不 clip 到 [0,1]**——只有到 S4 编码回 display(sRGB OETF)前的
最后一步才做范围收拢。若在 linear 段过早 crush,会把本可保留的高光信息压死(重现「muddy/断层」)。
因此 exposure 的 `×2^ev` 结果、WB 增益后的通道值在管线内以 float32 无上限保存,直到 display 编码。
这也是 D5 幅度阈值须重标的物理原因:线性域正确提亮后,再编码回 display 的均值不同于旧 gamma 域近似。

### 2.5 计划起草发现的 4 个缺口修订(2026-07-17)

writing-plans 起草时发现 4 个 spec 缝隙,在此拍定(计划与实现以本节为准):

1. **两张 8 色表去重**:`render._HSL_CENTERS`(色名→中心色相)与 `analyzer._COLOR_KEYS`(8 色枚举)是两处
   手抄表,会漂移。**决定**:`contract.py` 与 hsl operator 的 8 色**唯一来源是 `analyzer._COLOR_KEYS`**;
   `_HSL_CENTERS` 保留为「_COLOR_KEYS 各键 → 中心色相」的映射(键序对齐 _COLOR_KEYS),不再独立列色名。
2. **color_grading 光域**:原文「区权重按 display luma、叠色 blend 在 linear」在单次光域切换的融合内核里
   自相矛盾(linear 段还没有 display luma)。**决定**:**color_grading 整体留在 display 段**——它是艺术
   染色非物理合光,与 contrast/HSL 同域处理。消除歧义、简化内核。只有 exposure/white_balance 进 linear。
3. **grain 单点叠加**:§2.3 与 §四 曾两处提到 grain,有双叠风险。**决定**:grain **只在 S4 输出阶段叠加一次**
   (display 域、噪声场按亮度加权),内核主体不再出现 grain,§六 的 grain 实现挂到 S4。
4. **blending / balance 本期 contract-only**:`color_grading.blending`/`balance` 在 `param_paths()` 且被
   intensity 缩放,但现 `_apply_color_grading` 未使用它们(与 texture/clarity/dehaze/grain 同类的「有字段
   无实现」)。**决定**:本期把它们列为**契约存在、无像素效果**(面板可显示滑杆但拖动暂无渲染变化),
   在验收里明确标注为 v2.0-A 非目标(叠色的 blending 过渡宽度 / balance 阴影高光分界的像素实现**留后续迭代**)。
   —— 避免"假装实现"。

---

## 三、numba 融合策略

### 3.1 为什么单遍

瓶颈是**内存带宽不是算力**:40MP float32 单帧 ~480MB,现「逐 op numpy」9 步每步读写整张大数组,
一次滑杆走几个 GB 内存流量。融合成**单遍 `@njit(parallel=True, fastmath=True)`**:一个 `prange`
像素循环里顺序 inline 调用各 op 的 `apply_px`,**消掉全部中间数组分配与重复遍历**。

**spike 实证(单机 16 核,numba 0.66 + numpy 2.4,引自开发计划文档):**

| 场景 | numpy 逐 op(现 render.py 方式) | numba 融合单遍 | 加速 |
|---|---|---|---|
| 2048px 代理(2.8MP) | 291 ms | **9.4 ms** | 30× |
| 全分辨率 40MP 导出 | 3921 ms | **131 ms** | 30× |

spike 是 5 op 代表性子集;全管线(~13 op + 预处理)按 ×3-5 估:**代理 ~50ms、导出 ~650ms**,
仍在交互/可接受区。**结论:纯 CPU、无 GPU、无 Rust 即跨过实时线**;GPU 降级为 v2.x 可选。

### 3.2 代理与全分辨率同内核

**同一个 `fused()` 内核**,两个调用方:2048px 代理(拖滑杆,`preview` 路径)与全分辨率
(`apply`/导出)。空间性参数(暗角半径、texture/clarity 模糊半径、颗粒尺度)用**相对单位**
(按画幅归一),使同一内核在两种分辨率下视觉一致。不写两套渲染。

### 3.3 非「逐像素独立」的 op:预处理阶段

texture/clarity/dehaze/grain 不是每像素独立(要邻域/全局信息),不能塞进纯逐像素融合。解法:
**Stage 2 预处理**先算好它们要的辅助缓冲(见 §四),融合内核只做「读辅助缓冲 + 逐像素合成」:

- texture/clarity:预算一/两个半径的**高斯模糊亮度**(可分离卷积,自成一个小 numba kernel);
  内核里用 unsharp 残差合成。
- dehaze:预估局部模糊/对比辅助场;本期只做局部对比 + 饱和近似,不做暗通道先验。
- grain:S2 只预生成**噪声场**(定种子,可复现测试);融合内核主体不叠 grain,S4 按亮度加权叠加一次。

预处理是 O(n) 的少数几遍,相对整条管线开销小,不破坏「主色彩管线单遍」的收益。

### 3.4 编译期首帧延迟

`@njit` 冷编译需数秒(风险)。缓解:内核 `cache=True`(编译产物落盘,跨进程复用)+ 应用/引擎
启动时用一张极小 dummy 图**预热**(warmup)触发 JIT,把首个真实帧的编译延迟移到启动期。
`fastmath=True` 会重排浮点运算 → 「融合前后一致」测试用**容差**(≤1/255)而非严格相等。

---

## 四、分阶段管线(固定命名阶段,非节点图)

镜像 AlcedoStudio 的**固定命名阶段序列**(Image_Loading→To_WorkingSpace→…→Output_Transform):

| 阶段 | 职责 | 落点 |
|---|---|---|
| **S0 Ingest** | PIL→float32、mode 归一;代理路径缩到长边 2048 | `pipeline.py` |
| **S1 To Working Space** | sRGB(display)→**linear**(pyvips colourspace / 纯 numpy sRGB EOTF) | `color_space.py` |
| **S2 Pre-pass** | 算融合内核需要的辅助缓冲:模糊亮度(texture/clarity)、大气光+透射(dehaze)、噪声场(grain)、曲线 LUT 预烘 | `kernel.py` 的辅助 njit |
| **S3 Fused color ops** | 单遍 `@njit(parallel,fastmath)`:linear 段(exposure/WB/叠色)→编码 display→display 段(其余全部 op),inline 各 `apply_px` | `kernel.py` |
| **S4 Output** | display→输出空间(**本期 sRGB 保持**;P3 转基色留 v2.x)、grain 叠加、**嵌 sRGB ICC**、编码回 uint8 → PIL | `color_space.py` + `pipeline.py` |

`render(image, analysis)` = S0→S4 全跑;`preview`(代理)= S0 缩图 + S1-S4;LUT 采样 = 仅
「色彩映射子集」(S1 linear + S3 的非空间 op + S4 编码),复用同一 operator 的 `apply_numpy`。

---

## 五、文件结构规划

### 5.1 推荐:`render.py` → `looklift/render/` 包

现 `render.py` 单文件已承载 9 步 + spatial + score,再加 operator/线性光/numba/4 个新 op 会
变成典型「代码山」。**推荐拆成包**,一 operator 一职责,契合分层规范:

```
looklift/render/
  __init__.py       # 对外契约:render / score / preview;兼容 re-export(见 §七迁移)
  contract.py       # 参数契约单一真相源(D1):param_paths() / param_bounds(path) + hsl 数组/global_ 解析规则
  color_space.py    # sRGB↔linear、ICC 嵌入(pyvips 封装 + 纯 numpy 兜底);P3 转换留位(v2.x)
  base.py           # Operator 协议、Stage/Domain 枚举、RenderParams 扁平结构定义
  pipeline.py       # 分阶段编排 S0-S4;build_params(analysis)->RenderParams;proxy/full 两入口
  kernel.py         # @njit 融合内核 + 预处理辅助 njit(可分离模糊/大气光/噪声/曲线烘 LUT)
  operators/
    __init__.py     # operator 注册表(按 Stage 排序的有序列表)
    basic.py        # exposure / white_balance / contrast / highlights_shadows / whites_blacks
    tone.py         # tone_curve
    color.py        # hsl / saturation / color_grading
    detail.py       # texture / clarity / dehaze
    effects.py      # vignette / grain
```

**operator 按面板域分组(basic/tone/color/detail/effects),不是一 op 一文件。** 理由:AlcedoStudio
正是这样分组(`edit/operators/` 下 basic/color/curve/detail…);一 op 一文件会产生 13 个琐碎小
文件,反而「文件太多」;按 LR 右面板的自然分组既单一职责又不碎——也正好对上 v2.0-B 右面板的
tab 划分。

### 5.2 备选:保持 `render.py` 扁平 —— 不推荐

在单文件内用函数表 + 字典参数模拟 operator。省一次目录重构,但:① operator 的 params 契约、
apply_px/apply_numpy 双形态、enable、注册表塞进一个文件仍是代码山;② 与 lut/intensity 的
复用边界不清晰;③ 违背作者分层规范。**故推荐 5.1 的包结构。**

---

## 六、四个新像素 op 的近似实现思路

四项**均明确定位为「方向正确的近似」(APPROXIMATION)**,不承诺 LR 像素级一致(守
[产品宪法](../../requirements.md) 非目标)。验收判「方向 + 0 值恒等 + 两形态一致」,**不判**与 LR
逐像素吻合。四项工作量**不等权**,heavy 项(fused 内核 T6、大半径模糊 T8、clarity T9、dehaze T10)
在 tasks 里拆子步 + 标风险,不塞进一行平均分配。

| op | 思路 | 关键点 / 风险 |
|---|---|---|
| **texture** | 中频局部对比:亮度做中半径高斯模糊,`L' = L + k·(L − blur_mid(L))`,仅作用于亮度/细节通道避免偏色 | k 由 `texture/100` 定;负值 → 中频柔化(磨皮方向);中半径避免大光晕 |
| **clarity** | 中间调局部对比:更大半径 unsharp + **中间调保护掩码**(高光/阴影少受影响) | 大半径低量、亮度掩码 `4·luma·(1−luma)`;负值 → 柔光/朦胧感。**大半径模糊性能**是 heavy 项(见 T8 预算) |
| **dehaze** | **v2.0-A 只做简单近似**:基于**局部对比 + 饱和度**的去霾——在低对比低饱和区提对比、抬饱和、微压黑场(等效「去雾」方向)。**不实现暗通道先验(dark-channel-prior)** | 若观感不足只调整近似系数并记风险;负值 → 加雾(抬黑、降对比降饱和) |
| **grain** | 单色胶片颗粒:定种子生成高斯/泊松噪声场,按亮度加权(中间调最多),输出前 display 域叠加 | `grain_amount∈[0,100]`;**定种子**保证测试可复现;强度随 `intensity.scale_analysis` 已缩放 |

texture/clarity/dehaze 的邻域/全局部分在 S2 预处理算,grain 的噪声场在 S2 生成、S4 叠加。

> **S2 预处理有独立性能预算(开放问题决策)**:pointwise 融合内核的 <50ms(代理)/<1s(导出)
> 门槛是 spike 只测 pointwise 子集得出的。texture/clarity/dehaze 的**大半径模糊 / 透射估计属 S2
> 预处理**,不是 pointwise——它们**单独计量、单独设预算**。全分辨率导出因 S2 大半径 blur 可能**高于
> <1s**,这是**可接受的**(导出非交互);但代理路径的 S2 须仍落在交互预算内(可在更低分辨率估
> 辅助缓冲再上采样)。见 tasks T8 的 S2 专项 benchmark。

---

## 七、色彩管理

- **转换基元**:优先 **pyvips `colourspace()`**(sRGB↔scRGB-linear),库级正确、快、
  低内存。**纯 numpy 兜底**:精确 sRGB 传递函数(分段 gamma,非 2.2 近似)自实现,不依赖 pyvips
  也能跑核心 linear 运算——**pyvips 定为可选依赖**,主要用于 ICC-正确的 profile 嵌入。
- **导出嵌 ICC(本期 sRGB-only)**:随包附标准 **sRGB IEC61966-2.1** ICC profile 作为包数据;导出时
  `Image.save(..., icc_profile=bytes)`(Pillow 原生支持)或经 pyvips 写入。验收:查看器/exiftool 能
  识别到 profile。**Display-P3 输出导出延后到 v2.x**:色管基元与包结构为 P3 留位(转换函数可先写、
  测试可先备),但 P3 不作为本期交付、不进本期验收门槛,避免 P3 基色 + ICC 打包摩擦拖慢本期地基。
- **Windows/打包风险**:pyvips 依赖 libvips DLL,PyInstaller/Tauri sidecar 打包需带上二进制。
  缓解:pyvips 可选 + numpy 兜底(缺 libvips 时退化为 sRGB-only + Pillow 嵌 profile),**不让
  色管把引擎钉死在 pyvips 安装成功上**;v2.0-B 的打包 spike 再验证 libvips 随 sidecar 分发。

---

## 八、与旧 `render.py` 的迁移策略

**对外契约冻结,内部重写**:

| 对外符号 | 迁移后 |
|---|---|
| `render.render(image, analysis) -> Image` | `render/__init__.py` re-export,签名/语义不变;内部走 S0-S4 |
| `render.score(rendered, target) -> float` | 原样迁入(评分逻辑不属重构范围),行为不变 |
| `render._apply_color_ops(arr, analysis)` | 保留为**兼容 shim**:内部改调 pipeline 的「色彩映射子集」(operator 的 `apply_numpy` 串联,不含 spatial),使 `lut.py` 的 `from .render import _apply_color_ops` 与 `.cube` 采样零改动仍工作。**注意(D6)**:这条「色彩映射子集」现在也走**完整光域往返**(内部 linearize 做 exposure/WB、再 delinearize 回 display),与应用渲染同一条数学——不是另立一套只在 display 域的旧近似 |

### 8.1 LUT 与应用渲染:两条出口一条数学(D6)

review 发现 LUT 导出与应用渲染存在**数学分叉**风险(白盒两条出口不一致)。**决策:`.cube` 表达
与应用画面完全相同的 look**——

- `.cube` 采样一个 **display-referred [0,1]³ 立方体**,每个采样点走**与应用相同的完整色彩管线**
  (`contract`/operator 的 `apply_numpy` 子集:sRGB 入 → 内部 linearize 做 exposure/WB/叠色 →
  delinearize 回 display → 其余 display 段非空间 op),使 **sRGB-in → sRGB-out 与应用所见一致**。
- 由此 `.cube` **烘进了 linearize/delinearize 往返**,数值**不同于旧 LUT**(旧的只在 display 域算),
  但**更正确、且与应用两条出口一致**——这正是本决策要消除的分叉。
- LUT 只含**非空间**色彩映射(texture/clarity/dehaze/grain/vignette 是邻域/位置相关,LUT 表达不了,
  与现状一致,不回归)。
- 新增**LUT-vs-render 观感一致性测试**(见 tasks T13):取若干 RGB 采样点,断言 `.cube` 查表输出
  ≈ 同参数下 `render` 的对应像素输出(容差内),不只做 SIZE/DOMAIN/行数的结构校验。

**TDD 迁移顺序(方向断言先行,分层落地,见 [tasks.md](./tasks.md)):**

1. 先把现 9 步数学**逐字搬进各 operator 的 `apply_numpy`**(仍在 display 域)→ 跑现有
   `test_render.py`,方向断言全绿(此步不改数值,只搬家)。
2. 只把 exposure/white_balance **搬进 linear**(S1/S4 编解码),color_grading 留 display → 新增线性光
   正确性断言(1 档=2×)。此步**会改变数值**(更亮更干净),但现有测试是**方向断言**(exposure>0
   更亮),仍绿;无逐像素 golden 值测试会被打破。
3. 写融合内核 `apply_px` + `fused()`,加「融合 vs numpy 逐 op 一致」容差断言 + 2048px<50ms benchmark。
4. 补 texture/clarity/dehaze/grain 的 `apply_numpy` + `apply_px` + 方向单测。
5. `lut.py` 改为复用 operator 子集(保留 `_apply_color_ops` shim 直到确认无外部引用),`test_lut.py` 全绿。

> `intensity.scale_analysis` 完全不动:它产出的缩放后 analysis 仍是新引擎的输入;factor=0→恒等、
> factor=1→满调,由现有语义保证(§17)。

---

## 九、风险清单

| 风险 | 影响 | 缓解 |
|---|---|---|
| **numba 编译期首帧延迟** | 冷启动/首帧卡数秒,伤 v2.0-B 拖滑杆手感 | `cache=True` 落盘编译产物 + 引擎启动 dummy 图预热;把编译移到启动期 |
| **全管线比 spike 子集慢** | spike 是 5 op;全 13 op+预处理可能超 50ms | 按 ×3-5 估仍 ~50ms;预处理可在更低分辨率算;代理分辨率可调;benchmark 设软门槛及早发现回归 |
| **fastmath 数值发散** | 融合内核与 numpy 参考逐像素不严格相等 | 一致性断言用容差 ≤1/255(而非 `==`);关键正确性(1 档=2×)用独立解析断言 |
| **pyvips/libvips Windows 安装与打包** | 缺 DLL / sidecar 打包漏带二进制 → 导入即崩 | pyvips 可选 + 纯 numpy 兜底(退化 sRGB-only + Pillow 嵌 profile);打包验证移交 v2.0-B spike |
| **线性光改变现有产出数值** | 用户/测试若依赖旧「近似」数值会觉得变了 | 明确定位是画质**提升**(宪法允许「方向正确的近似」有数值演进);无 golden 值测试;CLI 产物只保「方向/格式」不回归 |
| **operator 双形态(px/numpy)漂移** | apply_px 与 apply_numpy 数学不一致 | 「融合前后一致」测试即守护线;新增 op 必须同时提供两形态并过一致性断言 |
| **全分辨率 40MP 导出 >1s** | 批量导出体验差 | 本迭代记录实测、不阻塞;GPU 后端(v2.x)是批量吞吐的答案,不是交互阻断问题 |
