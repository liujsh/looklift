import { useEffect, useState } from "react";
import type { LookliftClient } from "../api/client";
import type { LookSummary } from "../api/types";
import { loadLookIntoEditor, looksForSource, type GallerySource } from "../features/gallery/galleryStore";
import { editorStore } from "../store/editorStore";

type GalleryPaneProps = {
  client?: LookliftClient;
  initialLooks?: readonly LookSummary[];
};

export function GalleryPane({ client, initialLooks }: GalleryPaneProps) {
  const [source, setSource] = useState<GallerySource>("built_in");
  const [looks, setLooks] = useState<readonly LookSummary[]>(initialLooks ?? []);
  const [loading, setLoading] = useState(Boolean(client && !initialLooks));
  const [loadingName, setLoadingName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
      await loadLookIntoEditor(client, look.name, (analysis) => {
        editorStore.commitAnalysis(analysis, "library");
      });
    } catch (reason) {
      setError(`风格载入失败：${String(reason)}`);
    } finally {
      setLoadingName(null);
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
      </header>
      <div className="contact-sheet" aria-label={`${source === "built_in" ? "内置模板" : "我的风格"}卡片`}>
        {visible.map((look) => (
          <button
            className="look-card"
            data-source={look.source}
            type="button"
            key={look.name}
            disabled={!client || loadingName !== null}
            title={look.summary}
            onClick={() => void load(look)}
          >
            <span aria-hidden="true" />
            <strong>{loadingName === look.name ? "正在载入…" : look.name}</strong>
            <small>{look.summary}</small>
          </button>
        ))}
        {!loading && visible.length === 0 && <p className="gallery-empty">{source === "user" ? "还没有收藏的风格" : "暂无内置模板"}</p>}
      </div>
      {loading && <div className="gallery-status" aria-live="polite">正在载入图库…</div>}
      {error && <div className="gallery-status gallery-error" role="alert">{error}</div>}
    </section>
  );
}
