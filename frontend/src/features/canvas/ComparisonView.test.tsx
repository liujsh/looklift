import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { ComparisonView } from "./ComparisonView";

describe("ComparisonView", () => {
  it("默认单图按画布缩放变量展示完整效果图", () => {
    const html = renderToStaticMarkup(
      <ComparisonView
        beforeUrl="blob:before"
        afterUrl="blob:after"
        position={37}
        zoom={1.5}
        onPositionChange={() => undefined}
      />,
    );

    expect(html).toContain('data-mode="single"');
    expect(html).toContain("--canvas-zoom:1.5");
    expect(html).toContain('alt="效果"');
    expect(html).not.toContain("scale(");
    expect(html).not.toContain('alt="调整前"');
  });

  it("叠放 before/after 并暴露可访问的对比位置滑杆", () => {
    const html = renderToStaticMarkup(
      <ComparisonView
        beforeUrl="blob:before"
        afterUrl="blob:after"
        position={37}
        mode="split"
        onPositionChange={() => undefined}
      />,
    );

    expect(html).toContain('alt="调整前"');
    expect(html).toContain('src="blob:after"');
    expect(html).toContain('aria-label="原图与效果对比位置"');
    expect(html).toContain('value="37"');
    expect(html).toContain('--comparison-position:37%');
    expect(html).toContain("--canvas-zoom:1");
  });

  it("画布按容器 contain 整图，缩放改真实尺寸而不是裁切后再 scale", () => {
    const cssPath = fileURLToPath(new URL("../../theme/layout.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");

    expect(css).toMatch(/\.canvas-body\s*\{[^}]*container-type:\s*size/s);
    expect(css).toMatch(/\.canvas-stage\[data-mode="single"\] \.stage-frame img\s*\{[^}]*max-width:\s*calc\(100cqw \* var\(--canvas-zoom, 1\)\)/s);
    expect(css).toMatch(/\.canvas-stage\[data-mode="single"\] \.stage-frame img\s*\{[^}]*max-height:\s*calc\(100cqh \* var\(--canvas-zoom, 1\)\)/s);
    expect(css).toMatch(/\.comparison-view > img\s*\{[^}]*object-fit:\s*contain/s);
    expect(css).not.toMatch(/\.comparison-view[^{]*\{[^}]*aspect-ratio:\s*1\.159/s);
    expect(css).not.toMatch(/\.comparison-view > img\s*\{[^}]*object-fit:\s*cover/s);
    expect(css).not.toMatch(/\.canvas-stage\s*\{[^}]*transform:\s*scale/s);
  });
});
