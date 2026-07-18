import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ComparisonView } from "./ComparisonView";

describe("ComparisonView", () => {
  it("叠放 before/after 并暴露可访问的对比位置滑杆", () => {
    const html = renderToStaticMarkup(
      <ComparisonView
        beforeUrl="blob:before"
        afterUrl="blob:after"
        position={37}
        onPositionChange={() => undefined}
      />,
    );

    expect(html).toContain('alt="调整前"');
    expect(html).toContain('src="blob:after"');
    expect(html).toContain('aria-label="原图与效果对比位置"');
    expect(html).toContain('value="37"');
    expect(html).toContain('--comparison-position:37%');
  });
});
