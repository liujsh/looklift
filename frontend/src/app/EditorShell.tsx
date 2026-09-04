import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { isTauri } from "@tauri-apps/api/core";
import { CanvasPane } from "../components/CanvasPane";
import { ChatPane } from "../components/ChatPane";
import { PanelPane } from "../components/PanelPane";
import { FEATURES } from "./featureFlags";
import type { LookliftClient } from "../api/client";
import type { ImageInfo, ParamContract } from "../api/types";
import { createNeutralAnalysis } from "../panel/contractModel";
import { createChatWorkflow, type ChatWorkflow } from "../features/chat/chatWorkflow";
import { createSessionCoordinator, type SessionCoordinator } from "../features/sessions/sessionCoordinator";
import { createHistogramController } from "../features/histogram/histogramController";
import { calculateHistogramInWorker } from "../features/histogram/histogramWorkerClient";
import { Icon } from "../platform/icons";
import type { EditorStore } from "../store/editorStore";
import { useEditorState } from "../store/editorStore";

type EditorShellProps = {
  store: EditorStore;
  active?: boolean;
  chatEnabled?: boolean;
  engineLabel?: string;
  client?: LookliftClient;
  contract?: ParamContract;
  coordinator?: SessionCoordinator | null;
  workflow?: ChatWorkflow | null;
  onHome?(): void;
  onOpenSettings?(): void;
};

export function EditorShell({
  store,
  active = true,
  chatEnabled = FEATURES.chatPane,
  engineLabel = "本地引擎已连接",
  client,
  contract,
  coordinator: providedCoordinator,
  workflow: providedWorkflow,
  onHome,
  onOpenSettings,
}: EditorShellProps) {
  const editor = useEditorState(store);
  const [exporting, setExporting] = useState(false);
  const [exportStatus, setExportStatus] = useState<string | null>(null);
  const [providerLabel, setProviderLabel] = useState("正在读取…");
  const [exportDirectory, setExportDirectory] = useState("");
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
  const ownedCoordinator = useMemo(
    () => providedCoordinator === undefined && client ? createSessionCoordinator(client, store) : null,
    [client, providedCoordinator, store],
  );
  const sessionCoordinator = providedCoordinator === undefined ? ownedCoordinator : providedCoordinator;
  const sessionReady = Boolean(client && sessionCoordinator?.getSessionId());
  const ownedWorkflow = useMemo(
    () => providedWorkflow === undefined && client ? createChatWorkflow(client, store, {
      onMessagesOnly: (exchange) => sessionCoordinator?.recordMessages(exchange),
    }) : null,
    [client, providedWorkflow, sessionCoordinator, store],
  );
  const chatWorkflow = providedWorkflow === undefined ? ownedWorkflow : providedWorkflow;
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
  useEffect(() => {
    return () => ownedWorkflow?.dispose();
  }, [ownedWorkflow]);

  useEffect(() => {
    if (!client) return;
    let cancelled = false;
    void client.config().then((current) => {
      if (!cancelled) {
        setProviderLabel(current.provider === "auto" ? "自动选择（调用时确定）" : current.provider);
        setExportDirectory(current.export_dir || "");
      }
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

  const exportCurrentPhoto = async () => {
    const sessionId = sessionCoordinator?.getSessionId();
    if (!client || !sessionId || editor.pendingPreview) return;
    setExporting(true);
    setExportStatus(null);
    try {
      const result = await client.exportSession(sessionId);
      setExportStatus(`成片已保存：${result.path}`);
    } catch (reason) {
      setExportStatus(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setExporting(false);
    }
  };

  const exportCurrentPhotoTo = async () => {
    const sessionId = sessionCoordinator?.getSessionId();
    if (!client || !sessionId || editor.pendingPreview) return;
    if (!isTauri()) {
      setExportStatus("浏览器开发模式不能选择本地输出目录");
      return;
    }
    try {
      const selected = await open({
        multiple: false,
        directory: true,
        title: "选择成片输出目录",
        defaultPath: exportDirectory || undefined,
      });
      if (typeof selected !== "string") return;
      setExporting(true);
      setExportStatus(null);
      const result = await client.exportSession(sessionId, { output_dir: selected });
      setExportDirectory(selected);
      setExportStatus(`成片已保存：${result.path}`);
    } catch (reason) {
      setExportStatus(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setExporting(false);
    }
  };

  const exportDisabled = !sessionReady || exporting || editor.pendingPreview !== null;
  const exportTitle = editor.pendingPreview
    ? "请先保留或放弃当前候选，再导出正式版本"
    : !sessionReady
      ? "打开照片并建立正式版本后即可导出"
      : "保存当前正式版本为高质量 JPEG";
  const formatChip = [imageInfo?.file_format?.toUpperCase(), imageInfo?.color_space].filter(Boolean).join(" · ");

  return (
    <main className="editor-shell" data-chat-enabled={chatEnabled}>
      {/* 原型：品牌标只在标签栏出现一次，这里是文件元信息栏。 */}
      <header className="app-bar" data-tauri-drag-region>
        <div className="app-bar-meta">
          <span className="workspace-name" title={editor.imagePath ?? undefined}>
            {editor.imagePath ? fileName(editor.imagePath) : "未命名照片"}
          </span>
          {formatChip && <span className="format-chip">{formatChip}</span>}
          <span className="engine-status" title={engineLabel}>
            <i aria-hidden="true" />
            <span>{engineLabel}</span>
          </span>
        </div>
        <div className="app-actions">
          {exportStatus && (
            <span className="export-status" role="status" aria-live="polite" title={exportStatus}>
              <Icon name="info" />{exportStatus}
            </span>
          )}
          {sessionReady && (
            <details className="export-menu">
              <summary><Icon name="download" />更多导出<Icon name="chevron-down" /></summary>
              <div className="export-menu-popover">
                <button
                  type="button"
                  disabled={exportDisabled}
                  onClick={() => void exportCurrentPhotoTo()}
                >选择位置导出成片…</button>
              </div>
            </details>
          )}
          <button
            className="export-button"
            type="button"
            disabled={exportDisabled}
            title={exportTitle}
            onClick={() => void exportCurrentPhoto()}
          >
            <Icon name="check" />
            {exporting ? "导出中…" : editor.pendingPreview ? "先确认候选" : "导出成片"}
          </button>
        </div>
      </header>

      <section className="workbench" aria-label="照片编辑工作区">
        <ChatPane
          enabled={chatEnabled}
          workflow={chatWorkflow}
          coordinator={sessionCoordinator}
          providerLabel={providerLabel}
          renderStatus={editor.render.status}
          client={client}
          onHome={onHome}
          onOpenSettings={onOpenSettings}
        />
        <CanvasPane
          active={active}
          imagePath={editor.imagePath}
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
    </main>
  );
}

function fileName(path: string): string {
  return path.split(/[\\/]/).pop() ?? path;
}
