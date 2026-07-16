# 竞品分析

> 调研于 2026-07-16。结论已合入 [requirements.md](requirements.md) 路线图。

## 市场格局:两个流派

### 流派一:参考图取色 / LUT 提取(对应我们的「像」)

| 产品 | 核心玩法 | 值得借鉴 |
|---|---|---|
| [Color.io Match](https://www.color.io/match) | AI 从参考图提取色彩/对比/亮度,生成 3D 映射套用到目标图 | 导出格式矩阵(.cube LUT + LR Profile .xmp,兼容 Resolve/Premiere/FCP);"100% 本地处理,照片不上传"卖点;强度滑杆实时预览 |
| [fylm.ai AI Colour Extract](https://fylm.ai/ai-colour-extract/) | 神经网络从电影帧提取色调成 LUT | "电影帧作为风格来源"的场景营销 |
| [Imagen LUT Generator](https://imagen-ai.com/tools/lut-generator-from-image/) | 传图出 LUT 的免费引流工具 | 免费在线小工具引流策略 |
| [LUTBuilder.ai](https://www.lutbuilder.ai/) / [sammapix](https://www.sammapix.com/tools/color-match) | 同类 | — |

**洞察**:此流派全部输出 **LUT(黑盒)**——能"像"不能"懂",用户无法微调、无法学习。
我们输出**参数(白盒)**+讲解,这是核心差异化。反向借鉴:.cube LUT 导出成本低
(参数渲染管线采样成 3D 网格,与 preview 渲染同一套代码),能打通视频调色生态,应该做。

### 流派二:学习个人风格、批量修图(对应「库」+批量)

| 产品 | 核心玩法 | 值得借鉴 |
|---|---|---|
| [Imagen AI](https://imagen-ai.com/valuable-tips/best-ai-lightroom-editing-tools-2/) | 3000 张修过的图训练"个人 AI Profile",批量修 RAW | Talent Profiles(知名摄影师预训练风格库,即我们 v0.6 预置 look 的成熟版);Lite Profile 冷启动(一个预设+问卷);结果信心分 |
| [Aftershoot](https://aftershoot.com/blog/ai-photo-editing-tools/) | 选片+修图+修饰一体,离线运行,交付 XMP sidecar | XMP sidecar 交付物(验证了我们的技术路线是行业标准);离线本地化卖点 |
| [Neurapix](https://neurapix.com/blog/neurapix-vs-imagen-vs-aftershoot-ai-editing-solutions-for-professional-photographers) | LR 插件形态,SmartPreset 从滑杆值学习,按光线自适应 | LR 插件形态(backlog 终极工作流);SmartPreset 市场(风格社区化终态);[AI 结果可手动微调](https://www.ephotozine.com/article/new-neurapix-feature--manually-adjust-smartpresets-37356) |

**洞察**:三家都是付费订阅、面向职业婚礼/人像摄影师、卖"省时间"。
**没有一家做教学讲解**——「懂」这条线在市场上是空白,是 looklift 最独特的位置
(入门爱好者要的不是省时间,是学会)。

## 定位语(对外)

> LUT 工具给你黑盒,looklift 给你白盒——参数可改、原理可学、预设可攒。
> 100% 本地运行,照片不离开你的电脑。

## 合入路线图的动作

1. v0.3 增加 `.cube` LUT 导出(复用 preview 渲染管线)✅ 已合入
2. v0.4 GUI 增加强度滑杆、before/after 拖动对比条 ✅ 已合入
3. v0.6 预置 look 库对标 Talent Profiles,差异化是每个 look 附拆解课 ✅ 已确认
4. backlog 增加:LR 插件形态、风格市场/分享(远期)✅ 已合入
