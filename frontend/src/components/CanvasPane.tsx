import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import type { LookliftClient } from "../api/client";
import type { Analysis, JsonObject } from "../api/types";
import type { EditorState } from "../store/editorStore";
import { ComparisonView, type ComparisonMode } from "../features/canvas/ComparisonView";
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
import { Icon, type IconName } from "../platform/icons";

type CanvasPhase = "idle" | "loading" | "ready" | "error";
type PreviewUrls = { before: string; after: string };
type LivePreviewRequest = {
  path: string;
  analysis: JsonObject;
  factor: number;
  signature: string;
};

// 原型：视图切换只显示图标，文字走 tooltip。
const VIEW_MODES: ReadonlyArray<{ id: ComparisonMode; icon: IconName; label: string }> = [
  { id: "single", icon: "image", label: "单图" },
  { id: "lr", icon: "columns", label: "左右对比" },
  { id: "tb", icon: "rows", label: "上下对比" },
  { id: "split", icon: "split", label: "分隔线" },
];

// 当前项目的待修图片，占位素材来自 public/assets。
const PROJECT_SHOTS = [
  "/assets/thumb-1.jpg",
  "/assets/thumb-2.jpg",
  "/assets/thumb-3.jpg",
  "/assets/photo-before.jpg",
  "/assets/photo-after.jpg",
] as const;

type CanvasPaneProps = {
  active?: boolean;
  imagePath?: string | null;
  client?: LookliftClient;
  analysis?: JsonObject;
  factor?: number;
  onImagePathChange?(path: string): JsonObject | void;
  onPreviewSettled?(): void;
  onAnalysisComplete?(analysis: Analysis): void;
  onRenderStateChange?(render: EditorState["render"]): void;
  onPreviewRendered?(analysis: JsonObject): void;
  onEffectPreview?(blob: Blob, signature: string): void;
  analysisDisabled?: boolean;
};

export function CanvasPane({
  active = true,
  imagePath,
  client,
  analysis = {},
  factor = 1,
  onImagePathChange,
  onPreviewSettled,
  onAnalysisComplete,
  onRenderStateChange,
  onPreviewRendered,
  onEffectPreview,
  analysisDisabled = false,
}: CanvasPaneProps) {
  const paneRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const urlsRef = useRef<PreviewUrls | null>(null);
  const requestRef = useRef(0);
  const schedulerRef = useRef<PreviewScheduler<LivePreviewRequest> | null>(null);
  const previewCallbacksRef = useRef({ onPreviewSettled, onRenderStateChange, onPreviewRendered, onEffectPreview });
  const analysisControllerRef = useRef<AbortController | null>(null);
  const lastRenderedSignatureRef = useRef<string | null>(null);
  const loadPathRef = useRef<(path: string) => Promise<void>>(async () => undefined);
  const [phase, setPhase] = useState<CanvasPhase>("idle");
  const [loadedPath, setLoadedPath] = useState<string | null>(null);
  const [urls, setUrls] = useState<PreviewUrls | null>(null);
  const [position, setPosition] = useState(50);
  const [viewMode, setViewMode] = useState<ComparisonMode>("single");
  const [zoom, setZoom] = useState(1);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [projectShot, setProjectShot] = useState(0);
  previewCallbacksRef.current = { onPreviewSettled, onRenderStateChange, onPreviewRendered, onEffectPreview };

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
        previewCallbacksRef.current.onEffectPreview?.(blob, request.signature);
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

  const loadPath = useCallback(async (path: string, notify = true) => {
    if (!client) return;
    analysisControllerRef.current?.abort();
    analysisControllerRef.current = null;
    setAnalyzing(false);
    schedulerRef.current?.cancel();
    const nextAnalysis = notify ? onImagePathChange?.(path) ?? analysis : analysis;
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
      const signature = previewSignature(path, nextAnalysis, factor);
      lastRenderedSignatureRef.current = signature;
      previewCallbacksRef.current.onEffectPreview?.(pair.after, signature);
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

  useEffect(() => {
    if (!imagePath || imagePath === loadedPath || phase === "loading") return;
    void loadPath(imagePath, false);
  }, [imagePath, loadPath, loadedPath, phase]);

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
      setError("不支持的图片格式，请选择 JPEG、PNG、WebP、TIFF 或受支持的 RAW");
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
    if (!active || !element || !client) return;
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
  }, [active, client]);

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

  const selectProjectShot = async (index: number, asset: string) => {
    setProjectShot(index);
    if (!client || index === 0) return;
    try {
      const response = await fetch(asset);
      const file = new File([await response.blob()], asset.split("/").pop() ?? `project-${index}.jpg`, { type: "image/jpeg" });
      const uploaded = await client.upload(file);
      await loadPathRef.current(uploaded.path);
    } catch (reason) {
      setError(canvasErrorMessage(reason));
      setPhase("error");
    }
  };

  const ready = phase === "ready" && Boolean(urls);

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
        <div className="canvas-zoom-group" aria-label="画布缩放">
          <button type="button" aria-label="缩小" title="缩小" disabled={!ready || zoom <= 0.5} onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}>−</button>
          <button type="button" className="canvas-zoom" title="适合窗口" onClick={() => setZoom(1)}><Icon name="max" />{zoom === 1 ? "适合窗口 · 100%" : `${Math.round(zoom * 100)}%`}</button>
          <button type="button" aria-label="放大" title="放大" disabled={!ready || zoom >= 3} onClick={() => setZoom((value) => Math.min(3, value + 0.25))}>+</button>
        </div>
        <button
          className="canvas-analyze"
          type="button"
          disabled={!ready || analyzing || analysisDisabled}
          onClick={() => void runAnalysis()}
        >
          <Icon name="sparkles" />{analyzing ? "AI 分析中…" : "AI 分析"}
        </button>
      </div>

      <div className="canvas-body">
        {ready && urls ? (
          <ComparisonView
            beforeUrl={urls.before}
            afterUrl={urls.after}
            position={position}
            mode={viewMode}
            onPositionChange={setPosition}
            zoom={zoom}
          />
        ) : (
          <div className="canvas-empty" role={phase === "error" ? "alert" : undefined}>
            <div className="drop-outline" aria-hidden="true"><Icon name="image-plus" /></div>
            <h1>{phase === "loading" ? "正在生成对比预览" : dragActive ? "松开以载入照片" : "把照片拖到这里"}</h1>
            <p>{error ?? "或点击选择文件 · JPEG、PNG、WebP、TIFF"}</p>
            <button type="button" onClick={() => inputRef.current?.click()} disabled={!client || phase === "loading"}>
              选择照片
            </button>
          </div>
        )}
      </div>

      <input ref={inputRef} className="visually-hidden" type="file" accept="image/jpeg,image/png,image/webp,image/tiff" onChange={onFileChange} />

      <div className="canvas-view-switch" role="group" aria-label="画布视图">
        {VIEW_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            data-active={viewMode === mode.id}
            aria-pressed={viewMode === mode.id}
            title={mode.label}
            aria-label={mode.label}
            disabled={!ready}
            onClick={() => setViewMode(mode.id)}
          >
            <Icon name={mode.icon} />
          </button>
        ))}
      </div>

      <div className="canvas-filmstrip" aria-label="当前项目图片">
        <div className="filmstrip-track">
          {PROJECT_SHOTS.map((asset, index) => (
            <button
              key={asset}
              type="button"
              className="project-thumb"
              data-active={projectShot === index}
              title={`切换项目图片 ${index + 1}`}
              onClick={() => void selectProjectShot(index, asset)}
            >
              <span className="project-thumb-media">
                <img src={index === projectShot && urls?.before ? urls.before : asset} alt={`项目图片 ${index + 1}`} />
                <i className="project-thumb-state" data-done={index < 3} aria-hidden="true" />
              </span>
              <small>{index === 0 && loadedPath ? loadedPath.split(/[\\/]/).pop() : `项目图片 ${index + 1}`}</small>
            </button>
          ))}
        </div>
        <button type="button" className="project-add" onClick={() => inputRef.current?.click()} title="添加图片" aria-label="添加项目图片">
          <Icon name="add" />
        </button>
        <span className="filmstrip-count">{PROJECT_SHOTS.length} 张 · 已修 3</span>
      </div>

      {dragActive && <div className="drop-overlay" aria-hidden="true">放到画布中</div>}
      {ready && error && <div className="live-preview-error" role="alert">{error}</div>}
    </section>
  );
}
