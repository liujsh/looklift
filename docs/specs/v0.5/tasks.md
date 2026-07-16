# v0.5 任务:供应商 + 库

> 状态:草拟,待作者 review。同迭代:[需求](./requirements.md) · [设计](./design.md)。
> 任务按依赖顺序排列;人工验证项集中放最后「人工验收」区。

## T1 config.toml 扩展

- [ ] `config.py` 新增 `timeout` 字段(默认空,由调用方按 provider 类型取默认值);`provider` 取值文档更新
- [ ] `LOOKLIFT_TIMEOUT` 环境变量覆盖
- 验收:`test_config.py` 覆盖新字段读取 + env 覆盖

## T2 OpenAICompatProvider

- [ ] `providers.py` 新增 `OpenAICompatProvider`:base_url + api_key + model,复用现有「Pillow 缩到长边 1568 + base64」逻辑,组装成 OpenAI Chat Completions vision 格式请求
- [ ] 走 `_extract_json` + `_normalize` 容错路径解析响应
- [ ] 超时/重试/中文错误提示按 [design.md 决策 3、4](./design.md#关键设计决策) 实现
- 验收:mock HTTP 响应的单元测试覆盖正常解析、401、模型不存在、连接失败四种场景,不触网

## T3 OllamaProvider

- [ ] `providers.py` 新增 `OllamaProvider`:base_url(默认 `http://localhost:11434`)+ model,组装 `/api/chat` 请求(`images` 纯 base64 数组)
- [ ] 同样走 `_extract_json` + `_normalize`
- [ ] 中文错误提示覆盖「服务未启动」「模型未 pull」
- 验收:mock HTTP 响应单元测试;依赖 T2 已验证过的容错路径复用

## T4 批量分析 CLI

- [ ] `looklift analyze --batch <目录> [--force]`:扫描一级子目录为组,复用多图归纳分析
- [ ] 断点标记落盘,重跑跳过已完成组;开始前打印组数与额度提示
- [ ] 单组失败不中断整体批量,记录失败列表,结束后汇总打印
- 验收:tmp_path 下构造 3 组图片(mock provider),验证首次全部完成、模拟中断后重跑只补跑剩余组、`--force` 强制全部重跑

## T5 GUI 设置页扩展(依赖 v0.4)

- [ ] provider 类型下拉新增 `openai_compat`/`ollama`,联动展示 base_url/api_key/model/timeout 字段(ollama 隐藏 api_key)
- [ ] 依赖:v0.4 设置页存在。若 v0.4 未按期完成,本任务顺延到 v0.4 完成后再做,不阻塞 T1-T4/T6/T7
- 验收:GUI 内配置 openai_compat 后能跑通一次 analyze(人工验收区)

## T6 聚类(视情况/可裁剪)

- [ ] `--clusters N` 参数:对批量分析产出的模版做参数向量 k-means 分组,标注分组标签
- [ ] 时间不够可裁剪,裁剪不影响本迭代整体验收;裁剪决定需要在此打勾说明去向(留到 v0.6 或 backlog)
- 验收:构造已知能明显分两类的参数向量,聚类结果分组正确(单元测试,不依赖真实 AI)

## T7 收尾

- [ ] README 补充 openai_compat/ollama 配置示例、`--batch` 用法
- [ ] `docs/design.md` §8 回填本迭代实现要点
- [ ] 版本号 0.5.0,CI 绿(含新 provider 的 mock 测试),推送

## 人工验收

- [ ] 配置一个真实的 OpenAI 兼容中转站,`looklift analyze` 跑通全流程,产出模版可正常 `apply`/`report`
- [ ] 在装有 Ollama 且已 `pull` 一个视觉模型(如 Qwen-VL)的机器上,`looklift analyze --backend ollama` 跑通(记录所用模型名与耗时,供 README 参考)
- [ ] `--batch` 对一个真实的多组照片目录跑一遍,人工确认额度提示合理、断点续跑符合预期
- [ ] （若 T5 已做）GUI 设置页配置流程走一遍,确认字段联动符合直觉
