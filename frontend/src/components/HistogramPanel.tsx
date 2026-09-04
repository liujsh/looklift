import type { ImageInfo } from "../api/types";
import type { HistogramState } from "../features/histogram/histogramController";
import { Icon } from "../platform/icons";

type HistogramPanelProps = {
  histogram: HistogramState;
  imageInfo: ImageInfo | null;
};

function points(bins: readonly number[]): string {
  const peak = Math.max(1, ...bins.map((value) => Math.log1p(value)));
  return bins.map((value, index) => (
    `${(index / 255) * 100},${36 - (Math.log1p(value) / peak) * 34}`
  )).join(" ");
}

function formatInfo(info: ImageInfo): string[] {
  const values: string[] = [];
  if (info.file_format) values.push(info.file_format);
  if (info.color_space) values.push(info.color_space);
  const shot: string[] = [];
  if (info.iso !== undefined) shot.push(`ISO ${info.iso}`);
  if (info.aperture !== undefined) shot.push(`f/${info.aperture}`);
  if (info.shutter_seconds !== undefined) {
    shot.push(info.shutter_seconds < 1
      ? `1/${Math.round(1 / info.shutter_seconds)}s`
      : `${info.shutter_seconds}s`);
  }
  if (info.focal_length_mm !== undefined) shot.push(`${info.focal_length_mm}mm`);
  if (shot.length > 0) values.push(shot.join(" · "));
  return values;
}

function formatExposure(info: ImageInfo | null): string[] {
  return [
    `ISO ${info?.iso ?? "—"}`,
    `光圈 ${info?.aperture !== undefined ? `f/${info.aperture}` : "—"}`,
    `快门 ${info?.shutter_seconds !== undefined
      ? info.shutter_seconds < 1 ? `1/${Math.round(1 / info.shutter_seconds)}s` : `${info.shutter_seconds}s`
      : "—"}`,
  ];
}

export function HistogramPanel({ histogram, imageInfo }: HistogramPanelProps) {
  const data = histogram.data;
  return (
    <section className="histogram-panel" aria-label="当前效果直方图">
      <div className="histogram-heading">
        <strong><Icon name="activity" />直方图</strong>
        <span>{histogram.status === "updating" ? "更新中…" : "RGB · LOG"}</span>
      </div>
      {data ? (
        <>
          <svg viewBox="0 0 100 36" role="img" aria-label="RGB 亮度分布" preserveAspectRatio="none">
            <polyline data-channel="red" points={points(data.red)} />
            <polyline data-channel="green" points={points(data.green)} />
            <polyline data-channel="blue" points={points(data.blue)} />
          </svg>
          <div className="histogram-clipping">
            <span>阴影裁切 {(data.shadowClipping * 100).toFixed(1)}%</span>
            <span>高光裁切 {(data.highlightClipping * 100).toFixed(1)}%</span>
          </div>
        </>
      ) : <p>{histogram.status === "error" ? "直方图暂不可用" : "等待当前效果预览"}</p>}
      <div className="image-info" aria-label="基本参数">
        {imageInfo && formatInfo(imageInfo).map((value) => <span key={value}>{value}</span>)}
        {formatExposure(imageInfo).map((value) => <span key={value}>{value}</span>)}
      </div>
    </section>
  );
}
