# LookLift

> Lift the look — 把调色审美变成可解释、可微调、可学习的白盒参数。
> 别的 AI 修图给你黑盒结果，LookLift 给你白盒过程：参数可改、原理可学、模板可攒。
> 调色、渲染、风格库都在你电脑上；外部 AI 只接收 2048px 无 EXIF 代理图。接本地模型可彻底离线。

LookLift 是开源一站式 AI 调色应用。打开照片后，左侧和 AI 对话调参，中间看效果与原图对比，右侧用 Lightroom 风格滑杆精调，应用内直接出成片；也可以导出 LR 预设 / RAW sidecar / `.cube` LUT 给专业工作流。

**红线：白盒。** AI 改的永远是可解释参数，不是黑盒像素，也不驱动真 Adobe Lightroom。

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

产品定位、路线图与架构实况见 [文档中心](docs/README.md)。当前桌面包版本号为 **2.2.0**；图库、设备导入、模板教学、自动化技能与 Agent Runtime 已在后续版本落地，详见文档索引。

## 现在能做什么

- **三栏修图工作台**：左对话 / 中画布 / 右白盒滑杆，候选先预览，确认后才写入正式版本
- **本机 CLI 或 API Key**：设置页管理 Claude Code、Pi 等本机 CLI，以及 OpenAI 兼容接口 / 本机 Ollama；无 CLI 时可用 API Key 走受控工具循环
- **本地图库与导入**：索引本机文件夹，从相机/存储卡复制进图库后再进入 Studio
- **模板与风格库**：官方/用户模板起手，参数可学、可套用、可当 AI 附件
- **自动化成片**：把已有白盒风格做成技能，确认输入输出后批量出片，失败可重试
- **专业出口**：应用内导出成片，或写出 Lightroom 预设、RAW sidecar、3D LUT
- **CLI 脚本**：分析、读取内嵌 LR 元数据、套用、报告、预览、refine 仍可命令行完成

## 安装

```sh
git clone https://github.com/liujsh/looklift && cd looklift
python -m venv .venv
.venv\Scripts\pip install -e ".[render]"
```

可选依赖：

| extra | 用途 |
|---|---|
| `render` | libvips / pyvips，成品级渲染 |
| `raw` | rawpy，RAW 全解码 |
| `memory` | 本地记忆向量 |
| `gui` | 旧版 pywebview 窗口（开发回退） |

日常使用以 **Tauri 桌面应用** 为主。Python 引擎作为本机 sidecar，CLI 与 GUI 共用同一套实现。

### 从源码构建 Windows 安装包

需要 Python 3.11+、Node/pnpm、Rust：

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

安装包位于 `frontend/src-tauri/target/release/bundle/nsis/looklift_2.2.0_x64-setup.exe`。

冻结引擎可在仓库根目录做一次离线发布冒烟：

```powershell
.venv\Scripts\python packaging\smoke_release.py `
  frontend\src-tauri\target\release\looklift-engine.exe
```

开发时：

```powershell
cd frontend
pnpm tauri dev
```

### 旧版 pywebview GUI

仍可用于调试或浏览器回退：

```sh
pip install -e ".[gui]"
looklift gui
```

`--browser` 直接用系统浏览器打开；`--port` 指定本机端口。WebView2 缺失时会自动降级，不会崩溃退出。

## 模型与提供商

在应用「设置 → 模型与提供商」里选择，不需要再手抄 `~/.looklift/config.toml` 才能开始修图。

| 模式 | 说明 |
|---|---|
| 本机 CLI | 扫描已安装入口（如 Claude Code、Pi），启停、查看已发现模型和默认选择 |
| API 提供商 | 保存 OpenAI 兼容接口或本机 Ollama；密钥只进本机凭据存储，查询接口不回显 |

规则：

- 外部 AI 只接收最长边 2048px、无 EXIF 的代理图
- API 模式在没有本机 CLI 时不会安装或启动 Pi / OpenCode / Claude Code
- 未选择入口或模型时，对话框会阻止发送，不会静默换一个供应商

也可继续用 `~/.looklift/config.toml` 或环境变量给 CLI 分析命令指定后端。OpenAI 兼容示例：

```toml
provider = "openai_compat"
base_url = "https://your-endpoint.example/v1"
api_key = "sk-..."
model = "your-vision-model"
timeout = 120
```

Ollama 示例（先 `ollama pull <视觉模型名>`）：

```toml
provider = "ollama"
base_url = "http://localhost:11434"
model = "qwen2.5vl:7b"
timeout = 300
```

## CLI 用法

图形界面是主路径；命令行仍覆盖分析、风格库和导出。

```sh
# 分析大师成片，结果收入风格库
looklift analyze master.jpg --name "胶片青橙"

# 多张同风格成片一起归纳（上限 5 张）
looklift analyze a.jpg b.jpg c.jpg --name "某摄影师风格"

# 按目录批量分析
looklift analyze --batch D:/reference-looks --backend ollama

# 生成 HTML 风格报告
looklift report "胶片青橙"

# 原片 + 成片对照
looklift analyze after.jpg --original before.jpg --name "我的风格"

# 直接写 RAW sidecar
looklift analyze master.jpg --sidecar D:/photos/IMG_0001.CR3

# 读取 JPEG 内嵌 LR 元数据（精确参数）
looklift read exported.jpg --preset stolen-look.xmp

# 查看 / 套用风格库
looklift list
looklift apply 胶片青橙 --sidecar "D:/photos/*.CR3"

# 本地近似渲染预览（不开 LR）
looklift preview 胶片青橙 my-photo.jpg --target master.jpg

# 导出 3D LUT
looklift export-lut 胶片青橙 -o 胶片青橙.cube

# 迭代校准
looklift refine 胶片青橙 --attempt my-export.jpg --target master.jpg
looklift refine 胶片青橙 --auto --source raw-export.jpg --target master.jpg
```

生成的 `.xmp` 预设可在 Lightroom 预设面板导入；与 RAW 同名的 sidecar 会被 Lightroom / Camera Raw / Bridge 自动读取。

## 工作流

1. 把照片加入图库或直接打开进入 Studio
2. 用模板起手，或让 AI 根据当前画面给白盒建议
3. 候选先预览：保留、撤销、继续手调或再精修；确认后才成为正式版本
4. 应用内导出成片，或把同一套参数写成 LR 预设 / sidecar / LUT

CLI 分析路径仍然可用：`analyze` → 风格库 → `apply` / `preview` / `refine`。

## 已知限制

- AI 只改全局白盒参数，不做局部蒙版、径向/渐变滤镜，也不做扩散式像素改写
- 外部模型看到的是代理图和当前参数，不是原图、完整 EXIF 或未确认候选的内部推理
- 中途把对话从 CLI 换到 API loop 时，界面记录还在，但 API 路径目前主要带当前画面，不带完整历史原文
- `preview` / `export-lut` 覆盖全局色彩方向，暗角、颗粒等空间效果不进 LUT
- 桌面安装包优先 Windows；macOS / Linux 保持 Python 引擎兼容，图库与设备导入后续补齐

## License

MIT
