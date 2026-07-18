import { describe, expect, it, vi } from "vitest";
import type { Analysis, ChatStepResponse } from "../../api/types";
import { createEditorStore } from "../../store/editorStore";
import { createChatWorkflow } from "./chatWorkflow";

function analysis(exposure = 0): Analysis {
  return {
    summary: "测试", steps: [],
    basic: { temperature_shift: 0, tint_shift: 0, exposure, contrast: 0, highlights: 0,
      shadows: 0, whites: 0, blacks: 0, texture: 0, clarity: 0, dehaze: 0, vibrance: 0, saturation: 0 },
    tone_curve: [{ input: 0, output: 0 }, { input: 255, output: 255 }], hsl: [],
    color_grading: { shadows: { hue: 0, saturation: 0, luminance: 0 }, midtones: { hue: 0, saturation: 0, luminance: 0 }, highlights: { hue: 0, saturation: 0, luminance: 0 }, global_: { hue: 0, saturation: 0, luminance: 0 }, blending: 50, balance: 0 },
    effects: { vignette_amount: 0, grain_amount: 0 },
  };
}

function response(exposure: number, done = false): ChatStepResponse {
  return { analysis: analysis(exposure), changes: [{ path: "basic.exposure", before: 0, after: exposure }],
    rejected: [], explanation: `曝光 ${exposure}`, limitations: [], approximation: "", manual_steps: [],
    done, provider: "mock", proxy_count: 1, metadata_sent: false };
}

describe("chatWorkflow", () => {
  it("普通消息只调用一次并只建立 pending", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    const chatStep = vi.fn().mockResolvedValue(response(1));
    const workflow = createChatWorkflow({ chatStep }, store);

    await workflow.send("提亮");

    expect(chatStep).toHaveBeenCalledTimes(1);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0);
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(1);
    expect(store.getSnapshot().versions).toEqual([]);
  });

  it("AI 精修最多追加两轮，每轮使用最新 candidate，done 提前停止", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    const chatStep = vi.fn()
      .mockResolvedValueOnce(response(1))
      .mockResolvedValueOnce(response(2))
      .mockResolvedValueOnce(response(3));
    const workflow = createChatWorkflow({ chatStep }, store);
    await workflow.send("先调整");
    await workflow.refine();

    expect(chatStep).toHaveBeenCalledTimes(3);
    expect(chatStep.mock.calls[1][0].current_analysis.basic.exposure).toBe(1);
    expect(chatStep.mock.calls[2][0].current_analysis.basic.exposure).toBe(2);
    expect(workflow.getSnapshot().stopReason).toBe("round_limit");

    const early = vi.fn().mockResolvedValueOnce(response(4, true));
    const earlyWorkflow = createChatWorkflow({ chatStep: early }, store);
    await earlyWorkflow.refine();
    expect(early).toHaveBeenCalledTimes(1);
    expect(earlyWorkflow.getSnapshot().stopReason).toBe("done");
  });

  it("无变化停止且不替换候选，取消终止后续轮次", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.beginPendingPreview(analysis(1), [], [], 1);
    const noChange = vi.fn().mockResolvedValue({ ...response(1), changes: [], explanation: "无需再调" });
    const workflow = createChatWorkflow({ chatStep: noChange }, store);
    await workflow.refine();
    expect(noChange).toHaveBeenCalledTimes(1);
    expect(workflow.getSnapshot().stopReason).toBe("no_changes");
    expect(workflow.getSnapshot().phase).toBe("pending");
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(1);
    expect(store.getSnapshot().pendingPreview?.exchange).toHaveLength(2);

    const aborting = vi.fn((_request, signal?: AbortSignal) => new Promise<ChatStepResponse>((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    const cancelled = createChatWorkflow({ chatStep: aborting }, store);
    const running = cancelled.refine();
    cancelled.cancel();
    await running;
    expect(aborting).toHaveBeenCalledTimes(1);
    expect(cancelled.getSnapshot().stopReason).toBe("cancelled");
  });

  it("无变化、取消和失败通过消息钩子形成正式记录", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    const recorded: Array<readonly unknown[]> = [];
    const noChange = vi.fn().mockResolvedValue({ ...response(0), changes: [] });
    const current = createChatWorkflow({ chatStep: noChange }, store, {
      onMessagesOnly: async (items) => { recorded.push(items); },
    });
    await current.send("看看");
    expect(recorded[0]).toMatchObject([{ role: "user" }, { role: "assistant", status: "done" }]);

    const aborting = vi.fn((_request, signal?: AbortSignal) => new Promise<ChatStepResponse>((_resolve, reject) => {
      signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    }));
    const cancelled = createChatWorkflow({ chatStep: aborting }, store, {
      onMessagesOnly: async (items) => { recorded.push(items); },
    });
    const running = cancelled.send("取消它");
    cancelled.cancel();
    await running;
    expect(recorded[1]).toMatchObject([{ role: "user" }, { status: "cancelled" }]);

    const failed = createChatWorkflow({ chatStep: vi.fn().mockRejectedValue(new Error("服务未启动")) }, store, {
      onMessagesOnly: async (items) => { recorded.push(items); },
    });
    await expect(failed.send("失败请求")).rejects.toThrow("服务未启动");
    expect(recorded[2]).toMatchObject([{ role: "user" }, { status: "failed" }]);
  });

  it("候选无法进入 Store 时不得伪装 pending；结算和切图恢复会重置旧状态", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.setRenderState({ status: "error", error: "渲染失败" });
    const current = createChatWorkflow({ chatStep: vi.fn().mockResolvedValue(response(1)) }, store);
    await expect(current.send("提亮")).rejects.toThrow("候选预览");
    expect(current.getSnapshot().phase).toBe("error");
    expect(store.getSnapshot().pendingPreview).toBeNull();

    store.setRenderState({ status: "ready", error: null });
    await current.send("重试");
    current.settlePending();
    expect(current.getSnapshot().phase).toBe("idle");
    current.restoreMessages([{ role: "assistant", content: "另一张照片" }]);
    expect(current.getSnapshot()).toMatchObject({ phase: "idle", lastResponse: null, error: null });
  });
});
