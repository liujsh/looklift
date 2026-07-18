import { describe, expect, it } from "vitest";
import { PANEL_GROUPS } from "./groups";

describe("PANEL_GROUPS", () => {
  it("严格按 spec 映射五个 operator 面板分组", () => {
    expect(PANEL_GROUPS.map((group) => [group.id, group.section, group.label])).toEqual([
      ["basic", "basic", "基础"],
      ["hsl", "hsl", "色彩 HSL"],
      ["tone-curve", "tone_curve", "曲线"],
      ["color-grading", "color_grading", "分级"],
      ["effects", "effects", "效果"],
    ]);
  });

  it("基础和效果 operator 数量与冻结面板契约一致", () => {
    expect(PANEL_GROUPS.find((group) => group.id === "basic")?.operators).toHaveLength(13);
    expect(PANEL_GROUPS.find((group) => group.id === "effects")?.operators).toEqual([
      "vignette_amount",
      "grain_amount",
    ]);
  });
});
