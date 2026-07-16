# looklift 需求文档

## 背景与目标

摄影爱好者看到喜欢的成片(大师作品、胶片风格、电影感调色)时,想知道"这是怎么调出来的",
并希望能把这种风格一键套用到自己的 RAW 文件上。手动逆向调色需要多年经验;
looklift 用 AI 视觉模型完成逆向推断,并生成 Lightroom 可直接使用的预设文件。

**核心用户**:会用 Lightroom 的摄影爱好者,不要求编程能力(命令行即可)。

## 用户故事

| # | 用户故事 | 状态 |
|---|---|---|
| U1 | 我给一张大师成片,想知道它的调色参数和后期思路讲解 | ✅ v0.1 `analyze` |
| U2 | 我有原片+成片对照,希望分析更精确 | ✅ v0.1 `analyze --original` |
| U3 | 我自己导出的 JPEG 带 LR 元数据,想直接提取精确参数 | ✅ v0.1 `read` |
| U4 | 我想把分析结果做成模版,收藏成风格库,随时套用 | ✅ v0.1 `looks/` + `apply` + `list` |
| U5 | 我想把模版一键套到 RAW 上(批量) | ✅ v0.1 sidecar + 通配符 |
| U6 | 套用后不够像,我想让 AI 对比差异、迭代修正参数 | ✅ v0.1 `refine` |
| U7 | 一位摄影师的风格要从多张作品里归纳,单张有偶然性 | 🎯 v0.2 多图合成 |
| U8 | 我想要一份好看的风格报告(参数表+曲线图+讲解),方便保存/分享 | 🎯 v0.2 `report` |
| U9 | 我不想 `python -m`,想直接敲 `looklift` 命令 | 🎯 v0.2 打包 |
| U10 | 我想不开 LR 就能预览参数套用后的大概效果 | 📋 backlog(近似渲染,见设计文档) |
| U11 | 我想要图形界面 | 📋 backlog |

## v0.2 迭代范围

**目标:从"能用的脚本"到"可发布的工具"。**

1. **多图合成风格**(U7):`analyze` 接受多张成片,AI 归纳共同风格,降低单张偶然性。
   - 约束:多图模式下不支持 `--original`;上限 5 张(控制 token)
2. **HTML 风格报告**(U8):`report <风格名>` 生成自包含 HTML(概述、后期步骤、
   参数表、SVG 曲线图、HSL/色轮色块),零外部依赖,可直接分享。
3. **标准打包**(U9):`pyproject.toml` + console script,`pip install -e .` 后
   直接 `looklift <命令>`。
4. **工程质量**:pytest 单元测试(xmp 读写、normalize、CLI 解析)+ GitHub Actions CI
   (Windows + Ubuntu)。AI 调用部分 mock,CI 不消耗额度。

## 非目标(本迭代不做)

- 本地近似渲染预览(U10)——LR 渲染管线无法精确复刻,效果存疑,先归 backlog
- GUI / Web 界面
- 局部调整(蒙版/渐变)的参数化——预设格式本身可表达,但视觉逆向不可靠
- Capture One / DxO 等其他修图软件的格式

## 验收标准

- [ ] `looklift analyze a.jpg b.jpg c.jpg --name X` 产出合并风格模版+预设
- [ ] `looklift report X` 生成 `looks/X.html`,浏览器打开可见完整报告
- [ ] `pip install -e .` 后 `looklift --help` 可用
- [ ] `pytest` 全绿;push 后 GitHub Actions 双平台通过
- [ ] README 与新功能同步
