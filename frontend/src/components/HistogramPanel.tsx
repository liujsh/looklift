import type { ImageInfo } from "../api/types";
import type { HistogramState } from "../features/histogram/histogramController";

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
  if (info.iso !== undefined) values.push(`ISO ${info.iso}`);
  if (info.shutter_seconds !== undefined) {
    values.push(info.shutter_seconds < 1
      ? `1/${Math.round(1 / info.shutter_seconds)}s`
      : `${info.shutter_seconds}s`);
  }
  if (info.aperture !== undefined) values.push(`f/${info.aperture}`);
  if (info.focal_length_mm !== undefined) values.push(`${info.focal_length_mm}mm`);
  if (info.file_format) values.push(info.file_format);
  if (info.color_space) values.push(info.color_space);
  return values;
}

export function HistogramPanel({ histogram, imageInfo }: HistogramPanelProps) {
  const data = histogram.data;
  return (
    <section className="histogram-panel" aria-label="当前效果直方图">
      <div className="histogram-heading">
        <strong>直方图</strong>
        {histogram.status === "updating" && <span>更新中…</span>}
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
      <div className="image-info">
        {imageInfo ? formatInfo(imageInfo).map((value) => <span key={value}>{value}</span>) : <span>拍摄信息不可用</span>}
      </div>
    </section>
  );
}
