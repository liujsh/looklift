import type { EditableSection } from "../store/editorStore";

export type PanelGroup = Readonly<{
  id: "basic" | "hsl" | "tone-curve" | "color-grading" | "effects";
  label: string;
  section: EditableSection;
  operators: readonly string[];
}>;

export const PANEL_GROUPS: readonly PanelGroup[] = Object.freeze([
  {
    id: "basic",
    label: "基础",
    section: "basic",
    operators: Object.freeze([
      "temperature_shift", "tint_shift", "exposure", "contrast", "highlights",
      "shadows", "whites", "blacks", "texture", "clarity", "dehaze", "vibrance",
      "saturation",
    ]),
  },
  { id: "hsl", label: "色彩 HSL", section: "hsl", operators: Object.freeze(["hsl"]) },
  { id: "tone-curve", label: "曲线", section: "tone_curve", operators: Object.freeze(["tone_curve"]) },
  {
    id: "color-grading",
    label: "分级",
    section: "color_grading",
    operators: Object.freeze(["shadows", "midtones", "highlights", "global", "blending", "balance"]),
  },
  {
    id: "effects",
    label: "效果",
    section: "effects",
    operators: Object.freeze(["vignette_amount", "grain_amount"]),
  },
]);
