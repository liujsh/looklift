# v0.5 设计:供应商 + 库

> 状态:草拟,待作者 review。同迭代:[需求](./requirements.md) · [任务](./tasks.md)。
> 基线:[v0.3 provider 抽象](../2026-07-16-v0.3-precision-loop.md#t1-provider-抽象只定接口不加新供应商)、
> [当前架构](../../design.md)。

## 关键设计决策

| # | 决策点 | 选项 | 推荐 | 理由 |
|---|---|---|---|---|
| 1 | 图片传输格式 | (a) base64 data URI 统一两个 provider (b) 各自用最贴合自身 API 的编码 | (b) | OpenAI Chat Completions vision 格式要求 `image_url.url` 为 `data:image/jpeg;base64,...` 完整 data URI;Ollama `/api/chat` 的 `images` 字段是**纯 base64 字符串数组**,不带前缀。两者都不接受文件路径(不像 cli 后端能用 Read 工具吃本地路径)。统一按 (a) 会给 Ollama 多一层要剥掉的前缀,不如各自适配来得直接;复用 v0.3 api 后端已有的「Pillow 缩到长边 1568 再 base64」逻辑,两个新 provider 在各自 `complete()` 内部把公共 Block 列表翻译成自己的 wire 格式 |
| 2 | config.toml schema 是否要为新 provider 加分节 | (a) 沿用现有扁平 schema(`provider/model/api_key/base_url/looks_dir`),只加一个 `timeout` (b) 改成 `[provider.openai_compat]` / `[provider.ollama]` 分节,支持同时保存多套配置 | (a) | YAGNI:当前产品形态是"某一时刻只用一个 provider",分节支持的"多套配置同时存在、切换省得重填"是 v1.0 前用不上的便利。`base_url` 对 openai_compat 是中转站地址,对 ollama 默认 `http://localhost:11434`(留空时代码里给默认值);`api_key` 对 ollama 无意义,留空即可。扩展成本低于分节引入的复杂度 |
| 3 | 超时与重试 | — | 新增 `timeout` 配置项(秒),按 provider 给不同默认值:cli 600s(已有)、api 120s、openai_compat 120s、ollama 300s(本地 CPU 推理视觉模型可能很慢);网络级错误(连接失败/5xx)重试 1 次、指数退避;4xx(鉴权/参数错误)不重试,直接抛中文错误 | 本地模型推理耗时波动大,超时太短会误判失败;但不设上限又会导致 CLI 卡死无提示,所以给了单独的默认值而不是复用 api 的 120s |
| 4 | 错误信息中文化 | — | 在两个新 provider 的 `complete()` 里捕获 `HTTPError`/`ConnectionError`,按状态码/异常类型映射成中文提示 + 修复建议(如「401:api_key 无效,检查 config.toml 里的 api_key」「Ollama 连接失败:确认 `ollama serve` 已启动,或 base_url 配置是否正确」「模型不存在:先 `ollama pull <模型名>`」) | 沿用现有 `RuntimeError` 中文提示的风格(见 `analyzer.py` 现有的「未找到可用后端」提示) |
| 5 | 批量分析的目录约定与断点续跑 | — | 约定 `--batch <目录>` 下每个一级子目录是一"组"(复用 v0.2 多图归纳,一组内最多 5 张,超出的按修改时间取前 5 张并打印提示);每组分析成功后在该子目录写一个 `.looklift-done` 标记文件(或检测模版是否已存在于目标 looks 目录,取更简单的一种,留给实现阶段判断);重跑时跳过已标记的组,`--force` 强制重跑全部;开始前扫描一遍打印「共 N 组待分析,预计消耗 N 次调用额度」 | 断点状态必须落盘而不是纯内存,否则 Ctrl-C/机器休眠后重跑等于没有断点续跑 |
| 6 | 风格聚类(视情况/可裁剪) | — | 若本迭代时间允许:特征向量 = `basic` 13 维 + `hsl` 8 通道 × 3 属性 24 维,做 min-max 标准化后跑 k-means(k 默认按 `min(5, 组数)` 或让用户用 `--clusters N` 指定);聚类结果只用于给批量分析产出的模版打「分组标签」,不改变模版内容本身,不影响单独的 `analyze`/`apply` 流程 | 聚类质量依赖参数向量本身的代表性,不追求精确;若裁剪到 v0.6 或以后,`--batch` 本身的验收不受影响(聚类是加分项非必需项),这一决策与 [v0.6 design.md](../v0.6/design.md) 的聚类章节互相引用,避免重复实现 |

## 接口/数据结构变化

```python
# providers.py(v0.3 已定接口,本迭代新增两个实现)
class OpenAICompatProvider:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 120): ...
    def complete(self, system: str, content: list[Block], schema: dict) -> dict: ...
    # 内部:content -> OpenAI chat.completions messages 格式(image_url data URI)
    # 无结构化输出保证 -> 走 _extract_json + _normalize

class OllamaProvider:
    def __init__(self, base_url: str, model: str, timeout: int = 300): ...
    def complete(self, system: str, content: list[Block], schema: dict) -> dict: ...
    # 内部:content -> /api/chat 的 messages + images(纯 base64 数组)
    # 无结构化输出保证 -> 走 _extract_json + _normalize
```

- `config.toml` 新增字段:`timeout`(int,秒,可选,不填按 provider 类型给默认值);其余复用现有 `provider/model/api_key/base_url/looks_dir`
- `provider` 取值扩展为 `auto | cli | api | openai_compat | ollama`
- CLI 新增 `analyze --batch <目录> [--force] [--clusters N]`
- GUI 设置页(依赖 v0.4)新增 provider 类型下拉,选中 `openai_compat`/`ollama` 时展示对应字段(`ollama` 隐藏 api_key)

## 风险

- **中转站 API 格式不完全统一**:部分中转站对 vision content block 的字段名/结构有细微出入。缓解:只承诺兼容标准 OpenAI Chat Completions vision 格式,已知不兼容的中转站记录进 README 的「已知问题」清单,不逐一适配
- **本地模型输出质量不稳定**:Ollama 上的开源视觉模型输出 JSON 的遵从度可能远低于 Claude/GPT-4V,`_extract_json` 提取失败率会更高。缓解:沿用已验证的容错路径,失败时给出「换个模型试试」的中文提示,不在本迭代额外做模型专属的 prompt 调优
- **批量分析长时间运行中断**:目录很大时批量跑可能持续数小时,中途中断(Ctrl-C/机器休眠/网络断开)必须能安全续跑。缓解:断点状态落盘(决策 5),每组处理是幂等的独立事务
