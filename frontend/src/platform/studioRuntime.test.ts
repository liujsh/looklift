import { describe, expect, it, vi } from "vitest";
import type { Analysis, ChatStepResponse, SessionSnapshot } from "../api/types";
import type { LookliftClient } from "../api/client";
import { createStudioRuntime } from "./studioRuntime";

function analysis(exposure = 0): Analysis {
  return {
    summary: "正式版本", steps: [],
    basic: { temperature_shift: 0, tint_shift: 0, exposure, contrast: 0, highlights: 0,
      shadows: 0, whites: 0, blacks: 0, texture: 0, clarity: 0, dehaze: 0, vibrance: 0, saturation: 0 },
    tone_curve: [{ input: 0, output: 0 }, { input: 255, output: 255 }], hsl: [],
    color_grading: { shadows: { hue: 0, saturation: 0, luminance: 0 }, midtones: { hue: 0, saturation: 0, luminance: 0 }, highlights: { hue: 0, saturation: 0, luminance: 0 }, global_: { hue: 0, saturation: 0, luminance: 0 }, blending: 50, balance: 0 },
    effects: { vignette_amount: 0, grain_amount: 0 },
  };
}

function snapshot(id: string, imagePath: string, exposure = 0): SessionSnapshot {
  const current = analysis(exposure);
  return {
    id,
    image_path: imagePath,
    created_at: "2026-07-20T00:00:00Z",
    updated_at: "2026-07-20T01:00:00Z",
    messages: [{ id: "m1", role: "assistant", content: `${id} 的消息`, provider: "mock", status: "done", created_at: "2026-07-20T00:00:00Z" }],
    versions: [{ id: "v1", parent_id: null, analysis: current, source: "initial", summary: "正式版本", created_at: "2026-07-20T00:00:00Z" }],
    current_version_id: "v1",
    current_analysis: current,
  };
}

function client(): LookliftClient {
  return {
    chatStep: vi.fn<() => Promise<ChatStepResponse>>(),
    commitSession: vi.fn(),
    recordSessionMessages: vi.fn(),
  } as unknown as LookliftClient;
}

describe("studioRuntime", () => {
  it("从正式 snapshot 建立互相隔离的 Store 和聊天状态", () => {
    const first = createStudioRuntime(client(), snapshot("session-1", "C:\\照片\\第一张.jpg", 0.2));
    const second = createStudioRuntime(client(), snapshot("session-2", "C:\\照片\\第二张.jpg", 0.8));

    first.store.setFactor(0.35);

    expect(first.title).toBe("第一张.jpg");
    expect(first.store.getSnapshot()).toMatchObject({ factor: 0.35, pendingPreview: null });
    expect(second.store.getSnapshot()).toMatchObject({ factor: 1, pendingPreview: null });
    expect(first.workflow.getSnapshot().messages[0].content).toContain("session-1");
    expect(second.workflow.getSnapshot().messages[0].content).toContain("session-2");
  });

  it("销毁幂等且运行时不再存活", () => {
    const current = createStudioRuntime(client(), snapshot("session-1", "C:/照片/a.jpg"));

    current.dispose();
    current.dispose();

    expect(current.isAlive()).toBe(false);
  });

  it("AI 运行中先停止，晚到响应不能建立候选", async () => {
    let finish!: (value: ChatStepResponse) => void;
    const current = createStudioRuntime({
      ...client(),
      chatStep: vi.fn(() => new Promise<ChatStepResponse>((resolve) => { finish = resolve; })),
    } as unknown as LookliftClient, snapshot("session-1", "C:/照片/a.jpg"));

    const running = current.workflow.send("调整");
    await Promise.resolve();
    expect(current.closeRequirement()).toBe("ai");

    expect(current.stopAiForClose()).toBe("direct");
    current.dispose();
    finish({
      analysis: analysis(1), changes: [{ path: "basic.exposure", before: 0, after: 1 }],
      rejected: [], explanation: "完成", limitations: [], approximation: "", manual_steps: [],
      done: true, provider: "mock", proxy_count: 1, metadata_sent: false,
    });

    await expect(running).resolves.toBeNull();
    expect(current.store.getSnapshot().pendingPreview).toBeNull();
  });

  it("候选保留成功后才允许关闭，保存失败时保留运行时和候选", async () => {
    const commitSession = vi.fn().mockResolvedValue(snapshot("session-1", "C:/照片/a.jpg", 1));
    const current = createStudioRuntime({ ...client(), commitSession } as unknown as LookliftClient, snapshot("session-1", "C:/照片/a.jpg"));
    current.store.beginPendingPreview(analysis(1), [], [{ role: "user", content: "提亮" }], 1);
    current.store.setRenderState({ status: "ready", error: null });

    expect(current.closeRequirement()).toBe("pending");
    await current.resolvePendingForClose("keep");
    expect(commitSession).toHaveBeenCalledTimes(1);
    expect(current.store.getSnapshot().pendingPreview).toBeNull();
    expect(current.closeRequirement()).toBe("direct");

    const failing = createStudioRuntime({
      ...client(), commitSession: vi.fn().mockRejectedValue(new Error("磁盘已满")),
    } as unknown as LookliftClient, snapshot("session-2", "C:/照片/b.jpg"));
    failing.store.beginPendingPreview(analysis(1), [], [], 1);
    failing.store.setRenderState({ status: "ready", error: null });

    await expect(failing.resolvePendingForClose("keep")).rejects.toThrow("磁盘已满");
    expect(failing.isAlive()).toBe(true);
    expect(failing.store.getSnapshot().pendingPreview).not.toBeNull();
  });

  it("放弃候选只记录消息并清除临时预览", async () => {
    const recordSessionMessages = vi.fn().mockResolvedValue(snapshot("session-1", "C:/照片/a.jpg"));
    const current = createStudioRuntime({
      ...client(), recordSessionMessages,
    } as unknown as LookliftClient, snapshot("session-1", "C:/照片/a.jpg"));
    current.store.beginPendingPreview(analysis(1), [], [{ role: "user", content: "提亮" }], 1);

    await current.resolvePendingForClose("discard");

    expect(recordSessionMessages).toHaveBeenCalledTimes(1);
    expect(current.store.getSnapshot().analysis?.basic.exposure).toBe(0);
    expect(current.store.getSnapshot().pendingPreview).toBeNull();
  });
});
