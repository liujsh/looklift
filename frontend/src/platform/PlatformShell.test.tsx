// @vitest-environment happy-dom

import { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { Analysis, SessionSnapshot } from "../api/types";
import { createEditorStore } from "../store/editorStore";
import { createPlatformStore } from "./platformStore";
import { PlatformShell } from "./PlatformShell";
import { createStudioRuntime } from "./studioRuntime";

const client = {
  recentSessions: vi.fn().mockResolvedValue([]),
} as unknown as LookliftClient;

function analysis(): Analysis {
  return {
    summary: "正式版本", steps: [],
    basic: { temperature_shift: 0, tint_shift: 0, exposure: 0, contrast: 0, highlights: 0,
      shadows: 0, whites: 0, blacks: 0, texture: 0, clarity: 0, dehaze: 0, vibrance: 0, saturation: 0 },
    tone_curve: [{ input: 0, output: 0 }, { input: 255, output: 255 }], hsl: [],
    color_grading: { shadows: { hue: 0, saturation: 0, luminance: 0 }, midtones: { hue: 0, saturation: 0, luminance: 0 }, highlights: { hue: 0, saturation: 0, luminance: 0 }, global_: { hue: 0, saturation: 0, luminance: 0 }, blending: 50, balance: 0 },
    effects: { vignette_amount: 0, grain_amount: 0 },
  };
}

function session(): SessionSnapshot {
  const current = analysis();
  return {
    id: "session-1", image_path: "C:/照片/a.jpg",
    created_at: "2026-07-20T00:00:00Z", updated_at: "2026-07-20T00:00:00Z",
    messages: [], versions: [], current_version_id: "v1", current_analysis: current,
  };
}

describe("PlatformShell", () => {
  it("启动显示固定首页、完整导航和标签栏三入口", () => {
    const html = renderToStaticMarkup(
      <PlatformShell client={client} store={createPlatformStore()} engineLabel="测试引擎" />,
    );

    expect(html).toContain("LookLift");
    expect(html).toContain('data-tab-id="home"');
    expect(html).not.toContain('data-tab-id="home" data-closable="true"');
    for (const label of ["首页", "我的图库", "大师模板", "自动化技能", "插件", "设置与帮助"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain('aria-label="新建工作上下文"');
    for (const action of ["添加文件夹", "从设备导入", "快速修图"]) {
      expect(html).toContain(action);
    }
  });

  it("未来页面只展示版本边界说明", () => {
    const store = createPlatformStore();
    store.openPlatform("library", "我的图库");

    const html = renderToStaticMarkup(
      <PlatformShell client={client} store={store} engineLabel="测试引擎" />,
    );

    expect(html).toContain("将在 v2.3-A 提供");
    expect(html).toContain("只索引，不复制原文件");
    expect(html).toContain('data-closable="true"');
    expect(html).not.toContain("128 张");
  });

  it("Studio 标签通过关闭门禁入口而不是直接销毁", () => {
    const store = createPlatformStore();
    const runtime = {
      sessionId: "session-1",
      title: "a.jpg",
      store: createEditorStore(),
      dispose: vi.fn(),
    };
    store.openStudio(runtime);

    const html = renderToStaticMarkup(
      <PlatformShell client={client} store={store} engineLabel="测试引擎" />,
    );

    expect(html).toContain('aria-label="关闭 a.jpg"');
  });

  it("候选放弃成功后才移除 Studio 标签", async () => {
    const snapshot = session();
    const interactiveClient = {
      recentSessions: vi.fn().mockResolvedValue([]),
      config: vi.fn().mockResolvedValue({ configured: false, provider: "auto" }),
      listLooks: vi.fn().mockResolvedValue([]),
      imageInfo: vi.fn().mockResolvedValue({}),
      preview: vi.fn().mockResolvedValue(new Blob(["preview"])),
      recordSessionMessages: vi.fn().mockResolvedValue(snapshot),
      chatStep: vi.fn(),
    } as unknown as LookliftClient;
    const store = createPlatformStore();
    const runtime = createStudioRuntime(interactiveClient, snapshot);
    runtime.store.beginPendingPreview(analysis(), [], [{ role: "user", content: "尝试" }], 1);
    store.openStudio(runtime);
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<PlatformShell client={interactiveClient} store={store} engineLabel="测试引擎" />);
      await Promise.resolve();
    });
    await act(async () => {
      (container.querySelector('button[aria-label="关闭 a.jpg"]') as HTMLButtonElement).click();
    });
    expect(container.textContent).toContain("放弃并关闭");
    expect(store.findStudio("session-1")).toBeDefined();

    await act(async () => {
      (container.querySelector('button[aria-label="放弃并关闭"]') as HTMLButtonElement).click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(interactiveClient.recordSessionMessages).toHaveBeenCalledTimes(1);
    expect(store.findStudio("session-1")).toBeUndefined();
    expect(runtime.isAlive()).toBe(false);

    await act(async () => root.unmount());
    container.remove();
  });
});
