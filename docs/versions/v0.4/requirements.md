# v0.4 Spec:GUI alpha —— 需求

> 状态:已确认(2026-07-17,作者授权自主推进;人工验收项后置)。
> 上游文档:[产品需求](../../product/requirements.md)(定位/用户故事/路线图)、
> [产品架构](../../product/architecture.md)(当前架构)、[v0.3 spec](../v0.3/spec.md)
> (本迭代直接复用的核心 API 来源)。
> 约定:本文件定"做什么、给谁、怎么算完成";技术方案见同目录 [design.md](design.md);
> 任务分解见同目录 [tasks.md](tasks.md)。

## 一句话目标

给不会命令行的入门爱好者(P1)一个本地桌面界面:拖一张照片进来,看它分析、
看报告、收藏进风格库、导出预设——全程不碰终端。

## 背景

v0.3 把「像」这条线做硬(preview 渲染、auto-refine、还原度评分、LUT 导出),
但所有能力都锁在命令行后面。路线图排序逻辑是"先把还原度做硬 → 尽早上 GUI 壳
收集反馈"——v0.4 不新增分析能力,只是把 v0.1-v0.3 已经跑通的核心逻辑接上一层
本地界面。GUI 是壳,业务逻辑仍在 `analyzer`/`render`/`xmp_writer`/`report`/`config`
等核心模块,CLI 与 GUI 永远共享同一实现(见 [产品架构](../../product/architecture.md) 架构原则)。

## 覆盖的用户故事

| # | 用户故事 | 本迭代交付 |
|---|---|---|
| U1 | 给一张大师成片,想知道调色参数和后期思路讲解 | GUI 分析面板:拖拽→AI 分析→网页展示 summary/steps/参数,替代 `analyze` 命令 |
| U4 | 分析结果做成模版,收藏成风格库随时套用 | GUI 风格库面板:一键收藏当前分析结果、列表浏览、导出预设/sidecar |
| U8 | 好看的风格报告,方便保存/分享 | 库面板"打开报告"直接展示 `report.render_report` 生成的自包含 HTML |
| U12 | 不会命令行,想要拖拽图片的界面 | 本迭代的核心交付本身:pywebview 独立窗口 / `--browser` 网页兜底 |
| U20 | 预设想只套 70% 的强度 | 分析面板强度滑杆:对 analysis 参数做全局缩放,联动 before/after 对比条实时预览 |

**间接涉及、非本迭代交付主体**:

- U10(不开 LR 预览套用效果)—— before/after 对比条底层复用 `render.render`,
  但只服务于强度滑杆的实时反馈,不是独立的"preview 面板"功能。
- U6/U11(refine 迭代修正)—— GUI 暂不暴露交互式 refine/auto-refine 界面,
  核心 API(`autorefine.auto_refine`)已就绪,留给 v0.5 GUI 深化时再接 UI。

## 验收标准

对齐 [产品需求](../../product/requirements.md) 路线图 v0.4 行的验收口径:
**不碰命令行,完成 U1/U4/U8 全流程。** 具体拆解:

- [ ] 双击/命令启动 `looklift gui` 后,弹出本地窗口(pywebview),无需任何命令行参数即可操作
- [ ] `looklift gui --browser` 能在系统默认浏览器里打开同一套界面(开发调试/WebView2 缺失兜底)
- [ ] 首次启动且未配置 provider 时,自动弹出配置向导(选 provider、填 key)、写入
      `~/.looklift/config.toml`;配置过一次后再次启动直接进主界面
- [ ] 把一张照片拖进分析面板(window 模式原生拖拽、browser 模式拖拽或点选均可),
      在不输入任何命令的前提下看到 AI 分析结果(风格概述、后期步骤、基本面板参数)(U1)
- [ ] 分析结果可以点一下"收藏"存进风格库,风格库面板能看到列表并展示概述(U4)
- [ ] 从风格库面板打开某个风格的报告页,展示与 `looklift report` 命令等价的
      自包含 HTML(可直接另存分享)(U8)
- [ ] 强度滑杆从 0% 拖到 100%,before/after 对比条随之平滑变化;0% 时预览应与
      原图基本一致,100% 时应与不缩放的原始分析结果一致(U20)
- [ ] 滑杆调整后的强度会带入导出的预设/sidecar(而不是永远导出 100% 强度)
- [ ] 分析面板能导出预设(.xmp)和 RAW sidecar,产物与 CLI `analyze`/`apply` 命令
      写出的文件在同一份参数下内容等价
- [ ] 全程界面视觉基于 `assets/design-system/claude/tokens.css`,无 token 块之外的裸 hex
- [ ] GUI 运行期间除用户主动发起的 AI 分析请求(发给用户配置的 provider)外,
      不产生任何其他外部网络请求

## 非目标(v0.4 明确不做)

- **批量分析 UI**:目录批量拖拽/批量出预设的界面(排在 v0.5+,U14)
- **风格聚类**:自动归纳出几种风格的界面(v0.5+)
- **教学深化**:报告"调色课"式改版、参数原理深讲(v0.6,U15/U16);v0.4 报告页
  直接复用现有 `report.render_report`,不改报告内容/排版
- **auto-refine 交互界面**:上传原片+目标图、迭代校准的可视化流程(U11 底层 API
  已就绪,但不在本迭代做 UI;GUI 暂不暴露 refine/auto-refine 入口)
- **LUT 导出 UI**:`.cube` 导出目前只有 CLI(`export-lut`),GUI 不加对应按钮
- **打包 exe**:PyInstaller 单文件分发(v0.7,U17);v0.4 仍是 `pip install` 后
  `looklift gui` 启动
- **多供应商配置 UI**:仅暴露 v0.3 已有的 provider 选择(cli/api),不做 OpenAI
  兼容中转 / Ollama 的配置界面(v0.5,U13)
- **i18n/多语言**:全中文界面,不做语言切换(对齐产品级非目标)
- **风格库管理进阶操作**:重命名/删除/搜索/标签(超出"列表"范围,YAGNI,需要时
  仍可用文件系统或 CLI 操作 `looks/` 目录)
- **账号/云同步/分享社区**:保持本地工具定位不变(产品级非目标)
- **深色主题切换**:沿用 vendored 设计系统的暖色单一主题,不做主题切换开关
