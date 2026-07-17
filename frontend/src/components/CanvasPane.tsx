import { useCallback, useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import type { LookliftClient } from "../api/client";
import type { JsonObject } from "../api/types";
import { ComparisonView } from "../features/canvas/ComparisonView";
import {
  canvasErrorMessage,
  firstSupportedImage,
  loadPreviewPair,
  type CanvasApi,
} from "../features/canvas/canvasModel";
import { listenForTauriDrops } from "../features/canvas/tauriDrop";

type CanvasPhase = "idle" | "loading" | "ready" | "error";
type PreviewUrls = { before: string; after: string };

type CanvasPaneProps = {
  client?: LookliftClient;
  analysis?: JsonObject;
  factor?: number;
  onImagePathChange?(path: string): void;
};

export function CanvasPane({
  client,
  analysis = {},
  factor = 1,
  onImagePathChange,
}: CanvasPaneProps) {
  const paneRef = useRef<HTMLElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const urlsRef = useRef<PreviewUrls | null>(null);
  const requestRef = useRef(0);
  const [phase, setPhase] = useState<CanvasPhase>("idle");
  const [urls, setUrls] = useState<PreviewUrls | null>(null);
  const [position, setPosition] = useState(50);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const replaceUrls = useCallback((next: PreviewUrls | null) => {
    if (urlsRef.current) {
      URL.revokeObjectURL(urlsRef.current.before);
      URL.revokeObjectURL(urlsRef.current.after);
    }
    urlsRef.current = next;
    setUrls(next);
  }, []);

  const loadPath = useCallback(async (path: string) => {
    if (!client) return;
    onImagePathChange?.(path);
    const requestId = ++requestRef.current;
    setPhase("loading");
    setError(null);
    try {
      const pair = await loadPreviewPair(client as CanvasApi, path, analysis, factor);
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
      setPhase("ready");
    } catch (reason) {
      if (requestId !== requestRef.current) return;
      setError(canvasErrorMessage(reason));
      setPhase("error");
    }
  }, [analysis, client, factor, onImagePathChange, replaceUrls]);

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
    void listenForTauriDrops(element, { onActive: setDragActive, onPath: loadPath })
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
  }, [client, loadPath]);

  useEffect(() => () => {
    requestRef.current += 1;
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
        <span>{phase === "ready" ? "对比预览" : "100%"}</span>
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
      <div className="canvas-footer" aria-hidden="true">
        <span>原图</span><span className="diff-track"><i style={{ width: `${position}%` }} /></span><span>效果</span>
      </div>
    </section>
  );
}
