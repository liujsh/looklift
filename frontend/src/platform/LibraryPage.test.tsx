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
    const client = { libraryRoots: vi.fn().mockResolvedValue({ roots: [] }), libraryItems };

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

  it("缺失文件禁用 Studio 和定位入口", async () => {
    const missing = { ...item, available: false };
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [] }),
      libraryItems: vi.fn().mockResolvedValue({ items: [missing], total: 1, page: 1, page_size: 48 }),
    };

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    const disabled = [...container.querySelectorAll("button")]
      .filter((button) => button.textContent?.includes("Studio") || button.textContent?.includes("定位文件"));
    expect(disabled).toHaveLength(2);
    expect(disabled.every((button) => button.disabled)).toBe(true);
  });

  it("通过项目 ID 定位文件并保存标签", async () => {
    const setLibraryTags = vi.fn().mockResolvedValue({ ok: true });
    const revealLibraryItem = vi.fn().mockResolvedValue({ ok: true });
    const client = {
      libraryRoots: vi.fn().mockResolvedValue({ roots: [] }),
      libraryItems: vi.fn().mockResolvedValue({ items: [item], total: 1, page: 1, page_size: 48 }),
      setLibraryTags,
      revealLibraryItem,
    };
    vi.stubGlobal("prompt", vi.fn().mockReturnValue("纪实, 夜景"));

    await act(async () => {
      root.render(<LibraryPage client={client as unknown as LookliftClient} onOpen={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });
    const buttons = [...container.querySelectorAll("button")];
    await act(async () => {
      buttons.find((button) => button.textContent?.includes("定位文件"))?.click();
      buttons.find((button) => button.textContent?.includes("编辑标签"))?.click();
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
});
