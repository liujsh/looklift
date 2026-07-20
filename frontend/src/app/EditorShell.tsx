import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { CanvasPane } from "../components/CanvasPane";
import { ChatPane } from "../components/ChatPane";
import { GalleryPane } from "../components/GalleryPane";
import { PanelPane } from "../components/PanelPane";
import { FEATURES } from "./featureFlags";
import type { LookliftClient } from "../api/client";
import type { ImageInfo, ParamContract } from "../api/types";
import { createNeutralAnalysis } from "../panel/contractModel";
import { exportLookFile, isCurrentLookSnapshot } from "../features/looks/lookActions";
import { createChatWorkflow } from "../features/chat/chatWorkflow";
import { createSessionCoordinator } from "../features/sessions/sessionCoordinator";
import { createHistogramController } from "../features/histogram/histogramController";
import { calculateHistogramInWorker } from "../features/histogram/histogramWorkerClient";
import type { EditorStore } from "../store/editorStore";
import { useEditorState } from "../store/editorStore";

type EditorShellProps = {
  store: EditorStore;
  active?: boolean;
  chatEnabled?: boolean;
  engineLabel?: string;
  client?: LookliftClient;
  contract?: ParamContract;
};

export function EditorShell({
  store,
  active = true,
  chatEnabled = FEATURES.chatPane,
  engineLabel = "本地引擎已连接",
  client,
  contract,
}: EditorShellProps) {
  const editor = useEditorState(store);
  const [activeLookName, setActiveLookName] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [providerLabel, setProviderLabel] = useState("正在读取…");
  const [imageInfo, setImageInfo] = useState<ImageInfo | null>(null);
  const histogramController = useMemo(
    () => createHistogramController(calculateHistogramInWorker),
    [],
  );
  const histogram = useSyncExternalStore(
    histogramController.subscribe,
    histogramController.getSnapshot,
    histogramController.getSnapshot,
  );
  const manualCommitPending = useRef(false);
  const sessionCoordinator = useMemo(
    () => client ? createSessionCoordinator(client, store) : null,
    [client, store],
  );
  const chatWorkflow = useMemo(
    () => client ? createChatWorkflow(client, store, {
      onMessagesOnly: (exchange) => sessionCoordinator?.recordMessages(exchange),
    }) : null,
    [client, sessionCoordinator, store],
  );
  const activeLookSnapshot = useRef({ analysis: editor.analysis, factor: editor.factor });
  const neutral = !editor.analysis && contract ? createNeutralAnalysis(contract) : undefined;
  const openImage = useCallback((path: string) => {
    if (!contract) {
      store.setImagePath(path);
      return undefined;
    }
    const next = createNeutralAnalysis(contract);
    store.openImage(path, next);
    void sessionCoordinator?.open(path, next)
      .then((snapshot) => chatWorkflow?.restoreMessages(snapshot.messages))
      .catch((reason) => {
        store.setRenderState({
          status: "error",
          error: reason instanceof Error ? reason.message : String(reason),
        });
      });
    return next;
  }, [chatWorkflow, contract, sessionCoordinator, store]);
  const persistFormal = useCallback((analysis: Parameters<typeof store.commitAnalysis>[0], source: "manual" | "library" | "analysis") => {
    void sessionCoordinator?.commitFormal(analysis, source).catch((reason) => {
      setExportStatus(`版本保存失败：${reason instanceof Error ? reason.message : String(reason)}`);
    });
  }, [sessionCoordinator]);
  const settleManualPreview = useCallback(() => {
    manualCommitPending.current = store.finalizePreview("manual");
  }, [store]);
  const persistRenderedManual = useCallback((analysis: Parameters<typeof store.commitAnalysis>[0]) => {
    if (!manualCommitPending.current) return;
    manualCommitPending.current = false;
    persistFormal(analysis, "manual");
  }, [persistFormal]);
  const applyAnalysis = useCallback((analysis: Parameters<typeof store.commitAnalysis>[0]) => {
    store.setFactor(1);
    if (store.commitAnalysis(analysis, "ai")) persistFormal(analysis, "analysis");
  }, [persistFormal, store]);
  const setRenderState = useCallback(store.setRenderState, [store]);
  const activateLook = useCallback((name: string) => {
    const current = store.getSnapshot();
    activeLookSnapshot.current = { analysis: current.analysis, factor: current.factor };
    setActiveLookName(name);
    setExportStatus(null);
  }, [store]);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    void client.config().then((current) => {
      if (!cancelled) setProviderLabel(
        current.provider === "auto" ? "自动选择（调用时确定）" : current.provider,
      );
    }).catch(() => { if (!cancelled) setProviderLabel("配置读取失败"); });
    return () => { cancelled = true; };
  }, [client]);

  useEffect(() => {
    histogramController.reset();
    setImageInfo(null);
    if (!client || !editor.imagePath) return;
    const path = editor.imagePath;
    let cancelled = false;
    void client.imageInfo(path).then((info) => {
      if (!cancelled && store.getSnapshot().imagePath === path) setImageInfo(info);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [client, editor.imagePath, histogramController, store]);

  useEffect(() => {
    if (activeLookName && !isCurrentLookSnapshot(
      activeLookSnapshot.current,
      editor.analysis,
      editor.factor,
    )) {
      setActiveLookName(null);
      setExportStatus(null);
    }
  }, [activeLookName, editor.analysis, editor.factor]);

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
        <ChatPane
          enabled={chatEnabled}
          workflow={chatWorkflow}
          coordinator={sessionCoordinator}
          providerLabel={providerLabel}
          renderStatus={editor.render.status}
        />
        <CanvasPane
          active={active}
          client={client}
          analysis={editor.displayAnalysis ?? neutral}
          factor={editor.factor}
          onImagePathChange={openImage}
          onPreviewSettled={settleManualPreview}
          onAnalysisComplete={applyAnalysis}
          onRenderStateChange={setRenderState}
          onPreviewRendered={(analysis) => persistRenderedManual(analysis as Parameters<typeof store.commitAnalysis>[0])}
          onEffectPreview={(blob, signature) => void histogramController.update(blob, signature)}
          analysisDisabled={editor.pendingPreview !== null || editor.activeAiRequestId !== null}
        />
        <PanelPane store={store} contract={contract} onFormalAnalysis={persistFormal} histogram={histogram} imageInfo={imageInfo} />
      </section>

      <GalleryPane store={store} client={client} onActiveLookChange={activateLook} onFormalAnalysis={persistFormal} />
    </main>
  );
}
