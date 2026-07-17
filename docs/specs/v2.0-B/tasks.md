# v2.0-B Spec:三栏 GUI 壳(Tauri)—— 任务

> 状态:草拟,待作者 review。
> 上游:[requirements.md](requirements.md)、[design.md](design.md)。
> 约定:按依赖排序,每任务一句验收;**人工验收集中在最后一节**。
> **T1 是决策门(gate):不通过不进 T2+**。

## 任务依赖概览

```
T1 打包 gate(go/no-go)──┬─ NO-GO ─► 回退 pywebview(仍复用 api.py + React 产物)
                        └─ GO ─► T2 前端脚手架 ─► T3 通信 client ─► T4 中画布 diff
                                    │                                    │
                                    ├─► T5 右面板骨架+分组 ──► T6 各 operator 控件
                                    │                          ├ T6a 曲线(许可 gate)
                                    │                          ├ T6b HSL / T6c 色轮
                                    │                          └ T6d 强度滑杆
                                    ├─► T7 实时渲染绑定(防抖+串行防叠加)
                                    │      └─► T7b 版本栈 seam(editorStore,chat 与手动共用)
                                    ├─► T8 图库(lookstore 扩展 + 内置模板)
                                    ├─► T9 设计 token 主题移植
                                    └─► T10 收藏/导出/报告接线
                                             └─► T11 sidecar 生命周期打包收口
```

## T1 —— Tauri + Python sidecar 打包 gate(最先,决策门)

> 目标:证实"双语言 + sidecar + 双重打包"链路可行,**通过才建 UI,失败则回退 pywebview**。
> 详见 [design.md §2](design.md)。本任务不建任何业务 UI。

| # | 任务 | 验收 |
|---|---|---|
| T1.1 | 装 Rust 工具链(cargo/rustc)+ Tauri CLI,脚手架 Tauri + React+TS+Vite | `tauri dev` 起空窗口,`tauri build` 出安装包 |
| T1.2 | **打包真实引擎 sidecar(非 stub,D4)**:sidecar **真正 import numba + pyvips**、启动 JIT 编译一次并跑一帧真实渲染(v2.0-A 引擎;未就位则用真实 `@njit(cache=True)` 内核 + `pyvips.Image` 调用),PyInstaller **onedir** 成 exe | 独立双击该 exe,能跑通一帧真实渲染;numba/pyvips 均成功冻结加载(非 `/api/ping` stub) |
| T1.2b | **numba cache 可写 + 冷启动计量(D4)**:确保冻结应用里 numba cache 落在可写目录(否则每次启动重编译);测量冷启动耗时 | 二次启动**不重编译**(cache 命中);冷启动耗时记录在案;必要时落实预热/预编译 |
| T1.2c | **Defender 不误报(D4)** | 干净 Windows onedir 产物不被 Defender 拦截/隔离 |
| T1.3 | sidecar exe 声明为 Tauri `externalBin`,随包分发 | 安装包内含 sidecar 二进制 |
| T1.4 | Tauri 启动时 spawn sidecar + 端口协商注入前端;窗口关闭回收进程 | 启动后前端 `/api/ping` 与**一次真实渲染**往返成功;关闭后无孤儿进程 |
| T1.5 | **门禁判定**:干净环境双击安装包,T1.1–T1.4 全部成立(**含 numba+pyvips 真实冻结、cache 可写、Defender 通过**) | **GO** → 进 T2;**NO-GO** → 记录摩擦点(尤其 numba/libvips 冻结失败点),回退 pywebview 方案(design.md §2) |

## T2–T11 —— UI 与集成(T1 GO 后)

| # | 任务 | 依赖 | 验收 |
|---|---|---|---|
| T2 | 前端三栏布局骨架(grid:聊天seam/中画布/右面板 + 图库);聊天栏 feature-flag 关闭留 seam | T1 | 三栏空壳按 design.md §3 排布,窗口缩放不塌 |
| T3 | `api/client.ts`:封装对 sidecar 的 fetch(analyze/preview/looks/report);端口从壳注入 | T2 | client 能打通 sidecar `/api/ping` 与 `/api/looks` |
| T4 | 中画布:集成 sneas/img-comparison-slider(**先核 LICENSE**),显示 before/after + 加载/错误态 | T3 | 拖入图显示,diff 滑块可左右拖 |
| T5 | 右面板容器 + operator 分组(基础/HSL/曲线/分级/效果)骨架,绑定单一 `analysis` 状态对象 | T3 | 分组按 ART 风格排布,读写同一状态对象分片 |
| T6 | 各 operator 控件:滑杆(基础13/效果2)+ 数值输入 + 复位;**min/max/复位默认从 v2.0-A 参数契约导出(D1),经 api.py `GET /api/param-contract` 取,前端不手抄范围表** | T5 | 拖任一滑杆改 `analysis` 对应字段,数值即时反映;滑杆上下界与 `contract.param_bounds` 一致 |
| T6a | 曲线控件(ToneCurve):**许可 gate**——ColorCurve 许可宽松则包用,否则自研极简单调 Hermite 曲线 | T5 | 曲线点可增删拖动,产出 `tone_curve` 控制点 |
| T6b | HslMixer:8 通道 × 色相/饱和/明度 | T5 | 改任一通道写入 `hsl` 分片 |
| T6c | ColorGradingWheels:4 区色轮 + blending/balance | T5 | 改色轮写入 `color_grading` 分片 |
| T6d | 全局强度滑杆(factor),复用 `intensity.scale_analysis` 语义 | T5 | 70% 时预览按比例减弱 |
| T7 | 实时渲染绑定:滑杆改动 → 防抖 → `POST /api/preview` → 更新 after;**单一在途 + AbortController 取消过期** | T4,T6 | 连续拖动不堆积请求,慢响应不覆盖新画面 |
| T7b | **版本栈 seam(D2,editorStore 单一 owner)**:`editorStore` 每次应用变更(手动拖滑杆定格 / 未来 chat delta)push 一版 `analysis` 快照;**undo UI 本期不做**,只建 seam 供 v2.1 共用 | T6 | 应用 N 次变更后版本栈有 N 版;`applyDelta`/分片更新走同一 push 通路(v2.1 复用);无 undo 按钮/时间线 |
| T8 | 图库:`lookstore` 扩展"内置模板只读源"(青橙/胶片/日系,通用风格描述,不抄商业预设参数)+ 用户库合并列出;卡片网格 | T3 | 图库显示内置 + 用户库,卡片可载入到面板/画布 |
| T9 | 设计 token 主题:移植 `tokens.css` 为 React 主题,三栏套暖米/赤陶配色 | T2 | 三栏用 `var(--*)`,非默认蓝灰 |
| T10 | 收藏/导出/报告接线:复用 `POST /api/looks`、`/export`、`GET /report/<name>`(新窗口/新标签) | T3,T8 | "收藏当前"入库(重名拒);"打开报告"出 HTML;导出预设/sidecar 成功 |
| T11 | 打包收口:**真实引擎 numba/pyvips 冻结已在 T1 gate 证实(D4 提前)**,本任务收口——把完整 UI + 最终引擎 sidecar 一并打包 + 库目录定位到用户可写目录 + 内置模板随包只读 | T1,T8,T10 | 打包产物里收藏/内置模板/导出读写路径全部正确;沿用 T1 已验证的 numba cache 可写策略 |

> **T6a 许可 gate 提示**:ColorCurve 许可若在 T4 核对阶段确认不明,T6a 直接走自研分支,不阻塞。
> **YAGNI**:不实现撤销/重做/编辑历史;聊天栏只留 seam 不写逻辑;不做 RAW/局部/批量 UI。

## 人工验收(集中,作者/真机 WebView 环境)

> 自动化(playwright 驱动三栏流程 + 组件回归)覆盖功能正确性;以下是**只能人工判断**的项,
> 迭代收尾时集中验收。

| # | 验收项 | 判据 |
|---|---|---|
| M1 | 打包产物真机双击 | 干净 Windows 环境双击安装包 → 应用起 → 自动拉起 sidecar → 可用;关闭无孤儿进程 |
| M2 | 端到端手动调色闭环 | 拖图 → AI 分析回填面板 → 拖滑杆看 diff → 收藏 → 导出,全程不碰命令行 |
| M3 | 三栏视觉 | 暖米/赤陶配色 + 衬线标题 + 环形描边,符合 Claude 设计系统气质,不是模板默认样式 |
| M4 | 三栏手感 | 三栏比例/面板分组(基础/HSL/曲线/分级/效果)符合 ART 直觉;曲线/色轮操作顺手 |
| M5 | 拖拽 | 拖图入画布/图库在真机 WebView 流畅;拿到真实路径(无谓上传拷贝) |
| M6 | 实时预览手感 | 拖滑杆预览更新在交互延迟内(引擎融合后 <50ms 目标);连续拖动不卡不叠画面 |
| M7 | 内置模板 | 青橙/胶片/日系可载入并在画布预览,风格观感成立(版权用通用风格描述) |
| M8 | 大图稳定性 | 高分辨率图(如 40MP)预览不 OOM、不长时间冻结 |

## 待作者决策(不阻塞草拟)

- [ ] T1 打包若 NO-GO,回退 pywebview 是否接受(牺牲 ~10MB 轻分发,换不阻塞 UI 交付)?
- [ ] PyInstaller 用 onedir(启动快/易白名单)还是单文件(洁癖分发)?草案 onedir。
- [ ] 内置模板首批清单(青橙/胶片/日系的具体几个变体)—— 承接 v0.6 U16 未定项。
- [ ] 图库栏放底部横条还是右侧?(design.md 画的是下方横条,可调)
- [ ] 本期是否要 macOS/Linux 打包验收,还是仅 Windows 优先、其余顺延?
