import type { EditableSection } from "../store/editorStore";
import type { IconName } from "../platform/icons";

export type PanelGroup = Readonly<{
  id: "basic" | "hsl" | "tone-curve" | "color-grading" | "effects";
  label: string;
  section: EditableSection;
  icon: IconName;
  operators: readonly string[];
}>;

export const PANEL_GROUPS: readonly PanelGroup[] = Object.freeze([
  {
    id: "basic",
    label: "基础",
    section: "basic",
    icon: "sun",
    operators: Object.freeze([
      "temperature_shift", "tint_shift", "exposure", "contrast", "highlights",
      "shadows", "whites", "blacks", "texture", "clarity", "dehaze", "vibrance",
      "saturation",
    ]),
  },
  { id: "hsl", label: "色彩 HSL", section: "hsl", icon: "palette", operators: Object.freeze(["hsl"]) },
  { id: "tone-curve", label: "曲线", section: "tone_curve", icon: "spline", operators: Object.freeze(["tone_curve"]) },
  {
    id: "color-grading",
    label: "分级",
    section: "color_grading",
    icon: "contrast",
    operators: Object.freeze(["shadows", "midtones", "highlights", "global", "blending", "balance"]),
  },
  {
    id: "effects",
    label: "效果",
    section: "effects",
    icon: "droplets",
    operators: Object.freeze(["vignette_amount", "grain_amount"]),
  },
]);
