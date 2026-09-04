import type { CSSProperties } from "react";

export type ComparisonMode = "single" | "lr" | "tb" | "split";

type ComparisonViewProps = {
  beforeUrl: string;
  afterUrl: string;
  position: number;
  mode?: ComparisonMode;
  onPositionChange(position: number): void;
  zoom?: number;
};

type StageStyle = CSSProperties & { "--canvas-zoom": number };
type ComparisonStyle = CSSProperties & { "--comparison-position": string };

// 原型：单图 / 左右对比 / 上下对比 / 分隔线四种画布视图。
export function ComparisonView({
  beforeUrl,
  afterUrl,
  position,
  mode = "single",
  onPositionChange,
  zoom = 1,
}: ComparisonViewProps) {
  const stageStyle: StageStyle = { "--canvas-zoom": zoom };

  if (mode === "single") {
    return (
      <div className="canvas-stage" data-mode="single" style={stageStyle}>
        <div className="stage-frame">
          <img src={afterUrl} alt="效果" draggable={false} />
        </div>
      </div>
    );
  }

  if (mode === "lr" || mode === "tb") {
    return (
      <div className="canvas-stage" data-mode={mode} style={stageStyle}>
        <div className="stage-frame">
          <img src={beforeUrl} alt="原图" draggable={false} />
          <span className="stage-tag">原图</span>
        </div>
        <div className="stage-frame">
          <img src={afterUrl} alt="效果" draggable={false} />
          <span className="stage-tag is-after">效果</span>
        </div>
      </div>
    );
  }

  const style: ComparisonStyle = { "--comparison-position": `${position}%` };
  return (
    <div className="canvas-stage" data-mode="split" style={stageStyle}>
      <div className="comparison-view" style={style} data-position={position}>
        <img src={beforeUrl} alt="调整前" draggable={false} />
        <div className="comparison-after" aria-hidden="true">
          <img src={afterUrl} alt="" draggable={false} />
        </div>
        <div className="comparison-divider" aria-hidden="true">
          <span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6.5 8L3 12l3.5 4M17.5 8L21 12l-3.5 4M3 12h18" /></svg>
          </span>
        </div>
        <span className="stage-tag">原图</span>
        <span className="stage-tag is-after">效果</span>
        <input
          type="range"
          min="0"
          max="100"
          value={position}
          aria-label="原图与效果对比位置"
          onChange={(event) => onPositionChange(Number(event.currentTarget.value))}
        />
      </div>
    </div>
  );
}
