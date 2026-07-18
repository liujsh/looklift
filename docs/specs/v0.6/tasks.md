# v0.6 任务:懂——教学深化

> 状态:已终止（2026-07-18）。以下任务全部作废，仅保留历史记录；后续不得据此开工。
> 同迭代:[需求](./requirements.md) · [设计](./design.md)。
> 任务按依赖顺序排列;人工验证项集中放最后「人工验收」区。

## T1 schema 扩展

- [ ] `ANALYSIS_SCHEMA` 新增可选顶层字段 `rationales: dict[str, str]`
- [ ] `_normalize` 补默认空字典,不破坏旧模版反序列化
- [ ] `SYSTEM_PROMPT`/`_MULTI_TASK` 更新,要求两个已有后端(cli/api)对非零参数输出讲解
- 验收:新分析出的模版含非空 `rationales`;旧测试夹具(无该字段)反序列化不报错

## T2 report.py 渲染「为什么」

- [ ] 参数表新增「为什么」列,渲染 `rationales` 对应文本
- [ ] 无 `rationales` 字段时按 v0.2 原样式渲染,不显示该列
- 验收:两份测试模版(有/无 rationales)各渲染一次,输出 HTML 均合法且符合预期展现

## T3 预置 look 库内容制作(依赖 T1)

- [ ] 确定 10 个经典风格清单(胶片/电影感/日系/黑白/复古/清新/暗调... 由作者拍板具体 10 个)
- [ ] 每个 look:人工调参出 `template.json`(符合 `ANALYSIS_SCHEMA`,含 `rationales`)+ 生成 `preset.xmp` + 生成 `report.html`
- [ ] 作者逐个 review 确认参数与讲解不对标任何具体商业预设包(见 [requirements.md](./requirements.md) 非目标)
- 验收:10 套资产齐全,`report.html` 肉眼检查排版正常,`preset.xmp` 能在 LR 正常导入

## T4 package data 打包(依赖 T3)

- [ ] `looklift/presets/` 目录纳入 `pyproject.toml` package-data
- [ ] 运行时定位改用 `importlib.resources`(供 v0.7 打包复用同一套定位方式)
- 验收:`pip install -e .` 与 `pip install .`(非 editable,构建 wheel 后安装到隔离环境)两种方式都能读到预置库

## T5 CLI 展示区分来源(依赖 T4)

- [ ] `looklift list` 区分「预置」与「我的库」;预置库条目标注只读,`refine`/覆盖保存需先另存新名字
- 验收:`list` 输出两类来源清晰可辨;对预置 look 执行 `refine` 报错提示需先另存

## T6 聚类(视情况,依赖 v0.5 决策)

- [ ] 若 [v0.5](../v0.5/tasks.md) 已实现聚类:本任务改为报告/CLI 展示优化(标注风格分组)
- [ ] 若 v0.5 裁剪掉聚类:视本迭代剩余时间决定是否补做基础版本,标记「视情况/可裁剪」
- 验收:视选择的分支决定,裁剪本项不影响整体验收

## T7 收尾

- [ ] README 新增预置库使用说明(`looklift list` 输出示例、如何套用预置 look)
- [ ] `docs/design.md` §2/§6 回填本迭代 schema 与 report 变更要点
- [ ] 版本号 0.6.0,CI 绿,推送

## 人工验收

- [ ] 找 1-2 位不懂调色的朋友,读一份含 rationale 的报告,请其口头复述至少一个参数的调整原因,能说出即通过
  (对应 roadmap 验收:「入门用户看完报告能说出"为什么"」)
- [ ] 10 个预置 look 逐个在 LR 里实际导入套用一次,肉眼确认预设生效、风格符合命名描述
- [ ] （若作者对版权边界有疑虑)找一位懂摄影后期的朋友交叉检查预置 look 参数是否"撞脸"某知名商业预设
