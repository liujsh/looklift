# looklift 📷

把大师作品的"look"提取出来:分析照片的调色/影调参数,生成 Lightroom 可用的预设和 RAW sidecar。

## 三条路径

| 场景 | 命令 | 准确度 |
|---|---|---|
| 照片嵌有 LR 元数据(自己导出的 JPEG) | `read` | 100% 精确,免费 |
| 网上的大师成片(元数据已剥离) | `analyze` | AI 视觉逆向推断 |
| 有原片 + 成片对照 | `analyze --original` | AI 对比分析,更准 |

## 安装

```
pip install -r requirements.txt
```

AI 分析二选一:
- **本地 Claude Code CLI**(推荐,走 Claude Code 登录额度,无需 API key):已安装 `claude` 命令即可
- **Anthropic API**:设置环境变量 `ANTHROPIC_API_KEY`

默认 `--backend auto`:有 API key 走 API,否则走本地 CLI。

## 用法

```sh
# 分析大师成片 → 打印参数讲解,预设+模版自动收入 looks/ 风格库
python -m looklift analyze master.jpg --name "胶片青橙"

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
```

## 工作流

1. `analyze` 大师成片,起个名字 → 存入 `looks/` 风格库
2. LR 导入 `looks/<名字>.xmp` 预设,套到自己的照片上
3. 不够像?导出效果图,`refine` 一轮,重新导入预设(会自动备份上一版)
4. 之后任何 RAW 直接 `apply <名字> --sidecar` 一键套用

## 生成的文件怎么用

- **预设 .xmp**:Lightroom → 修改照片 → 预设面板 → `+` → 导入预设,之后一键套用到任何照片
- **sidecar .xmp**:与 RAW 同名、放在同一目录,Lightroom / Camera Raw / Bridge 打开该 RAW 时自动读取应用(若 RAW 已在 LR 目录中,需在图库中右键 → 元数据 → 从文件读取元数据)

## 已知限制

- AI 推断的白平衡写成增量色温/色调(`IncrementalTemperature`),对 JPEG/TIFF 生效;RAW 文件的开尔文色温需在 LR 中微调
- 局部调整(蒙版、径向/渐变滤镜)无法通过全局预设表达,分析结果的"后期步骤"里会用文字说明
- AI 推断是估计值,建议套用后按讲解微调
