# looklift 任务清单

> 路线图与验收标准见 [requirements.md](requirements.md)。这里只放当前迭代的可执行任务和历史记录。

## v0.5(下一迭代):供应商 + 库

> 详细设计与验收:[specs/v0.5/](specs/v0.5/)(requirements.md / design.md / tasks.md)

## Backlog(未排期)

- 手机 DNG 预设(LR Mobile 免费版可用)(U18)
- LR 插件形态(U21,Neurapix 验证过的工作流终态)
- 风格分享/社区(U22,远期)
- 风格报告 before/after 对比图(需可公开图片)
- Capture One 风格文件导出
- 目录批量分析自动聚类(排在 v0.5+)

## 历史

### v0.4(2026-07-17)✅ 除 9 项人工验收

> 详细设计:[specs/v0.4/](specs/v0.4/)(requirements.md / design.md / tasks.md);要点已回填 [design.md](design.md) §16-19。

`looklift gui` 子命令(默认 pywebview 独立窗口,未装/WebView2 缺失自动降级浏览器模式并
中文提示;`--browser`/`--port`)/ 本地 stdlib `ThreadingHTTPServer`(127.0.0.1:随机端口,
统一服务窗口与浏览器两种模式)/ `looklift/gui/` 包(app/server/api/tasks/upload/lookstore,
分层清晰,CLI 与 GUI 共享同一核心实现)/ 前端 SPA 壳(分析/风格库/设置三面板)+ 强度滑杆
before/after 对比条 + 风格库收藏导出 + 可跳过的首次配置向导/ 新核心
`intensity.scale_analysis`(U20 强度语义)、`config.save_config`、render 曲线域外斜率
外推/ 安全:XSS 双层修复(report.py 转义 + analysis 结构校验)、`api_key` 永不回传、上传
文件名硬化、库名拒绝式校验/ 视觉:vendored Claude tokens + components 配方,tokens-only
强制扫描,零外部网络请求/ 214 pytest(v0.3 末 71 + 新增 143,全部离线)+ 三平台 CI/
版本 0.4.0

- [ ] **人工验收(9 项)全部待作者**:视觉核对/两种模式的拖拽体验/强度滑杆手感/首次配置
  向导两条路径(填写完成/稍后跳过)/WebView2 缺失兜底/长任务体验(窗口不"未响应")/
  U1·U4·U8 全流程复核/视觉 token 合规抽查,逐条清单见
  [specs/v0.4/tasks.md](specs/v0.4/tasks.md) 「人工验收」一节
- [ ] **待作者产品决策**:分析面板"导出需先收藏"是否符合预期 UX(是 spec 路由表的忠实
  实现,但 requirements.md 原始措辞有歧义,已记录自主决策依据),见 [dev-log.md](dev-log.md)

### v0.3(2026-07-17)✅ 除 2 项人工验收

> 详细设计:[specs/2026-07-16-v0.3-precision-loop.md](specs/2026-07-16-v0.3-precision-loop.md);要点已回填 [design.md](design.md) §10-15。

provider 抽象(`~/.looklift/config.toml` + Block 约定,cli/api 双后端迁入 providers.py)/
风格库默认目录迁至 `~/.looklift/looks/`(cwd `looks/` 向后兼容优先)/
本地近似渲染 `preview` + 还原度评分 `score` / `refine --auto` 自动闭环(渲染→评分→AI 修正)/
LUT 导出 `export-lut`(.cube,U19)/ 57 pytest(含 autouse 隔离夹具)+ 三平台 CI(ubuntu/windows/macos)/
版本 0.3.0

- [ ] 真实照片端到端验证:auto-refine 3 轮内评分上升(**人工验收,待作者素材**,见 [dev-log.md](dev-log.md))
- [ ] .cube LUT 剪映加载验证(**人工,待作者**,达芬奇留社区反馈,见 [dev-log.md](dev-log.md))

### v0.2(2026-07-16)✅
打包(looklift 命令)/ 多图合成风格 / HTML 风格报告(SVG 曲线)/ 23 pytest + 双平台 CI / docs 三件套

### v0.1(2026-07-16)✅
analyze(单图/原片对照,双后端)/ read(内嵌 XMP 提取)/ 预设+sidecar 生成 /
looks/ 风格库 + apply/list / refine 手动校准 / GitHub 仓库(MIT)
