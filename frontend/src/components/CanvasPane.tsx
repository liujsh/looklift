import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import type { LookliftClient } from "../api/client";
import type { Analysis, JsonObject } from "../api/types";
import type { EditorState } from "../store/editorStore";
import { ComparisonView } from "../features/canvas/ComparisonView";
import {
  canvasErrorMessage,
  firstSupportedImage,
  loadPreviewPair,
  previewSignature,
  type CanvasApi,
} from "../features/canvas/canvasModel";
import { listenForTauriDrops } from "../features/canvas/tauriDrop";
import { analyzeImage } from "../features/analysis/analyzeWorkflow";
import { createPreviewScheduler, type PreviewScheduler } from "../features/preview/previewScheduler";

type CanvasPhase = "idle" | "loading" | "ready" | "error";
type PreviewUrls = { before: string; after: string };
type LivePreviewRequest = {
  path: string;
  analysis: JsonObject;
  factor: number;
  signature: string;
};

type CanvasPaneProps = {
  client?: LookliftClient;
  analysis?: JsonObject;
  factor?: number;
  onImagePathChange?(path: string): JsonObject | void;
  onPreviewSettled?(): void;
  onAnalysisComplete?(analysis: Analysis): void;
  onRenderStateChange?(render: EditorState["render"]): void;
  onPreviewRendered?(analysis: JsonObject): void;
  analysisDisabled?: boolean;
};

export function CanvasPane({
  client,
  analysis = {},
  factor = 1,
  onImagePathChange,
  onPreviewSettled,
  onAnalysisComplete,
  onRenderStateChange,
  onPreviewRendered,
  analysisDisabled = false,
}: CanvasPaneProps) {
  const paneRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const urlsRef = useRef<PreviewUrls | null>(null);
  const requestRef = useRef(0);
  const schedulerRef = useRef<PreviewScheduler<LivePreviewRequest> | null>(null);
  const previewCallbacksRef = useRef({ onPreviewSettled, onRenderStateChange, onPreviewRendered });
  const analysisControllerRef = useRef<AbortController | null>(null);
  const lastRenderedSignatureRef = useRef<string | null>(null);
  const loadPathRef = useRef<(path: string) => Promise<void>>(async () => undefined);
  const [phase, setPhase] = useState<CanvasPhase>("idle");
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [urls, setUrls] = useState<PreviewUrls | null>(null);
  const [position, setPosition] = useState(50);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  previewCallbacksRef.current = { onPreviewSettled, onRenderStateChange, onPreviewRendered };

  const replaceUrls = useCallback((next: PreviewUrls | null) => {
    if (urlsRef.current) {
      URL.revokeObjectURL(urlsRef.current.before);
      URL.revokeObjectURL(urlsRef.current.after);
    }
    urlsRef.current = next;
    setUrls(next);
  }, []);

  const replaceAfter = useCallback((blob: Blob) => {
    const current = urlsRef.current;
    if (!current) return;
    URL.revokeObjectURL(current.after);
    const next = { before: current.before, after: URL.createObjectURL(blob) };
    urlsRef.current = next;
    setUrls(next);
  }, []);

  useEffect(() => {
    if (!client) return;
    const scheduler = createPreviewScheduler<LivePreviewRequest, Blob>({
      delay: 160,
      execute: (request, signal) => client.preview({
        path: request.path,
        analysis: request.analysis,
        factor: request.factor,
      }, signal),
      onDispatch: () => {
        previewCallbacksRef.current.onPreviewSettled?.();
        previewCallbacksRef.current.onRenderStateChange?.({ status: "rendering", error: null });
      },
      onResult: (blob, request) => {
        replaceAfter(blob);
        lastRenderedSignatureRef.current = request.signature;
        setError(null);
        previewCallbacksRef.current.onRenderStateChange?.({ status: "ready", error: null });
        previewCallbacksRef.current.onPreviewRendered?.(request.analysis);
      },
      onError: (reason) => {
        const message = canvasErrorMessage(reason);
        setError(message);
        previewCallbacksRef.current.onRenderStateChange?.({ status: "error", error: message });
      },
    });
    schedulerRef.current = scheduler;
    return () => {
      scheduler.dispose();
      if (schedulerRef.current === scheduler) schedulerRef.current = null;
    };
  }, [client, replaceAfter]);

  const loadPath = useCallback(async (path: string) => {
    if (!client) return;
    analysisControllerRef.current?.abort();
    analysisControllerRef.current = null;
    setAnalyzing(false);
    schedulerRef.current?.cancel();
    const nextAnalysis = onImagePathChange?.(path) ?? analysis;
    const requestId = ++requestRef.current;
    setLoadedPath(null);
    setPhase("loading");
    setError(null);
    onRenderStateChange?.({ status: "rendering", error: null });
    try {
      const pair = await loadPreviewPair(client as CanvasApi, path, nextAnalysis, factor);
      const next = {
        before: URL.createObjectURL(pair.before),
        after: URL.createObjectURL(pair.after),
      };
      if (requestId !== requestRef.current) {
        URL.revokeObjectURL(next.before);
        URL.revokeObjectURL(next.after);
        return;
      }
      replaceUrls(next);
      setLoadedPath(path);
      lastRenderedSignatureRef.current = previewSignature(path, nextAnalysis, factor);
      setPhase("ready");
      onRenderStateChange?.({ status: "ready", error: null });
    } catch (reason) {
      if (requestId !== requestRef.current) return;
      setError(canvasErrorMessage(reason));
      setPhase("error");
      onRenderStateChange?.({ status: "error", error: canvasErrorMessage(reason) });
    }
  }, [analysis, client, factor, onImagePathChange, onRenderStateChange, replaceUrls]);
  loadPathRef.current = loadPath;

  const runAnalysis = async () => {
    if (!client || !loadedPath || analyzing) return;
    const controller = new AbortController();
    analysisControllerRef.current?.abort();
    analysisControllerRef.current = controller;
    setAnalyzing(true);
    setError(null);
    try {
      const result = await analyzeImage(client, loadedPath, { signal: controller.signal });
      if (!controller.signal.aborted) onAnalysisComplete?.(result);
    } catch (reason) {
      if (!(reason instanceof DOMException && reason.name === "AbortError")) {
        setError(canvasErrorMessage(reason));
      }
    } finally {
      if (analysisControllerRef.current === controller) {
        analysisControllerRef.current = null;
        setAnalyzing(false);
      }
    }
  };

  useEffect(() => {
    if (!client || !loadedPath || phase !== "ready") return;
    const signature = previewSignature(loadedPath, analysis, factor);
    if (signature === lastRenderedSignatureRef.current) return;
    schedulerRef.current?.schedule({ path: loadedPath, analysis, factor, signature });
  }, [analysis, client, factor, loadedPath, phase]);

  const uploadFile = useCallback(async (file: File) => {
    if (!client) return;
    if (!firstSupportedImage([file.name])) {
      setError("不支持的图片格式，请选择 JPEG、PNG、WebP 或 TIFF");
      setPhase("error");
      return;
    }
    setPhase("loading");
    setError(null);
    try {
      const { path } = await client.upload(file);
      await loadPath(path);
    } catch (reason) {
      setError(canvasErrorMessage(reason));
      setPhase("error");
    }
  }, [client, loadPath]);

  useEffect(() => {
    const element = paneRef.current;
    if (!element || !client) return;
    let cancelled = false;
    let unlisten: (() => void) | undefined;
    void listenForTauriDrops(element, {
      onActive: setDragActive,
      onPath: (path) => { void loadPathRef.current(path); },
    })
      .then((stop) => {
        if (cancelled) stop();
        else unlisten = stop;
      })
      .catch(() => {
        // 普通浏览器没有 Tauri runtime，继续使用 HTML5 file 回退。
      });
    return () => {
      cancelled = true;
      unlisten?.();
    };
  }, [client]);

  useEffect(() => () => {
    requestRef.current += 1;
    analysisControllerRef.current?.abort();
    if (urlsRef.current) {
      URL.revokeObjectURL(urlsRef.current.before);
      URL.revokeObjectURL(urlsRef.current.after);
    }
  }, []);

  const onDrop = (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    setDragActive(false);
    const file = event.dataTransfer.files[0];
    if (file) void uploadFile(file);
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (file) void uploadFile(file);
    event.currentTarget.value = "";
  };

  return (
    <section
      ref={paneRef}
      className="canvas-pane"
      data-pane="canvas"
      data-phase={phase}
      data-drag-active={dragActive}
      aria-label="照片画布"
      onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={() => setDragActive(false)}
      onDrop={onDrop}
    >
      <div className="canvas-toolbar" aria-label="画布工具">
        <span>适合窗口</span>
        {phase === "ready" ? (
          <button type="button" disabled={analyzing || analysisDisabled} onClick={() => void runAnalysis()}>
            {analyzing ? "AI 分析中…" : "AI 分析"}
          </button>
        ) : <span>100%</span>}
      </div>

      {phase === "ready" && urls ? (
        <ComparisonView
          beforeUrl={urls.before}
          afterUrl={urls.after}
          position={position}
          onPositionChange={setPosition}
        />
      ) : (
        <div className="canvas-empty" role={phase === "error" ? "alert" : undefined}>
          <div className="drop-outline" aria-hidden="true"><span>{phase === "loading" ? "…" : "＋"}</span></div>
          <h1>{phase === "loading" ? "正在生成对比预览" : dragActive ? "松开以载入照片" : "把照片拖到这里"}</h1>
          <p>{error ?? "或点击选择文件 · JPEG、PNG、WebP、TIFF"}</p>
          <button type="button" onClick={() => inputRef.current?.click()} disabled={!client || phase === "loading"}>
            选择照片
          </button>
          <input ref={inputRef} className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp,image/tiff" onChange={onFileChange} />
        </div>
      )}

      {dragActive && <div className="drop-overlay" aria-hidden="true">放到画布中</div>}
      {phase === "ready" && error && <div className="live-preview-error" role="alert">{error}</div>}
      <div className="canvas-footer" aria-hidden="true">
        <span>原图</span><span className="diff-track"><i style={{ width: `${position}%` }} /></span><span>效果</span>
      </div>
    </section>
  );
}
