# v0.7 任务:分发

> 状态:草拟,待作者 review。同迭代:[需求](./requirements.md) · [设计](./design.md)。
> 任务按依赖顺序排列;人工验证项集中放最后「人工验收」区。

## T1 GUI/CLI 双入口分流(依赖 v0.4 GUI 已存在)

- [ ] 入口按 `sys.argv` 分流:命中已知 CLI 子命令走现有 argparse,否则默认启动 GUI
- 验收:开发环境下 `python -m looklift`(无参数)起 GUI,`python -m looklift analyze ...` 走 CLI,行为不变

## T2 资产路径统一改用 importlib.resources(依赖 v0.6 已改造预置库路径)

- [ ] `assets/design-system/` 等 GUI 静态资源读取方式与 v0.6 预置库保持同一套 `importlib.resources` 用法
- 验收:开发环境(`pip install -e .`)与正式安装(构建 wheel 后 `pip install`)两种方式下 GUI 均能正常加载静态资源

## T3 PyInstaller spec + onedir 打包脚本(依赖 T1、T2)

- [ ] `looklift.spec`:`datas` 收录 design-system 资产、v0.6 预置库、tokens
- [ ] `scripts/build_exe.ps1`(或等价脚本):一键产出 onedir 文件夹并打包成 zip
- 验收:本地跑打包脚本成功产出 zip,解压后目录结构符合预期(exe + 依赖 DLL + 资产)

## T4 WebView2 缺失检测与引导(依赖 T3)

- [ ] 启动时检测 WebView2 Runtime 是否存在,缺失则弹中文提示框 + 官方下载链接
- 验收:卸载/在没有 WebView2 的虚拟机上跑一次打包产物,确认提示而非崩溃/白屏(人工验收区重复记录一次结果)

## T5 打包产物冒烟测试(依赖 T3、T4)

- [ ] 干净 Windows 虚拟机(无 Python、无开发环境)跑一次完整流程:解压 → 双击 → 首次配置向导 → 拖图分析 → 出报告 → 导出预设
- [ ] 记录 PyInstaller 隐藏依赖问题(如有)并修复,重新打包验证
- 验收:见 [人工验收](#人工验收)

## T6 杀毒软件误报排查(依赖 T3,视情况持续)

- [ ] Windows Defender 扫描打包产物,确认是否误报
- [ ] 如有误报:整理提交 Microsoft 白名单申报的材料/流程记录进文档(不要求申报本身在本迭代内生效)
- 验收:文档记录当前误报状态 + 应对流程,不要求"一定不误报"(申报生效有延迟,不受本迭代控制)

## T7 文档与演示

- [ ] README 新增「下载即用」章节(下载链接占位、解压说明、WebView2 前置条件)
- [ ] 保留并更新 `pip install looklift` 章节,标注给技术用户/Mac 用户
- [ ] 录屏脚本大纲(拖图 → 报告 → 导出的演示脚本要点,不要求本迭代实际录制)
- 验收:README 走一遍,一个没接触过项目的人能照着装上

## T8 收尾

- [ ] `docs/design.md` §7(打包)回填本迭代打包方案要点
- [ ] 版本号 0.7.0,CI 绿(ubuntu/windows/macos 的 pip 路线不受影响),推送
- [ ] （视情况)新增打包专属 CI job,手动触发或 release 分支产出 exe artifact

## 人工验收

- [ ] 无 Python 环境的干净 Windows 10/11 机器(或虚拟机),解压 zip 双击 exe,完整跑通 U1/U4/U8(拖图分析 → 报告 → 导出预设)
- [ ] 首次启动配置向导在打包环境下正常工作(provider 配置能保存、生效)
- [ ] 缺 WebView2 的机器上验证提示与引导链接可用
- [ ] Windows Defender 默认扫描打包产物,记录是否误报及处理结果
- [ ] README 按文档操作一遍,确认没有断链接/过时步骤
