import { CanvasPane } from "../components/CanvasPane";
import { ChatPane } from "../components/ChatPane";
import { GalleryPane } from "../components/GalleryPane";
import { PanelPane } from "../components/PanelPane";
import { FEATURES } from "./featureFlags";
import type { LookliftClient } from "../api/client";

type EditorShellProps = {
  chatEnabled?: boolean;
  engineLabel?: string;
  client?: LookliftClient;
};

export function EditorShell({
  chatEnabled = FEATURES.chatPane,
  engineLabel = "本地引擎已连接",
  client,
}: EditorShellProps) {
  return (
    <main className="editor-shell" data-chat-enabled={chatEnabled}>
      <header className="app-bar" data-tauri-drag-region>
        <div className="brand-lockup" data-tauri-drag-region>
          <span className="brand-mark" aria-hidden="true">L</span>
          <strong>looklift</strong>
          <span className="workspace-name">未命名照片</span>
        </div>
        <div className="engine-status" title={engineLabel}>
          <span aria-hidden="true" />
          引擎已连接
        </div>
        <button className="export-button" type="button" disabled>导出</button>
      </header>

      <section className="workbench" aria-label="照片编辑工作区">
        <ChatPane enabled={chatEnabled} />
        <CanvasPane client={client} />
        <PanelPane />
      </section>

      <GalleryPane />
    </main>
  );
}
