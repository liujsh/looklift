# looklift 任务清单

## v0.2(本迭代)

### T1 打包
- [x] pyproject.toml(metadata、依赖、console script `looklift`)
- [x] 验证 `pip install -e .` 后 `looklift --help` 可用

### T2 多图合成风格
- [x] `analyzer.analyze` 支持 `edited: list`,多图 prompt(cli/api 两后端)
- [x] CLI `analyze` 改 `nargs="+"`,>5 张报错,多图 + `--original` 报错
- [x] 冒烟测试(单图路径回归 + 多图一次真实调用)

### T3 HTML 风格报告
- [x] 新模块 `report.py`:`render_report(analysis, name) -> html`
- [x] SVG 曲线图(参考线、平滑曲线、控制点)
- [x] 基本面板/HSL/颜色分级表格,色块可视化
- [x] CLI `report <风格名>` 子命令,输出 `looks/<名字>.html`
- [x] 用 grassland 模版实测,浏览器检查渲染

### T4 测试与 CI
- [x] tests/test_xmp_writer.py
- [x] tests/test_xmp_reader.py
- [x] tests/test_analyzer.py(_normalize/_extract_json/resolve_backend)
- [x] tests/test_cli.py(_resolve_template/_expand_raws/apply 端到端)
- [x] .github/workflows/ci.yml(ubuntu+windows)
- [x] 本地 pytest 全绿

### T5 收尾
- [x] README 同步新命令/安装方式
- [x] 版本号 0.2.0
- [x] 提交推送,确认 CI 通过

## Backlog(未排期)

- 本地近似渲染预览(`preview` 命令,Pillow 模拟曲线/白平衡/饱和度,效果打折需验证)
- 批量分析目录并自动聚类风格
- 风格报告加 before/after 对比图(需用户提供可公开图片)
- GUI(拖拽图片出报告)
- Capture One 风格文件导出

## 已完成(v0.1,2026-07-16)

- [x] analyze:AI 逆向推断(单图/原片对照),中文讲解
- [x] 双后端:本地 claude CLI(stdin 传 prompt)/ Anthropic API(结构化输出)
- [x] read:JPEG 内嵌 XMP 精确提取
- [x] xmp_writer:LR 预设 + RAW sidecar 生成
- [x] looks/ 风格库、apply、list、sidecar 通配符
- [x] refine:迭代校准(备份+重生成预设)
- [x] GitHub 仓库(MIT,topics,README)
