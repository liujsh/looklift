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
  const exchange = [
    { role: "user" as const, content: "提亮" },
    { role: "assistant" as const, content: "已生成候选", status: "done" as const },
  ];

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

  it("画面参数变化立即使旧预览失效，渲染失败仍保留待确认候选", () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis(0));
    store.setRenderState({ status: "ready", error: null });

    store.setFactor(0.7);
    expect(store.getSnapshot().render.status).toBe("rendering");
    store.setRenderState({ status: "ready", error: null });

    store.previewFragment("basic", { ...store.getSnapshot().analysis!.basic, exposure: 0.5 });
    expect(store.getSnapshot().render.status).toBe("rendering");
    store.setRenderState({ status: "ready", error: null });

    store.commitAnalysis(analysis(1), "library");
    expect(store.getSnapshot().render.status).toBe("rendering");
    store.setRenderState({ status: "ready", error: null });

    expect(store.beginPendingPreview(analysis(2), [], exchange, 1)).toBe(true);
    expect(store.getSnapshot().render.status).toBe("rendering");
    store.setRenderState({ status: "error", error: "渲染失败" });
    expect(store.getSnapshot().pendingPreview).not.toBeNull();
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(1);
  });

  it("打开新图片同时装入中性 analysis，并清空上一张图的版本栈", () => {
    const store = createEditorStore();
    store.openImage("C:/first.jpg", analysis(0));
    store.commitAnalysis(analysis(1), "manual");

    store.openImage("C:/second.jpg", analysis(0));

    expect(store.getSnapshot()).toMatchObject({
      imagePath: "C:/second.jpg",
      factor: 1,
      versions: [],
    });
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0);
  });

  it("拖动期间乐观更新但不堆历史，定格时只压入拖动前快照", () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis(0));
    const original = store.getSnapshot().analysis!;

    store.previewFragment("basic", { ...original.basic, exposure: 0.5 });
    store.previewFragment("basic", { ...store.getSnapshot().analysis!.basic, exposure: 1.25 });
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(1.25);
    expect(store.getSnapshot().versions).toEqual([]);

    expect(store.finalizePreview("manual")).toBe(true);
    expect(store.finalizePreview("manual")).toBe(false);
    expect(store.getSnapshot().versions).toHaveLength(1);
    expect(store.getSnapshot().versions[0].analysis).toBe(original);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(1.25);
  });

  it("applyDelta 与分片更新共用版本 push，且不会修改已有快照", () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis(0));
    const original = store.getSnapshot().analysis!;

    store.applyDelta((current) => ({
      ...current,
      basic: { ...current.basic, exposure: current.basic.exposure + 0.75 },
    }), "chat");

    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0.75);
    expect(store.getSnapshot().versions).toHaveLength(1);
    expect(store.getSnapshot().versions[0]).toMatchObject({ analysis: original, source: "chat" });
    expect(original.basic.exposure).toBe(0);
  });

  it("AI 候选只影响 displayAnalysis，保留后才进入正式版本", () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis(0));

    expect(store.beginPendingPreview(analysis(1), [], exchange, 1, "now")).toBe(true);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0);
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(1);
    expect(store.getSnapshot().versions).toEqual([]);

    expect(store.acceptPendingPreview()).toEqual(exchange);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(1);
    expect(store.getSnapshot().pendingPreview).toBeNull();
    expect(store.getSnapshot().versions).toHaveLength(1);
  });

  it("撤销候选、切图和恢复会话都不会恢复未确认预览", () => {
    const store = createEditorStore();
    store.openImage("C:/first.jpg", analysis(0));
    store.beginPendingPreview(analysis(1), [], exchange, 1);
    store.discardPendingPreview();
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(0);

    store.beginPendingPreview(analysis(2), [], exchange, 2);
    store.openImage("C:/second.jpg", analysis(0.5));
    expect(store.getSnapshot().pendingPreview).toBeNull();

    store.beginPendingPreview(analysis(3), [], exchange, 3);
    store.restoreSession("C:/second.jpg", analysis(0.75));
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(0.75);
  });

  it("继续手调先以候选为正式基线，并交回待持久化消息", () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis(0));
    store.beginPendingPreview(analysis(1), [], exchange, 1);

    expect(store.beginManualFromPending()).toEqual(exchange);
    store.updateFragment("basic", { ...store.getSnapshot().analysis!.basic, contrast: 12 }, "manual");

    expect(store.getSnapshot().analysis?.basic.exposure).toBe(1);
    expect(store.getSnapshot().analysis?.basic.contrast).toBe(12);
  });

  it("undo/redo 可逆，新提交清空 redo，旧响应和渲染错误不展示候选", () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", analysis(0));
    store.commitAnalysis(analysis(1), "manual");
    expect(store.undo()).toBe(true);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(0);
    expect(store.redo()).toBe(true);
    expect(store.getSnapshot().analysis?.basic.exposure).toBe(1);
    store.undo();
    store.commitAnalysis(analysis(2), "manual");
    expect(store.redo()).toBe(false);

    expect(store.beginPendingPreview(analysis(4), [], exchange, 4)).toBe(true);
    expect(store.beginPendingPreview(analysis(3), [], exchange, 3)).toBe(false);
    expect(store.getSnapshot().displayAnalysis?.basic.exposure).toBe(4);
    store.discardPendingPreview();
    store.setRenderState({ status: "error", error: "渲染失败" });
    expect(store.beginPendingPreview(analysis(5), [], exchange, 5)).toBe(false);
    expect(store.getSnapshot().pendingPreview).toBeNull();
  });
});
