# v0.5 需求:供应商 + 库

> 状态:已确认(2026-07-18,作者授权开工)。
> 上游文档:[产品需求](../../requirements.md)(定位/路线图)、[当前架构](../../design.md)、
> [v0.3 spec](../2026-07-16-v0.3-precision-loop.md)(provider 抽象、Block 约定、`_extract_json`+`_normalize` 容错路径,本迭代直接复用)。
> 同迭代:[设计](./design.md) · [任务](./tasks.md)。

## 一句话目标

让 looklift 不再绑定 Anthropic——接入 OpenAI 兼容中转站和本地 Ollama 视觉模型,
并支持整目录批量出模版,把「库」的规模化能力打通。

## 依赖前置版本

| 依赖 | 内容 | 状态 |
|---|---|---|
| v0.3 | `providers.py` 的 `VisionProvider` 协议、`Block` 类型、config.toml、`_extract_json`+`_normalize` 容错路径 | 本迭代的直接地基,假定已实现 |
| v0.4 | GUI 设置页(pywebview 壳、首次配置向导) | GUI 内配置 provider 这部分任务依赖它;若 v0.4 未完成,GUI 任务顺延,不阻塞本迭代其余部分(见 [tasks.md](./tasks.md)) |

## 用户故事

| 编号 | 用户故事 | 本迭代范围 |
|---|---|---|
| U13 | 用国内 API 中转站或本地模型,不依赖 Anthropic | 核心交付:OpenAICompatProvider + OllamaProvider |
| U14 | 整个目录批量分析,自动归纳出几种风格 | 批量分析核心交付;聚类部分视情况(见非目标) |

## 验收标准

- [ ] 配置一个 OpenAI 兼容中转站(base_url + api_key + model)后,`looklift analyze` 全流程跑通,产出的模版通过现有 `ANALYSIS_SCHEMA` 校验
- [ ] Ollama + 本地视觉模型(如 Qwen-VL)跑通 `looklift analyze`(人工验收,需要装了 Ollama 且拉取了对应模型的机器,见 [tasks.md](./tasks.md) 人工验收区)
- [ ] `looklift analyze --batch <目录>` 对目录下多组图片批量出模版;中途中断后重跑,已完成的组不重复消耗额度
- [ ] 批量分析开始前打印预计组数与额度消耗提示
- [ ] 两个新 provider 的常见错误(鉴权失败、模型不存在、Ollama 服务未启动)均输出中文提示,不抛原始堆栈
- [ ] 现有 pytest 全部回归通过;新 provider 用 mock HTTP 响应做单元测试,不触网、不调真实 AI

## 非目标

- 不做 OpenAI 兼容 / Ollama 之外的其他供应商(vLLM、其他云厂商等,归 backlog)
- 风格聚类延期到 v0.6/backlog；v0.5 只交付可续跑的批量分析与独立结果模版，不引入聚类依赖
- 不做批量分析结果的自动去重/自动建库,用户仍需手动把满意的模版收进 `looks/`
- 不做除进度打印外的批量 UX 打磨(进度条、暂停/恢复按钮等留给有 GUI 之后再看)
- 不改变已实现的 Anthropic API / Claude CLI 两个 provider 的行为
