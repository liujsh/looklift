import { describe, expect, it } from "vitest";
import { addCurvePoint, moveCurvePoint, removeCurvePoint, sampleMonotoneCurve } from "./toneCurveModel";

describe("toneCurveModel", () => {
  it("增点会夹取范围、按 input 排序并替换同 input 点", () => {
    const points = [{ input: 0, output: 0 }, { input: 255, output: 255 }];
    expect(addCurvePoint(points, { input: 140, output: 170 })).toEqual([
      { input: 0, output: 0 }, { input: 140, output: 170 }, { input: 255, output: 255 },
    ]);
    expect(addCurvePoint(points, { input: -20, output: 300 })[0]).toEqual({ input: 0, output: 255 });
  });

  it("移动中间点不能越过相邻 input，端点 input 固定", () => {
    const points = [{ input: 0, output: 0 }, { input: 128, output: 150 }, { input: 255, output: 255 }];
    expect(moveCurvePoint(points, 1, { input: 300, output: 180 })[1]).toEqual({ input: 254, output: 180 });
    expect(moveCurvePoint(points, 0, { input: 60, output: 20 })[0]).toEqual({ input: 0, output: 20 });
  });

  it("只允许删除中间点且至少保留两个端点", () => {
    const points = [{ input: 0, output: 0 }, { input: 128, output: 150 }, { input: 255, output: 255 }];
    expect(removeCurvePoint(points, 1)).toEqual([{ input: 0, output: 0 }, { input: 255, output: 255 }]);
    expect(removeCurvePoint(points, 0)).toBe(points);
  });

  it("单调控制点的 Hermite 采样保持端点和单调性", () => {
    const samples = sampleMonotoneCurve([
      { input: 0, output: 0 }, { input: 80, output: 55 },
      { input: 170, output: 210 }, { input: 255, output: 255 },
    ], 12);

    expect(samples[0]).toEqual({ input: 0, output: 0 });
    expect(samples[samples.length - 1]).toEqual({ input: 255, output: 255 });
    expect(samples.every((point, index) => index === 0 || point.output >= samples[index - 1].output)).toBe(true);
  });
});
