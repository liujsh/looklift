import { describe, expect, it } from "vitest";
import type { HistogramData } from "./histogramModel";
import { createHistogramController } from "./histogramController";

const histogram = (pixelCount: number): HistogramData => ({
  red: Array(256).fill(0), green: Array(256).fill(0), blue: Array(256).fill(0),
  shadowClipping: 0, highlightClipping: 0, pixelCount,
});

describe("histogramController", () => {
  it("保留上一结果更新，并丢弃旧签名的晚到结果", async () => {
    const resolvers: Array<(value: HistogramData) => void> = [];
    const controller = createHistogramController(
      () => new Promise<HistogramData>((resolve) => resolvers.push(resolve)),
    );

    const first = controller.update(new Blob(), "preview-1");
    resolvers[0](histogram(1));
    await first;
    expect(controller.getSnapshot()).toMatchObject({ status: "ready", signature: "preview-1" });

    const stale = controller.update(new Blob(), "preview-2");
    const current = controller.update(new Blob(), "preview-3");
    expect(controller.getSnapshot()).toMatchObject({ status: "updating", data: { pixelCount: 1 } });
    resolvers[1](histogram(2));
    await stale;
    expect(controller.getSnapshot().signature).toBe("preview-1");
    resolvers[2](histogram(3));
    await current;
    expect(controller.getSnapshot()).toMatchObject({ status: "ready", signature: "preview-3", data: { pixelCount: 3 } });
  });

  it("计算失败只降级直方图状态", async () => {
    const controller = createHistogramController(async () => { throw new Error("decode failed"); });
    await controller.update(new Blob(), "preview-1");
    expect(controller.getSnapshot()).toMatchObject({ status: "error", error: "decode failed" });
  });
});
