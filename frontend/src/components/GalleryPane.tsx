import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { Analysis, LookSummary } from "../api/types";
import { loadLookIntoEditor, looksForSource, type GallerySource } from "../features/gallery/galleryStore";
import { exportLookFile, openLookReport, saveCurrentLook } from "../features/looks/lookActions";
import type { EditorStore } from "../store/editorStore";
import { useEditorState } from "../store/editorStore";

type GalleryPaneProps = {
  store: EditorStore;
  client?: LookliftClient;
  initialLooks?: readonly LookSummary[];
  onActiveLookChange?(name: string): void;
  onFormalAnalysis?(analysis: Analysis, source: "library"): Promise<void> | void;
};

function actionError(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason);
}

export function GalleryPane({ store, client, initialLooks, onActiveLookChange, onFormalAnalysis }: GalleryPaneProps) {
  const editor = useEditorState(store);
  const [source, setSource] = useState<GallerySource>("built_in");
  const [looks, setLooks] = useState<readonly LookSummary[]>(initialLooks ?? []);
  const [loading, setLoading] = useState(Boolean(client && !initialLooks));
  const [loadingName, setLoadingName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [actionStatus, setActionStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!client || initialLooks) return;
    let cancelled = false;
    setLoading(true);
    void client.listLooks()
      .then((items) => { if (!cancelled) setLooks(items); })
      .catch((reason) => { if (!cancelled) setError(`图库载入失败：${String(reason)}`); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [client, initialLooks]);

  const visible = looksForSource(looks, source);
  const load = async (look: LookSummary) => {
    if (!client) return;
    setLoadingName(look.name);
    setError(null);
    try {
      let applied = false;
      const analysis = await loadLookIntoEditor(client, look.name, (analysis, factor) => {
        store.setFactor(factor);
        applied = store.commitAnalysis(analysis, "library");
      });
      if (!applied) return;
      await onFormalAnalysis?.(analysis, "library");
      onActiveLookChange?.(look.name);
      setActionStatus(`已载入：${look.name}`);
    } catch (reason) {
      setError(`风格载入失败：${String(reason)}`);
    } finally {
      setLoadingName(null);
    }
  };

  const save = async () => {
    if (!client || !editor.analysis) return;
    setSaving(true);
    setError(null);
    try {
      const result = await saveCurrentLook(client, name, editor.analysis, editor.factor);
      setLooks(result.looks);
      setSource("user");
      setName("");
      onActiveLookChange?.(result.name);
      setActionStatus(`已收藏：${result.name}`);
    } catch (reason) {
      setError(actionError(reason));
    } finally {
      setSaving(false);
    }
  };

  const exportFile = async (look: LookSummary, sidecar?: string) => {
    if (!client) return;
    setError(null);
    try {
      const path = await exportLookFile(client, look.name, sidecar);
      setActionStatus(`已导出：${path}`);
    } catch (reason) {
      setError(actionError(reason));
    }
  };

  return (
    <section className="gallery-pane" data-pane="gallery" aria-label="风格图库">
      <header className="gallery-heading">
        <div>
          <p className="pane-kicker">LOOKS</p>
          <h2>风格图库</h2>
        </div>
        <nav aria-label="图库来源">
          <button type="button" aria-pressed={source === "built_in"} onClick={() => setSource("built_in")}>内置模板</button>
          <button type="button" aria-pressed={source === "user"} onClick={() => setSource("user")}>我的风格</button>
        </nav>
        <div className="gallery-save">
          <input
            value={name}
            aria-label="收藏名称"
            placeholder="给当前风格命名"
            onChange={(event) => setName(event.currentTarget.value)}
          />
          <button
            type="button"
            disabled={!client || !editor.analysis || saving || !name.trim()}
            onClick={() => void save()}
          >{saving ? "收藏中…" : "收藏当前"}</button>
        </div>
      </header>
      <div className="contact-sheet" aria-label={`${source === "built_in" ? "内置模板" : "我的风格"}卡片`}>
        {visible.map((look) => (
          <article
            className="look-card"
            data-source={look.source}
            key={look.name}
            title={look.summary}
          >
            <button
              className="look-load"
              type="button"
              disabled={!client || loadingName !== null || editor.pendingPreview !== null || editor.activeAiRequestId !== null}
              onClick={() => void load(look)}
            >
              <span aria-hidden="true" />
              <strong>{loadingName === look.name ? "正在载入…" : look.name}</strong>
              <small>{look.summary}</small>
            </button>
            <div className="look-card-actions">
              <button type="button" disabled={!client} onClick={() => client && openLookReport(client, look.name)}>报告</button>
              <button type="button" disabled={!client} onClick={() => void exportFile(look)}>预设</button>
              <button
                type="button"
                disabled={!client}
                onClick={() => {
                  const path = window.prompt("输入 RAW 文件完整路径");
                  if (path?.trim()) void exportFile(look, path.trim());
                }}
              >sidecar</button>
            </div>
          </article>
        ))}
        {!loading && visible.length === 0 && <p className="gallery-empty">{source === "user" ? "还没有收藏的风格" : "暂无内置模板"}</p>}
      </div>
      {loading && <div className="gallery-status" aria-live="polite">正在载入图库…</div>}
      {error
        ? <div className="gallery-status gallery-error" role="alert">{error}</div>
        : actionStatus && <div className="gallery-status" aria-live="polite">{actionStatus}</div>}
    </section>
  );
}
