import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { HistogramPanel } from "./HistogramPanel";

describe("HistogramPanel", () => {
  it("显示 RGB 曲线、裁切提示和安全拍摄信息", () => {
    const bins = Array(256).fill(0).map((_, index) => index);
    const html = renderToStaticMarkup(<HistogramPanel
      histogram={{
        status: "ready",
        signature: "one",
        error: null,
        data: { red: bins, green: bins, blue: bins, shadowClipping: 0.02, highlightClipping: 0.03, pixelCount: 256 },
      }}
      imageInfo={{ iso: 200, aperture: 2.8, shutter_seconds: 0.008, file_format: "JPEG" }}
    />);

    expect(html).toContain('data-channel="red"');
    expect(html).toContain("阴影裁切 2.0%");
    expect(html).toContain("高光裁切 3.0%");
    expect(html).toContain("ISO 200");
    expect(html).toContain("f/2.8");
    expect(html).toContain("JPEG");
  });
});
