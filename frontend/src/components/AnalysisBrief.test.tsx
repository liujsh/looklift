import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Analysis } from "../api/types";
import { AnalysisBrief } from "./AnalysisBrief";

describe("AnalysisBrief", () => {
  it("显示 AI 概述和操作步骤", () => {
    const analysis = {
      summary: "低反差暖调胶片感",
      steps: ["降低高光", "暖化中间调"],
    } as Analysis;

    const html = renderToStaticMarkup(<AnalysisBrief analysis={analysis} />);

    expect(html).toContain('aria-label="AI 分析说明"');
    expect(html).toContain("低反差暖调胶片感");
    expect(html).toContain("降低高光");
    expect(html).toContain("暖化中间调");
  });
});
