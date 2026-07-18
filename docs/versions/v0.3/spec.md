# v0.3 Spec:像 —— 精度闭环

> 状态:已确认(2026-07-16 与作者 brainstorm 敲定)。
> 上游文档:[产品需求](../../product/requirements.md)(定位/路线图)、[架构实况](../../product/architecture.md)(当前架构)。
> 约定:本文件现归档于 `docs/versions/v0.3/`;实现完成后的架构要点已回填产品架构文档。

## 目标

让「套预设后像不像」从盲猜变成可量化、可自动优化:不开 LR 本地预览套用效果、
auto-refine 自动迭代到收敛、还原度打分;顺带用同一渲染管线导出 `.cube` LUT 打通视频调色生态。
覆盖用户故事 U10、U11、U19。

## T1 Provider 抽象(只定接口,不加新供应商)

现有 cli/api 双后端重构为统一 provider 接口,为 v0.5 的 OpenAI 兼容/Ollama 铺路:

```python
class VisionProvider(Protocol):
    def complete(self, system: str, content: list[Block], schema: dict) -> dict: ...

# v0.3 实现:ClaudeCliProvider(现 cli 后端)/ AnthropicProvider(现 api 后端)
# v0.5 再加:OpenAICompatProvider / OllamaProvider
```

- 新模块 `providers.py`;`analyzer.py` 只依赖接口,行为与 v0.2 完全一致(现有测试回归通过)
- 配置文件 `~/.looklift/config.toml`(provider 选择、key、base_url、模型名),环境变量可覆盖
- **风格库目录迁移**(为 v0.4 GUI 铺路,GUI 双击启动没有"当前目录"概念):
  默认库迁至 `~/.looklift/looks/`(config 可改);向后兼容——cwd 下存在 `looks/` 时优先用它
- 无结构化输出保证的 provider 统一走 `_extract_json + _normalize` 容错路径(cli 后端已验证)
- **明确不做**:本迭代不实现任何新供应商

## T2 本地近似渲染 preview

目的:不开 LR 快速看"套上参数大概什么样",并为 auto-refine 提供反馈信号。
**定位是方向正确的近似,不承诺与 LR 渲染一致**(见 requirements.md 非目标)。

- 新模块 `render.py`,Pillow/numpy 按顺序应用:
  曝光(2^ev 增益)→ 白平衡(温/色调通道增益)→ 对比度(S 曲线)→
  高光/阴影(亮度蒙版加权)→ 饱和度/自然饱和度(HSV)→ 色调曲线(LUT 插值)→
  HSL 定向(色相范围蒙版)→ 分离色调(亮度加权叠色)→ 暗角
- CLI:`looklift preview <look> <照片> [-o 输出]`
- 还原度评分 `score(rendered, target) -> 0-100`:缩略图尺度上比较,
  亮度直方图相关性 + ab 通道均值/方差接近度加权;**只用于趋势判断**,
  具体权重/阈值在实现时用作者真实照片标定,不在本 spec 拍死

## T3 refine 自动闭环

`looklift refine <look> --target 目标.jpg --source 原片.jpg --auto [N]`:

- 循环:渲染 preview → 评分 → AI 对比目标图与渲染图、修正参数 → 再渲染
- 终止:评分收敛(提升 < 阈值)或达 N 轮(默认 3);每轮打印评分曲线
- 结束后更新模版(先备份 `.json.bak`)并重生成同名预设
- 无 `--source` 原片时退化为现有手动 refine 流程,行为不变

## T4 `.cube` LUT 导出(U19,竞品借鉴 Color.io)

- `looklift export-lut <look> [-o x.cube] [--size 33]`:用 render.py 管线对 3D RGB
  网格采样,写标准 .cube 文件(含 `LUT_3D_SIZE`、`DOMAIN_MIN/MAX`)
- 注意:LUT 只能承载全局色彩映射,曝光/暗角等空间性参数不进 LUT,导出时打印提示

### 验收调整(作者只用 LR,无达芬奇)

1. **程序化校验**:单元测试按 Resolve .cube 规范校验输出(标题行、size³ 行数据、
   数值 0-1 范围、可被参考解析器往返读取)
2. **人工验证**:剪映(免费)导入加载一次,肉眼确认色调方向正确
3. 达芬奇兼容性留给社区/后续反馈,不作为 v0.3 验收门槛

## T5 收尾

README/文档同步(含本 spec 回填 design.md)、版本号 0.3.0、CI 绿、推送。
CI 矩阵增加 `macos-latest`(核心跨平台保障,见 requirements.md 非目标节 Mac 策略)。

## 色彩空间边界

preview 渲染、评分、LUT 导出均**假设 sRGB JPEG/PNG 输入**;不处理 RAW 解码、
HDR、log 素材。RAW 用户的工作流仍是"LR 套 sidecar",preview 只服务于快速方向判断。

## 验收标准(汇总)

| 项 | 标准 |
|---|---|
| T1 | 现有全部 pytest 回归通过;config.toml + env 覆盖有测试 |
| T2 | 各调整项方向正确的单元测试(如 exposure>0 → 更亮);preview 出图肉眼方向正确 |
| T3 | 作者真实照片端到端:auto-refine 3 轮内评分单调或净上升(素材:作者提供 3-5 组 LR 原片+成片,放 `test-assets/`,gitignore 不进仓库) |
| T4 | .cube 程序化校验通过 + 剪映加载成功 |
| 整体 | 双平台 CI 绿;不触网、不调 AI 的测试原则不变 |

## 本迭代非目标

- 不实现 OpenAI/Ollama provider(v0.5)
- 不做 GUI(v0.4;形态已定:同一套 HTML,发布默认 pywebview 独立窗口,`--browser` 浏览器模式兜底/开发用)
- preview 不追求与 LR 像素级一致
- 评分不用于跨风格横向比较,只用于同一目标的迭代趋势

## 风险

- **评分函数不可靠**是最大风险:若评分与人眼判断背离,auto-refine 会向错误方向收敛。
  缓解:先用「同一张图 + 已知参数扰动」构造可控实验验证评分单调性,再接入闭环。
- cli 后端每轮 refine 都要走一次完整对话,3 轮耗时可能较长:打印进度、允许 Ctrl-C 保留最优轮结果。
