import type { ParamRule } from "../api/types";
import { clampToRule } from "./controlModels";

type SliderControlProps = {
  label: string;
  rule: ParamRule;
  value: number;
  disabled?: boolean;
  onChange(value: number): void;
};

function stepFor(rule: ParamRule): number {
  return rule.max - rule.min <= 10 ? 0.01 : 1;
}

export function SliderControl({ label, rule, value, disabled, onChange }: SliderControlProps) {
  const change = (raw: string) => {
    const next = Number(raw);
    if (Number.isFinite(next)) onChange(clampToRule(next, rule));
  };
  const step = stepFor(rule);

  return (
    <div className="slider-control" data-control-label={label}>
      <div className="slider-heading">
        <label>{label}</label>
        <div>
          <input
            className="slider-number"
            type="number"
            aria-label={`${label}数值`}
            min={rule.min}
            max={rule.max}
            step={step}
            value={value}
            disabled={disabled}
            onChange={(event) => change(event.currentTarget.value)}
          />
          <button
            className="slider-reset"
            type="button"
            aria-label={`重置${label}`}
            disabled={disabled || value === rule.default}
            onClick={() => onChange(rule.default)}
          >↺</button>
        </div>
      </div>
      <input
        className="slider-range"
        type="range"
        aria-label={label}
        min={rule.min}
        max={rule.max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(event) => change(event.currentTarget.value)}
      />
    </div>
  );
}
