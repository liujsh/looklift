import type {
  Analysis,
  BasicAnalysis,
  ColorGradingAnalysis,
  EffectsAnalysis,
  HslEntry,
  ParamContract,
  ParamRule,
} from "../api/types";

export type ControlDeclaration = Readonly<{ path: string; label: string }>;

export const BASIC_CONTROLS = [
  { path: "basic.temperature_shift", label: "色温" },
  { path: "basic.tint_shift", label: "色调" },
  { path: "basic.exposure", label: "曝光" },
  { path: "basic.contrast", label: "对比度" },
  { path: "basic.highlights", label: "高光" },
  { path: "basic.shadows", label: "阴影" },
  { path: "basic.whites", label: "白色色阶" },
  { path: "basic.blacks", label: "黑色色阶" },
  { path: "basic.texture", label: "纹理" },
  { path: "basic.clarity", label: "清晰度" },
  { path: "basic.dehaze", label: "去朦胧" },
  { path: "basic.vibrance", label: "自然饱和度" },
  { path: "basic.saturation", label: "饱和度" },
] as const satisfies readonly ControlDeclaration[];

export const EFFECT_CONTROLS = [
  { path: "effects.vignette_amount", label: "暗角" },
  { path: "effects.grain_amount", label: "颗粒" },
] as const satisfies readonly ControlDeclaration[];

export const HSL_COLORS = [
  ["red", "红"],
  ["orange", "橙"],
  ["yellow", "黄"],
  ["green", "绿"],
  ["aqua", "青"],
  ["blue", "蓝"],
  ["purple", "紫"],
  ["magenta", "洋红"],
] as const;

export const GRADING_ZONES = [
  ["shadows", "阴影"],
  ["midtones", "中间调"],
  ["highlights", "高光"],
  ["global", "全局"],
] as const;

export function requireRule(contract: ParamContract, path: string): ParamRule {
  const rule = contract[path];
  if (!rule) throw new Error(`参数契约缺少 ${path}`);
  return rule;
}

function defaultFor(contract: ParamContract, path: string): number {
  return requireRule(contract, path).default;
}

export function createNeutralAnalysis(contract: ParamContract): Analysis {
  const basic = Object.fromEntries(
    BASIC_CONTROLS.map(({ path }) => [path.slice("basic.".length), defaultFor(contract, path)]),
  ) as BasicAnalysis;
  const effects = Object.fromEntries(
    EFFECT_CONTROLS.map(({ path }) => [path.slice("effects.".length), defaultFor(contract, path)]),
  ) as EffectsAnalysis;
  const hsl: HslEntry[] = HSL_COLORS.map(([color]) => ({
    color,
    hue: defaultFor(contract, `hsl.${color}.hue`),
    saturation: defaultFor(contract, `hsl.${color}.saturation`),
    luminance: defaultFor(contract, `hsl.${color}.luminance`),
  }));
  const grading = Object.fromEntries(
    GRADING_ZONES.map(([zone]) => {
      const key = zone === "global" ? "global_" : zone;
      return [key, {
        hue: defaultFor(contract, `color_grading.${zone}.hue`),
        saturation: defaultFor(contract, `color_grading.${zone}.saturation`),
        luminance: defaultFor(contract, `color_grading.${zone}.luminance`),
      }];
    }),
  ) as Pick<ColorGradingAnalysis, "shadows" | "midtones" | "highlights" | "global_">;

  return {
    summary: "",
    steps: [],
    basic,
    tone_curve: [{ input: 0, output: 0 }, { input: 255, output: 255 }],
    hsl,
    color_grading: {
      ...grading,
      blending: defaultFor(contract, "color_grading.blending"),
      balance: defaultFor(contract, "color_grading.balance"),
    },
    effects,
  };
}
