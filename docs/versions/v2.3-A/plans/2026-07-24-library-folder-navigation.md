# 图库文件夹导航 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「我的图库」的平铺分页网格改成逐层钻进 + 面包屑的文件夹导航，文件夹层级完全从已索引照片路径推导。

**Architecture:** 后端 `LibraryStore` 新增 `browse_folder(folder, page, page_size)`，从 `library_items.path` 推导子文件夹与本层直接子文件（不遍历磁盘、不改扫描）；新增 `GET /api/library/folder` 路由投影为 JSON。前端 `LibraryPage` 加 `currentFolder` 状态：无搜索词走文件夹钻进（面包屑 + 文件夹卡 + 本层照片卡），有搜索词临时切回现有全库平铺搜索。

**Tech Stack:** Python 3 + SQLite（后端）、pathlib 做路径推导；React + TypeScript + vitest（前端）；pytest（后端测试）。

## Global Constraints

- 图库只建立本地索引，**绝不复制/移动/删除/改写原文件**，也不新增磁盘遍历——文件夹层级只从已入库的 `library_items.path` 推导。（spec「核心思路」「不做」）
- 照片路径在库中以 `str(Path(...).resolve())` 存储（绝对路径，OS 原生分隔符）。路径推导一律用 `pathlib` 操作（`.relative_to` / `.parts` / `.is_relative_to`），不手写分隔符字符串，保证同机一致。
- 分页参数校验规则与文案与现有 `/api/library/items` 完全一致：`page` 从 1 开始，`page_size` 范围 1–100，非法一律 `400 {"error": "分页参数无效：page 从 1 开始，page_size 范围为 1 到 100"}`。
- 现有 `/api/library/items`（平铺搜索）路由与语义保持不变，搜索模式继续走它。
- 中文错误/提示文案，与现有图库模块风格一致。

---

## File Structure

- `looklift/library_store.py` — 新增 `FolderEntry`、`FolderView` dataclass 与 `browse_folder`；给内部 `_query_items` 增加 `item_ids` 过滤参数（本层直接子文件按 id 集合分页装配）。
- `looklift/gui/api.py` — 新增 handler `_get_library_folder` 并注册路由 `GET /api/library/folder`。
- `frontend/src/api/types.ts` — 新增 `LibraryFolderEntry`、`LibraryFolderView` 类型。
- `frontend/src/api/client.ts` — 新增 `libraryFolder(path, page, pageSize)` 方法。
- `frontend/src/platform/libraryFolderPath.ts` — 新建：纯函数 `folderCrumbs(folder, roots)` 从当前文件夹路径 + roots 推导面包屑分段。
- `frontend/src/platform/LibraryPage.tsx` — 加 `currentFolder` 状态与浏览/搜索双模式渲染（面包屑、文件夹卡、模式切换、管理行仅首页）。
- `frontend/src/theme/components.css` — 新增 `.library-breadcrumb`、`.library-folders`、`.library-folder-card` 样式。
- 测试：`tests/test_library_store.py`、`tests/test_gui_server.py`、`frontend/src/platform/libraryFolderPath.test.ts`、`frontend/src/platform/LibraryPage.test.tsx`。

---

## Task 1: `browse_folder` 存储层

**Files:**
- Modify: `looklift/library_store.py`（新增 dataclass + `browse_folder`；`_query_items` 增参）
- Test: `tests/test_library_store.py`

**Interfaces:**
- Consumes: 现有 `LibraryStore._connect`、`_query_items`、`LibraryItem`、`add_root`、`scan_root`。
- Produces:
  - `FolderEntry(name: str, path: str, count: int, cover_item_id: str | None)`（frozen dataclass）
  - `FolderView(folders: tuple[FolderEntry, ...], items: tuple[LibraryItem, ...], total: int, page: int, page_size: int)`（frozen dataclass）
  - `LibraryStore.browse_folder(self, folder: str | None, *, page: int = 1, page_size: int = 48) -> FolderView`
  - `_query_items` 新签名新增末位关键字参 `item_ids: list[str] | None = None`（`None`=不按 id 过滤；空列表=返回空）。

- [ ] **Step 1: 写失败测试——首页节点列出各 root**

在 `tests/test_library_store.py` 末尾追加：

```python
from looklift.library_store import FolderEntry, FolderView  # 顶部已有其它 import，可合并


def _seed(tmp_path):
    root = tmp_path / "照片"
    (root / "2024" / "云南" / "大理").mkdir(parents=True)
    (root / "2024" / "云南" / "丽江").mkdir(parents=True)
    (root / "散图").mkdir(parents=True)
    (root / "2024" / "云南" / "大理" / "a.jpg").write_bytes(b"jpeg")
    (root / "2024" / "云南" / "大理" / "b.jpg").write_bytes(b"jpeg")
    (root / "2024" / "云南" / "丽江" / "c.jpg").write_bytes(b"jpeg")
    (root / "散图" / "d.jpg").write_bytes(b"jpeg")
    (root / "顶层.jpg").write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")
    added = store.add_root(root)
    store.scan_root(added.id)
    return store, str(root)


def test_browse_folder_home_lists_roots_with_counts(tmp_path):
    store, root = _seed(tmp_path)
    view = store.browse_folder(None)
    assert [(f.name, f.count) for f in view.folders] == [("照片", 5)]
    assert view.folders[0].path == root
    assert view.folders[0].cover_item_id is not None
    assert view.items == ()
    assert view.total == 0
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_library_store.py::test_browse_folder_home_lists_roots_with_counts -v`
Expected: FAIL（`ImportError: cannot import name 'FolderEntry'` 或 `AttributeError: 'LibraryStore' object has no attribute 'browse_folder'`）

- [ ] **Step 3: 加 dataclass + `_query_items` 增参 + `browse_folder` 首页分支**

在 `library_store.py` 的 dataclass 区（`LibraryPage` 之后）追加：

```python
@dataclass(frozen=True)
class FolderEntry:
    name: str
    path: str
    count: int
    cover_item_id: str | None


@dataclass(frozen=True)
class FolderView:
    folders: tuple[FolderEntry, ...]
    items: tuple[LibraryItem, ...]
    total: int
    page: int
    page_size: int
```

修改 `_query_items` 签名与 WHERE 拼接，增加按 id 集合过滤（放在 `item_id` 处理之后）：

```python
    def _query_items(self, keyword: str, tag: str, *, limit: int | None, offset: int,
                     item_id: str | None = None, item_ids: list[str] | None = None) -> tuple[LibraryItem, ...]:
        clauses, values = self._filters(keyword, tag)
        if item_id is not None:
            clauses.append("items.id = ?")
            values.append(item_id)
        if item_ids is not None:
            if not item_ids:
                return ()
            clauses.append(f"items.id IN ({','.join('?' for _ in item_ids)})")
            values.extend(item_ids)
```

（该方法其余部分不变。）

在 `get_item` 之后新增：

```python
    def browse_folder(self, folder: str | None, *, page: int = 1, page_size: int = 48) -> FolderView:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page 必须是正整数")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ValueError("page_size 必须是 1 到 100 的整数")
        with self._connect() as connection:
            roots = connection.execute("SELECT id, path FROM library_roots ORDER BY path COLLATE NOCASE").fetchall()
            if folder is None:
                folders = tuple(self._root_folder_entry(connection, row) for row in roots)
                return FolderView(folders, (), 0, page, page_size)
            base = Path(folder)
            if not any(base == Path(r["path"]) or base.is_relative_to(Path(r["path"])) for r in roots):
                return FolderView((), (), 0, page, page_size)
            rows = connection.execute(
                "SELECT id, path, thumbnail_path FROM library_items WHERE path LIKE ? ESCAPE '\\'",
                (self._like_prefix(base),),
            ).fetchall()
        return self._folder_view_from_rows(base, rows, page, page_size)
```

新增三个辅助（放在 `browse_folder` 之后）：

```python
    @staticmethod
    def _like_prefix(base: Path) -> str:
        prefix = str(base) + os.sep
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return escaped + "%"

    def _root_folder_entry(self, connection, row) -> FolderEntry:
        items = connection.execute(
            "SELECT id, thumbnail_path FROM library_items WHERE root_id = ?", (row["id"],)
        ).fetchall()
        cover = next((i["id"] for i in items if i["thumbnail_path"]), items[0]["id"] if items else None)
        return FolderEntry(Path(row["path"]).name, row["path"], len(items), cover)

    def _folder_view_from_rows(self, base: Path, rows, page: int, page_size: int) -> FolderView:
        direct_files: list[str] = []
        groups: dict[str, dict] = {}
        for row in rows:
            rel = Path(row["path"]).relative_to(base)
            if len(rel.parts) == 1:
                direct_files.append(row["id"])
                continue
            segment = rel.parts[0]
            group = groups.setdefault(segment, {"count": 0, "cover": None, "cover_has_thumb": False})
            group["count"] += 1
            if group["cover"] is None or (row["thumbnail_path"] and not group["cover_has_thumb"]):
                group["cover"] = row["id"]
                group["cover_has_thumb"] = bool(row["thumbnail_path"])
        folders = tuple(
            FolderEntry(name, str(base / name), data["count"], data["cover"])
            for name, data in sorted(groups.items(), key=lambda kv: kv[0].casefold())
        )
        total = len(direct_files)
        items = self._query_items("", "", limit=page_size, offset=(page - 1) * page_size, item_ids=direct_files)
        return FolderView(folders, items, total, page, page_size)
```

顶部确认 `import os`（若无则加）。

- [ ] **Step 4: 运行验证首页测试通过**

Run: `python -m pytest tests/test_library_store.py::test_browse_folder_home_lists_roots_with_counts -v`
Expected: PASS

- [ ] **Step 5: 补钻进/嵌套/无效路径/分页测试**

追加：

```python
def test_browse_folder_drills_into_subfolders_and_direct_files(tmp_path):
    store, root = _seed(tmp_path)
    view = store.browse_folder(root)
    # 顶层：子文件夹 2024(3)+散图(1)，本层直接文件 顶层.jpg
    assert sorted((f.name, f.count) for f in view.folders) == [("2024", 3), ("散图", 1)]
    assert [i.display_name for i in view.items] == ["顶层.jpg"]
    assert view.total == 1
    # 再钻两层到大理，两张直接文件、无子文件夹
    dali = next(f for f in store.browse_folder(str(Path(root) / "2024" / "云南")).folders if f.name == "大理")
    leaf = store.browse_folder(dali.path)
    assert leaf.folders == ()
    assert [i.display_name for i in leaf.items] == ["a.jpg", "b.jpg"]


def test_browse_folder_paginates_direct_files_only(tmp_path):
    root = tmp_path / "照片"
    root.mkdir()
    for name in ("1.jpg", "2.jpg", "3.jpg"):
        (root / name).write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")
    added = store.add_root(root)
    store.scan_root(added.id)
    page1 = store.browse_folder(str(root), page=1, page_size=2)
    assert [i.display_name for i in page1.items] == ["1.jpg", "2.jpg"]
    assert page1.total == 3
    page2 = store.browse_folder(str(root), page=2, page_size=2)
    assert [i.display_name for i in page2.items] == ["3.jpg"]


def test_browse_folder_rejects_path_outside_roots(tmp_path):
    store, _ = _seed(tmp_path)
    view = store.browse_folder(str(tmp_path / "库外目录"))
    assert view == FolderView((), (), 0, 1, 48)
```

- [ ] **Step 6: 运行整组测试通过**

Run: `python -m pytest tests/test_library_store.py -v`
Expected: PASS（含既有测试，全绿）

- [ ] **Step 7: Commit**

```bash
git add looklift/library_store.py tests/test_library_store.py
git commit -m "feat(v2.3): 图库存储层新增 browse_folder 文件夹推导"
```

---

## Task 2: `/api/library/folder` 路由

**Files:**
- Modify: `looklift/gui/api.py`（新增 `_get_library_folder`，注册路由）
- Test: `tests/test_gui_server.py`

**Interfaces:**
- Consumes: `LibraryStore.browse_folder`（Task 1）、现有 `_library_item_payload`、`SessionStore().summaries_for_paths`。
- Produces: 路由 `("GET", "/api/library/folder")`。响应形状：
  `{"folders": [{"name", "path", "count", "cover_item_id"}], "items": [<library item payload>], "total", "page", "page_size"}`。

- [ ] **Step 1: 写失败测试**

先看 `tests/test_gui_server.py` 里既有 `/api/library/items` 测试怎么起 server 与发请求，仿照其风格。追加（把 `<helpers>` 换成该文件既有的建 store/发请求辅助）：

```python
def test_library_folder_home_then_drill(tmp_path, <server helpers>):
    # 用既有辅助建库：root 下 顶层.jpg + 子目录/内层.jpg，扫描入库
    ...
    home = <GET>("/api/library/folder")
    assert home.status == 200
    assert [f["name"] for f in home.json["folders"]] == [<root 目录名>]
    assert home.json["items"] == []

    drilled = <GET>(f"/api/library/folder?path={quote(<root 绝对路径>)}")
    assert {f["name"] for f in drilled.json["folders"]} == {"子目录"}
    assert [i["display_name"] for i in drilled.json["items"]] == ["顶层.jpg"]
    assert drilled.json["total"] == 1


def test_library_folder_rejects_bad_pagination(<server helpers>):
    resp = <GET>("/api/library/folder?page=0")
    assert resp.status == 400
    assert "分页参数无效" in resp.json["error"]
```

- [ ] **Step 2: 运行验证失败**

Run: `python -m pytest tests/test_gui_server.py -k library_folder -v`
Expected: FAIL（404 未知路由，或断言不满足）

- [ ] **Step 3: 实现 handler 并注册路由**

在 `api.py` 的 `_get_library_items` 之后新增：

```python
def _get_library_folder(ctx: dict) -> tuple[int, dict]:
    query = ctx.get("query", {})
    folder = query.get("path") or None
    try:
        page = int(query.get("page", "1"))
        page_size = int(query.get("page_size", "48"))
        view = LibraryStore().browse_folder(folder, page=page, page_size=page_size)
    except (TypeError, ValueError):
        return 400, {"error": "分页参数无效：page 从 1 开始，page_size 范围为 1 到 100"}
    try:
        sessions = SessionStore().summaries_for_paths([item.path for item in view.items])
    except (OSError, DatabaseRecoveryRequired):
        sessions = {}
    return 200, {
        "folders": [
            {"name": f.name, "path": f.path, "count": f.count, "cover_item_id": f.cover_item_id}
            for f in view.folders
        ],
        "items": [_library_item_payload(item, sessions.get(item.path)) for item in view.items],
        "total": view.total,
        "page": view.page,
        "page_size": view.page_size,
    }
```

在 `ROUTES` 里紧邻 `/api/library/items` 注册：

```python
    ("GET", "/api/library/folder"): _get_library_folder,
```

- [ ] **Step 4: 运行验证通过**

Run: `python -m pytest tests/test_gui_server.py -k library_folder -v`
Expected: PASS

- [ ] **Step 5: 跑完整 server 测试确认无回归**

Run: `python -m pytest tests/test_gui_server.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add looklift/gui/api.py tests/test_gui_server.py
git commit -m "feat(v2.3): 新增 GET /api/library/folder 路由"
```

---

## Task 3: 前端 types + client 方法

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: 现有 `LibraryItem` 类型、`LookliftClient.json`。
- Produces:
  - `LibraryFolderEntry = { name: string; path: string; count: number; cover_item_id: string | null }`
  - `LibraryFolderView = { folders: LibraryFolderEntry[]; items: LibraryItem[]; total: number; page: number; page_size: number }`
  - `LookliftClient.libraryFolder(path: string | null, page?: number, pageSize?: number): Promise<LibraryFolderView>`

- [ ] **Step 1: 加类型**

在 `types.ts` 的 `LibraryItemsPage` 定义之后追加：

```typescript
export type LibraryFolderEntry = { name: string; path: string; count: number; cover_item_id: string | null };
export type LibraryFolderView = {
  folders: LibraryFolderEntry[];
  items: LibraryItem[];
  total: number;
  page: number;
  page_size: number;
};
```

- [ ] **Step 2: 加 client 方法**

在 `client.ts` 顶部类型 import 里加入 `LibraryFolderView`（与 `LibraryItemsPage` 同组）。在 `libraryItems` 方法之后新增：

```typescript
  libraryFolder(path: string | null, page = 1, pageSize = 48): Promise<LibraryFolderView> {
    const pathQuery = path === null ? "" : `path=${encodeURIComponent(path)}&`;
    return this.json(`/api/library/folder?${pathQuery}page=${page}&page_size=${pageSize}`);
  }
```

- [ ] **Step 3: 类型检查 + 构建通过**

Run: `cd frontend && npm run build`
Expected: 无 TS 报错，构建成功

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts
git commit -m "feat(v2.3): 前端加 libraryFolder client 与类型"
```

---

## Task 4: 面包屑纯函数 `folderCrumbs`

**Files:**
- Create: `frontend/src/platform/libraryFolderPath.ts`
- Test: `frontend/src/platform/libraryFolderPath.test.ts`

**Interfaces:**
- Consumes: `LibraryRoot`（`{ id: string; path: string }`）、`LibraryFolderEntry`。
- Produces:
  - `type Crumb = { label: string; path: string | null }`（`path === null` 代表「首页」）
  - `folderCrumbs(folder: string | null, roots: LibraryRoot[]): Crumb[]`
  - 首段永远是 `{ label: "首页", path: null }`；`folder === null` 时只返回该首段。
  - 当 `folder` 落在某 root 内：其后依次是「root 目录名 →…→ 当前目录名」，每段 `path` 是可点回退的绝对路径。root 段的 `path` 为 root 绝对路径。
  - 当 `folder` 不属于任何 root：只返回首页段（安全兜底）。
  - 分隔符判定用 `/` 与 `\` 两种都切分（`str.split(/[\\/]/)`），因为存储路径为 Windows `\`，测试与浏览器里可能出现 `/`。

- [ ] **Step 1: 写失败测试**

```typescript
import { describe, expect, it } from "vitest";
import { folderCrumbs } from "./libraryFolderPath";

const roots = [{ id: "r1", path: "C:\\Users\\me\\照片" }];

describe("folderCrumbs", () => {
  it("首页只有首页段", () => {
    expect(folderCrumbs(null, roots)).toEqual([{ label: "首页", path: null }]);
  });

  it("钻进多层时按 root 目录名起、逐段可回退", () => {
    const crumbs = folderCrumbs("C:\\Users\\me\\照片\\2024\\云南", roots);
    expect(crumbs).toEqual([
      { label: "首页", path: null },
      { label: "照片", path: "C:\\Users\\me\\照片" },
      { label: "2024", path: "C:\\Users\\me\\照片\\2024" },
      { label: "云南", path: "C:\\Users\\me\\照片\\2024\\云南" },
    ]);
  });

  it("库外路径只回首页段", () => {
    expect(folderCrumbs("D:\\别处", roots)).toEqual([{ label: "首页", path: null }]);
  });
});
```

- [ ] **Step 2: 运行验证失败**

Run: `cd frontend && npx vitest run src/platform/libraryFolderPath.test.ts`
Expected: FAIL（`folderCrumbs` 不存在）

- [ ] **Step 3: 实现**

`frontend/src/platform/libraryFolderPath.ts`：

```typescript
import type { LibraryRoot } from "../api/types";

export type Crumb = { label: string; path: string | null };

const SEP = /[\\/]/;

export function folderCrumbs(folder: string | null, roots: LibraryRoot[]): Crumb[] {
  const home: Crumb = { label: "首页", path: null };
  if (folder === null) return [home];
  const root = roots.find((r) => folder === r.path || folder.startsWith(r.path + "\\") || folder.startsWith(r.path + "/"));
  if (!root) return [home];
  const sep = root.path.includes("\\") ? "\\" : "/";
  const rootSegments = root.path.split(SEP);
  const rootName = rootSegments[rootSegments.length - 1] || root.path;
  const crumbs: Crumb[] = [home, { label: rootName, path: root.path }];
  const rest = folder.slice(root.path.length).split(SEP).filter(Boolean);
  let acc = root.path;
  for (const segment of rest) {
    acc = acc + sep + segment;
    crumbs.push({ label: segment, path: acc });
  }
  return crumbs;
}
```

- [ ] **Step 4: 运行验证通过**

Run: `cd frontend && npx vitest run src/platform/libraryFolderPath.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/platform/libraryFolderPath.ts frontend/src/platform/libraryFolderPath.test.ts
git commit -m "feat(v2.3): 面包屑分段纯函数 folderCrumbs"
```

---

## Task 5: LibraryPage 浏览模式 UI

**Files:**
- Modify: `frontend/src/platform/LibraryPage.tsx`
- Modify: `frontend/src/theme/components.css`
- Test: `frontend/src/platform/LibraryPage.test.tsx`

**Interfaces:**
- Consumes: `client.libraryFolder`（Task 3）、`folderCrumbs`（Task 4）、`client.libraryThumbnail`、现有 `LibraryCard`、`client.libraryItems`、`client.libraryRoots`。
- Produces: 无对外新接口；`LibraryPage` 内部两种模式。测试通过组件行为验证。

- [ ] **Step 1: 写失败测试——浏览模式钻进与面包屑回退**

在 `LibraryPage.test.tsx` 追加（沿用文件顶部已有的 `changeInput`、`item` 夹具、`act` 模式）：

```typescript
it("默认浏览模式展示文件夹卡，点击钻进并可用面包屑回退", async () => {
  const libraryFolder = vi
    .fn()
    // 首页
    .mockResolvedValueOnce({
      folders: [{ name: "2024", path: "C:/图库/2024", count: 3, cover_item_id: null }],
      items: [], total: 0, page: 1, page_size: 48,
    })
    // 钻进 2024
    .mockResolvedValueOnce({
      folders: [{ name: "云南", path: "C:/图库/2024/云南", count: 2, cover_item_id: null }],
      items: [item], total: 1, page: 1, page_size: 48,
    })
    // 面包屑点“首页”回退
    .mockResolvedValueOnce({
      folders: [{ name: "2024", path: "C:/图库/2024", count: 3, cover_item_id: null }],
      items: [], total: 0, page: 1, page_size: 48,
    });
  const client = {
    libraryRoots: vi.fn().mockResolvedValue({ roots: [{ id: "r1", path: "C:/图库" }] }),
    libraryItems: vi.fn(),
    libraryFolder,
  };

  await act(async () => {
    root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
    await Promise.resolve(); await Promise.resolve();
  });
  expect(libraryFolder).toHaveBeenLastCalledWith(null, 1, 48);
  expect(container.textContent).toContain("2024");

  await act(async () => {
    (container.querySelector("button[data-folder='C:/图库/2024']") as HTMLButtonElement).click();
    await Promise.resolve(); await Promise.resolve();
  });
  expect(libraryFolder).toHaveBeenLastCalledWith("C:/图库/2024", 1, 48);
  expect(container.textContent).toContain("云南");

  await act(async () => {
    (container.querySelector("button[data-crumb='home']") as HTMLButtonElement).click();
    await Promise.resolve(); await Promise.resolve();
  });
  expect(libraryFolder).toHaveBeenLastCalledWith(null, 1, 48);
});

it("输入搜索词切到全库平铺，清空后回浏览模式", async () => {
  const libraryFolder = vi.fn().mockResolvedValue({ folders: [], items: [], total: 0, page: 1, page_size: 48 });
  const libraryItems = vi.fn().mockResolvedValue({ items: [item], total: 1, page: 1, page_size: 48 });
  const client = {
    libraryRoots: vi.fn().mockResolvedValue({ roots: [{ id: "r1", path: "C:/图库" }] }),
    libraryItems, libraryFolder,
  };
  await act(async () => {
    root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
    await Promise.resolve(); await Promise.resolve();
  });

  const inputs = container.querySelectorAll("input");
  await act(async () => {
    changeInput(inputs[1], "海边");
    container.querySelector("form[data-form='search']")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve(); await Promise.resolve();
  });
  expect(libraryItems).toHaveBeenLastCalledWith("海边", "", 1, 48);
  expect(container.textContent).toContain("海边.jpg");

  await act(async () => {
    changeInput(inputs[1], "");
    container.querySelector("form[data-form='search']")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await Promise.resolve(); await Promise.resolve();
  });
  expect(libraryFolder).toHaveBeenLastCalledWith(null, 1, 48);
});
```

同时把文件顶部第一处既有测试对 `client` 的构造补上 `libraryFolder`（那条测试直接进搜索态，`libraryFolder` 可给 `vi.fn().mockResolvedValue({ folders: [], items: [], total: 0, page: 1, page_size: 48 })`，避免初次浏览模式加载报错）。若既有测试初始无 root、也无搜索词，会触发一次浏览模式加载——给它加 `libraryFolder` mock 即可保持通过。

- [ ] **Step 2: 运行验证失败**

Run: `cd frontend && npx vitest run src/platform/LibraryPage.test.tsx`
Expected: FAIL（`libraryFolder is not a function` 或找不到 `button[data-folder=...]`）

- [ ] **Step 3: 改 LibraryPage —— 状态与加载分流**

在 `LibraryPage.tsx` 顶部 import 加：

```typescript
import type { LibraryItem, LibraryFolderEntry, LibraryRoot, LibraryScanTask } from "../api/types";
import { folderCrumbs } from "./libraryFolderPath";
```

在状态区（`filters` 附近）新增：

```typescript
  const [currentFolder, setCurrentFolder] = useState<string | null>(null);
  const [folders, setFolders] = useState<LibraryFolderEntry[]>([]);
```

新增一个「浏览模式」判定与加载函数（放在 `loadItems` 之后）：

```typescript
  const browsing = !filters.keyword && !filters.tag;

  const loadFolder = async (folder: string | null, nextPage = 1) => {
    const view = await client.libraryFolder(folder, nextPage, PAGE_SIZE);
    setFolders(view.folders);
    setItems(view.items);
    setTotal(view.total);
    setPage(view.page);
    setCurrentFolder(folder);
  };
```

把 `refresh` 改为按模式分流（替换现有 `refresh`）：

```typescript
  const refresh = async (nextPage = page, nextFilters = filters) => {
    setError("");
    const browsingNow = !nextFilters.keyword && !nextFilters.tag;
    const [rootResult] = await Promise.all([
      client.libraryRoots(),
      browsingNow ? loadFolder(currentFolder, nextPage) : loadItems(nextPage, nextFilters),
    ]);
    setRoots(rootResult.roots);
  };
```

初次加载的 `useEffect` 已调用 `refresh(1, { keyword: "", tag: "" })`——浏览态下会走 `loadFolder(null, 1)`，符合预期，无需改。

- [ ] **Step 4: 改 `search` —— 模式切换**

替换 `search`：

```typescript
  const search = async (event: FormEvent) => {
    event.preventDefault();
    const nextFilters = { keyword: keywordInput.trim(), tag: tagInput.trim() };
    setFilters(nextFilters);
    try {
      if (!nextFilters.keyword && !nextFilters.tag) {
        await loadFolder(currentFolder, 1);
      } else {
        await loadItems(1, nextFilters);
      }
    } catch (reason) {
      setError(message(reason, "图库搜索失败"));
    }
  };
```

新增文件夹钻进与面包屑回退处理（放在 `search` 之后）：

```typescript
  const openFolder = async (folder: string | null) => {
    try {
      await loadFolder(folder, 1);
    } catch (reason) {
      setError(message(reason, "图库读取失败"));
    }
  };
```

- [ ] **Step 5: 改 `changePage` —— 浏览态翻页走 loadFolder**

替换 `changePage`：

```typescript
  const changePage = async (nextPage: number) => {
    try {
      if (browsing) await loadFolder(currentFolder, nextPage);
      else await loadItems(nextPage);
    } catch (reason) {
      setError(message(reason, "图库翻页失败"));
    }
  };
```

- [ ] **Step 6: 改渲染 —— 面包屑、文件夹卡、管理行仅首页**

把管理行 `library-roots` 的外层条件改为「浏览态且在首页」：

```tsx
      {browsing && currentFolder === null && roots.length > 0 && <section className="library-roots" aria-label="索引文件夹">
```

在 `error`/`status` 提示之后、`library-grid` 之前插入面包屑与文件夹卡（仅浏览态）：

```tsx
      {browsing && <nav className="library-breadcrumb" aria-label="文件夹路径">
        {folderCrumbs(currentFolder, roots).map((crumb, index, all) => {
          const isLast = index === all.length - 1;
          return isLast
            ? <span key={crumb.path ?? "home"} aria-current="page">{crumb.label}</span>
            : <button
                key={crumb.path ?? "home"}
                type="button"
                data-crumb={crumb.path === null ? "home" : crumb.path}
                onClick={() => void openFolder(crumb.path)}
              >{crumb.label}</button>;
        })}
      </nav>}

      {browsing && folders.length > 0 && <section className="library-folders" aria-label="子文件夹">
        {folders.map((folder) => <button
          key={folder.path}
          type="button"
          className="library-folder-card"
          data-folder={folder.path}
          onClick={() => void openFolder(folder.path)}
        >
          <span className="library-folder-name" title={folder.path}>📁 {folder.name}</span>
          <span className="library-folder-count">{folder.count} 张</span>
        </button>)}
      </section>}
```

（文件夹封面缩略图为增量优化，可后续接 `client.libraryThumbnail(cover_item_id)`；本任务先落名字 + 数量角标，`cover_item_id` 已在数据里备好，不阻塞。）

空态判断维持：浏览态若既无子文件夹又无本层照片，仍显示现有「没有符合条件的照片」。把该空态条件放宽为 `items.length === 0 && folders.length === 0`：

```tsx
      {loading ? <p className="library-empty">正在读取图库…</p> : items.length === 0 && folders.length === 0 ? <p className="library-empty">没有符合条件的照片</p> : <div className="library-grid">
```

- [ ] **Step 7: 加样式**

在 `frontend/src/theme/components.css` 末尾（`.library-*` 区域附近）追加：

```css
.library-breadcrumb { display: flex; flex-wrap: wrap; align-items: center; gap: 0.25rem; margin: 0.5rem 0; font-size: 0.9rem; }
.library-breadcrumb button { background: none; border: none; padding: 0.1rem 0.3rem; color: var(--accent, #b45309); cursor: pointer; }
.library-breadcrumb button:hover { text-decoration: underline; }
.library-breadcrumb span[aria-current="page"] { font-weight: 600; }
.library-breadcrumb > :not(:last-child)::after { content: "›"; margin-left: 0.25rem; color: #9ca3af; }
.library-folders { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0.75rem; margin-bottom: 1rem; }
.library-folder-card { display: flex; flex-direction: column; gap: 0.35rem; padding: 0.9rem; text-align: left; border: 1px solid var(--border, #e5e7eb); border-radius: 0.6rem; background: var(--surface, #fff); cursor: pointer; }
.library-folder-card:hover { border-color: var(--accent, #b45309); }
.library-folder-name { font-weight: 600; }
.library-folder-count { font-size: 0.8rem; color: #6b7280; }
```

（若 `components.css` 已定义 `--accent`/`--border`/`--surface` 变量则复用；未定义时上面的回退色生效。）

- [ ] **Step 8: 运行前端测试通过**

Run: `cd frontend && npx vitest run src/platform/LibraryPage.test.tsx src/platform/libraryFolderPath.test.ts`
Expected: PASS

- [ ] **Step 9: 全量前端测试 + 构建无回归**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 全绿，构建成功

- [ ] **Step 10: Commit**

```bash
git add frontend/src/platform/LibraryPage.tsx frontend/src/theme/components.css frontend/src/platform/LibraryPage.test.tsx
git commit -m "feat(v2.3): 图库改为文件夹钻进 + 面包屑导航"
```

---

## Self-Review Notes

- **Spec 覆盖**：核心思路（路径推导，Task 1）、后端 `browse_folder` 三段返回 + 首页节点 + 无效 path 空视图（Task 1）、`/api/library/folder` 路由（Task 2）、client + types（Task 3）、面包屑（Task 4）、浏览/搜索双模式 + 管理行仅首页 + 分页仅本层照片（Task 5）均有对应任务。封面 `cover_item_id` 已贯穿数据链路，前端渲染留作增量（Step 6 说明），不阻塞闭环。
- **类型一致**：`FolderEntry`/`FolderView`（Py）与 `LibraryFolderEntry`/`LibraryFolderView`（TS）字段逐一对应（name/path/count/cover_item_id、folders/items/total/page/page_size）；`libraryFolder(path, page, pageSize)` 签名在 Task 3 定义、Task 5 按 `(null, 1, 48)` 调用一致。
- **无占位符**：各步给出完整代码与命令；Task 2 测试因 server 测试脚手架因文件而异，以 `<server helpers>` 显式标注需照抄既有 `/api/library/items` 测试的建库/发请求方式（该文件既有模式即事实来源）。
