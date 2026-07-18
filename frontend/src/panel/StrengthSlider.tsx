import { factorToPercent, percentToFactor } from "./controlModels";

type StrengthSliderProps = {
  factor: number;
  disabled?: boolean;
  onChange(factor: number): void;
};

export function StrengthSlider({ factor, disabled, onChange }: StrengthSliderProps) {
  const percent = factorToPercent(factor);
  return (
    <div className="strength-control" data-control="factor">
      <div><span>整体强度</span><strong>{percent}%</strong></div>
      <input
        type="range"
        aria-label="整体强度"
        min="0"
        max="100"
        value={percent}
        disabled={disabled}
        onChange={(event) => onChange(percentToFactor(Number(event.currentTarget.value)))}
      />
    </div>
  );
}
