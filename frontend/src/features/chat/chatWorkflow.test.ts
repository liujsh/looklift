import { describe, expect, it, vi } from "vitest";
import type { Analysis, ChatStepRequest, ChatStepResponse } from "../../api/types";
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
    expect(chatStep.mock.calls[0][0].factor).toBe(1);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0);
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(1);
    expect(store.getSnapshot().versions).toEqual([]);
  });

  it("请求期间锁定编辑并丢弃切图后的晚到响应", async () => {
    const store = createEditorStore();
    store.openImage("C:/first.jpg", analysis());
    store.setFactor(0.65);
    let finish!: (value: ChatStepResponse) => void;
    const chatStep = vi.fn((_request: ChatStepRequest) => new Promise<ChatStepResponse>((resolve) => { finish = resolve; }));
    const workflow = createChatWorkflow({ chatStep }, store);

    const running = workflow.send("调整当前效果");
    await Promise.resolve();
    expect(store.getSnapshot().activeAiRequestId).not.toBeNull();
    expect(chatStep.mock.calls[0][0].factor).toBe(0.65);
    store.setFactor(0.2);
    expect(store.getSnapshot().factor).toBe(0.65);

    store.openImage("C:/second.jpg", analysis());
    finish(response(2));
    await running;
    expect(store.getSnapshot().imagePath).toBe("C:/second.jpg");
    expect(store.getSnapshot().pendingPreview).toBeNull();
    expect(store.getSnapshot().activeAiRequestId).toBeNull();
  });

  it("供应商忽略 AbortSignal 并晚到时仍释放请求锁", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    let finish!: (value: ChatStepResponse) => void;
    const workflow = createChatWorkflow({
      chatStep: () => new Promise<ChatStepResponse>((resolve) => { finish = resolve; }),
    }, store);

    const running = workflow.send("调整");
    workflow.cancel();
    expect(store.getSnapshot().activeAiRequestId).toBeNull();
    finish(response(1));
    await running;

    expect(store.getSnapshot().activeAiRequestId).toBeNull();
    expect(store.getSnapshot().pendingPreview).toBeNull();
  });

  it("每次点击只精修一轮，累计两轮且每轮使用最新 candidate", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    const chatStep = vi.fn()
      .mockResolvedValueOnce(response(1))
      .mockResolvedValueOnce(response(2))
      .mockResolvedValueOnce(response(3));
    const workflow = createChatWorkflow({ chatStep }, store);
    await workflow.send("先调整");
    store.setRenderState({ status: "ready", error: null });
    await workflow.refine();

    expect(chatStep).toHaveBeenCalledTimes(2);
    expect(chatStep.mock.calls[1][0].current_analysis.basic.exposure).toBe(1);
    expect(workflow.getSnapshot().round).toBe(1);

    store.setRenderState({ status: "ready", error: null });
    await workflow.refine();
    expect(chatStep).toHaveBeenCalledTimes(3);
    expect(chatStep.mock.calls[2][0].current_analysis.basic.exposure).toBe(2);
    expect(workflow.getSnapshot().stopReason).toBe("round_limit");

    await workflow.refine();
    expect(chatStep).toHaveBeenCalledTimes(3);

    const early = vi.fn().mockResolvedValueOnce(response(4, true));
    const earlyWorkflow = createChatWorkflow({ chatStep: early }, store);
    store.setRenderState({ status: "ready", error: null });
    await earlyWorkflow.refine();
    expect(early).toHaveBeenCalledTimes(1);
    expect(earlyWorkflow.getSnapshot().stopReason).toBe("done");
  });

  it("候选未渲染完成时不会追加精修请求", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.beginPendingPreview(analysis(1), [], [], 1);
    const chatStep = vi.fn().mockResolvedValue(response(2));
    const workflow = createChatWorkflow({ chatStep }, store);

    await expect(workflow.refine()).rejects.toThrow("候选预览尚未渲染成功");
    expect(chatStep).not.toHaveBeenCalled();
  });

  it("并发重复点击不会追加第二个精修请求", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.beginPendingPreview(analysis(1), [], [], 1);
    store.setRenderState({ status: "ready", error: null });
    let finish!: (value: ChatStepResponse) => void;
    const chatStep = vi.fn(() => new Promise<ChatStepResponse>((resolve) => { finish = resolve; }));
    const workflow = createChatWorkflow({ chatStep }, store);

    const first = workflow.refine();
    const second = workflow.refine();
    await Promise.resolve();
    expect(chatStep).toHaveBeenCalledTimes(1);
    finish(response(2));
    await first;
    await expect(second).rejects.toThrow("正在处理");
  });

  it("无变化停止且不替换候选，取消终止后续轮次", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    store.beginPendingPreview(analysis(1), [], [], 1);
    store.setRenderState({ status: "ready", error: null });
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
    store.setRenderState({ status: "ready", error: null });
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

  it("销毁后拒绝晚到响应和新的请求", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis());
    let finish!: (value: ChatStepResponse) => void;
    const recorded = vi.fn();
    const workflow = createChatWorkflow({
      chatStep: () => new Promise<ChatStepResponse>((resolve) => { finish = resolve; }),
    }, store, { onMessagesOnly: recorded });

    const running = workflow.send("调整");
    await Promise.resolve();
    workflow.dispose();
    finish(response(1));

    await expect(running).resolves.toBeNull();
    await expect(workflow.send("再次请求")).rejects.toThrow("已关闭");
    expect(store.getSnapshot().activeAiRequestId).toBeNull();
    expect(store.getSnapshot().pendingPreview).toBeNull();
    expect(recorded).not.toHaveBeenCalled();
  });
});
