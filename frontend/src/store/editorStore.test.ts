import { describe, expect, it } from "vitest";
import type { Analysis } from "../api/types";
import { createEditorStore } from "./editorStore";

function analysis(exposure = 0): Analysis {
  return {
    summary: "测试风格",
    steps: ["步骤一"],
    basic: {
      temperature_shift: 0,
      tint_shift: 0,
      exposure,
      contrast: 0,
      highlights: 0,
      shadows: 0,
      whites: 0,
      blacks: 0,
      texture: 0,
      clarity: 0,
      dehaze: 0,
      vibrance: 0,
      saturation: 0,
    },
    tone_curve: [{ input: 0, output: 0 }, { input: 255, output: 255 }],
    hsl: [{ color: "blue", hue: 0, saturation: 0, luminance: 0 }],
    color_grading: {
      shadows: { hue: 0, saturation: 0, luminance: 0 },
      midtones: { hue: 0, saturation: 0, luminance: 0 },
      highlights: { hue: 0, saturation: 0, luminance: 0 },
      global_: { hue: 0, saturation: 0, luminance: 0 },
      blending: 50,
      balance: 0,
    },
    effects: { vignette_amount: 0, grain_amount: 0 },
  };
}

describe("editorStore", () => {
  it("AI 整对象首次回填建立当前 analysis，不制造虚假的初始历史", () => {
    const store = createEditorStore();
    const incoming = analysis(0.5);

    store.commitAnalysis(incoming, "ai");
    incoming.basic.exposure = 4;

    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0.5);
    expect(store.getSnapshot().versions).toEqual([]);
  });

  it("后续整对象替换把旧 analysis 作为不可变快照压入唯一版本栈", () => {
    const store = createEditorStore();
    let notifications = 0;
    store.subscribe(() => { notifications += 1; });
    store.commitAnalysis(analysis(0.5), "ai");
    const first = store.getSnapshot().analysis;

    store.commitAnalysis(analysis(1.25), "manual");

    const state = store.getSnapshot();
    expect(state.analysis?.basic.exposure).toBe(1.25);
    expect(state.versions).toHaveLength(1);
    expect(state.versions[0].analysis).toBe(first);
    expect(state.versions[0].source).toBe("manual");
    expect(Object.isFrozen(state.versions[0].analysis)).toBe(true);
    expect(notifications).toBe(2);
  });

  it("分片更新只替换目标 section，并保存更新前快照", () => {
    const store = createEditorStore();
    store.commitAnalysis(analysis(0.5), "ai");
    const before = store.getSnapshot().analysis!;

    store.updateFragment("basic", { ...before.basic, exposure: 2 }, "manual");

    const state = store.getSnapshot();
    expect(state.analysis?.basic.exposure).toBe(2);
    expect(state.analysis?.effects).toEqual(before.effects);
    expect(state.analysis).not.toBe(before);
    expect(state.versions[0].analysis).toBe(before);
  });

  it("图片、渲染态和 factor 由同一 store 持有，factor 被限制在 0-1", () => {
    const store = createEditorStore();

    store.setImagePath("C:/photo.jpg");
    store.setFactor(1.4);
    store.setRenderState({ status: "rendering", error: null });

    expect(store.getSnapshot()).toMatchObject({
      imagePath: "C:/photo.jpg",
      factor: 1,
      render: { status: "rendering", error: null },
    });
    expect(store.getSnapshot().versions).toEqual([]);
  });
});
