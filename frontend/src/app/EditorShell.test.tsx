import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { createEditorStore } from "../store/editorStore";
import type { ChatWorkflow } from "../features/chat/chatWorkflow";
import type { SessionCoordinator } from "../features/sessions/sessionCoordinator";
import type { Analysis } from "../api/types";
import type { LookliftClient } from "../api/client";
import { EditorShell } from "./EditorShell";

describe("EditorShell", () => {
  it("保留四个 pane 的稳定语义结构", () => {
    const html = renderToStaticMarkup(<EditorShell store={createEditorStore()} />);

    expect(html).toContain('aria-label="照片编辑工作区"');
    expect(html).toContain('data-pane="chat"');
    expect(html).toContain('data-pane="canvas"');
    expect(html).toContain('data-pane="controls"');
  });

  it("聊天功能默认开启且仍可通过 seam 故障回退", () => {
    const disabled = renderToStaticMarkup(<EditorShell store={createEditorStore()} chatEnabled={false} />);
    const enabled = renderToStaticMarkup(<EditorShell store={createEditorStore()} />);

    expect(disabled).toContain('data-chat-enabled="false"');
    expect(disabled).toMatch(/data-pane="chat"[^>]*hidden=""/);
    expect(enabled).toContain('data-chat-enabled="true"');
    expect(enabled).not.toMatch(/data-pane="chat"[^>]*hidden=""/);
  });

  it("每个编辑壳只读取显式传入的 Store", () => {
    const first = createEditorStore();
    const second = createEditorStore();
    first.setFactor(0.35);
    second.setFactor(0.8);

    const firstHtml = renderToStaticMarkup(<EditorShell store={first} />);
    const secondHtml = renderToStaticMarkup(<EditorShell store={second} />);

    expect(firstHtml).toContain("35%");
    expect(firstHtml).not.toContain("80%");
    expect(secondHtml).toContain("80%");
    expect(secondHtml).not.toContain("35%");
  });

  it("使用 StudioRuntime 注入的聊天工作流", () => {
    const workflow = {
      getSnapshot: () => ({
        phase: "idle", messages: [{ role: "assistant", content: "来自所属运行时" }],
        lastResponse: null, error: null, round: 0, stopReason: null,
      }),
      subscribe: vi.fn(() => () => undefined),
    } as unknown as ChatWorkflow;

    const html = renderToStaticMarkup(<EditorShell store={createEditorStore()} workflow={workflow} />);

    expect(html).toContain("来自所属运行时");
  });

  it("把当前成片作为主导出，并在候选未确认时阻止混淆正式版本", () => {
    const coordinator = { getSessionId: () => "session-1" } as unknown as SessionCoordinator;
    const client = {} as LookliftClient;
    const analysis = { summary: "正式版本", steps: [] } as unknown as Analysis;
    const ready = createEditorStore();
    ready.restoreSession("C:/照片/旅途.jpg", analysis);

    const readyHtml = renderToStaticMarkup(
      <EditorShell store={ready} client={client} coordinator={coordinator} />,
    );
    expect(readyHtml).toMatch(/<button[^>]*class="export-button"[^>]*>导出成片<\/button>/);
    expect(readyHtml).not.toMatch(/class="export-button"[^>]*disabled/);
    expect(readyHtml).toContain("选择位置导出成片…");

    const pending = createEditorStore();
    pending.restoreSession("C:/照片/旅途.jpg", analysis);
    pending.beginPendingPreview(analysis, [], [], 1);
    const pendingHtml = renderToStaticMarkup(
      <EditorShell store={pending} client={client} coordinator={coordinator} />,
    );
    expect(pendingHtml).toMatch(/class="export-button"[^>]*disabled[^>]*>先确认候选<\/button>/);
  });

  it("布局轨道允许画布收缩且各工作区自行处理溢出", () => {
    const cssPath = fileURLToPath(new URL("../theme/layout.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");

    expect(css).toMatch(/grid-template-columns:[^;]*minmax\(0, 1fr\)/);
    expect(css).toMatch(/\.workbench\s*\{[^}]*min-width:\s*0[^}]*min-height:\s*0[^}]*overflow:\s*hidden/s);
    expect(css).toMatch(/\.contact-sheet\s*\{[^}]*overflow-x:\s*auto/s);
  });

  it("聊天折叠和窄窗口时画布与控制面板保持稳定轨道", () => {
    const cssPath = fileURLToPath(new URL("../theme/layout.css", import.meta.url));
    const css = readFileSync(cssPath, "utf8");

    expect(css).toMatch(/\.workbench\s*\{[^}]*grid-template-areas:\s*"chat canvas controls"/s);
    expect(css).toMatch(/\.chat-pane\s*\{[^}]*grid-area:\s*chat/s);
    expect(css).toMatch(/\.canvas-pane\s*\{[^}]*grid-area:\s*canvas/s);
    expect(css).toMatch(/\.panel-pane\s*\{[^}]*grid-area:\s*controls/s);
    expect(css).toMatch(/:has\(\.chat-pane\[data-collapsed="true"\]\)\s*\{[^}]*--chat-track:\s*46px/s);
    expect(css).toMatch(/@media\s*\(max-width:\s*820px\)[\s\S]*?\.workbench\s*\{[^}]*grid-template-areas:\s*"chat canvas controls"/s);
  });
});
