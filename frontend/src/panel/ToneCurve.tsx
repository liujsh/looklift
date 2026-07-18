import { useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent, PointerEvent as ReactPointerEvent } from "react";
import type { ToneCurvePoint } from "../api/types";
import { addCurvePoint, moveCurvePoint, removeCurvePoint, sampleMonotoneCurve } from "./toneCurveModel";

type ToneCurveProps = {
  value: ToneCurvePoint[];
  onChange(value: ToneCurvePoint[]): void;
};

export function ToneCurve({ value, onChange }: ToneCurveProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const samples = sampleMonotoneCurve(value, 64);
  const path = samples.map((point, index) => `${index ? "L" : "M"}${point.input},${255 - point.output}`).join(" ");

  const pointFromEvent = (
    event: ReactPointerEvent<SVGSVGElement> | ReactMouseEvent<SVGSVGElement>,
  ): ToneCurvePoint => {
    const bounds = svgRef.current!.getBoundingClientRect();
    return {
      input: (event.clientX - bounds.left) / bounds.width * 255,
      output: 255 - (event.clientY - bounds.top) / bounds.height * 255,
    };
  };

  const drag = (event: ReactPointerEvent<SVGSVGElement>) => {
    if (dragging === null) return;
    onChange(moveCurvePoint(value, dragging, pointFromEvent(event)));
  };

  return (
    <div className="tone-curve-control">
      <svg
        ref={svgRef}
        viewBox="0 0 255 255"
        role="img"
        aria-label="色调曲线"
        onDoubleClick={(event) => onChange(addCurvePoint(value, pointFromEvent(event)))}
        onPointerMove={drag}
        onPointerUp={() => setDragging(null)}
        onPointerCancel={() => setDragging(null)}
      >
        <path className="curve-grid" d="M0 63.75H255 M0 127.5H255 M0 191.25H255 M63.75 0V255 M127.5 0V255 M191.25 0V255" />
        <path className="curve-diagonal" d="M0 255L255 0" />
        <path className="curve-line" d={path} />
        {value.map((point, index) => (
          <circle
            key={`${index}-${point.input}`}
            className={selected === index ? "active" : ""}
            cx={point.input}
            cy={255 - point.output}
            r="5"
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setSelected(index);
              setDragging(index);
            }}
          />
        ))}
      </svg>
      <div className="curve-actions">
        <span>双击曲线区域添加控制点</span>
        <button
          type="button"
          disabled={selected === null || selected === 0 || selected === value.length - 1}
          onClick={() => {
            if (selected !== null) onChange([...removeCurvePoint(value, selected)]);
            setSelected(null);
          }}
        >删除选中点</button>
      </div>
    </div>
  );
}
