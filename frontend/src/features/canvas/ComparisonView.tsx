import type { CSSProperties } from "react";

type ComparisonViewProps = {
  beforeUrl: string;
  afterUrl: string;
  position: number;
  onPositionChange(position: number): void;
};

type ComparisonStyle = CSSProperties & { "--comparison-position": string };

export function ComparisonView({
  beforeUrl,
  afterUrl,
  position,
  onPositionChange,
}: ComparisonViewProps) {
  const style: ComparisonStyle = { "--comparison-position": `${position}%` };
  return (
    <div className="comparison-view" style={style} data-position={position}>
      <img src={beforeUrl} alt="调整前" draggable={false} />
      <div className="comparison-after" aria-hidden="true">
        <img src={afterUrl} alt="" draggable={false} />
      </div>
      <div className="comparison-divider" aria-hidden="true"><span>↔</span></div>
      <input
        type="range"
        min="0"
        max="100"
        value={position}
        aria-label="原图与效果对比位置"
        onChange={(event) => onPositionChange(Number(event.currentTarget.value))}
      />
    </div>
  );
}
