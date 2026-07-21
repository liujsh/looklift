// @vitest-environment happy-dom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { Analysis, ChatStepResponse, SessionSnapshot } from "../api/types";
import { createPlatformStore } from "./platformStore";
import { PlatformShell } from "./PlatformShell";
import { createStudioRuntime } from "./studioRuntime";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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

function snapshot(id: string, path: string, exposure = 0): SessionSnapshot {
  const current = analysis(exposure);
  return {
    id, image_path: path,
    created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T01:00:00Z",
    messages: [], versions: [], current_version_id: `${id}-v1`, current_analysis: current,
  };
}

function response(exposure: number): ChatStepResponse {
  return {
    analysis: analysis(exposure), changes: [{ path: "basic.exposure", before: 0, after: exposure }],
    rejected: [], explanation: "只更新发起请求的照片", limitations: [], approximation: "", manual_steps: [],
    done: true, provider: "mock", proxy_count: 1, metadata_sent: false,
  };
}

describe("PlatformShell 集成流程", () => {
  it("首页进入、多标签后台 AI、候选关闭和最近会话聚焦保持同一状态边界", async () => {
    const firstSnapshot = snapshot("session-1", "C:/照片/第一张.jpg");
    const secondSnapshot = snapshot("session-2", "C:/照片/第二张.jpg", .4);
    let finishFirst!: (value: ChatStepResponse) => void;
    const chatStep = vi.fn((request: { path: string }) => request.path.includes("第一张")
      ? new Promise<ChatStepResponse>((resolve) => { finishFirst = resolve; })
      : Promise.resolve(response(.8)));
    const client = {
      recentSessions: vi.fn().mockResolvedValue([
        { id: "session-2", display_name: "第二张.jpg", updated_at: "2026-07-20T01:00:00Z", current_version_id: "session-2-v1", summary: "正式版本", source_available: true },
      ]),
      getSession: vi.fn().mockResolvedValue(secondSnapshot),
      config: vi.fn().mockResolvedValue({ configured: true, provider: "mock" }),
      listLooks: vi.fn().mockResolvedValue([]), imageInfo: vi.fn().mockResolvedValue({}),
      preview: vi.fn().mockResolvedValue(new Blob(["preview"], { type: "image/jpeg" })),
      chatStep,
      recordSessionMessages: vi.fn().mockImplementation(async (id: string) => id === "session-1" ? firstSnapshot : secondSnapshot),
      commitSession: vi.fn().mockResolvedValue(firstSnapshot),
    } as unknown as LookliftClient;
    const store = createPlatformStore();
    const first = createStudioRuntime(client, firstSnapshot);
    const second = createStudioRuntime(client, secondSnapshot);
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<PlatformShell
        client={client}
        store={store}
        onQuickEdit={() => { store.openStudio(first); }}
        engineLabel="测试引擎"
      />);
      await Promise.resolve();
      await Promise.resolve();
    });
    await act(async () => {
      ([...container.querySelectorAll("button")].find((button) => button.textContent?.includes("快速修图")) as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(store.getSnapshot().activeTabId).toBe("studio:session-1");

    let running!: Promise<ChatStepResponse | null>;
    await act(async () => {
      running = first.workflow.send("只调整第一张");
      await Promise.resolve();
      store.openStudio(second);
    });
    expect(store.getSnapshot().activeTabId).toBe("studio:session-2");
    await act(async () => {
      finishFirst(response(1));
      await running;
    });
    expect(first.store.getSnapshot().pendingPreview?.candidate.basic.exposure).toBe(1);
    expect(second.store.getSnapshot().pendingPreview).toBeNull();

    await act(async () => { store.activateTab("studio:session-1"); });
    await act(async () => {
      (container.querySelector('button[aria-label="关闭 第一张.jpg"]') as HTMLButtonElement).click();
    });
    expect(container.textContent).toContain("放弃并关闭");
    await act(async () => {
      (container.querySelector('button[aria-label="放弃并关闭"]') as HTMLButtonElement).click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(store.findStudio("session-1")).toBeUndefined();
    expect(store.findStudio("session-2")).toBeDefined();

    await act(async () => { store.activateTab("home"); });
    await act(async () => {
      ([...container.querySelectorAll("button")].find((button) => button.textContent?.includes("继续 第二张.jpg")) as HTMLButtonElement).click();
      await Promise.resolve();
    });
    expect(store.getSnapshot().activeTabId).toBe("studio:session-2");
    expect(store.getSnapshot().tabs.filter((tab) => tab.id === "studio:session-2")).toHaveLength(1);
    expect(client.getSession).not.toHaveBeenCalled();

    await act(async () => root.unmount());
    container.remove();
  });
});
