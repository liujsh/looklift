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

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={analysis(0)} factor={1} />);
      await Promise.resolve();
    });
    expect(drop.callbacks).not.toBeNull();

    await act(async () => {
      drop.callbacks!.onPath("C:/photo.jpg");
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(preview).toHaveBeenCalledTimes(2);

    await act(async () => {
      root.render(<CanvasPane client={client} analysis={analysis(0.5)} factor={0.9} />);
      root.render(<CanvasPane client={client} analysis={analysis(1)} factor={0.8} />);
      root.render(<CanvasPane client={client} analysis={analysis(2)} factor={0.7} />);
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
  });
});
