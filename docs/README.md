# LookLift 文档中心

> 状态：已生效。本文档是 `docs/` 的唯一导航入口和存放规范。

## 1. 目标

文档按“产品级、版本级、历史记录、调研资料”划分。一个版本的需求、设计、任务和实施计划必须集中在同一个版本目录，不再并存 `specs/`、`plans/` 与 `superpowers/` 三套入口。

## 2. 目标目录

```text
docs/
├─ README.md
├─ product/
│  ├─ requirements.md
│  ├─ architecture.md
│  └─ platform-ui-design.md
├─ versions/
│  ├─ <版本>/
│  │  ├─ requirements.md
│  │  ├─ design.md
│  │  ├─ tasks.md
│  │  └─ plans/
│  │     └─ implementation.md
│  └─ ...
├─ history/
│  ├─ dev-log.md
│  ├─ legacy-tasks.md
│  └─ legacy-spec-process.md
└─ research/
   └─ competitors.md
```

早期只有一份综合规格的版本允许保留 `spec.md`，不强行为了形式拆成三份空洞文档。一个版本存在多个实施计划时，统一放入该版本的 `plans/` 子目录并使用能说明目的的文件名。

## 3. 文档职责

| 位置 | 唯一职责 | 不应包含 |
|---|---|---|
| `product/requirements.md` | 产品定位、完整用户故事、正式路线图和版本边界 | 单个任务的实现步骤 |
| `product/architecture.md` | 已实现系统的架构实况 | 尚未确认的未来实现细节 |
| `product/platform-ui-design.md` | 已确认的平台整体信息架构与跨版本设计 | 某一版本的逐任务计划 |
| `versions/<版本>/requirements.md` | 该版本做什么、不做什么、验收结果 | 实现代码级步骤 |
| `versions/<版本>/design.md` | 该版本怎么做、状态所有权和技术决策 | 全产品路线图 |
| `versions/<版本>/tasks.md` | 版本任务、依赖、完成条件和人工验收 | 跨版本待办汇总 |
| `versions/<版本>/plans/*.md` | 可执行的 TDD 实施顺序和验证命令 | 产品方向讨论 |
| `history/dev-log.md` | 跨版本开发事实、坑和人工待办 | 未来版本需求正文 |
| `history/legacy-tasks.md` | 旧根任务文件的只读历史 | 当前迭代状态 |
| `history/legacy-spec-process.md` | 旧 spec 规范和早期决策记录 | 当前文档规则 |
| `research/competitors.md` | 竞品与外部资料研究 | 已确认的产品契约 |

## 4. 当前版本索引

迁移完成后，本节作为查看版本状态的首要入口。

| 版本 | 状态 | 说明 |
|---|---|---|
| v0.3 | 已完成，历史格式 | 保留单文件 spec 与对应实施计划 |
| v0.4 | 历史迭代 | 保留三文档与实施计划 |
| v0.5 | 历史迭代 | 保留三文档与实施计划 |
| v0.6 | 已终止、范围迁移 | 合理范围已并入 v2.4，不再按旧规格开发 |
| v0.7 | 已终止 | 已被 v2.0-B 及新平台路线取代 |
| v2.0-A | 已完成 | 2.0.0 引擎内部阶段 |
| v2.0-B | 已完成 | 2.0.0 GUI 内部阶段，M1-M8 已通过 |
| v2.1 | 已完成 | AI Studio，2026-07-20 验收并合入 `main` |
| v2.2 | 已完成，2026-07-21 合入 main | 平台外壳 |
| v2.3-A | 规格已建立，开发中 | 本地文件夹图库 |

尚未进入规格阶段的 v2.3 及后续版本只存在于产品路线图和平台总体设计中。当前版本接近收口时，才建立下一版本目录和三文档。

## 5. 迁移映射

| 当前路径 | 目标路径 |
|---|---|
| `docs/requirements.md` | `docs/product/requirements.md` |
| `docs/design.md` | `docs/product/architecture.md` |
| `docs/superpowers/specs/2026-07-18-looklift-platform-ui-design.md` | `docs/product/platform-ui-design.md` |
| `docs/specs/<版本>/` | `docs/versions/<版本>/` |
| `docs/specs/2026-07-16-v0.3-precision-loop.md` | `docs/versions/v0.3/spec.md` |
| `docs/specs/README.md` | `docs/history/legacy-spec-process.md` |
| `docs/plans/<版本实施计划>.md` | 对应 `docs/versions/<版本>/plans/implementation.md` |
| `docs/superpowers/plans/2026-07-18-v2.1-ai-studio.md` | `docs/versions/v2.1/plans/implementation.md` |
| `docs/superpowers/plans/2026-07-18-fix-hidden-canvas-layout.md` | `docs/versions/v2.0-B/plans/fix-hidden-canvas-layout.md` |
| `docs/dev-log.md` | `docs/history/dev-log.md` |
| `docs/tasks.md` | `docs/history/legacy-tasks.md` |
| `docs/competitors.md` | `docs/research/competitors.md` |

迁移采用纯路径移动，不重写历史内容；仅修改为了适配新位置而失效的相对链接，以及明确错误的现状描述。

## 6. 后续写入规则

1. 新版本只在 `docs/versions/<版本>/` 中建立 `requirements.md`、`design.md`、`tasks.md` 和 `plans/`。
2. 实施计划必须属于一个明确版本；跨版本设计进入 `product/`，不得再创建通用 `docs/plans/`。
3. 不再创建 `docs/superpowers/`。工具或技能给出的默认目录必须服从本文件约定。
4. `product/architecture.md` 只记录已经实现的架构；版本完成后从版本设计回填必要实况。
5. 版本状态只在本索引、产品路线图和该版本文档中维护，不新增第四份状态表。
6. Markdown 内部链接优先使用相对路径；移动文档后必须扫描整个仓库并修复所有引用。
7. 历史版本文档原则上只修断链和明显事实错误，不继续扩写需求。

## 7. 本次整理范围

本次会：

- 建立目标目录并移动现有文档；
- 更新 `AGENTS.md` 的文档地图和工作流；
- 修复仓库内 Markdown 对旧路径的引用；
- 删除搬空后的 `docs/specs/`、`docs/plans/` 和 `docs/superpowers/`；
- 检查所有本地 Markdown 链接和 Git 工作树，确保没有遗漏或误删。

本次不会：

- 改写产品需求、版本范围或实现方案；
- 把 v0.6、v0.7 重新列为待开发版本；
- 提前创建 v2.2 及后续版本的详细规格；
- 修改业务代码、测试代码或构建配置。

## 8. 验收标准

- `docs/` 顶层除 `README.md` 外只保留 `product/`、`versions/`、`history/`、`research/` 四个目录。
- 每份现有文档都能在迁移映射中找到唯一归属，没有内容重复拷贝。
- 仓库内不再引用 `docs/specs/`、`docs/plans/` 或 `docs/superpowers/`。
- Markdown 本地链接检查通过，Git 能识别为移动而不是内容丢失。
- `AGENTS.md` 明确以后只按本结构写文档。
