# v0.5 设计:供应商 + 库

> 状态:已确认(2026-07-18,作者授权开工)。同迭代:[需求](./requirements.md) · [任务](./tasks.md)。
> 基线:[v0.3 provider 抽象](../v0.3/spec.md#t1-provider-抽象只定接口不加新供应商)、
> [当前架构](../../product/architecture.md)。

## 关键设计决策

| # | 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|---|
| 1 | 图片传输格式 | (a) base64 data URI 统一两个 provider (b) 各自用最贴合自身 API 的编码 | (b) | OpenAI Chat Completions vision 格式要求 `image_url.url` 为 `data:image/jpeg;base64,...` 完整 data URI;Ollama `/api/chat` 的 `images` 字段是**纯 base64 字符串数组**,不带前缀。两者都不接受文件路径(不像 cli 后端能用 Read 工具吃本地路径)。统一按 (a) 会给 Ollama 多一层要剥掉的前缀,不如各自适配来得直接;复用 v0.3 api 后端已有的「Pillow 缩到长边 1568 再 base64」逻辑,两个新 provider 在各自 `complete()` 内部把公共 Block 列表翻译成自己的 wire 格式 |
| 2 | config.toml schema 是否要为新 provider 加分节 | (a) 沿用现有扁平 schema(`provider/model/api_key/base_url/looks_dir`),只加一个 `timeout` (b) 改成 `[provider.openai_compat]` / `[provider.ollama]` 分节,支持同时保存多套配置 | (a) | YAGNI:当前产品形态是"某一时刻只用一个 provider",分节支持的"多套配置同时存在、切换省得重填"是 v1.0 前用不上的便利。`base_url` 对 openai_compat 是中转站地址,对 ollama 默认 `http://localhost:11434`(留空时代码里给默认值);`api_key` 对 ollama 无意义,留空即可。扩展成本低于分节引入的复杂度 |
| 3 | 超时与重试 | — | 新增 `timeout` 配置项(秒),按 provider 给不同默认值:cli 600s(已有)、api 120s、openai_compat 120s、ollama 300s(本地 CPU 推理视觉模型可能很慢);网络级错误(连接失败/5xx)重试 1 次、指数退避;4xx(鉴权/参数错误)不重试,直接抛中文错误 | 本地模型推理耗时波动大,超时太短会误判失败;但不设上限又会导致 CLI 卡死无提示,所以给了单独的默认值而不是复用 api 的 120s |
| 4 | 错误信息中文化 | — | 在两个新 provider 的 `complete()` 里捕获 `HTTPError`/`ConnectionError`,按状态码/异常类型映射成中文提示 + 修复建议(如「401:api_key 无效,检查 config.toml 里的 api_key」「Ollama 连接失败:确认 `ollama serve` 已启动,或 base_url 配置是否正确」「模型不存在:先 `ollama pull <模型名>`」) | 沿用现有 `RuntimeError` 中文提示的风格(见 `analyzer.py` 现有的「未找到可用后端」提示) |
| 5 | 批量分析的目录约定与断点续跑 | — | `--batch <目录>` 下每个含受支持图片的一级子目录是一组；图片按修改时间升序取前 5 张。成功结果原子写入该组的 `.looklift-result.json`，它同时是可直接复用的模版与断点标记；重跑跳过已有结果，`--force` 强制重跑。结果不自动写入 `looks/`。单组失败不留结果、继续后续组，最终有失败则命令返回 1 | 用一个原子结果文件同时承担产物和断点，避免 marker 与模版状态漂移；不自动建库守住非目标 |
| 6 | 风格聚类 | — | 延期到 v0.6/backlog，v0.5 不提供 `--clusters` | 核心 gate 是多供应商与可续跑 batch；聚类是 roadmap 的 v0.5+ 能力，不应拖住供应商收口 |
| 7 | HTTP 传输 | (a) 新增第三方 SDK (b) 标准库 `urllib.request` | (b) | 当前只需 JSON POST、超时、状态码与一次重试；标准库足够且避免引入 OpenAI/Ollama SDK。公共传输放 `provider_http.py`，provider 只负责 wire 格式和中文错误映射 |

## 接口/数据结构变化

```python
# providers.py(v0.3 已定接口,本迭代新增两个实现)
class OpenAICompatProvider:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120): ...
    def complete(self, system: str, content: list[Block], schema: dict) -> dict: ...
    # 内部:content -> OpenAI chat.completions messages 格式(image_url data URI)
    # 无结构化输出保证 -> complete 内 _extract_json，analyzer 返回前统一 _normalize

class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: int = 300): ...
    def complete(self, system: str, content: list[Block], schema: dict) -> dict: ...
    # 内部:content -> /api/chat 的 messages + images(纯 base64 数组)
    # 无结构化输出保证 -> complete 内 _extract_json，analyzer 返回前统一 _normalize
```

两个 provider 的 `complete()` 只负责 `_extract_json`；现有 `analyzer.analyze/refine` 在
`provider.complete()` 返回后统一调用 `_normalize`，不得让 `providers.py` 反向导入 analyzer 形成循环依赖。

OpenAI 兼容地址按 `base_url.rstrip('/') + '/chat/completions'` 组装（用户配置通常已含 `/v1`）；
Ollama 按 `base_url.rstrip('/') + '/api/chat'` 组装。公共 HTTP 层只重试连接错误与 5xx 一次，
4xx 不重试。测试注入/替换 opener 与 sleeper，不触网、不真实等待。

- `config.toml` 新增字段:`timeout`(int,秒,可选,不填按 provider 类型给默认值);其余复用现有 `provider/model/api_key/base_url/looks_dir`
- `provider` 取值扩展为 `auto | cli | api | openai_compat | ollama`
- CLI 新增 `analyze --batch <目录> [--force]`；batch 模式与位置参数 `edited`、`--original`、
  `--name/--json/--preset/--sidecar` 互斥，`--hint` 与 `--backend` 作用于每一组
- GUI 设置页(依赖 v0.4)新增 provider 类型下拉,选中 `openai_compat`/`ollama` 时展示对应字段(`ollama` 隐藏 api_key)

## 风险

- **中转站 API 格式不完全统一**:部分中转站对 vision content block 的字段名/结构有细微出入。缓解:只承诺兼容标准 OpenAI Chat Completions vision 格式,已知不兼容的中转站记录进 README 的「已知问题」清单,不逐一适配
- **本地模型输出质量不稳定**:Ollama 上的开源视觉模型输出 JSON 的遵从度可能远低于 Claude/GPT-4V,`_extract_json` 提取失败率会更高。缓解:沿用已验证的容错路径,失败时给出「换个模型试试」的中文提示,不在本迭代额外做模型专属的 prompt 调优
- **批量分析长时间运行中断**:目录很大时批量跑可能持续数小时,中途中断(Ctrl-C/机器休眠/网络断开)必须能安全续跑。缓解:断点状态落盘(决策 5),每组处理是幂等的独立事务
