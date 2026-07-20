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
});
