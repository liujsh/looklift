# v2.0-B Spec:三栏 GUI 壳(Tauri)—— 需求

> 状态:草拟,待作者 review。
> 上游文档:[产品宪法 requirements.md](../../requirements.md)(定位/用户故事/路线图)、
> [方案 plan](../../plans/)(一站式升级调研与技术栈定案,见根 plan 文件的"技术栈定案"表)、
> [specs 规范](../README.md)。
> 平级依赖:本迭代驱动的是 **v2.0-A 引擎**(operator 化 + 线性光 + numba 融合渲染);
> v2.0-A spec 尚未落地,本文件对引擎的引用按"现有 `render.render(PIL, analysis)->PIL`
> + `ANALYSIS_SCHEMA` operator 参数模型"的概念契约书写,v2.0-A 落地后回填精确接口。
> 约定:本文件定"做什么、给谁、怎么算完成";技术方案见同目录 [design.md](design.md);
> 任务分解见同目录 [tasks.md](tasks.md)。

## 一句话目标

把 looklift 从"逆向分析 + 导出预设"的伴侣工具,升级出一个**一站式调色应用的交互壳**:
用户在一个原生桌面窗口里,以 **Open-Design 三栏形态**(中画布 + 右全局调色面板 + 图库)
完成"拖图 → 面板逐参数手动精调 → 看 before/after diff → 收藏进库 → 导出"的闭环,
全程不碰命令行,也不再依赖 LR/PS。

## 范围边界(binding scope)

本迭代**只交付三栏中的两栏半**:**中画布 + 右全局调色面板 + 图库**。
**左侧 AI 聊天调参不在本期**(属 v2.1)。壳采用 **Tauri(Rust 构建期)+ React+TS+Vite
前端 + Python 引擎作 sidecar**,取代 v0.4 的 pywebview + vanilla-JS SPA。

## 背景

方案调研(六路)已收敛:一站式方向底层哲学有顶会背书,引擎约七成已就位,渲染只能手搓
(v2.0-A 做),GUI 形态换 Tauri+React(有意推翻 v0.4"不引入 Node/Electron 栈"的旧约束——
那是 pywebview 的约束,新大版本线重开)。v0.4 的 **Python 引擎、api.py 路由设计、设计 tokens
100% 留用**;只有 pywebview 壳 + vanilla-JS 前端被 React 取代(carry-forward 清单见
[design.md](design.md))。

## 覆盖的用户故事

| # | 用户故事 | 本迭代在新形态下的交付 |
|---|---|---|
| U1 | 大师成片想知道参数+后期思路 | 拖图入中画布 → 右面板展示 AI 分析出的逐参数值 + summary/steps,不再只读、可继续手调 |
| U4 | 分析结果收藏成风格库随时套用 | 图库栏"收藏当前"入库(复用 `POST /api/looks`);库卡片一键载入到面板/画布 |
| U8 | 好看的风格报告,方便保存/分享 | 库卡片"打开报告"沿用 `GET /report/<name>` 自包含 HTML(新窗口/新标签) |
| U12 | 不会命令行,想要拖拽界面 | 本迭代核心:Tauri 原生窗口三栏形态,拖拽入库/入画布 |
| U20 | 预设只套 70% 强度 | 面板顶部全局强度滑杆(复用 `intensity.scale_analysis`),联动实时预览 |
| **新** | **应用内手动精调** | 右面板每个 operator 参数一根滑杆/曲线控件,拖动 → 防抖 → 代理渲染 → 中画布实时更新 |
| U16 | 预置经典风格库开箱即用 | 图库栏内置**知名调色模板**(青橙/胶片/日系,= 原 v0.6 U16 并入),版权用通用风格描述 |

**间接涉及、非本期交付主体**:U10(不开 LR 预览)—— 实时预览底层复用引擎渲染,但服务于
面板精调而非独立 preview 功能;U6/U11(AI 迭代修正)、U13(多供应商)—— 留给 v2.1 左聊天。

## 可勾选验收标准

### A. 端到端手动调色闭环(不碰命令行)

- [ ] 拖一张 JPEG/PNG/TIFF 进中画布(或图库),图片显示,右面板出现该图的参数控件
- [ ] 点"AI 分析"后,右面板各 operator 滑杆/曲线**回填**为分析结果值,中画布出成片预览
- [ ] 拖动任一参数滑杆(如曝光/对比/HSL/曲线),**防抖后**中画布在交互延迟内更新预览
- [ ] 中画布 before/after 对比滑块可左右拖动,直观对比原图与当前参数下的成片
- [ ] 顶部全局强度滑杆拖到 70%,预览按比例减弱,数值语义与 `intensity.scale_analysis` 一致
- [ ] "收藏当前"输入名称入库,图库栏立即出现新卡片(重名被拒,提示中文)
- [ ] 库卡片可"载入"(参数回到面板/画布)、"打开报告"、"导出预设/sidecar"
- [ ] 图库栏能看到内置知名模板(青橙/胶片/日系),点击可载入并在画布预览

### B. 打包产物(T1 gate 的交付物)

- [ ] `T1` 打包 spike 通过:Tauri 安装包能**双击运行**,启动时**自动拉起 Python sidecar**,
      前端与 sidecar IPC 往返成功(见 [design.md](design.md) T1 go/no-go 设计)
- [ ] **T1 冻结的是真实引擎 sidecar,不是 `/api/ping` stub(D4)**:该 sidecar **真正 import
      numba + pyvips**、启动时 JIT 编译一次并跑一帧真实渲染,验证:(a) PyInstaller **onedir**
      能运行;(b) **numba cache 目录在冻结应用里可写**(否则每次启动多秒重编译——须落实可写
      cache 位置 / 构建期预热 / 预编译产物);(c) 记录**冷启动耗时**;(d) Windows **Defender 不误报**
- [ ] 关闭窗口时 sidecar 进程随之退出(不留孤儿进程)
- [ ] 内置模板与用户上传库在打包产物里可读写(库目录定位在安装后仍正确)

### C. 视觉与手感(人工验收,集中在 tasks.md 最后一节)

- [ ] 三栏配色/字体沿用 Claude 设计 tokens(暖米/赤陶),不是默认蓝灰
- [ ] 三栏比例、面板分组(基础/色彩HSL/曲线/分级/效果)符合 ART 风格分组直觉
- [ ] 拖拽入库、滑杆手感、曲线编辑在真机 WebView 环境流畅

## 非目标(本期明确不做)

| 不做 | 归属 |
|---|---|
| 左侧 AI 聊天调参 | v2.1(壳里为其**预留栏位/状态 seam**,但不实现) |
| 局部调整(蒙版/渐变/画笔) | v2.x backlog |
| RAW 解码输入 | v2.x(守 sRGB/JPEG/TIFF 输入边界) |
| 批量分析/批量导出 UI | 沿用 CLI;GUI 只做单图交互 |
| 从 Instagram 等抓取模板 | 永不做,只手动上传 + 内置(避开反爬/版权/ToS) |
| 引擎内部实现(operator/线性光/numba) | v2.0-A;本期只**调用**引擎渲染契约 |
| 撤销/重做 **UI**(时间线/快捷键) | 本期不做,避免过度设计。**但版本栈 seam 本期建**(D2):`editorStore` 每次应用变更(手动拖滑杆 **或** 未来 chat delta)都 push 一版——**chat 与手动编辑共用这一个版本栈**;undo 界面延后,但状态层的编辑历史单一 owner 本期就位(见 design.md §6) |
| 代码签名/安装器美化/自动更新 | 分发打磨,后置 |

## 对 v2.0-A 引擎的依赖

本迭代是**壳**,不含任何调色像素逻辑;强依赖 v2.0-A 提供以下契约(未落地前按现有
`render.py`/`intensity.py` 概念等价物对接):

| 依赖项 | 契约(本期需要的最小面) | 现状 |
|---|---|---|
| 渲染 | `render(image, analysis) -> image`,2048px 代理单帧在交互延迟内(spike 实测 numba 融合 9.4ms) | v2.0-A 落地;现 `render.render` 已可用但未融合 |
| operator 参数模型 | `ANALYSIS_SCHEMA` 分片(基础13项/tone_curve/8通道HSL/4区color_grading/effects)= 面板绑定的状态对象 | 现有,直接用 |
| **参数契约(min/max/路径)** | v2.0-A 的 `looklift/render/contract.py`(D1):`param_paths()` + `param_bounds(path)` + `resolve_path`。右面板每根滑杆的 **min/max/复位默认从此导出**,**不在前端手抄/回填**一份范围表 | v2.0-A 交付;经 api.py 暴露给前端(见 design.md §3.1) |
| 强度缩放 | `intensity.scale_analysis(analysis, factor)` | 现有 |
| 导出 | 预设/sidecar/LUT 导出(`xmp_writer`/`lut`) | 现有,复用 api.py 路由 |
| 库 IO | `lookstore` list/load/save/export | 现有,本期扩展内置模板 |

> 若 v2.0-A 未先行,本期可先对接现有 `render.render`(未融合、2048px ~1-2s),
> 面板手感验收在引擎融合后复测;**打包 gate(T1)不依赖引擎性能,可独立先行**。
