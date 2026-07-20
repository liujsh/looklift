// @vitest-environment happy-dom

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LookliftClient } from "../api/client";
import type { JsonObject } from "../api/types";
import { CanvasPane } from "./CanvasPane";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const drop = vi.hoisted(() => ({
  callbacks: null as null | { onActive(active: boolean): void; onPath(path: string): void },
  unlisten: vi.fn(),
  listen: vi.fn(),
}));

vi.mock("../features/canvas/tauriDrop", () => ({
  listenForTauriDrops: drop.listen,
}));

const analysis = (exposure: number): JsonObject => ({
  summary: "测试",
  steps: [],
  basic: { exposure },
  tone_curve: [],
  hsl: [],
  color_grading: {},
  effects: {},
});

describe("CanvasPane lifecycle", () => {
  let container: HTMLDivElement;
  let root: Root;
  let objectUrl = 0;

  beforeEach(() => {
    vi.useFakeTimers();
    drop.callbacks = null;
    drop.unlisten.mockReset();
    drop.listen.mockReset().mockImplementation(async (_element, callbacks) => {
      drop.callbacks = callbacks;
      return drop.unlisten;
    });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => `blob:test-${++objectUrl}`),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    container = document.createElement("div");
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    container.remove();
    vi.useRealTimers();
  });

  it("参数连续变化时只保留一份原生拖图监听并渲染最终值", async () => {
    const preview = vi.fn(async () => new Blob(["jpeg"], { type: "image/jpeg" }));
    const client = {
      preview,
      upload: vi.fn(),
    } as unknown as LookliftClient;
    const effectPreview = vi.fn();

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={analysis(0)} factor={1} onEffectPreview={effectPreview} />);
      await Promise.resolve();
    });
    expect(drop.callbacks).not.toBeNull();

    await act(async () => {
      drop.callbacks!.onPath("C:/photo.jpg");
      for (let index = 0; index < 5; index += 1) await Promise.resolve();
    });
    expect(container.querySelector(".canvas-pane")?.getAttribute("data-phase")).toBe("ready");
    expect(preview).toHaveBeenCalledTimes(2);
    expect(effectPreview).toHaveBeenCalledWith(expect.any(Blob), expect.stringContaining("C:/photo.jpg"));

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={analysis(0.5)} factor={0.9} onEffectPreview={effectPreview} />);
      root.render(<CanvasPane client={client} analysis={analysis(1)} factor={0.8} onEffectPreview={effectPreview} />);
      root.render(<CanvasPane client={client} analysis={analysis(2)} factor={0.7} onEffectPreview={effectPreview} />);
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(160);
    });

    expect(drop.listen).toHaveBeenCalledTimes(1);
    expect(drop.unlisten).not.toHaveBeenCalled();
    expect(preview).toHaveBeenLastCalledWith(
      { path: "C:/photo.jpg", analysis: analysis(2), factor: 0.7 },
      expect.any(AbortSignal),
    );
    expect(effectPreview).toHaveBeenLastCalledWith(expect.any(Blob), expect.stringContaining("0.7"));
  });

  it("父层回调身份变化不会取消已经发出的实时预览", async () => {
    let liveSignal: AbortSignal | undefined;
    const preview = vi.fn((_payload, signal?: AbortSignal) => {
      if (preview.mock.calls.length <= 2) {
        return Promise.resolve(new Blob(["jpeg"], { type: "image/jpeg" }));
      }
      liveSignal = signal;
      return new Promise<Blob>(() => undefined);
    });
    const client = { preview, upload: vi.fn() } as unknown as LookliftClient;
    const changedAnalysis = analysis(1);

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={analysis(0)} onPreviewRendered={vi.fn()} />);
      await Promise.resolve();
    });
    await act(async () => {
      drop.callbacks!.onPath("C:/photo.jpg");
      for (let index = 0; index < 5; index += 1) await Promise.resolve();
    });
    expect(container.querySelector(".canvas-pane")?.getAttribute("data-phase")).toBe("ready");

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={changedAnalysis} onPreviewRendered={vi.fn()} />);
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(160);
    });
    expect(preview).toHaveBeenCalledTimes(3);
    expect(liveSignal).toBeDefined();
    expect(liveSignal!.aborted).toBe(false);

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={changedAnalysis} onPreviewRendered={vi.fn()} />);
      await Promise.resolve();
    });

    expect(liveSignal!.aborted).toBe(false);
  });

  it("只有活动 Studio 注册原生拖图监听", async () => {
    const client = {
      preview: vi.fn(),
      upload: vi.fn(),
    } as unknown as LookliftClient;

    await act(async () => {
      root.render(<CanvasPane client={client} active={false} />);
      await Promise.resolve();
    });
    expect(drop.listen).not.toHaveBeenCalled();

    await act(async () => {
      root.render(<CanvasPane client={client} active />);
      await Promise.resolve();
    });
    expect(drop.listen).toHaveBeenCalledTimes(1);

    await act(async () => {
      root.render(<CanvasPane client={client} active={false} />);
      await Promise.resolve();
    });
    expect(drop.unlisten).toHaveBeenCalledTimes(1);
  });
});
