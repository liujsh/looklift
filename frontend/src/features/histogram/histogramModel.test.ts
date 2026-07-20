import { describe, expect, it } from "vitest";
import { computeHistogram } from "./histogramModel";

describe("computeHistogram", () => {
  it("统计 256 档 RGB 并给出黑白场裁切比例", () => {
    const pixels = new Uint8ClampedArray([
      0, 10, 255, 255,
      255, 10, 20, 255,
      100, 255, 0, 255,
      100, 10, 20, 255,
    ]);

    const result = computeHistogram(pixels);

    expect(result.red[0]).toBe(1);
    expect(result.red[100]).toBe(2);
    expect(result.red[255]).toBe(1);
    expect(result.green[10]).toBe(3);
    expect(result.blue[0]).toBe(1);
    expect(result.shadowClipping).toBe(0.5);
    expect(result.highlightClipping).toBe(0.75);
    expect(result.pixelCount).toBe(4);
  });

  it("拒绝不是 RGBA 四通道的数据", () => {
    expect(() => computeHistogram(new Uint8ClampedArray([1, 2, 3]))).toThrow("RGBA");
  });
});
