import { describe, expect, it, vi } from "vitest";
import type { Analysis, LookSummary } from "../../api/types";
import { loadPreviewPair } from "../canvas/canvasModel";
import { createEditorStore } from "../../store/editorStore";
import { exportLookFile, saveCurrentLook } from "./lookActions";

function neutral(): Analysis {
  const zone = { hue: 0, saturation: 0, luminance: 0 };
  return {
    summary: "离线闭环",
    steps: [],
    basic: {
      temperature_shift: 0, tint_shift: 0, exposure: 0, contrast: 0,
      highlights: 0, shadows: 0, whites: 0, blacks: 0, texture: 0,
      clarity: 0, dehaze: 0, vibrance: 0, saturation: 0,
    },
    tone_curve: [{ input: 0, output: 0 }, { input: 255, output: 255 }],
    hsl: [{ color: "blue", hue: 0, saturation: 0, luminance: 0 }],
    color_grading: {
      shadows: zone, midtones: zone, highlights: zone, global_: zone, blending: 50, balance: 0,
    },
    effects: { vignette_amount: 0, grain_amount: 0 },
  };
}

describe("桌面调色离线闭环", () => {
  it("手调、预览、收藏和导出沿用同一 analysis 与 factor", async () => {
    const store = createEditorStore();
    store.openImage("C:/photo.jpg", neutral());
    store.previewFragment("basic", { ...store.getSnapshot().analysis!.basic, exposure: 1.25 });
    store.setFactor(0.7);
    store.finalizePreview("manual");
    const current = store.getSnapshot();
    const before = new Blob(["before"]);
    const after = new Blob(["after"]);
    const preview = vi.fn(async (payload: { factor: number }) => payload.factor === 0 ? before : after);

    await expect(loadPreviewPair(
      { preview, upload: async () => ({ path: "unused" }) },
      current.imagePath!, current.analysis!, current.factor,
    )).resolves.toEqual({ before, after });

    const look: LookSummary = {
      name: "闭环风格", summary: "离线闭环", has_preset: true, source: "user", readonly: false,
    };
    const client = {
      saveLook: vi.fn(async () => ({ name: look.name })),
      listLooks: vi.fn(async () => [look]),
      exportLook: vi.fn(async () => ({ preset: "C:/looks/闭环风格.xmp" })),
    };
    await saveCurrentLook(client, look.name, current.analysis!, current.factor);
    await expect(exportLookFile(client, look.name)).resolves.toBe("C:/looks/闭环风格.xmp");

    expect(preview.mock.calls.map(([payload]) => payload.factor)).toEqual([0, 0.7]);
    expect(client.saveLook).toHaveBeenCalledWith({
      name: look.name, analysis: current.analysis, factor: 0.7,
    });
    expect(current.analysis?.basic.exposure).toBe(1.25);
  });
});
