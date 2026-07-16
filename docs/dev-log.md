# 开发日志(坑、决策、待作者处理)

> 自主开发期间(2026-07-16 起)的问题记录与自主决策,供作者回来后快速过目。
> 待作者决策的产品问题另见 [specs/README.md](specs/README.md) 的「待作者决策」区。

## 需要你人工处理的事项

- [ ] **删除一个测试遗留文件**:`C:\Users\刘金山\.looklift\looks\MyLook.xmp`。
  v0.3 Task 2 的 TDD 红灯阶段,老测试曾意外写到真实用户目录(根因已修,见下)。
  按你"不碰项目外文件"的指令,安全分类器拦截了我的清理,需要你手动删一下。
- [ ] **准备 v0.3 验收素材**:3-5 组「LR 原片+成片」JPEG,放 `test-assets/`(已 gitignore),
  用于 auto-refine 端到端人工验收(spec Task 8)。
- [ ] **装剪映**:验证导出的 .cube LUT 能加载(程序化格式校验已由单元测试覆盖)。
- [ ] **review 草拟 specs**:v0.4-v0.7 的三文档 spec 已产出(docs/specs/v0.X/),
  开发按其推进中;待决问题清单在 specs/README.md。

## v0.3 开发中踩的坑(已解决)

| # | 坑 | 解决 |
|---|---|---|
| 1 | 测试红灯阶段污染真实用户目录:`_resolve_template` 改走 `config.looks_dir()` 后,无 cwd looks/ 的测试会落到真实 `~/.looklift`,一度写入了文件 | tests/conftest.py 加 autouse `_isolate_env` 夹具:假 home、假 CONFIG_PATH、清 `LOOKLIFT_*` 环境变量——结构性根治,任何未来测试都不可能再碰真实 home |
| 2 | render 管线 float64 泄漏:`_apply_color_grading` 的 tint 数组把整条管线提升成 float64,违反 LUT 依赖的 float32 契约,且默认 fixture 恰好触发 | tint 构造显式 float32 + `_apply_color_ops` 返回处加 astype 双保险,配 dtype 回归测试 |
| 3 | 计划自带缺陷:`if not s: continue` 使纯 luminance 颜色分级(saturation=0)静默失效 | 拆成独立分支(s 控染色、lum 控明度),配方向回归测试;此为计划骨架的 bug,已作为计划作者授权修复 |
| 4 | Windows `tempfile.mkstemp` 返回打开的 fd,PIL 往该路径写文件会 PermissionError | autorefine 改用 `mkdtemp` + 轮次编号文件 + try/finally 清理 |
| 5 | 审查者误报一例:Task 3 审查(只看本任务 diff)认为四个测试未隔离 CONFIG_PATH,实际 Task 2 的 autouse 夹具已全局隔离 | 控制器仲裁为误报,不改代码;跨任务上下文由控制器把关 |

## 过程备注

- Task 7 实现者的报告 TDD 叙述自相矛盾(声称"实现已存在"又列了 RED/GREEN 过程)。
  审查者独立手推了收敛/最优语义并复跑测试(57 通过),**代码本身确认正确**;
  报告可信度问题已记录,不影响交付质量。
- 每任务均经 spec 合规+代码质量双审查;发现的 Minor 级问题(文案/风格/覆盖盲区)
  统一记在 `.superpowers/sdd/progress.md`,由最终全分支 review 统一裁量。

## 自主决策记录(按你的授权,按推荐执行)

| 决策 | 内容 |
|---|---|
| U23 归属 | 「原片→正向推荐风格」记为 v0.6 候选,RAW 走内嵌 JPEG 预览方案(不引 rawpy) |
| v0.4 GUI 后端 | stdlib ThreadingHTTPServer(窗口/浏览器两模式共用)+ 轮询进度;不引入 FastAPI |
| v0.4 组件 | 纯 tokens.css + components.html 配方即可,Shoelace 暂不需要 |
| 强度滑杆语义 | 偏移类参数按比例缩、曲线向恒等线插值;color_grading 的 hue 与 blending 不缩放 |
| Task 7 计划缺陷 | 以计划作者身份授权修复(见坑 3) |
