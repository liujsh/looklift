import { useSyncExternalStore } from "react";
import type { Analysis } from "../api/types";

export type ChangeSource = "ai" | "manual" | "chat" | "library";
export type EditableSection = "basic" | "hsl" | "tone_curve" | "color_grading" | "effects";
export type RenderStatus = "idle" | "rendering" | "ready" | "error";

export type AnalysisVersion = Readonly<{
  analysis: Analysis;
  source: ChangeSource;
}>;

export type EditorState = Readonly<{
  imagePath: string | null;
  analysis: Analysis | null;
  factor: number;
  render: Readonly<{ status: RenderStatus; error: string | null }>;
  versions: readonly AnalysisVersion[];
}>;

export type EditorStore = {
  getSnapshot(): EditorState;
  subscribe(listener: () => void): () => void;
  openImage(imagePath: string, analysis: Analysis): void;
  commitAnalysis(analysis: Analysis, source: ChangeSource): void;
  updateFragment<K extends EditableSection>(section: K, value: Analysis[K], source: ChangeSource): void;
  previewFragment<K extends EditableSection>(section: K, value: Analysis[K]): void;
  finalizePreview(source: ChangeSource): void;
  applyDelta(transform: (analysis: Analysis) => Analysis, source: ChangeSource): void;
  setImagePath(path: string | null): void;
  setFactor(factor: number): void;
  setRenderState(render: EditorState["render"]): void;
};

const INITIAL_STATE: EditorState = Object.freeze({
  imagePath: null,
  analysis: null,
  factor: 1,
  render: Object.freeze({ status: "idle", error: null }),
  versions: Object.freeze([]),
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
  const listeners = new Set<() => void>();

  const publish = (next: EditorState) => {
    state = Object.freeze(next);
    for (const listener of listeners) listener();
  };

  const commitAnalysis = (nextAnalysis: Analysis, source: ChangeSource) => {
    const next = immutableCopy(nextAnalysis);
    const previous = previewBase ?? state.analysis;
    const versions = previous
      ? Object.freeze([...state.versions, Object.freeze({ analysis: previous, source })])
      : state.versions;
    previewBase = null;
    publish({ ...state, analysis: next, versions });
  };

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    openImage(imagePath, analysis) {
      previewBase = null;
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
      if (!previewBase || !state.analysis) return;
      const previous = previewBase;
      previewBase = null;
      publish({
        ...state,
        versions: Object.freeze([
          ...state.versions,
          Object.freeze({ analysis: previous, source }),
        ]),
      });
    },
    applyDelta(transform, source) {
      if (!state.analysis) throw new Error("尚未载入 analysis，不能应用参数 delta");
      commitAnalysis(transform(state.analysis), source);
    },
    setImagePath(imagePath) {
      publish({ ...state, imagePath });
    },
    setFactor(factor) {
      if (!Number.isFinite(factor)) throw new TypeError("factor 必须是有限数值");
      publish({ ...state, factor: Math.min(1, Math.max(0, factor)) });
    },
    setRenderState(render) {
      publish({ ...state, render: Object.freeze({ ...render }) });
    },
  };
}

export const editorStore = createEditorStore();

export function useEditorState(): EditorState {
  return useSyncExternalStore(editorStore.subscribe, editorStore.getSnapshot, editorStore.getSnapshot);
}
