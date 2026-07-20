// @vitest-environment happy-dom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionSummary } from "../api/types";
import { HomePage } from "./HomePage";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const sessions: SessionSummary[] = [
  { id: "s1", display_name: "可恢复.jpg", updated_at: "2026-07-20T02:00:00Z", current_version_id: "v1", summary: "柔和暖调", source_available: true },
  { id: "s2", display_name: "已移动.jpg", updated_at: "2026-07-20T01:00:00Z", current_version_id: "v2", summary: "清透", source_available: false },
];

describe("HomePage", () => {
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
  });

  it("展示真实开始入口并只允许恢复存在的源文件", async () => {
    const client = { recentSessions: vi.fn().mockResolvedValue(sessions) };
    const onResume = vi.fn();
    const onQuickEdit = vi.fn();
    const onFuture = vi.fn();

    await act(async () => {
      root.render(<HomePage client={client} onResume={onResume} onQuickEdit={onQuickEdit} onFuture={onFuture} />);
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(container.textContent).toContain("今天想修哪组照片？");
    expect(container.textContent).toContain("添加文件夹");
    expect(container.textContent).toContain("从设备导入");
    expect(container.textContent).toContain("快速修图");
    expect(container.textContent).toContain("柔和暖调");
    expect(container.textContent).toContain("源文件不可用");

    const buttons = [...container.querySelectorAll("button")];
    await act(async () => {
      buttons.find((button) => button.textContent?.includes("快速修图"))?.click();
      buttons.find((button) => button.textContent?.includes("添加文件夹"))?.click();
      buttons.find((button) => button.textContent?.includes("继续 可恢复.jpg"))?.click();
      await Promise.resolve();
    });

    expect(onQuickEdit).toHaveBeenCalledTimes(1);
    expect(onFuture).toHaveBeenCalledWith("folder");
    expect(onResume).toHaveBeenCalledWith("s1");
    expect(buttons.find((button) => button.textContent?.includes("已移动.jpg"))?.disabled).toBe(true);
  });

  it("最近会话失败时保留开始入口并允许重试", async () => {
    const recentSessions = vi.fn()
      .mockRejectedValueOnce(new Error("数据库忙"))
      .mockResolvedValueOnce([]);

    await act(async () => {
      root.render(<HomePage client={{ recentSessions }} onResume={vi.fn()} onQuickEdit={vi.fn()} onFuture={vi.fn()} />);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(container.textContent).toContain("最近会话载入失败");
    expect(container.textContent).toContain("快速修图");

    await act(async () => {
      (container.querySelector("button[data-action='retry-sessions']") as HTMLButtonElement).click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(recentSessions).toHaveBeenCalledTimes(2);
    expect(container.textContent).toContain("还没有可继续的正式会话");
  });
});
