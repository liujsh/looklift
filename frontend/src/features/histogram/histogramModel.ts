export type HistogramData = Readonly<{
  red: readonly number[];
  green: readonly number[];
  blue: readonly number[];
  shadowClipping: number;
  highlightClipping: number;
  pixelCount: number;
}>;

export function computeHistogram(pixels: Uint8ClampedArray): HistogramData {
  if (pixels.length % 4 !== 0) throw new Error("直方图输入必须是 RGBA 四通道数据");
  const red = Array<number>(256).fill(0);
  const green = Array<number>(256).fill(0);
  const blue = Array<number>(256).fill(0);
  let shadows = 0;
  let highlights = 0;
  for (let offset = 0; offset < pixels.length; offset += 4) {
    const r = pixels[offset];
    const g = pixels[offset + 1];
    const b = pixels[offset + 2];
    red[r] += 1;
    green[g] += 1;
    blue[b] += 1;
    if (r === 0 || g === 0 || b === 0) shadows += 1;
    if (r === 255 || g === 255 || b === 255) highlights += 1;
  }
  const pixelCount = pixels.length / 4;
  return Object.freeze({
    red: Object.freeze(red),
    green: Object.freeze(green),
    blue: Object.freeze(blue),
    shadowClipping: pixelCount ? shadows / pixelCount : 0,
    highlightClipping: pixelCount ? highlights / pixelCount : 0,
    pixelCount,
  });
}
