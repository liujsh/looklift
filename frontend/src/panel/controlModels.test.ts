import { describe, expect, it } from "vitest";
import type { ColorGradingAnalysis, HslEntry } from "../api/types";
import {
  clampToRule,
  factorToPercent,
  percentToFactor,
  ruleToUnit,
  unitToRule,
  updateGradingZone,
  updateHslEntry,
} from "./controlModels";

describe("controlModels", () => {
  it("数值输入按后端规则夹取，70% 与 factor=0.7 精确互转", () => {
    const rule = { min: -5, max: 5, default: 0 };
    expect(clampToRule(8, rule)).toBe(5);
    expect(clampToRule(-8, rule)).toBe(-5);
    expect(percentToFactor(70)).toBe(0.7);
    expect(factorToPercent(0.7)).toBe(70);
  });

  it("任意契约范围都能与控件标准坐标双向映射", () => {
    const rule = { min: -100, max: 100, default: 0 };
    expect(ruleToUnit(0, rule, 100)).toBe(50);
    expect(unitToRule(75, rule, 100)).toBe(50);
    expect(unitToRule(120, rule, 100)).toBe(100);
  });

  it("HSL 更新命中单个颜色且不修改原数组", () => {
    const hsl: HslEntry[] = [
      { color: "orange", hue: 0, saturation: 0, luminance: 0 },
      { color: "blue", hue: 0, saturation: 10, luminance: 0 },
    ];
    const next = updateHslEntry(hsl, "blue", "saturation", 25);

    expect(next[1].saturation).toBe(25);
    expect(next[0]).toBe(hsl[0]);
    expect(hsl[1].saturation).toBe(10);
  });

  it("分级更新只替换目标色轮字段", () => {
    const zone = { hue: 0, saturation: 0, luminance: 0 };
    const grading: ColorGradingAnalysis = {
      shadows: zone,
      midtones: zone,
      highlights: zone,
      global_: zone,
      blending: 50,
      balance: 0,
    };
    const next = updateGradingZone(grading, "shadows", "hue", 215);

    expect(next.shadows.hue).toBe(215);
    expect(next.highlights).toBe(grading.highlights);
    expect(grading.shadows.hue).toBe(0);
  });
});
