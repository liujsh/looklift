import { describe, expect, it, vi } from "vitest";
import type { Analysis, SessionSnapshot } from "../../api/types";
import { createEditorStore } from "../../store/editorStore";
import { createSessionCoordinator } from "./sessionCoordinator";

const analysis = (exposure = 0) => ({ summary: "测试", steps: [], basic: { exposure }, tone_curve: [], hsl: [], color_grading: {}, effects: {} }) as unknown as Analysis;
const snapshot = (current: Analysis): SessionSnapshot => ({
  id: "s1", image_path: "C:/photo.jpg", created_at: "", updated_at: "", messages: [], versions: [],
  current_version_id: "v1", current_analysis: current,
});

describe("sessionCoordinator", () => {
  it("打开时创建或恢复正式状态，不恢复 pending", async () => {
    const store = createEditorStore();
    const client = { createSession: vi.fn().mockResolvedValue(snapshot(analysis(0.5))) };
    const coordinator = createSessionCoordinator(client, store);
    await coordinator.open("C:/photo.jpg", analysis());
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0.5);
    expect(store.getSnapshot().pendingPreview).toBeNull();
  });

  it("保留成功后才清 pending，失败则保留以便重试", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.setRenderState({ status: "ready", error: null });
    store.beginPendingPreview(analysis(1), [], [{ role: "user", content: "提亮" }], 1);
    const client = {
      createSession: vi.fn(),
      commitSession: vi.fn().mockRejectedValueOnce(new Error("保存失败")).mockResolvedValue(snapshot(analysis(1))),
    };
    const coordinator = createSessionCoordinator(client, store, "s1");
    await expect(coordinator.acceptPending()).rejects.toThrow("保存失败");
    expect(store.getSnapshot().pendingPreview).not.toBeNull();
    await coordinator.acceptPending();
    expect(store.getSnapshot().pendingPreview).toBeNull();
    expect(client.commitSession).toHaveBeenCalledTimes(2);
  });

  it("撤销和无变更只记消息不 commit；继续手调成功后以候选为基线", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.setRenderState({ status: "ready", error: null });
    const exchange = [{ role: "assistant" as const, content: "无需调整" }];
    store.beginPendingPreview(analysis(1), [], exchange, 1);
    const client = {
      createSession: vi.fn(), commitSession: vi.fn().mockResolvedValue(snapshot(analysis(1))),
      recordSessionMessages: vi.fn().mockResolvedValue(snapshot(analysis())),
    };
    const coordinator = createSessionCoordinator(client, store, "s1");
    await coordinator.discardPending();
    expect(client.commitSession).not.toHaveBeenCalled();
    expect(client.recordSessionMessages).toHaveBeenCalledTimes(1);

    store.setRenderState({ status: "ready", error: null });
    store.beginPendingPreview(analysis(2), [], exchange, 2);
    await coordinator.continueManual();
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(2);
    expect(client.commitSession).toHaveBeenCalledTimes(1);
    await coordinator.recordMessages(exchange);
    expect(client.recordSessionMessages).toHaveBeenCalledTimes(2);
  });
});
