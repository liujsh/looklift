import { useSyncExternalStore } from "react";
import type { Analysis, ChatChange, ChatMessage } from "../api/types";

export type ChangeSource = "ai" | "manual" | "chat" | "library";
export type EditableSection = "basic" | "hsl" | "tone_curve" | "color_grading" | "effects";
export type RenderStatus = "idle" | "rendering" | "ready" | "error";

export type AnalysisVersion = Readonly<{
  analysis: Analysis;
  source: ChangeSource;
}>;

export type PendingPreview = Readonly<{
  baseAnalysis: Analysis;
  candidate: Analysis;
  changes: readonly ChatChange[];
  exchange: readonly ChatMessage[];
  requestId: number;
  createdAt: string;
}>;

export type EditorState = Readonly<{
  imagePath: string | null;
  analysis: Analysis | null;
  displayAnalysis: Analysis | null;
  pendingPreview: PendingPreview | null;
  factor: number;
  render: Readonly<{ status: RenderStatus; error: string | null }>;
  versions: readonly AnalysisVersion[];
  redoVersions: readonly AnalysisVersion[];
}>;

export type EditorStore = {
  getSnapshot(): EditorState;
  subscribe(listener: () => void): () => void;
  openImage(imagePath: string, analysis: Analysis): void;
  commitAnalysis(analysis: Analysis, source: ChangeSource): void;
  updateFragment<K extends EditableSection>(section: K, value: Analysis[K], source: ChangeSource): void;
  previewFragment<K extends EditableSection>(section: K, value: Analysis[K]): void;
  finalizePreview(source: ChangeSource): boolean;
  applyDelta(transform: (analysis: Analysis) => Analysis, source: ChangeSource): void;
  setImagePath(path: string | null): void;
  setFactor(factor: number): void;
  setRenderState(render: EditorState["render"]): void;
  beginPendingPreview(
    candidate: Analysis,
    changes: readonly ChatChange[],
    exchange: readonly ChatMessage[],
    requestId: number,
    createdAt?: string,
  ): boolean;
  acceptPendingPreview(): readonly ChatMessage[] | null;
  discardPendingPreview(): void;
  beginManualFromPending(): readonly ChatMessage[] | null;
  undo(): boolean;
  redo(): boolean;
  restoreSession(imagePath: string, analysis: Analysis): void;
};

const INITIAL_STATE: EditorState = Object.freeze({
  imagePath: null,
  analysis: null,
  displayAnalysis: null,
  pendingPreview: null,
  factor: 1,
  render: Object.freeze({ status: "idle", error: null }),
  versions: Object.freeze([]),
  redoVersions: Object.freeze([]),
});

function immutableCopy<T>(value: T): T {
  const copy = structuredClone(value);
  const freeze = (target: unknown): void => {
    if (!target || typeof target !== "object" || Object.isFrozen(target)) return;
    for (const child of Object.values(target)) freeze(child);
    Object.freeze(target);
  };
  freeze(copy);
  return copy;
}

export function createEditorStore(): EditorStore {
  let state = INITIAL_STATE;
  let previewBase: Analysis | null = null;
  let latestPendingRequestId = 0;
  const listeners = new Set<() => void>();

  const publish = (next: EditorState) => {
    state = Object.freeze({
      ...next,
      displayAnalysis: next.pendingPreview?.candidate ?? next.analysis,
    });
    for (const listener of listeners) listener();
  };

  const commitAnalysis = (nextAnalysis: Analysis, source: ChangeSource) => {
    const next = immutableCopy(nextAnalysis);
    const previous = previewBase ?? state.analysis;
    const versions = previous
      ? Object.freeze([...state.versions, Object.freeze({ analysis: previous, source })])
      : state.versions;
    previewBase = null;
    publish({
      ...state,
      analysis: next,
      pendingPreview: null,
      versions,
      redoVersions: Object.freeze([]),
    });
  };

  const promotePending = (): readonly ChatMessage[] | null => {
    const pending = state.pendingPreview;
    if (!pending) return null;
    const exchange = pending.exchange;
    previewBase = null;
    publish({
      ...state,
      analysis: pending.candidate,
      pendingPreview: null,
      versions: Object.freeze([
        ...state.versions,
        Object.freeze({ analysis: pending.baseAnalysis, source: "chat" as const }),
      ]),
      redoVersions: Object.freeze([]),
    });
    return exchange;
  };

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    openImage(imagePath, analysis) {
      previewBase = null;
      latestPendingRequestId = 0;
      publish({
        ...INITIAL_STATE,
        imagePath,
        analysis: immutableCopy(analysis),
      });
    },
    commitAnalysis,
    updateFragment(section, value, source) {
      if (!state.analysis) throw new Error("尚未载入 analysis，不能更新参数分片");
      commitAnalysis({ ...state.analysis, [section]: value }, source);
    },
    previewFragment(section, value) {
      if (!state.analysis) throw new Error("尚未载入 analysis，不能预览参数分片");
      previewBase ??= state.analysis;
      publish({ ...state, analysis: immutableCopy({ ...state.analysis, [section]: value }) });
    },
    finalizePreview(source) {
      if (!previewBase || !state.analysis) return false;
      const previous = previewBase;
      previewBase = null;
      publish({
        ...state,
        versions: Object.freeze([
          ...state.versions,
          Object.freeze({ analysis: previous, source }),
        ]),
      });
      return true;
    },
    applyDelta(transform, source) {
      if (!state.analysis) throw new Error("尚未载入 analysis，不能应用参数 delta");
      commitAnalysis(transform(state.analysis), source);
    },
    setImagePath(imagePath) {
      if (imagePath !== state.imagePath) {
        previewBase = null;
        latestPendingRequestId = 0;
      }
      publish({ ...state, imagePath, pendingPreview: null });
    },
    setFactor(factor) {
      if (!Number.isFinite(factor)) throw new TypeError("factor 必须是有限数值");
      publish({ ...state, factor: Math.min(1, Math.max(0, factor)) });
    },
    setRenderState(render) {
      publish({
        ...state,
        render: Object.freeze({ ...render }),
        pendingPreview: render.status === "error" ? null : state.pendingPreview,
      });
      return true;
    },
    beginPendingPreview(candidate, changes, exchange, requestId, createdAt = new Date().toISOString()) {
      if (!state.analysis || state.render.status === "error" || requestId < latestPendingRequestId) {
        return false;
      }
      latestPendingRequestId = requestId;
      const pending = immutableCopy({
        baseAnalysis: state.analysis,
        candidate,
        changes: [...changes],
        exchange: [...exchange],
        requestId,
        createdAt,
      });
      previewBase = null;
      publish({ ...state, pendingPreview: pending });
      return true;
    },
    acceptPendingPreview: promotePending,
    discardPendingPreview() {
      if (state.pendingPreview) publish({ ...state, pendingPreview: null });
    },
    beginManualFromPending: promotePending,
    undo() {
      if (state.pendingPreview) {
        publish({ ...state, pendingPreview: null });
        return true;
      }
      const previous = state.versions[state.versions.length - 1];
      if (!previous || !state.analysis) return false;
      previewBase = null;
      publish({
        ...state,
        analysis: previous.analysis,
        versions: Object.freeze(state.versions.slice(0, -1)),
        redoVersions: Object.freeze([
          ...state.redoVersions,
          Object.freeze({ analysis: state.analysis, source: previous.source }),
        ]),
      });
      return true;
    },
    redo() {
      const next = state.redoVersions[state.redoVersions.length - 1];
      if (!next || !state.analysis) return false;
      previewBase = null;
      publish({
        ...state,
        analysis: next.analysis,
        versions: Object.freeze([
          ...state.versions,
          Object.freeze({ analysis: state.analysis, source: next.source }),
        ]),
        redoVersions: Object.freeze(state.redoVersions.slice(0, -1)),
      });
      return true;
    },
    restoreSession(imagePath, analysis) {
      previewBase = null;
      latestPendingRequestId = 0;
      publish({ ...INITIAL_STATE, imagePath, analysis: immutableCopy(analysis) });
    },
  };
}

export const editorStore = createEditorStore();

export function useEditorState(): EditorState {
  return useSyncExternalStore(editorStore.subscribe, editorStore.getSnapshot, editorStore.getSnapshot);
}
