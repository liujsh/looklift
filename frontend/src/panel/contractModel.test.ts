import { describe, expect, it } from "vitest";
import type { ParamContract } from "../api/types";
import { BASIC_CONTROLS, EFFECT_CONTROLS, createNeutralAnalysis, requireRule } from "./contractModel";

function contractFixture(): ParamContract {
  const contract: ParamContract = {};
  for (const control of [...BASIC_CONTROLS, ...EFFECT_CONTROLS]) {
    contract[control.path] = { min: -100, max: 100, default: 0 };
  }
  for (const color of ["red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"]) {
    for (const field of ["hue", "saturation", "luminance"]) {
      contract[`hsl.${color}.${field}`] = { min: -100, max: 100, default: 0 };
    }
  }
  for (const zone of ["shadows", "midtones", "highlights", "global"]) {
    for (const field of ["hue", "saturation", "luminance"]) {
      contract[`color_grading.${zone}.${field}`] = {
        min: field === "hue" ? 0 : field === "saturation" ? 0 : -100,
        max: field === "hue" ? 360 : 100,
        default: 0,
      };
    }
  }
  contract["color_grading.blending"] = { min: 0, max: 100, default: 50 };
  contract["color_grading.balance"] = { min: -100, max: 100, default: 0 };
  contract["basic.exposure"] = { min: -5, max: 5, default: 0.25 };
  return contract;
}

describe("contractModel", () => {
  it("基础 13 项和效果 2 项只声明 path/中文标签，不保存范围副本", () => {
    expect(BASIC_CONTROLS).toHaveLength(13);
    expect(EFFECT_CONTROLS).toHaveLength(2);
    expect(BASIC_CONTROLS[0]).toEqual({ path: "basic.temperature_shift", label: "色温" });
    expect(EFFECT_CONTROLS.map((item) => item.label)).toEqual(["暗角", "颗粒"]);
    expect(BASIC_CONTROLS.every((item) => Object.keys(item).length === 2)).toBe(true);
  });

  it("中性 analysis 完全读取契约默认值并保持 schema 形状", () => {
    const neutral = createNeutralAnalysis(contractFixture());

    expect(neutral.basic.exposure).toBe(0.25);
    expect(neutral.hsl.map((item) => item.color)).toEqual([
      "red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta",
    ]);
    expect(neutral.color_grading.global_).toEqual({ hue: 0, saturation: 0, luminance: 0 });
    expect(neutral.color_grading.blending).toBe(50);
    expect(neutral.effects).toEqual({ vignette_amount: 0, grain_amount: 0 });
    expect(neutral.tone_curve).toEqual([{ input: 0, output: 0 }, { input: 255, output: 255 }]);
  });

  it("契约缺失时明确失败，禁止控件偷偷回落到手写范围", () => {
    expect(() => requireRule({}, "basic.exposure")).toThrow("参数契约缺少 basic.exposure");
  });
});
