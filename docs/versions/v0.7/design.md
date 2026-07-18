# v0.7 设计:分发

> 状态:已终止（2026-07-18）。历史设计仅供追溯；不得回退到 pywebview/PyInstaller 路线。
> 同迭代:[需求](./requirements.md) · [任务](./tasks.md)。
> 基线:[当前架构](../../product/architecture.md) §8(v0.4 GUI 架构:pywebview 独立窗口,`--browser` 兜底,零外部网络请求)、
> [v0.6 design.md](../v0.6/design.md) 决策 4(`importlib.resources` 资源定位)。

## 关键设计决策

| # | 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|---|
| 1 | onefile vs onedir | (a) onefile:单文件,启动时解压到临时目录 (b) onedir:启动快,分发是一个文件夹(需 zip 打包发布) | (b) onedir + zip 分发 | onefile 双击体验最简单,但启动慢(几秒到十几秒解压)、且自解压行为是常见恶意软件特征,更容易被杀毒软件启发式误报。目标用户是"不会装 Python 但会用电脑"的摄影爱好者,解压 zip 双击里面的 exe 这个心智负担可接受(很多绿色软件都这样发布)。优先保证"能用、不被杀软拦截吓跑用户",而不是"看起来最简单" |
| 2 | GUI/CLI 双入口方式 | (a) 打包两个 exe(gui.exe / cli.exe) (b) 单 exe 内按 `sys.argv` 分流 | (b) | (a) 体积翻倍、维护两份 spec;(b) 无参数或明确 GUI 参数时起 pywebview 窗口,带已知 CLI 子命令(`analyze`/`apply`/...)时走现有 argparse 入口,复用同一个 `cli.py` 分发逻辑,只在最外层加一层判断 |
| 3 | 资产路径解析 | (a) 沿用开发时的相对路径假设 (b) 统一用 `importlib.resources` | (b) | PyInstaller 运行时资源不在源码树位置(onefile 在 `sys._MEIPASS` 临时目录,onedir 在 exe 同级目录下由 `datas` 复制过去的路径),沿用相对路径必炸。[v0.6](../v0.6/design.md) 打包预置 look 库时已经改用 `importlib.resources`,本迭代把 `assets/design-system/` 等其余静态资源也统一改成同一套定位方式,避免开发/pip/PyInstaller 三种运行形态各写一套路径逻辑 |
| 4 | WebView2 缺失处理 | (a) 提示 + 跳转官方下载链接 (b) 内置 evergreen bootstrapper 一起分发 | (a) | Win11 自带 WebView2,只有精简版/旧版 Win10 才可能缺;(b) 会显著增大分发体积换一个低概率场景的便利,不划算。启动时检测(查注册表或已知 DLL 路径),缺失则弹出中文提示框 + 官方下载链接,不崩溃、不白屏 |
| 5 | 杀毒误报缓解 | (a) 付费代码签名证书 (b) 提交样本到 Windows Defender/主流杀软做白名单申报 (c) onedir 打包降低启发式误报概率(已在决策 1 采纳) | (b) + (c) 组合,(a) 留待作者决定 | (a) 效果最好但 ~$200-400/年与"零运营成本"定位冲突,是否例外由作者判断(见待决问题);(b) 免费但生效需要时间、每次新版本可能要重新提交,作为长期动作而非一次性任务;(c) 已通过决策 1 落地,是当前唯一"零成本立即生效"的缓解手段 |

## 接口/数据结构变化

- 新增打包配置:`looklift.spec`(PyInstaller spec 文件),`datas` 里收录 `assets/design-system/`、
  `looklift/presets/`(v0.6 预置库)以及 `tokens.css` 等静态资源
- 新增打包脚本(如 `scripts/build_exe.ps1`),产出 onedir 文件夹 + 打包成 zip
- `looklift/__main__.py`(或 `cli.py` 顶层)新增入口分流逻辑:判断 `sys.argv` 是否命中已知 CLI 子命令,
  否则默认启动 GUI
- README 新增「下载即用」章节:下载链接、解压说明、双击哪个文件、WebView2 前置条件说明
- 新增录屏脚本大纲文档(供后续录制演示视频参考,不要求本迭代真正录制)

## 风险

- **PyInstaller 隐藏依赖收集不全**:pywebview、Pillow、numpy 等包可能有 PyInstaller 默认收集不到的隐藏导入或数据文件,
  导致打包后运行报 `ModuleNotFoundError` 或资源缺失。缓解:构建成功不等于能跑,必须在干净虚拟机做端到端冒烟测试
  (见 [tasks.md](./tasks.md) 人工验收),不能只信任 CI 构建绿
- **CI 目前不验证打包产物**:现有 CI 只验证 `pip install -e .` 后 pytest 通过。缓解:视情况新增一个手动触发或
  release 分支专属的打包 CI job,产出 artifact 供人工下载测试;是否常态化在每次 CI 都打包(耗时、非必要)留待作者决定
  (待决问题)
- **预置 look 库体积影响分发体积**:[v0.6](../v0.6/design.md) 的 10 套预置资产如果图片/HTML 报告较大,
  会显著拉大 exe/zip 体积,影响下载体验。缓解:打包前检查 look 库资产大小,报告中的示例图适当压缩
- **杀毒误报是持续性风险,不是一次性任务**:即便本迭代验收时 Defender 不报毒,后续版本更新也可能重新触发误报。
  README/文档需要记录应对流程(如何提交白名单申报),不是修一次就永久解决
