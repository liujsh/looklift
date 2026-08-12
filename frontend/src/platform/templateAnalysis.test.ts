import { describe, expect, it } from "vitest";
import type { Analysis } from "../api/types";
import { buildTemplateParameterSections } from "./templateAnalysis";

const analysis: Analysis = {
  summary: "完整参数",
  steps: [],
  basic: {
    temperature_shift: 8, tint_shift: -2, exposure: 0.4, contrast: 12,
    highlights: -20, shadows: 10, whites: 4, blacks: -8,
    texture: 3, clarity: 5, dehaze: 2, vibrance: 9, saturation: -3,
  },
  tone_curve: [{ input: 0, output: 4 }, { input: 100, output: 96 }],
  hsl: [{ color: "orange", hue: -4, saturation: 12, luminance: 8 }],
  color_grading: {
    shadows: { hue: 192, saturation: 15, luminance: -3 },
    midtones: { hue: 32, saturation: 4, luminance: 1 },
    highlights: { hue: 42, saturation: 10, luminance: 2 },
    global_: { hue: 0, saturation: 0, luminance: 0 },
    blending: 50, balance: -8,
  },
  effects: { vignette_amount: -12, grain_amount: 18 },
};

describe("模板完整参数分组", () => {
  it("覆盖基础、曲线、HSL、颜色分级和效果", () => {
    expect(buildTemplateParameterSections(analysis).map((section) => section.title)).toEqual([
      "基础调整", "色调曲线", "HSL 颜色", "颜色分级", "效果",
    ]);
  });

  it("每种 HSL 颜色同时展示色相、饱和度和明亮度", () => {
    const hsl = buildTemplateParameterSections(analysis).find((section) => section.title === "HSL 颜色");
    expect(hsl?.rows[0]).toEqual({
      label: "橙色",
      values: [
        { label: "色相", value: -4 },
        { label: "饱和度", value: 12 },
        { label: "明亮度", value: 8 },
      ],
    });
  });
});
