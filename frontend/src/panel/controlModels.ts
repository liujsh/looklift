import type {
  ColorGradingAnalysis,
  ColorGradingZone,
  HslEntry,
  ParamRule,
} from "../api/types";

export function clampToRule(value: number, rule: ParamRule): number {
  return Math.min(rule.max, Math.max(rule.min, value));
}

export function ruleToUnit(value: number, rule: ParamRule, unitMax: number): number {
  if (rule.max === rule.min) return 0;
  return (clampToRule(value, rule) - rule.min) / (rule.max - rule.min) * unitMax;
}

export function unitToRule(value: number, rule: ParamRule, unitMax: number): number {
  const normalized = Math.min(unitMax, Math.max(0, value)) / unitMax;
  return rule.min + normalized * (rule.max - rule.min);
}

export function percentToFactor(percent: number): number {
  return Math.min(1, Math.max(0, percent / 100));
}

export function factorToPercent(factor: number): number {
  return Math.round(Math.min(1, Math.max(0, factor)) * 100);
}

export function updateHslEntry(
  entries: readonly HslEntry[],
  color: string,
  field: "hue" | "saturation" | "luminance",
  value: number,
): HslEntry[] {
  return entries.map((entry) => entry.color === color ? { ...entry, [field]: value } : entry);
}

type GradingZoneKey = "shadows" | "midtones" | "highlights" | "global_";

export function updateGradingZone(
  grading: ColorGradingAnalysis,
  zone: GradingZoneKey,
  field: keyof ColorGradingZone,
  value: number,
): ColorGradingAnalysis {
  return { ...grading, [zone]: { ...grading[zone], [field]: value } };
}
