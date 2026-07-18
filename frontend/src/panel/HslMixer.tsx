import { useState } from "react";
import type { HslEntry, ParamContract } from "../api/types";
import { HSL_COLORS, requireRule } from "./contractModel";
import { updateHslEntry } from "./controlModels";
import { SliderControl } from "./SliderControl";

type HslMixerProps = {
  contract: ParamContract;
  value: HslEntry[];
  onChange(value: HslEntry[]): void;
};

const FIELDS = [
  ["hue", "色相"],
  ["saturation", "饱和度"],
  ["luminance", "明亮度"],
] as const;

export function HslMixer({ contract, value, onChange }: HslMixerProps) {
  const [activeColor, setActiveColor] = useState<string>(HSL_COLORS[0][0]);
  const entry = value.find((item) => item.color === activeColor);
  if (!entry) return <p className="control-error">HSL 参数缺少 {activeColor}</p>;

  return (
    <div className="hsl-mixer">
      <div className="hsl-tabs" role="tablist" aria-label="HSL 颜色通道">
        {HSL_COLORS.map(([color, label]) => (
          <button
            type="button"
            role="tab"
            aria-selected={activeColor === color}
            data-color={color}
            key={color}
            onClick={() => setActiveColor(color)}
          >{label}</button>
        ))}
      </div>
      {FIELDS.map(([field, label]) => (
        <SliderControl
          key={field}
          label={label}
          rule={requireRule(contract, `hsl.${activeColor}.${field}`)}
          value={entry[field]}
          onChange={(next) => onChange(updateHslEntry(value, activeColor, field, next))}
        />
      ))}
    </div>
  );
}
