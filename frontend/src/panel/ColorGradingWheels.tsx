import { HslColorPicker, type HslColor } from "react-colorful";
import type { ColorGradingAnalysis, ParamContract } from "../api/types";
import { GRADING_ZONES, requireRule } from "./contractModel";
import { ruleToUnit, unitToRule } from "./controlModels";
import { SliderControl } from "./SliderControl";

type ColorGradingWheelsProps = {
  contract: ParamContract;
  value: ColorGradingAnalysis;
  onChange(value: ColorGradingAnalysis): void;
};

export function ColorGradingWheels({ contract, value, onChange }: ColorGradingWheelsProps) {
  return (
    <div className="grading-controls">
      <div className="grading-grid">
        {GRADING_ZONES.map(([contractZone, label]) => {
          const zone = contractZone === "global" ? "global_" : contractZone;
          const current = value[zone];
          const prefix = `color_grading.${contractZone}`;
          const hueRule = requireRule(contract, `${prefix}.hue`);
          const saturationRule = requireRule(contract, `${prefix}.saturation`);
          const luminanceRule = requireRule(contract, `${prefix}.luminance`);
          const picker: HslColor = {
            h: ruleToUnit(current.hue, hueRule, 360),
            s: ruleToUnit(current.saturation, saturationRule, 100),
            l: ruleToUnit(current.luminance, luminanceRule, 100),
          };
          return (
            <section className="grading-wheel" key={zone}>
              <h4>{label}</h4>
              <HslColorPicker
                color={picker}
                onChange={(next) => onChange({
                  ...value,
                  [zone]: {
                    hue: unitToRule(next.h, hueRule, 360),
                    saturation: unitToRule(next.s, saturationRule, 100),
                    luminance: unitToRule(next.l, luminanceRule, 100),
                  },
                })}
              />
              <span>{Math.round(current.hue)}° · {Math.round(current.saturation)}%</span>
            </section>
          );
        })}
      </div>
      <SliderControl
        label="混合"
        rule={requireRule(contract, "color_grading.blending")}
        value={value.blending}
        onChange={(blending) => onChange({ ...value, blending })}
      />
      <SliderControl
        label="平衡"
        rule={requireRule(contract, "color_grading.balance")}
        value={value.balance}
        onChange={(balance) => onChange({ ...value, balance })}
      />
    </div>
  );
}
