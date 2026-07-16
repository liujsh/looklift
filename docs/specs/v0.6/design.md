# v0.6 设计:懂——教学深化

> 状态:草拟,待作者 review。同迭代:[需求](./requirements.md) · [任务](./tasks.md)。
> 基线:[当前架构](../../design.md) §2(ANALYSIS_SCHEMA)、§6(report.py)。

## 关键设计决策

| # | 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|---|
| 1 | rationale 字段结构 | (a) 每个叶子值包一层对象 `{value, rationale}` (b) 并列的顶层字典 `rationales: {字段名: 讲解文本}` | (b) | (a) 改动面极大——`basic`/`hsl`/`color_grading` 所有读写点(xmp_writer、render.py、report.py、测试)都要跟着改结构;(b) 只在 `ANALYSIS_SCHEMA` 顶层加一个新的可选字段,现有字段结构完全不动,`_normalize`/`xmp_writer`/`render.py` 零改动,只有 `report.py` 和 prompt 需要感知新字段。字典 key 用参数名(如 `temperature_shift`、`hsl.orange.saturation`),嵌套字段用点号路径避免歧义 |
| 2 | 向后兼容降级 | — | `report.py` 渲染前检查 `analysis.get("rationales")` 是否存在且非空;不存在时按 v0.2 原有模板渲染(不显示"为什么"列),不抛异常、不报缺字段警告。`_normalize` 里 `rationales` 默认给 `{}` 而不是必填,保证旧模版反序列化不报错 |
| 3 | 预置 look 内容生产方式 | (a) 用 AI analyze 一批参考图直接产出 (b) 人工撰写 | (b) | 预置库是"官方教材",质量要求高于 AI 单次输出;且 (a) 有版权风险——如果参考图来自具体商业预设效果图,等于间接逆向复刻。改为作者依据摄影通用手法(如"电影感=青橙对比+压高光+轻微暗角"这类教科书级描述)独立调参、独立撰写讲解文案,不以任何具体商业图片为分析对象 |
| 4 | package data 打包方式 | (a) 相对路径拼接(`Path(__file__).parent / "presets"`) (b) `importlib.resources` | (b) | (a) 在 `pip install`(非 editable)后包不在源码树位置,或被打进 zip/wheel 时相对路径可能失效;(b) 是标准做法,且与 v0.7 PyInstaller 打包要读取同一批资源的需求一致——现在就统一路径定位方式,v0.7 不用再改一遍(见 [v0.7 design.md](../v0.7/design.md) 决策 3) |
| 5 | 聚类与 v0.5 的关系 | — | 若 [v0.5](../v0.5/design.md) 已实现聚类(决策 6),本迭代不重复实现,只在报告/CLI 展示层做优化(如报告标注"属于哪个风格分组");若 v0.5 裁剪掉聚类,本迭代视本迭代时间决定是否补上,同样标记「视情况/可裁剪」,裁剪不影响本迭代整体验收 | 避免两个迭代重复设计同一个功能;显式标注依赖关系,作者到时按实际排期二选一执行 |

## 接口/数据结构变化

```jsonc
// ANALYSIS_SCHEMA 新增可选顶层字段(不改动现有字段)
{
  "rationales": {
    "type": "object",
    "description": "参数名(或点号路径)→ 为什么这么调的中文讲解,可选,旧模版可不含此字段",
    "additionalProperties": { "type": "string" }
  }
}
```

- `analyzer.py` 的 `SYSTEM_PROMPT`/`_MULTI_TASK` 扩展:要求模型对每个非零参数给出一句话讲解,
  写入 `rationales`;`_normalize` 给 `rationales` 补默认空字典
- `report.py` `render_report`:非零参数表新增「为什么」列(有 rationale 就显示,没有留空或整列隐藏——
  取决于该模版是否含 `rationales`,不是逐格判断)
- 新增预置资产目录 `looklift/presets/<look-id>/`(`template.json` + `preset.xmp` + `report.html`),
  10 个子目录;`pyproject.toml` `[tool.setuptools.package-data]` 纳入
- CLI:现有 `looklift list` 扩展为区分展示「预置」和「我的库」两类来源(预置库只读,不可 `refine`/覆盖保存,
  另存为新名字才能改)

## 风险

- **rationale 讲解质量依赖 AI 生成,可能空泛**(如"因为更好看"):prompt 需要明确要求"结合具体摄影语言,
  一句话内说清楚意图,避免车轱辘话"。预置库的讲解全部人工撰写把关,不依赖 AI 生成质量,规避这条风险
- **版权风险**:预置 look 若被质疑抄袭某商业预设包。缓解:设计上要求参数来自作者独立调试或通用摄影手法描述,
  不引用/不逆向具体商业产品;README 记录这一原则,供社区贡献新预置 look 时参照
- **"入门用户能说出为什么"验收主观、难以自动化**:人工验收区设计一个简单测试协议——找 1-2 位不懂调色的
  朋友读一份报告,请他们口头复述其中一个参数的调整原因,能说出即通过,不追求量化打分
