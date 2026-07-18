import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EditorShell } from "./EditorShell";

describe("EditorShell", () => {
  it("保留四个 pane 的稳定语义结构", () => {
    const html = renderToStaticMarkup(<EditorShell />);

    expect(html).toContain('aria-label="照片编辑工作区"');
    expect(html).toContain('data-pane="chat"');
    expect(html).toContain('data-pane="canvas"');
    expect(html).toContain('data-pane="controls"');
    expect(html).toContain('data-pane="gallery"');
  });

  it("聊天功能默认关闭但 seam 仍保留在 DOM", () => {
    const disabled = renderToStaticMarkup(<EditorShell />);
    const enabled = renderToStaticMarkup(<EditorShell chatEnabled />);

    expect(disabled).toContain('data-chat-enabled="false"');
    expect(disabled).toMatch(/data-pane="chat"[^>]*hidden=""/);
    expect(enabled).toContain('data-chat-enabled="true"');
    expect(enabled).not.toMatch(/data-pane="chat"[^>]*hidden=""/);
  });

  it("布局轨道允许画布收缩且各工作区自行处理溢出", () => {
    const cssPath = fileURLToPath(new URL("../theme/layout.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");

    expect(css).toMatch(/grid-template-columns:[^;]*minmax\(0, 1fr\)/);
    expect(css).toMatch(/\.workbench\s*\{[^}]*min-width:\s*0[^}]*min-height:\s*0[^}]*overflow:\s*hidden/s);
    expect(css).toMatch(/\.contact-sheet\s*\{[^}]*overflow-x:\s*auto/s);
  });
});
