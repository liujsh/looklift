import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PanelPane } from "./PanelPane";

describe("PanelPane", () => {
  it("从固定映射渲染五个分组与全局强度 seam", () => {
    const html = renderToStaticMarkup(<PanelPane />);

    expect(html).toContain('data-control="factor"');
    expect(html).toContain("100%");
    expect(html.match(/data-section=/g)).toHaveLength(5);
    for (const label of ["基础", "色彩 HSL", "曲线", "分级", "效果"]) {
      expect(html).toContain(`>${label}<`);
    }
  });

  it("没有 analysis 时保留分组结构但明确等待回填", () => {
    const html = renderToStaticMarkup(<PanelPane />);

    expect(html).toContain("载入分析结果后显示参数");
    expect(html).toContain("导入照片后显示参数控件");
  });
});
