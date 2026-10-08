// @vitest-environment happy-dom
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { PluginActionSummary } from "../api/types";
import { PluginActions } from "./PluginActions";

const pending: PluginActionSummary = {
  action_id: "action-1",
  project_id: "project-a",
  plugin_identity: "redbook@1.0.0/main/publish",
  account_id: "work",
  arguments: { title: "初稿", visibility: "公开" },
  asset_hashes: ["b".repeat(64)],
  state: "pending_confirmation",
  revision: 1,
  expires_at: 2_000_000_000,
  result: null,
  created_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
  confirmation_fields: [
    { key: "title", label: "标题", control: "text", options: [] },
    { key: "visibility", label: "可见范围", control: "select", options: ["公开", "仅自己"] },
  ],
};

describe("PluginActions", () => {
  let container: HTMLDivElement;
  let root: ReturnType<typeof createRoot>;

  beforeEach(() => {
    (globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
  });

  function client(overrides = {}) {
    return {
      pluginActions: vi.fn().mockResolvedValue([pending]),
      revisePluginAction: vi.fn().mockResolvedValue({ ...pending, arguments: { ...pending.arguments, title: "最终稿" }, revision: 2 }),
      confirmPluginAction: vi.fn().mockResolvedValue({ ...pending, state: "succeeded", revision: 2, result: { url: "https://example.invalid/post/1" } }),
      rejectPluginAction: vi.fn().mockResolvedValue({ ...pending, state: "rejected" }),
      cancelPluginAction: vi.fn(),
      ...overrides,
    } as unknown as LookliftClient;
  }

  async function fill(input: HTMLInputElement, value: string) {
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value);
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  }

  it("展示宿主可信事实和声明式字段", async () => {
    const current = client();
    await act(async () => root.render(<PluginActions client={current} projectId="project-a" />));

    await vi.waitFor(() => expect(container.textContent).toContain("待你确认"));
    expect(current.pluginActions).toHaveBeenCalledWith("project-a");
    expect(container.textContent).toContain("work");
    expect(container.textContent).toContain("1 张图片");
    expect(container.querySelector('input[name="title"]')).not.toBeNull();
    expect(container.querySelector('select[name="visibility"]')).not.toBeNull();
  });

  it("修改后使用新 revision 确认执行", async () => {
    const revisePluginAction = vi.fn().mockResolvedValue({ ...pending, arguments: { ...pending.arguments, title: "最终稿" }, revision: 2 });
    const confirmPluginAction = vi.fn().mockResolvedValue({ ...pending, state: "succeeded", revision: 2, result: { ok: true } });
    const current = client({ revisePluginAction, confirmPluginAction });
    await act(async () => root.render(<PluginActions client={current} projectId="project-a" />));
    await vi.waitFor(() => expect(container.querySelector('input[name="title"]')).not.toBeNull());

    await fill(container.querySelector('input[name="title"]') as HTMLInputElement, "最终稿");
    const confirm = [...container.querySelectorAll("button")].find((item) => item.textContent === "确认并执行")!;
    expect(confirm.disabled).toBe(true);
    const save = [...container.querySelectorAll("button")].find((item) => item.textContent === "保存修改")!;
    await act(async () => save.click());
    await vi.waitFor(() => expect(revisePluginAction).toHaveBeenCalledWith(
      "action-1", "project-a", 1, { title: "最终稿", visibility: "公开" },
    ));
    await vi.waitFor(() => expect(confirm.disabled).toBe(false));

    await act(async () => confirm.click());
    await vi.waitFor(() => expect(confirmPluginAction).toHaveBeenCalledWith("action-1", "project-a", 2));
  });

  it("拒绝前要求二次确认", async () => {
    const rejectPluginAction = vi.fn().mockResolvedValue({ ...pending, state: "rejected" });
    const current = client({ rejectPluginAction });
    await act(async () => root.render(<PluginActions client={current} projectId="project-a" />));
    await vi.waitFor(() => expect(container.textContent).toContain("拒绝"));

    const reject = [...container.querySelectorAll("button")].find((item) => item.textContent === "拒绝")!;
    await act(async () => reject.click());
    expect(rejectPluginAction).not.toHaveBeenCalled();
    const confirmReject = [...container.querySelectorAll("button")].find((item) => item.textContent === "确认拒绝")!;
    await act(async () => confirmReject.click());
    await vi.waitFor(() => expect(rejectPluginAction).toHaveBeenCalledWith("action-1", "project-a"));
  });
});
