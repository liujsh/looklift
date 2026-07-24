# 图库文件夹导航 · 设计

- 日期：2026-07-24
- 分支：v2.3-library
- 状态：已确认，待转实现计划

## 背景与目标

当前「我的图库」把一个 root 下所有照片平铺成分页网格。用户本地已经按日期/地点整理成多层文件夹（如 `2024/云南/大理`），希望图库也复现这个层级，而不是全部铺平。

2.3-A 手测已完成，UI 尚粗糙。经确认：**把平铺网格改成文件夹导航本身就是最大的一次 UI 重构**，先做这个功能性重构、顺带把涉及界面定稿，之后再评估是否需要单独美化 pass——避免先泛泛美化再推倒重来的白工。

### 已确认的决策

1. **推进顺序**：先做文件夹结构重构（不先做纯 UI 美化）。
2. **浏览方式**：逐层钻进 + 面包屑（类 Windows 资源管理器）。当前层只显示子文件夹和本层照片，点文件夹钻进下一层，顶部面包屑可回退。
3. **搜索范围**：搜索时切到全库平铺。无搜索词 = 文件夹钻进视图；一旦输入关键词或选标签，临时变回跨全库平铺搜索结果（显示完整路径）；清空搜索回到钻进视图。两种模式各自干净。

## 核心思路

文件夹层级**完全从已索引的照片路径推导**，不额外扫描磁盘、不改扫描逻辑。

每张照片已存绝对 `path` + 所属 `root_id`（见 `library_store.py` 的 `LibraryItem` 与 `library_items` 表），root 存了根目录绝对路径。因此：

- 一个「文件夹」就是某个目录绝对路径。
- 只列出「底下确实有已索引照片」的目录——不 `rglob` 磁盘、不枚举库外任意路径（安全性：避免把图库当任意目录浏览器），且与扫描解耦。
- 路径分隔符沿用入库时 `str(Path.resolve())` 的 OS 分隔符（Windows 为 `\`）。

## 架构与组件

### 后端

#### `library_store.py`：`LibraryStore.browse_folder(folder, *, page, page_size)`

输入：
- `folder: str | None`——当前目录绝对路径；`None` 表示「首页」虚拟节点。
- `page`、`page_size`——仅对**本层照片**分页，沿用 `search_items` 的校验规则（page≥1，1≤page_size≤100）。

返回一个新 dataclass `FolderView`：
- `folders: tuple[FolderEntry, ...]`——当前目录的直接下级子文件夹，每个含：
  - `name`：目录名（路径最后一段）。
  - `path`：子文件夹绝对路径。
  - `count`：该子文件夹下（任意深度）已索引照片总数。
  - `cover_item_id: str | None`：取该子文件夹下任意一张照片的 id 当封面（复用现有缩略图接口）。
- `items: tuple[LibraryItem, ...]`——路径正好是当前目录**直接子文件**的照片（分页后）。
- `total: int`——本层直接子文件照片总数（供本层分页）。
- `page`、`page_size`——回显。

行为细节：
- **首页节点（`folder is None`）**：`folders` = 各个 root（`name` 取 root 路径最后一段，`path` = root 绝对路径，`count` = 该 root 下全部索引照片数，`cover_item_id` 取一张）；`items` = 空，`total` = 0。（root 本身直接放着的松散照片，在钻进该 root 后作为其本层照片显示。）
- **子文件夹推导**：对当前目录 `D`，取所有 `path` 以 `D + sep` 开头的索引照片，按「`D` 之后的下一段目录名」分组；每组即一个子文件夹，`count` = 组内条数，`cover_item_id` = 组内任一 id。
- **本层直接子文件**：`path` 以 `D + sep` 开头、且其后不再含分隔符的照片；用 SQL LIKE 谓词筛出后复用现有 `LibraryItem` 装配路径（含 tags、export 统计）。分页作用于此。
- 子文件夹一律全列，不分页。
- `folder` 必须落在某个已知 root 内（或等于某 root）；否则视为无效，返回空视图（不抛未捕获异常）。

排序：子文件夹按 `name COLLATE NOCASE`；本层照片沿用现有 `display_name COLLATE NOCASE, id`。

#### `api.py`：新增路由

`GET /api/library/folder`
- query：`path`（可选，绝对路径；缺省 = 首页）、`page`（默认 1）、`page_size`（默认 48）。
- handler `_get_library_folder`：解析分页参数（无效 → 400，文案与 `_get_library_items` 一致），调用 `browse_folder`，把 `FolderView` 投影为 JSON。照片项复用现有 `_library_item_payload`（含 session 摘要合并）。folders 项投影为 `{name, path, count, cover_item_id}`。
- 注册进 `ROUTES`，紧邻现有 `/api/library/items`。

现有 `/api/library/items`（平铺搜索）**不动**，搜索模式继续走它。

### 前端 `LibraryPage.tsx`

新增状态 `currentFolder: string | null`（`null` = 首页）。渲染分两种模式：

- **搜索模式**（`filters.keyword` 或 `filters.tag` 非空）：走现有 `client.libraryItems(...)`，照片卡显示完整路径，与现状一致。分页照旧。
- **浏览模式**（无搜索词）：走新的 `client.libraryFolder(currentFolder, page)`。渲染：
  1. **面包屑**：`首页 › 2024 › 云南 › 大理`，每段可点回退（点「首页」→ `currentFolder=null`）。每段展示目录名，`title` 挂完整路径。分段由 `currentFolder` 相对其所属 root 推导；root 那段用其目录名。
  2. **文件夹卡**：封面缩略图（用 `cover_item_id` 调现有 `client.libraryThumbnail(id)`）+ 目录名 + 数量角标；点击 `setCurrentFolder(folder.path)` 并回到第 1 页。
  3. **本层照片卡**：复用现有 `LibraryCard`。
  4. **分页** 只作用于本层照片。

模式切换：
- 提交搜索（有词）→ 进搜索模式。
- 清空搜索并提交 → 回浏览模式，`currentFolder` 保持不变（停在原来钻进的位置）。
- 钻进/回退只在浏览模式内发生。

工具栏与管理行：
- 「加入图库 / 选择文件夹 / 搜索」工具栏保留在顶部。
- root 的「刷新 / 移除索引」管理行**只在首页层**（`currentFolder === null` 且非搜索模式）显示，钻进后隐藏，减少干扰。

### API client（`client.ts` + `types.ts`）

- `types.ts`：新增 `LibraryFolderEntry`（`{name, path, count, cover_item_id}`）、`LibraryFolderView`（`{folders, items, total, page, page_size}`，`items` 复用现有 `LibraryItem` 类型）。
- `client.ts`：新增 `libraryFolder(path: string | null, page, pageSize)`，GET `/api/library/folder`，返回 `LibraryFolderView`。

## 不做（YAGNI）

- 不做左侧常驻文件夹树（已选逐层钻进）。
- 不做拖拽移动、新建/重命名/删除文件夹——图库只建索引、不动原文件，这条铁律不破。
- 不做跨文件夹合并封面拼图，封面就取一张现有缩略图。
- 不改扫描逻辑、不新增磁盘遍历。

## 错误处理

- 无效 `path`（不在任何 root 内）→ 返回空视图，前端显示「没有符合条件的照片」空态（不报错）。
- 分页参数非法 → 400，文案与现有 `/api/library/items` 一致。
- 封面 `cover_item_id` 对应缩略图缺失 → 沿用现有 `/thumbnail` 接口的 404 与前端占位逻辑（`LibraryCard` 已有缩略图加载失败处理）。

## 测试

沿用现有测试规范（pytest + vitest）：

- **store 层**（`tests/test_library_store.py` 或对应文件）：`browse_folder` 的子文件夹推导、直接子文件筛选、count/cover 正确、分页、多 root、首页节点、无效/库外 path 返回空、深层嵌套。
- **API 层**（`tests/test_gui_server.py`）：`/api/library/folder` 的首页与钻进响应形状、分页参数校验 400、缺省 path。
- **前端**（`LibraryPage.test.tsx`）：钻进文件夹、面包屑回退、搜索切到平铺再清空回浏览模式、文件夹卡数量角标、管理行仅首页可见。

## 交付顺序（供实现计划参考）

1. store 层 `browse_folder` + dataclass + 单测。
2. api 路由 `_get_library_folder` + 测试。
3. client + types。
4. `LibraryPage` 浏览模式 UI（面包屑 / 文件夹卡 / 模式切换）+ 组件测试。
