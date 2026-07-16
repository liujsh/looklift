# looklift 任务清单

> 路线图与验收标准见 [requirements.md](requirements.md)。这里只放当前迭代的可执行任务和历史记录。

## v0.3(下一迭代):像 —— 精度闭环

> 详细设计与验收:[specs/2026-07-16-v0.3-precision-loop.md](specs/2026-07-16-v0.3-precision-loop.md)

### T1 Provider 抽象重构
- [ ] `providers.py`:VisionProvider 接口;现有 cli/api 后端迁入(行为不变,测试回归)
- [ ] `~/.looklift/config.toml` 配置读取(provider/key/base_url/model),env 覆盖
- [ ] 风格库默认目录迁至 `~/.looklift/looks/`(cwd 下有 looks/ 时优先,向后兼容)

### T2 本地近似渲染 preview
- [ ] `render.py`:按设计文档顺序实现参数→图像的近似渲染(Pillow+numpy)
- [ ] `looklift preview <look> <照片> [-o 输出]`:渲染套用效果图
- [ ] 还原度评分 `score(rendered, target) -> 0-100`
- [ ] 单元测试:各调整项方向正确(如 exposure>0 → 更亮)

### T3 refine 自动闭环
- [ ] `refine --auto [N] --source 原片 --target 目标`:渲染→评分→AI 修正循环
- [ ] 收敛判定(提升<阈值提前停止),每轮打印评分
- [ ] 真实照片端到端验证:3 轮内评分上升

### T4 LUT 导出(U19,竞品借鉴)
- [ ] `looklift export-lut <look> [-o x.cube] [--size 33]`:用 render.py 管线对 3D 网格采样生成 .cube
- [ ] .cube 格式程序化校验(单元测试)+ 剪映加载验证(人工);达芬奇留社区反馈

### T5 收尾
- [ ] CI 矩阵加 macos-latest(Mac 策略:核心兼容,不做 .app 打包)
- [ ] README/文档同步,版本 0.3.0,CI 绿,推送

## Backlog(未排期)

- 手机 DNG 预设(LR Mobile 免费版可用)(U18)
- LR 插件形态(U21,Neurapix 验证过的工作流终态)
- 风格分享/社区(U22,远期)
- 风格报告 before/after 对比图(需可公开图片)
- Capture One 风格文件导出
- 目录批量分析自动聚类(排在 v0.5+)

## 历史

### v0.2(2026-07-16)✅
打包(looklift 命令)/ 多图合成风格 / HTML 风格报告(SVG 曲线)/ 23 pytest + 双平台 CI / docs 三件套

### v0.1(2026-07-16)✅
analyze(单图/原片对照,双后端)/ read(内嵌 XMP 提取)/ 预设+sidecar 生成 /
looks/ 风格库 + apply/list / refine 手动校准 / GitHub 仓库(MIT)
