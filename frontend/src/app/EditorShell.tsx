import { useCallback, useEffect, useRef, useState } from "react";
import { CanvasPane } from "../components/CanvasPane";
import { ChatPane } from "../components/ChatPane";
import { GalleryPane } from "../components/GalleryPane";
import { PanelPane } from "../components/PanelPane";
import { FEATURES } from "./featureFlags";
import type { LookliftClient } from "../api/client";
import type { ParamContract } from "../api/types";
import { createNeutralAnalysis } from "../panel/contractModel";
import { exportLookFile } from "../features/looks/lookActions";
import { editorStore, useEditorState } from "../store/editorStore";

type EditorShellProps = {
  chatEnabled?: boolean;
  engineLabel?: string;
  client?: LookliftClient;
  contract?: ParamContract;
};

export function EditorShell({
  chatEnabled = FEATURES.chatPane,
  engineLabel = "本地引擎已连接",
  client,
  contract,
}: EditorShellProps) {
  const editor = useEditorState();
  const [activeLookName, setActiveLookName] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const activeLookAnalysis = useRef(editor.analysis);
  const neutral = !editor.analysis && contract ? createNeutralAnalysis(contract) : undefined;
  const openImage = useCallback((path: string) => {
    if (!contract) {
      editorStore.setImagePath(path);
      return undefined;
    }
    const next = createNeutralAnalysis(contract);
    editorStore.openImage(path, next);
    return next;
  }, [contract]);
  const settleManualPreview = useCallback(() => editorStore.finalizePreview("manual"), []);
  const setRenderState = useCallback(editorStore.setRenderState, []);
  const activateLook = useCallback((name: string) => {
    activeLookAnalysis.current = editorStore.getSnapshot().analysis;
    setActiveLookName(name);
    setExportStatus(null);
  }, []);

  useEffect(() => {
    if (activeLookName && activeLookAnalysis.current !== editor.analysis) {
      setActiveLookName(null);
      setExportStatus(null);
    }
  }, [activeLookName, editor.analysis]);

  const exportActiveLook = async () => {
    if (!client || !activeLookName) return;
    setExporting(true);
    try {
      setExportStatus(`已导出：${await exportLookFile(client, activeLookName)}`);
    } catch (reason) {
      setExportStatus(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setExporting(false);
    }
  };

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
        <div className="app-actions">
          {exportStatus && <span title={exportStatus}>{exportStatus}</span>}
          <button
            className="export-button"
            type="button"
            disabled={!activeLookName || exporting}
            onClick={() => void exportActiveLook()}
          >{exporting ? "导出中…" : "导出预设"}</button>
        </div>
      </header>

      <section className="workbench" aria-label="照片编辑工作区">
        <ChatPane enabled={chatEnabled} />
        <CanvasPane
          client={client}
          analysis={editor.analysis ?? neutral}
          factor={editor.factor}
          onImagePathChange={openImage}
          onPreviewSettled={settleManualPreview}
          onRenderStateChange={setRenderState}
        />
        <PanelPane contract={contract} />
      </section>

      <GalleryPane client={client} onActiveLookChange={activateLook} />
    </main>
  );
}
