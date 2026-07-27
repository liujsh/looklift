// @vitest-environment happy-dom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LibraryItem } from "../api/types";
import type { LookliftClient } from "../api/client";
import { LibraryPage } from "./LibraryPage";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const item: LibraryItem = {
  id: "item-1", path: "C:/图库/海边.jpg", display_name: "海边.jpg", available: true,
  thumbnail_path: null, file_size: 2048, modified_ns: 1, width: 80, height: 40,
  file_format: "JPEG", metadata: { iso: 200 }, tags: ["旅行", "胶片"], export_count: 2,
  last_export_at: "2026-07-21T00:00:00Z", session_id: "session-1", current_version_id: "version-1",
  current_summary: "柔和暖调",
};

function changeInput(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
  setter?.call(input, value);
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

describe("LibraryPage", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("展示标签、文件信息、当前版本和导出摘要，并执行分页搜索", async () => {
    const libraryItems = vi.fn().mockResolvedValue({ items: [item], total: 49, page: 1, page_size: 48 });
    const libraryFolder = vi.fn().mockResolvedValue({ folders: [], items: [item], total: 49, page: 1, page_size: 48 });
    const client = { libraryRoots: vi.fn().mockResolvedValue({ roots: [] }), libraryItems, libraryFolder };

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("旅行");
    expect(container.textContent).toContain("80 × 40");
    expect(container.textContent).toContain("ISO 200");
    expect(container.textContent).toContain("柔和暖调");
    expect(container.textContent).toContain("已导出 2 次");

    const inputs = container.querySelectorAll("input");
    await act(async () => {
      changeInput(inputs[1], "海边");
      changeInput(inputs[2], "旅行");
      container.querySelector("form[data-form='search']")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(libraryItems).toHaveBeenLastCalledWith("海边", "旅行", 1, 48);

    await act(async () => {
      (container.querySelector("button[data-action='next-page']") as HTMLButtonElement).click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(libraryItems).toHaveBeenLastCalledWith("海边", "旅行", 2, 48);
  });

  it("通过鉴权客户端加载缩略图，空摘要显示稳定的已编辑标识", async () => {
    vi.stubGlobal("URL", {
      createObjectURL: vi.fn(() => "blob:library-thumbnail"),
      revokeObjectURL: vi.fn(),
    });
    const thumbnailItem = {
      ...item,
      thumbnail_path: "C:/用户数据/thumbnails/item.jpg",
      current_summary: "",
    };
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [] }),
      libraryItems: vi.fn().mockResolvedValue({
        items: [thumbnailItem], total: 1, page: 1, page_size: 48,
      }),
      libraryFolder: vi.fn().mockResolvedValue({
        folders: [], items: [thumbnailItem], total: 1, page: 1, page_size: 48,
      }),
      libraryThumbnail: vi.fn().mockResolvedValue(
        new Blob(["thumbnail"], { type: "image/jpeg" }),
      ),
    };

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(client.libraryThumbnail).toHaveBeenCalledWith("item-1", expect.any(AbortSignal));
    expect(container.querySelector("img")?.getAttribute("src")).toBe("blob:library-thumbnail");
    expect(container.textContent).toContain("当前版本 · 已建立 Studio 会话");
  });

  it("缺失文件禁用 Studio 和定位入口", async () => {
    const missing = { ...item, available: false };
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [] }),
      libraryItems: vi.fn().mockResolvedValue({ items: [missing], total: 1, page: 1, page_size: 48 }),
      libraryFolder: vi.fn().mockResolvedValue({ folders: [], items: [missing], total: 1, page: 1, page_size: 48 }),
    };

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const disabled = [...container.querySelectorAll("button")]
      .filter((button) => ["进入 Studio", "定位文件"].includes(button.getAttribute("aria-label") ?? ""));
    expect(disabled).toHaveLength(2);
    expect(disabled.every((button) => button.disabled)).toBe(true);
  });

  it("通过项目 ID 定位文件并保存标签", async () => {
    const setLibraryTags = vi.fn().mockResolvedValue({ ok: true });
    const revealLibraryItem = vi.fn().mockResolvedValue({ ok: true });
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [] }),
      libraryItems: vi.fn().mockResolvedValue({ items: [item], total: 1, page: 1, page_size: 48 }),
      libraryFolder: vi.fn().mockResolvedValue({ folders: [], items: [item], total: 1, page: 1, page_size: 48 }),
      setLibraryTags,
      revealLibraryItem,
    };
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("纪实, 夜景"));

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const byLabel = (label: string) => [...container.querySelectorAll("button")]
      .find((button) => button.getAttribute("aria-label") === label);
    await act(async () => {
      byLabel("定位文件")?.click();
      byLabel("编辑标签")?.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(revealLibraryItem).toHaveBeenCalledWith("item-1");
    expect(setLibraryTags).toHaveBeenCalledWith("item-1", ["纪实", " 夜景"]);
  });

  it("添加根目录后启动后台扫描并在终态刷新", async () => {
    const emptyPage = { items: [], total: 0, page: 1, page_size: 48 };
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [] }),
      libraryItems: vi.fn().mockResolvedValue(emptyPage),
      libraryFolder: vi.fn().mockResolvedValue({ folders: [], ...emptyPage }),
      addLibraryRoot: vi.fn().mockResolvedValue({ id: "root-1", path: "C:/图库" }),
      scanLibraryRoot: vi.fn().mockResolvedValue({ task_id: "scan-1" }),
      libraryScan: vi.fn().mockResolvedValue({
        status: "done", message: null, result: { added: 3, updated: 0, missing: 0 },
        error: null, scanned: 3, current: null,
      }),
      cancelLibraryScan: vi.fn(),
    };

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const pathInput = container.querySelector("input") as HTMLInputElement;
    await act(async () => {
      changeInput(pathInput, "C:/图库");
      container.querySelector("form[data-form='add-root']")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(client.addLibraryRoot).toHaveBeenCalledWith("C:/图库");
    expect(client.scanLibraryRoot).toHaveBeenCalledWith("root-1");
    expect(client.libraryScan).toHaveBeenCalledWith("scan-1");
    expect(container.textContent).toContain("扫描完成：新增 3");
  });

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

  it("浏览模式下编辑标签保存后按文件夹视图刷新，不误触全库平铺", async () => {
    const libraryFolder = vi.fn().mockResolvedValue({
      folders: [], items: [item], total: 1, page: 1, page_size: 48,
    });
    const libraryItems = vi.fn();
    const setLibraryTags = vi.fn().mockResolvedValue({ ok: true });
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [{ id: "r1", path: "C:/图库" }] }),
      libraryItems,
      libraryFolder,
      setLibraryTags,
    };
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("纪实, 夜景"));

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve(); await Promise.resolve();
    });

    await act(async () => {
      [...container.querySelectorAll("button")]
        .find((button) => button.getAttribute("aria-label") === "编辑标签")?.click();
      await Promise.resolve(); await Promise.resolve();
    });

    expect(setLibraryTags).toHaveBeenCalledWith("item-1", ["纪实", " 夜景"]);
    expect(libraryFolder).toHaveBeenLastCalledWith(null, 1, 48);
    expect(libraryItems).not.toHaveBeenCalled();
  });

  it("文件夹已加载后搜索无结果时显示空态提示", async () => {
    const libraryFolder = vi.fn().mockResolvedValue({
      folders: [{ name: "2024", path: "C:/图库/2024", count: 3, cover_item_id: null }],
      items: [item], total: 1, page: 1, page_size: 48,
    });
    const libraryItems = vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 48 });
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [{ id: "r1", path: "C:/图库" }] }),
      libraryItems, libraryFolder,
    };

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve(); await Promise.resolve();
    });
    expect(container.textContent).toContain("2024");

    const inputs = container.querySelectorAll("input");
    await act(async () => {
      changeInput(inputs[1], "不存在的关键字");
      container.querySelector("form[data-form='search']")?.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
      await Promise.resolve(); await Promise.resolve();
    });

    expect(libraryItems).toHaveBeenLastCalledWith("不存在的关键字", "", 1, 48);
    expect(container.textContent).toContain("没有符合条件的照片");
  });
});
