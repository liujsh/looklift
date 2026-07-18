# looklift 📷

> Lift the look — 把大师作品的"look"提取出来。
> LUT 工具给你黑盒,looklift 给你白盒:参数可改、原理可学、预设可攒。
> 预设生成、渲染、风格库全部在你电脑上;AI 分析只把照片发给你自己选的模型,接本地模型可彻底离线。

分析照片的调色/影调参数,生成 Lightroom 可导入的预设和 RAW sidecar。
喂一张喜欢的成片,AI 视觉模型逆向推断出基本面板、HSL、颜色分级、曲线等全套参数,
并用中文讲解这种风格是怎么调出来的。

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

完整的产品路线、架构、版本规格与实施记录见 [文档中心](docs/README.md)。

## 三条路径

| 场景 | 命令 | 准确度 |
|---|---|---|
| 照片嵌有 LR 元数据(自己导出的 JPEG) | `read` | 100% 精确,免费 |
| 网上的大师成片(元数据已剥离) | `analyze` | AI 视觉逆向推断 |
| 有原片 + 成片对照 | `analyze --original` | AI 对比分析,更准 |

## 安装

```
git clone https://github.com/liujsh/looklift && cd looklift
pip install -e .
```

想用图形界面(拖拽照片、强度滑杆、风格库面板)而不是命令行,装 `[gui]` extra:

```
pip install -e ".[gui]"
```

之后直接使用 `looklift` 命令(下面示例中的 `python -m looklift` 同样可用)。

AI 分析支持四类后端:
- **本地 Claude Code CLI**(推荐,走 Claude Code 登录额度,无需 API key):已安装 `claude` 命令即可
- **Anthropic API**:设置环境变量 `ANTHROPIC_API_KEY`
- **OpenAI-compatible**:标准 Chat Completions vision 接口,可接 OpenAI 或兼容中转站
- **Ollama**:本机视觉模型,照片不离开电脑

默认 `--backend auto`:若 config 已固定 provider 就使用它；否则有 API key 走 API，
再否则走本地 CLI。

也可在 `~/.looklift/config.toml` 固定后端。OpenAI-compatible 示例:

```toml
provider = "openai_compat"
base_url = "https://your-endpoint.example/v1"
api_key = "sk-..."
model = "your-vision-model"
timeout = 120
```

Ollama 示例（先自行 `ollama pull <视觉模型名>`）:

```toml
provider = "ollama"
base_url = "http://localhost:11434"
model = "qwen2.5vl:7b"
timeout = 300
```

`timeout` 可留空；默认值分别为 CLI 600 秒、Anthropic/OpenAI-compatible 120 秒、
Ollama 300 秒。命令行也可用 `--backend openai_compat` 或 `--backend ollama` 临时选择。

## GUI 使用

### Tauri 桌面版（v2.0-B）

Windows 桌面版提供拖图、before/after、契约驱动的完整调色面板、内置模板、收藏、
报告和 XMP/RAW sidecar 导出。应用启动时自动拉起本地 Python 引擎，关闭窗口时一并
回收；业务逻辑仍与 CLI 共用同一套 Python 实现。

从源码构建最终安装包（需要 Node/pnpm、Rust 和 Python 3.11+）：

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[render]" pyinstaller
.venv\Scripts\python -m PyInstaller --noconfirm --clean `
  --distpath build\pyinstaller\dist --workpath build\pyinstaller\work `
  packaging\looklift-engine.spec
cd frontend
pnpm install
pnpm tauri build
```

产物位于
`frontend/src-tauri/target/release/bundle/nsis/looklift_2.0.0_x64-setup.exe`。
冻结引擎可在仓库根目录执行以下离线发布冒烟：

```powershell
.venv\Scripts\python packaging\smoke_release.py `
  frontend\src-tauri\target\release\looklift-engine.exe
```

### 旧版 pywebview GUI

旧版 GUI 仍可用于开发和浏览器回退，复用和 CLI 完全相同的分析/渲染/风格库逻辑：

```
pip install -e ".[gui]"
looklift gui
```

默认弹出独立窗口(Windows 用系统自带的 WebView2);没装 `pywebview` 或窗口组件启动失败
(如 WebView2 缺失)时自动降级为系统浏览器打开,并打印中文提示,不会崩溃退出。

| 参数 | 作用 |
|---|---|
| `--browser` | 不弹窗口,直接用系统浏览器打开(开发调试 / WebView2 缺失兜底) |
| `--port` | 指定本地端口(默认 `0`,由系统分配空闲端口) |

首次启动会看到一个可跳过的配置向导(选 provider、填 key);跳过也能先逛风格库和报告页,
只有点"分析"才真正需要配置好 AI 后端。

## 用法

```sh
# 分析大师成片 → 打印参数讲解,预设+模版自动收入 looks/ 风格库
looklift analyze master.jpg --name "胶片青橙"

# 多张同风格成片一起分析,归纳共同风格(降低单张偶然性,上限 5 张)
looklift analyze a.jpg b.jpg c.jpg --name "某摄影师风格"

# 批量分析:根目录下每个一级子目录是一组,成功结果写入组内 .looklift-result.json
looklift analyze --batch D:/reference-looks --backend ollama

# 已有结果默认跳过;需要全部重算时显式加 --force
looklift analyze --batch D:/reference-looks --force

# 生成 HTML 风格报告(概述+步骤+参数表+曲线图),可直接分享
looklift report "胶片青橙"

# 有原片对照(分析更准)
python -m looklift analyze after.jpg --original before.jpg --name "我的风格"

# 直接写 RAW sidecar,LR/Camera Raw 打开 RAW 时自动套用
python -m looklift analyze master.jpg --sidecar D:/photos/IMG_0001.CR3

# 读取照片内嵌的 LR 元数据(精确参数),直接转预设
python -m looklift read exported.jpg --preset stolen-look.xmp

# 查看风格库
python -m looklift list

# 把风格库中的风格批量套用到 RAW(支持通配符)
python -m looklift apply 胶片青橙 --sidecar "D:/photos/*.CR3"

# 迭代校准:在 LR 里套用预设导出效果图,和目标成片一起喂回去,AI 给出修正
python -m looklift refine 胶片青橙 --attempt my-export.jpg --target master.jpg

# 本地近似渲染预览(不开 LR),可选给目标成片打相似度分
looklift preview 胶片青橙 my-photo.jpg --target master.jpg

# 导出 3D LUT(.cube),给达芬奇/剪映等视频剪辑软件调色用
looklift export-lut 胶片青橙 -o 胶片青橙.cube

# 全自动校准:本地渲染→评分→AI 修正循环,不用手动导出效果图
looklift refine 胶片青橙 --auto --source raw-export.jpg --target master.jpg
```

## 示例输出

对一张草原风光成片运行 `analyze` 的真实输出(节选):

```
=== 风格分析 ===
这是一张典型的『明快风光』风格照片……影调上黑场扎实不褪色(马群和电线接近纯黑剪影),
白场干净,反差中等偏高、中间调明亮。白平衡中性略偏冷,保持天空的清爽蓝。核心色彩处理在于:
草地绿色被明显提饱和并向翠绿偏移,天空蓝色饱和度提高、明度略压以增强蓝白层次……

=== 后期步骤 ===
1. 白平衡保持中性,色温略向蓝偏移 3-5,营造清爽通透的基调
3. 高光 -25 左右压回云层和塔筒的细节,白色 +10 保持白场干净明亮
8. HSL:绿色色相 -15(偏翠绿)、饱和度 +30,蓝色饱和度 +20、明度 -10 加深天空
……

=== 基本面板 ===
  色温     -4        高光     -25       去朦胧    +10
  曝光     +0.1      阴影     +10       自然饱和度  +25
  对比度    +15       黑色     -10       饱和度    +8

=== 曲线控制点 ===
  (0,0)  (64,58)  (128,132)  (192,198)  (255,255)

[预设] 已生成: looks\grassland.xmp  (Lightroom → 预设面板 → 导入预设)
```

## 工作流

1. `analyze` 大师成片,起个名字 → 存入 `looks/` 风格库
2. LR 导入 `looks/<名字>.xmp` 预设,套到自己的照片上
3. 不够像?导出效果图,`refine` 一轮,重新导入预设(会自动备份上一版)
4. 之后任何 RAW 直接 `apply <名字> --sidecar` 一键套用

批量目录约定如下；每组图片按修改时间升序取前 5 张，失败组不会阻塞后续组，重跑会从
没有 `.looklift-result.json` 的组继续:

```text
reference-looks/
├── warm-film/       # 一组同风格照片
│   ├── 01.jpg
│   └── 02.jpg
└── cool-cinema/     # 另一组
    ├── a.jpg
    └── b.jpg
```

## 生成的文件怎么用

- **预设 .xmp**:Lightroom → 修改照片 → 预设面板 → `+` → 导入预设,之后一键套用到任何照片
- **sidecar .xmp**:与 RAW 同名、放在同一目录,Lightroom / Camera Raw / Bridge 打开该 RAW 时自动读取应用(若 RAW 已在 LR 目录中,需在图库中右键 → 元数据 → 从文件读取元数据)

## 已知限制

- AI 推断的白平衡写成增量色温/色调(`IncrementalTemperature`),对 JPEG/TIFF 生效;RAW 文件的开尔文色温需在 LR 中微调
- 局部调整(蒙版、径向/渐变滤镜)无法通过全局预设表达,分析结果的"后期步骤"里会用文字说明
- AI 推断是估计值,建议套用后按讲解微调,或用 `refine` 命令迭代校准
- `preview` 是本地近似渲染(sRGB 输入,Pillow+numpy 实现),用于快速预览方向和 `refine --auto` 打分,不等价于 Lightroom 的精确色彩管线
- `export-lut` 只覆盖全局色彩(曝光/白平衡/对比/曲线/HSL/颜色分级),暗角、颗粒等空间效果不进 LUT
- v0.5 批量模式只按目录分组,不做自动风格聚类

## License

MIT
