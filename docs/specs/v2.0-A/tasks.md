# v2.0-A Spec:引擎重构 —— 任务清单

> 状态:已确认(2026-07-17,作者授权开工)。同迭代:[需求](./requirements.md) · [设计](./design.md)。
> 任务按依赖顺序排列,每条一句验收;TDD 友好——**方向/正确性断言先行,再写实现**。
> 需真人在真实环境操作的验证集中放最后「人工验收」一节,不混进自动化任务。

## T1 依赖与包骨架

`pyproject.toml` 加依赖 `numba`(BSD)+ 可选 `pyvips`(建议进 `[project.optional-dependencies]`
如 `render = ["pyvips"]`);把 `looklift/render.py` 转为 `looklift/render/` 包,建
`__init__.py`/`contract.py`/`base.py`/`pipeline.py`/`kernel.py`/`color_space.py`/`operators/`(见
[design.md §5.1](./design.md));`operators/` **按面板域分 5 文件**(basic/tone/color/detail/effects,
**不是一 op 一文件**——避免 13 个碎文件,且对齐 v2.0-B 右面板 tab);随包附 **sRGB** ICC profile
为包数据(Display-P3 输出留 v2.x,本期不附 P3 profile 也不作 P3 验收)。

**验收**:`python -c "import looklift.render"` 不报错;`from looklift.render import render, score`
可导入;现有 `test_render.py` 在**旧数学原样搬入**后全绿(纯搬家,不改数值)。

## T2.5 参数契约模块 `contract.py`(D1,最早,B/C 消费前必须就位)

跨 spec 单一真相源(见 [design.md §1.5](./design.md))。**次序上要早**——v2.0-B 右面板(min/max/复位)
与 v2.1 delta(path 枚举 + clamp)都从它导出,故排在引擎大改前先落地:
- 给 `ANALYSIS_SCHEMA` 各**数值字段**补 `minimum`/`maximum`(标准 JSON-Schema 关键字;单一 schema
  仍是唯一真相源,不建平行范围表,不增删业务字段);
- `param_paths() -> list[str]`:枚举可调路径(`basic.*`/`hsl.<color>.*`/`color_grading.<zone>.*`
  + `blending`/`balance`/`effects.*`;**不含 `tone_curve`**);
- `param_bounds(path) -> (min,max)`:从 schema 读范围;
- `resolve_path(analysis, path)`:封装 **hsl 数组按 `color` 段定位/补零** 与 **`color_grading.global_`
  下划线映射** 两个怪癖。

**验收**:单测——`param_paths()` 每条 path 都能被 `resolve_path` 解析到 analysis 落点(含
`hsl.blue.saturation` 命中数组项、`color_grading.global.hue`→`global_` 键);每个数值字段
`param_bounds` 都返回 (min,max)、无 None;`tone_curve` 不在 `param_paths()` 内。

## T2 operator 基类与扁平参数结构

`base.py`:定义 `Operator` 协议(`name`/`stage`/`domain`/`resolve`/`apply_numpy`/`apply_px`)、
`Stage`/`Domain` 枚举、扁平 `RenderParams` 结构 + per-op enable 位掩码(见 [design.md §1.2/§1.4](./design.md))。

**验收**:pytest 覆盖一个 stub operator 的 `resolve` 全 0 返回 `None`(enable=False)、非 0 返回
参数元组;`RenderParams` 打包/取用往返一致。

## T3 色彩空间基元(`color_space.py`)

sRGB↔linear(精确分段传递函数,**纯 numpy** 实现)+ ICC 嵌入封装(Display-P3 基色转换**留位、v2.x**,本期只做 sRGB);
pyvips 可用时走 `colourspace()`,不可用时走 numpy 兜底路径(见 [design.md §七](./design.md))。

**验收**:pytest 断言 sRGB→linear→sRGB 往返误差 <1e-5;线性光下中灰 0.5(display)映到已知
linear 值;pyvips 缺失时(monkeypatch)兜底路径仍给出一致结果。

## T4 现有色彩 op 逐字迁入(display 域,不改数值)

把现 `_apply_color_ops` 的 exposure/white_balance/contrast/highlights_shadows/whites_blacks/
tone_curve/hsl/saturation/color_grading 九步的数学**逐字搬进各 operator 的 `apply_numpy`**
(暂全在 display 域),`pipeline.py` 串起来。

**验收**:每个 op 有方向单测(exposure>0 更亮、contrast>0 反差增大、HSV 往返等);现有
`test_render.py` 全绿;此步渲染输出与重构前**数值一致**(证明纯搬家)。

## T5 曝光/白平衡迁入线性光

按 [design.md §二](./design.md):只有 `exposure`/`white_balance` 移到 linear 段(S1 编码进、
编码 display 后再走其余 op);`color_grading` 整体留在 display 段。linear 中间值不得提前 clip。

**验收**:线性光正确性断言——纯 +1.0 EV 使 linear 亮度精确 ×2(误差<1%)、+2.0 EV ×4;
白平衡叠加符合线性叠加;linear 段内**不提前 clip**(中间值可 >1,直到 display 编码前,见
[design.md §2.4](./design.md))。**方向断言保持,但审计并重新标定 `test_render.py` 所有幅度阈值(D5)**:
如 `test_exposure_positive_brightens` 现断言均值 >0.4——线性光下 +1EV @0.25 得约 0.352,方向仍变亮
但阈值须调低;逐个复核每条幅度标定断言并重设阈值(方向不变、阈值可变;本项目无逐像素 golden)。

## T6 numba 融合内核(`kernel.py`)—— **heavy,拆子步**

把各 op 的 `apply_px`(njit device 函数)inline 进单个 `@njit(parallel=True, fastmath=True,
cache=True)` 的 `fused()`;linear 段→编码→display 段的单次光域切换在内核内完成(见
[design.md §3](./design.md))。**这是本迭代最大的单块工作,分子步推进,不当一行估:**
- T6a:把已迁入的 `apply_px` 逐个 inline,先跑通「linear 段(exposure/WB/叠色)→编码→display 段」骨架;
- T6b:接 RenderParams 扁平结构 + per-op enable 位掩码(0 值 op 内核里 `if` 短路);
- T6c:开 `parallel=True, fastmath=True, cache=True`,处理浮点结合序带来的容差;
- **风险**:`fastmath` 数值发散(用容差 ≤1/255 而非严格相等)、冷编译首帧延迟(见 T7 预热)。

**验收**:「融合 vs numpy 逐 op 参考」逐像素一致,容差 ≤1/255;`fused()` 服务代理与全分辨率
两入口(同一内核);`cache=True` 生效(二次导入不重编译);numba 缺失时**纯 numpy 兜底管线**
(`apply_numpy` 串联)仍能出图(方向一致,慢),不只用于测试/LUT。

## T7 性能 benchmark 与预热

`pipeline.py` 提供代理(长边 2048)与全分辨率两入口;加启动预热(dummy 图触发 JIT);
2048px 全 op benchmark 计时(warmup 后)。

**验收**:2048px 代理的 pointwise 融合内核 **<50ms**(全 pointwise op 全开、单机、warmup 后)
作为软门槛回归项(超阈告警);
记录 40MP 全分辨率导出实测(不阻塞)。

## T8 预处理阶段(空间辅助缓冲)—— **heavy(大半径模糊),含 S2 专项 benchmark**

`kernel.py` 加 S2 预处理 njit:可分离高斯模糊(texture/clarity 用,**大半径是性能重点**)、
dehaze 局部对比辅助场、定种子噪声场(grain 用);融合内核只读前三个新 op 的空间缓冲,
grain 噪声场留给 S4,融合内核主体不得叠 grain
(见 [design.md §3.3/§六](./design.md))。子步:
- T8a:可分离高斯模糊 njit(小/中/大半径);大半径用低分辨率估 + 上采样控成本;
- T8b:噪声场(定种子);
- T8c:**S2 专项 benchmark**——S2 预处理不是 pointwise,代理路径独立软门槛 **<200ms**;
  完整帧只记录,不与融合内核 <50ms 混算。

**验收**:模糊/噪声各有单测(模糊核归一、噪声定种子可复现);预处理输出形状与主内核对接正确;
**S2 专项 benchmark 记录**——代理路径 S2 仍落在交互预算内(必要时更低分辨率估辅助缓冲);全分辨率
导出因 S2 大半径 blur **可高于 <1s**(可接受,导出非交互),实测记录、超预期记入风险。

## T9 texture / clarity 像素实现 —— **近似(APPROXIMATION),clarity heavy**

`operators/detail.py`:texture(中半径 unsharp,仅亮度)、clarity(大半径 unsharp + 中间调保护掩码),
各提供 `apply_numpy` + `apply_px`(见 [design.md §六](./design.md))。两者均**明确定位方向正确的近似**,
不判与 LR 逐像素吻合。clarity 大半径掩码合成是 heavy 项(依赖 T8a 的大半径模糊)。

**验收**:texture>0 使中频局部方差增大、clarity>0 使中间调对比增强且高光/阴影少受影响;0 值恒等;
px 与 numpy 两形态一致(容差);验收只判**方向 + 0 值恒等 + 两形态一致**,不判 LR 像素级一致。

## T10 dehaze 像素实现 —— ⚠️ **最高研究风险,简单近似优先 / 可 mini-spike**

`operators/detail.py`:**v2.0-A 只做简单近似**——基于**局部对比 + 饱和度**的去霾(低对比低饱和雾区
提对比、抬饱和、微压黑场),**不做完整暗通道先验(dark-channel-prior)**(大气光/透射估计精度与性能
不确定,超本期)。先用方向测试验证简单局部对比/饱和近似;若观感不足,只调整近似系数并
记入风险,不得转入暗通道、大气光或透射图实现。

**验收**:dehaze>0 使低对比低饱和雾区对比与饱和上升、dehaze<0 加雾(抬黑降对比);0 值恒等;两形态一致;
**明确标注为近似**,不判与 LR 逐像素一致。

## T11 grain 像素实现

`operators/effects.py`:定种子噪声场按亮度加权、输出前 display 域叠加;`vignette` 一并迁入本文件。

**验收**:grain_amount>0 使局部方差增大且中间调最明显、同种子可复现;S2 只生成噪声场、S4
只叠加一次且融合内核主体不含 grain;vignette 迁移后 `test_render.py`
暗角断言全绿;0 值恒等。

## T12 输出阶段 + ICC 嵌入(本期 **sRGB-only**)

S4:display→输出(**本期 sRGB 保持**)、grain 叠加、嵌 **sRGB** ICC、编码回 PIL(见
[design.md §四/§七](./design.md))。**Display-P3 输出延后 v2.x**:色管基元/包结构可为 P3 留位,
但 P3 转基色 + P3 profile 不作为本期交付、不进本期验收。

**验收**:导出图能被 exiftool / 系统查看器识别到 sRGB ICC profile 字段;pyvips 缺失时退化为
Pillow 嵌 profile 仍产出合法带 profile 文件。(P3 色块落点验收随 v2.x。)

## T13 LUT 复用同一 operator 管线 + 观感一致性(D6)

`lut.py` 的 `.cube` 采样改为复用 operator 的「色彩映射子集」(`apply_numpy` 串联,不含 spatial);
保留 `render._apply_color_ops` 兼容 shim 直到确认无外部引用(见 [design.md §八/§8.1](./design.md))。
**关键(D6)**:`.cube` 采样 display-referred [0,1]³ 立方体、走**与应用相同的完整光域往返**
(内部 linearize 做 exposure/WB、再 delinearize 回 display),使 sRGB-in→sRGB-out 与应用画面一致。
这会使 `.cube` 数值不同于旧 LUT(旧的只在 display 域算),但更正确、两条出口一致。

**验收**:`test_lut.py` 全绿(SIZE/DOMAIN/行数/取值范围结构不回归);**新增 LUT-vs-render 观感一致性
测试**——取若干 RGB 采样点,断言 `.cube` 查表输出 ≈ 同参数下 `render` 对应像素输出(容差内),
不只做结构校验;LUT 采样走新管线子集,不再依赖旧大函数内部实现。

## T14 对外契约与 CLI 不回归验证

确认 `render.render`/`render.score` 签名语义不变;`intensity.scale_analysis` 与新引擎联调
(factor=0 渲染≈原图、factor=1 满调);CLI 的 `preview`/`export-lut`/`apply` 端到端跑通。

**验收**:`test_autorefine.py`/调用 `render` 的既有测试全绿;新增 factor=0/1 语义断言;CLI 三命令
产物在「方向/格式」层面与重构前等价(允许线性光数值改进)。

## T15 文档回填与 CI

`docs/design.md` 按惯例在实现后回填本迭代架构要点(operator/线性光/融合/分阶段/ICC);
`docs/tasks.md` 补 v2.0-A 历史记录;版本号推进;CI 绿(含 numba 编译、benchmark 软门槛)。

**验收**:`pytest -q` 全绿;design.md 新增引擎重构小节;CI 三平台矩阵通过(numba/pyvips 可选依赖
在缺失时有兜底,不装也能跑核心测试)。

---

## 人工验收

以下需真人在真实环境操作确认,不追加到上面的自动化任务。

- [ ] **渲染保真度肉眼对比 LR**:取几张真实照片,在 LR 里调一组已知参数导出,用同一份参数喂
      新引擎渲染,肉眼对比色调/影调方向是否一致、有无明显偏色/断层——不追求像素级一致,追求
      「方向正确、干净、不 muddy」
- [ ] **线性光画质跃迁感知**:同一张欠曝照片分别用旧引擎(gamma 域曝光)与新引擎(线性光曝光)
      提亮,确认新引擎更亮更干净、不发暗发浊
- [ ] **四个新 op 观感**:分别拉 texture/clarity/dehaze/grain,确认效果方向与 LR 同名滑杆一致、
      无明显光晕/噪点异常;负值方向(柔化/加雾)也观感合理
- [ ] **交互手感(为 v2.0-B 预验)**:在一张全分辨率真实照片的 2048px 代理上连续快速改参,确认
      单帧刷新接近瞬时(<50ms 无肉眼卡顿),预热后首帧无明显编译停顿
- [ ] **导出成片跨设备正确**:导出嵌 **sRGB** ICC 的成片(P3 输出留 v2.x),在不同显示器/查看器打开
      确认颜色一致(嵌 ICC 生效),对比不嵌 profile 的旧产物的偏差
- [ ] **全分辨率导出耗时**:对 40MP 照片实测导出耗时,确认在可接受区间(记录数值,超预期则评估
      是否需提前引入 v2.x GPU 后端)
