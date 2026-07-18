# LookLift Documentation Reorganization Implementation Plan

**Goal:** 将所有现有文档迁入 `product/`、`versions/`、`history/`、`research/` 四个唯一分类，消除 `specs/`、根 `plans/` 和 `superpowers/` 的重复入口，并修复全部仓库内链接。

**Architecture:** 迁移以 `docs/README.md` 的一对一映射为契约，内容文件只做路径移动和相对链接修复，不改写产品或版本范围。先建立目标路径并逐文件移动，再统一更新导航与引用，最后用路径清单、旧引用扫描和本地 Markdown 链接检查证明没有遗漏。

**Tech Stack:** Markdown、PowerShell、Git 只读命令、仓库现有文档规范。

## Global Constraints

- 不修改业务代码、测试代码或构建配置。
- 不删除或覆盖任何无法在目标目录找到唯一归属的文档。
- 保留当前工作树中尚未提交的 2.0.0 收口和 v2.1 计划改动。
- 所有移动使用明确的源路径与目标路径，不使用递归通配符移动。
- 迁移时只修路径、状态索引和明显失效的现状描述，不重写历史设计。
- 不执行 `git add`、`git commit`、`git push` 或其他 Git 写操作，除非作者另行授权。

---

### Task 1: 建立产品、历史和调研唯一归属

**Files:**
- Keep/Create: `docs/README.md`
- Move: `docs/requirements.md` → `docs/product/requirements.md`
- Move: `docs/design.md` → `docs/product/architecture.md`
- Move: `docs/superpowers/specs/2026-07-18-looklift-platform-ui-design.md` → `docs/product/platform-ui-design.md`
- Move: `docs/dev-log.md` → `docs/history/dev-log.md`
- Move: `docs/tasks.md` → `docs/history/legacy-tasks.md`
- Move: `docs/specs/README.md` → `docs/history/legacy-spec-process.md`
- Move: `docs/competitors.md` → `docs/research/competitors.md`

**Interfaces:**
- Consumes: `docs/README.md` 第 3、5、7 节的职责与迁移映射。
- Produces: 后续版本文档可引用的稳定产品级路径和历史路径。

- [x] **Step 1: 记录源文件清单和目标冲突检查**

Run:

```powershell
Get-Item docs\requirements.md,docs\design.md,docs\dev-log.md,docs\tasks.md,docs\competitors.md,docs\specs\README.md,docs\superpowers\specs\2026-07-18-looklift-platform-ui-design.md | Select-Object FullName,Length
Get-Item docs\product,docs\history,docs\research -ErrorAction SilentlyContinue
```

Expected: 七个源文件都存在；若目标目录已存在，只能包含本计划或空目录，不得有同名目标文件。

- [x] **Step 2: 建立三个目标目录**

Run:

```powershell
New-Item -ItemType Directory -Force docs\product,docs\history,docs\research
```

Expected: 三个目录存在，不改动其他文件。

- [x] **Step 3: 使用明确路径逐个移动文件**

Run:

```powershell
Move-Item -LiteralPath docs\requirements.md -Destination docs\product\requirements.md
Move-Item -LiteralPath docs\design.md -Destination docs\product\architecture.md
Move-Item -LiteralPath docs\superpowers\specs\2026-07-18-looklift-platform-ui-design.md -Destination docs\product\platform-ui-design.md
Move-Item -LiteralPath docs\dev-log.md -Destination docs\history\dev-log.md
Move-Item -LiteralPath docs\tasks.md -Destination docs\history\legacy-tasks.md
Move-Item -LiteralPath docs\specs\README.md -Destination docs\history\legacy-spec-process.md
Move-Item -LiteralPath docs\competitors.md -Destination docs\research\competitors.md
```

Expected: 每个目标文件存在且字节长度与 Step 1 一致；源文件不再存在。

- [x] **Step 4: 检查 Git 对移动的识别基础**

Run: `git status --short docs`

Expected: 只出现预期的删除/新增或 rename 候选，没有内容范围外文件。

---

### Task 2: 将规格和实施计划集中到版本目录

**Files:**
- Move: `docs/specs/2026-07-16-v0.3-precision-loop.md` → `docs/versions/v0.3/spec.md`
- Move: `docs/specs/v0.4/` → `docs/versions/v0.4/`
- Move: `docs/specs/v0.5/` → `docs/versions/v0.5/`
- Move: `docs/specs/v0.6/` → `docs/versions/v0.6/`
- Move: `docs/specs/v0.7/` → `docs/versions/v0.7/`
- Move: `docs/specs/v2.0-A/` → `docs/versions/v2.0-A/`
- Move: `docs/specs/v2.0-B/` → `docs/versions/v2.0-B/`
- Move: `docs/specs/v2.1/{requirements,design,tasks}.md` → `docs/versions/v2.1/`
- Move: five files from `docs/plans/` into matching `docs/versions/<版本>/plans/implementation.md`
- Move: `docs/superpowers/plans/2026-07-18-fix-hidden-canvas-layout.md` → `docs/versions/v2.0-B/plans/fix-hidden-canvas-layout.md`
- Move: `docs/superpowers/plans/2026-07-18-v2.1-ai-studio.md` → `docs/versions/v2.1/plans/implementation.md`

**Interfaces:**
- Consumes: 版本名和计划文件名中的唯一版本归属。
- Produces: `docs/versions/<版本>/` 下自包含的规格和实施记录。

- [x] **Step 1: 枚举所有待迁移规格和计划**

Run:

```powershell
Get-ChildItem docs\specs -Recurse -File | Select-Object FullName
Get-ChildItem docs\plans -File | Select-Object FullName
Get-ChildItem docs\superpowers\plans -File | Select-Object FullName
```

Expected: 除 Task 1 已移动的旧 `specs/README.md` 外，规格为 v0.3 单文件及七个版本三文档；计划为五个旧根计划和两个 superpowers 计划。

- [x] **Step 2: 建立明确的版本与计划目录**

Run:

```powershell
New-Item -ItemType Directory -Force docs\versions\v0.3\plans,docs\versions\v0.4\plans,docs\versions\v0.5\plans,docs\versions\v0.6,docs\versions\v0.7,docs\versions\v2.0-A\plans,docs\versions\v2.0-B\plans,docs\versions\v2.1\plans
```

Expected: 不覆盖当前已存在的 `docs/versions/v2.1/plans/documentation-reorganization.md`。

- [x] **Step 3: 移动所有版本规格**

Run:

```powershell
Move-Item -LiteralPath docs\specs\2026-07-16-v0.3-precision-loop.md -Destination docs\versions\v0.3\spec.md
Move-Item -LiteralPath docs\specs\v0.4\requirements.md,docs\specs\v0.4\design.md,docs\specs\v0.4\tasks.md -Destination docs\versions\v0.4
Move-Item -LiteralPath docs\specs\v0.5\requirements.md,docs\specs\v0.5\design.md,docs\specs\v0.5\tasks.md -Destination docs\versions\v0.5
Move-Item -LiteralPath docs\specs\v0.6\requirements.md,docs\specs\v0.6\design.md,docs\specs\v0.6\tasks.md -Destination docs\versions\v0.6
Move-Item -LiteralPath docs\specs\v0.7\requirements.md,docs\specs\v0.7\design.md,docs\specs\v0.7\tasks.md -Destination docs\versions\v0.7
Move-Item -LiteralPath docs\specs\v2.0-A\requirements.md,docs\specs\v2.0-A\design.md,docs\specs\v2.0-A\tasks.md -Destination docs\versions\v2.0-A
Move-Item -LiteralPath docs\specs\v2.0-B\requirements.md,docs\specs\v2.0-B\design.md,docs\specs\v2.0-B\tasks.md -Destination docs\versions\v2.0-B
Move-Item -LiteralPath docs\specs\v2.1\requirements.md,docs\specs\v2.1\design.md,docs\specs\v2.1\tasks.md -Destination docs\versions\v2.1
```

Expected: v0.4 至 v2.1 每个版本有三文档；v0.3 有 `spec.md`。

- [x] **Step 4: 移动所有实施计划**

Run:

```powershell
Move-Item -LiteralPath docs\plans\2026-07-16-v0.3-precision-loop.md -Destination docs\versions\v0.3\plans\implementation.md
Move-Item -LiteralPath docs\plans\2026-07-17-v0.4-gui-alpha.md -Destination docs\versions\v0.4\plans\implementation.md
Move-Item -LiteralPath docs\plans\2026-07-18-v0.5-providers-batch.md -Destination docs\versions\v0.5\plans\implementation.md
Move-Item -LiteralPath docs\plans\2026-07-17-v2.0-A-engine-refactor.md -Destination docs\versions\v2.0-A\plans\implementation.md
Move-Item -LiteralPath docs\plans\2026-07-18-v2.0-B-tauri-gui.md -Destination docs\versions\v2.0-B\plans\implementation.md
Move-Item -LiteralPath docs\superpowers\plans\2026-07-18-fix-hidden-canvas-layout.md -Destination docs\versions\v2.0-B\plans\fix-hidden-canvas-layout.md
Move-Item -LiteralPath docs\superpowers\plans\2026-07-18-v2.1-ai-studio.md -Destination docs\versions\v2.1\plans\implementation.md
```

Expected: 每个原计划只存在于对应版本目录；v2.0-B 有主计划和修复计划，v2.1 有主计划和本次整理计划。

- [x] **Step 5: 确认旧目录只剩空目录后删除**

Run:

```powershell
Get-ChildItem docs\specs,docs\plans,docs\superpowers -Recurse -Force
```

Expected: 没有文件输出，只可能有空目录。随后只删除这些已经核实位于 `C:\work\looklift\docs\` 下的空目录。

---

### Task 3: 更新导航规则与全部内部链接

**Files:**
- Modify: `AGENTS.md`
- Modify: `docs/README.md`
- Modify: Markdown files returned by old-path scan under repository root

**Interfaces:**
- Consumes: Task 1、2 的最终路径。
- Produces: 后续作者和 agent 都遵循的唯一写入规则，以及可访问的相对链接。

- [x] **Step 1: 扫描所有旧目录引用**

Run:

```powershell
rg -n "docs/specs|docs/plans|docs/superpowers|specs/|\.\./plans|superpowers/(specs|plans)" -g "*.md" .
```

Expected: 输出只包含需要改写的文档引用；迁移映射中的历史源路径可保留为带说明的旧路径，其他引用必须改成目标路径。

- [x] **Step 2: 更新 `AGENTS.md` 文档地图和工作流**

将文档地图固定为：

```markdown
| [docs/README.md](docs/README.md) | 唯一文档导航与存放规范 |
| [docs/product/requirements.md](docs/product/requirements.md) | 产品定位、用户故事与路线图 |
| [docs/product/architecture.md](docs/product/architecture.md) | 已实现架构实况 |
| [docs/versions/](docs/versions/) | 各版本需求、设计、任务与实施计划 |
| [docs/history/dev-log.md](docs/history/dev-log.md) | 开发事实、坑与人工待办 |
```

并把工作流改为：版本三文档 → 同版本 `plans/` → TDD 实现；禁止新建 `docs/specs/`、根 `docs/plans/` 和 `docs/superpowers/`。

- [x] **Step 3: 更新移动后产生的相对链接**

逐条根据目标位置重算相对路径：

- `product/*.md` 引用版本时使用 `../versions/<版本>/`；
- `versions/<版本>/*.md` 引用产品需求时使用 `../../product/requirements.md`；
- `versions/<版本>/*.md` 引用平台 UI 时使用 `../../product/platform-ui-design.md`；
- `history/*.md` 引用版本时使用 `../versions/<版本>/`；
- 版本内部三文档继续使用同级 `requirements.md`、`design.md`、`tasks.md`；
- 版本计划引用同版本规格时使用 `../requirements.md`、`../design.md` 或 `../tasks.md`。

Expected: 不通过复制文件来兼容旧链接，不建立跳转占位文件。

- [x] **Step 4: 将 `docs/README.md` 状态切换为已生效**

将顶部状态改为：

```markdown
> 状态：已生效。本文档是 `docs/` 的唯一导航入口和存放规范。
```

删除“迁移完成前目标路径可能尚未建立”的提示；迁移映射继续作为历史说明保留。

- [x] **Step 5: 重新扫描旧引用**

Run:

```powershell
rg -n "docs/specs|docs/plans|docs/superpowers|superpowers/(specs|plans)" -g "*.md" .
```

Expected: 只允许 `docs/README.md` 的迁移映射和“禁止创建旧目录”规则，以及本迁移计划的历史命令出现；任何作为当前链接使用的旧路径都必须清零。

---

### Task 4: 验证文档完整性和工作树范围

**Files:**
- Verify: all `*.md` in repository
- Verify: `docs/` directory tree
- Verify: Git working tree

**Interfaces:**
- Consumes: 最终目录与修复后的链接。
- Produces: 可审计的迁移完成证据。

- [x] **Step 1: 检查 docs 顶层结构**

Run:

```powershell
Get-ChildItem docs -Force | Select-Object Name,PSIsContainer
```

Expected: 仅 `README.md`、`product/`、`versions/`、`history/`、`research/`。

- [x] **Step 2: 检查版本文档数量**

Run:

```powershell
Get-ChildItem docs\versions -Recurse -File | Select-Object FullName
```

Expected: 原有 30 份版本规格/计划全部存在，加上本迁移计划；没有同一内容的重复副本。

- [x] **Step 3: 运行本地 Markdown 链接检查**

使用 PowerShell 解析所有 Markdown 的相对文件链接：跳过 `http://`、`https://`、锚点、代码围栏及图片数据 URL；对去掉锚点后的目标使用当前文档父目录解析，并断言文件或目录存在。

Expected: broken link count 为 0。若历史文档原本已有断链，必须修到新目标，不把它列为迁移例外。

- [x] **Step 4: 检查格式和意外内容修改**

Run:

```powershell
git diff --check
git diff --stat
git status --short
```

Expected: 无空白错误；变更只涉及先前已有的 2.0.0 收口文件、文档移动、链接修复、`AGENTS.md` 和本次新增规范/计划，不出现业务代码或构建产物。

- [x] **Step 5: 人工抽查导航**

从 `docs/README.md` 依次打开产品需求、平台 UI、v2.1 requirements、v2.1 implementation plan、v2.0-B 修复计划和开发日志。

Expected: 六个入口均能通过新路径直接打开，且不存在需要到旧目录寻找文档的说明。
