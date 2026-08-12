import type { Analysis } from "../api/types";

export type TemplateParameterValue = { label: string; value: number };
export type TemplateParameterRow = { label: string; values: TemplateParameterValue[] };
export type TemplateParameterSection = { id: string; title: string; rows: TemplateParameterRow[] };

const BASIC_PARAMETERS: ReadonlyArray<[keyof Analysis["basic"], string]> = [
  ["temperature_shift", "色温"], ["tint_shift", "色调"], ["exposure", "曝光"],
  ["contrast", "对比度"], ["highlights", "高光"], ["shadows", "阴影"],
  ["whites", "白色色阶"], ["blacks", "黑色色阶"], ["texture", "纹理"],
  ["clarity", "清晰度"], ["dehaze", "去朦胧"], ["vibrance", "自然饱和度"],
  ["saturation", "饱和度"],
];

const COLOR_LABELS: Record<string, string> = {
  red: "红色", orange: "橙色", yellow: "黄色", green: "绿色",
  aqua: "浅绿色", blue: "蓝色", purple: "紫色", magenta: "洋红",
};

const GRADING_ZONES: ReadonlyArray<[keyof Pick<Analysis["color_grading"], "shadows" | "midtones" | "highlights" | "global_">, string]> = [
  ["shadows", "阴影"], ["midtones", "中间调"], ["highlights", "高光"], ["global_", "全局"],
];

export function buildTemplateParameterSections(analysis: Analysis): TemplateParameterSection[] {
  return [
    {
      id: "basic",
      title: "基础调整",
      rows: BASIC_PARAMETERS.map(([key, label]) => ({ label, values: [{ label: "数值", value: analysis.basic[key] }] })),
    },
    {
      id: "curve",
      title: "色调曲线",
      rows: analysis.tone_curve.map((point, index) => ({
        label: `控制点 ${index + 1}`,
        values: [{ label: "输入", value: point.input }, { label: "输出", value: point.output }],
      })),
    },
    {
      id: "hsl",
      title: "HSL 颜色",
      rows: analysis.hsl.map((entry) => ({
        label: COLOR_LABELS[entry.color] ?? entry.color,
        values: [
          { label: "色相", value: entry.hue },
          { label: "饱和度", value: entry.saturation },
          { label: "明亮度", value: entry.luminance },
        ],
      })),
    },
    {
      id: "grading",
      title: "颜色分级",
      rows: [
        ...GRADING_ZONES.map(([key, label]) => ({
          label,
          values: [
            { label: "色相", value: analysis.color_grading[key].hue },
            { label: "饱和度", value: analysis.color_grading[key].saturation },
            { label: "明亮度", value: analysis.color_grading[key].luminance },
          ],
        })),
        {
          label: "混合控制",
          values: [
            { label: "混合", value: analysis.color_grading.blending },
            { label: "平衡", value: analysis.color_grading.balance },
          ],
        },
      ],
    },
    {
      id: "effects",
      title: "效果",
      rows: [
        { label: "暗角", values: [{ label: "数值", value: analysis.effects.vignette_amount }] },
        { label: "颗粒", values: [{ label: "数值", value: analysis.effects.grain_amount }] },
      ],
    },
  ];
}

export function formatTemplateParameter(value: number): string {
  const rounded = Number.isInteger(value) ? String(value) : String(Number(value.toFixed(2)));
  return value > 0 ? `+${rounded}` : rounded;
}
