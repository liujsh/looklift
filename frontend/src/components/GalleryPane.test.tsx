import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { LookSummary } from "../api/types";
import { GalleryPane } from "./GalleryPane";

const looks: LookSummary[] = [
  { name: "青橙经典", summary: "冷暖对比", has_preset: false, source: "built_in", readonly: true },
  { name: "柔和胶片", summary: "柔和颗粒", has_preset: false, source: "built_in", readonly: true },
  { name: "我的收藏", summary: "自定义", has_preset: true, source: "user", readonly: false },
];

describe("GalleryPane", () => {
  it("默认显示内置模板卡片并保留用户来源 tab", () => {
    const html = renderToStaticMarkup(<GalleryPane initialLooks={looks} />);

    expect(html).toContain('aria-pressed="true">内置模板');
    expect(html).toContain('aria-pressed="false">我的风格');
    expect(html).toContain("青橙经典");
    expect(html).toContain("柔和胶片");
    expect(html).not.toContain("我的收藏");
    expect(html.match(/data-source="built_in"/g)).toHaveLength(2);
    expect(html).toContain('aria-label="收藏名称"');
    for (const action of ["报告", "预设", "sidecar"]) {
      expect(html).toContain(`>${action}<`);
    }
  });
});
