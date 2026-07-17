import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (name: string) => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

describe("统一桌面暗房主题", () => {
  it("颜色和字体只在 tokens 中定义，组件样式不散落十六进制色值", () => {
    const tokens = read("./tokens.css");
    const layout = read("./layout.css");
    const app = read("../App.css");

    for (const token of ["--color-paper", "--color-stage", "--color-accent", "--font-display", "--font-data"]) {
      expect(tokens).toContain(token);
    }
    expect(layout).not.toMatch(/#[0-9a-f]{3,8}/i);
    expect(app).not.toMatch(/#[0-9a-f]{3,8}/i);
  });

  it("桌面、紧凑窗口和低动态模式都有明确边界", () => {
    const layout = read("./layout.css");
    const app = read("../App.css");

    expect(layout).toContain("@media (max-width: 1100px)");
    expect(layout).toContain("@media (max-width: 820px)");
    expect(layout).toContain("@media (prefers-reduced-motion: reduce)");
    expect(app).toContain(":focus-visible");
  });

  it("图库以接触印样带作为唯一视觉签名", () => {
    const layout = read("./layout.css");

    expect(layout).toMatch(/\.contact-sheet::before[^}]*repeating-linear-gradient/s);
    expect(layout).toMatch(/\.look-card:hover:not\(:disabled\)[^}]*translateY\(-2px\)/s);
  });
});
