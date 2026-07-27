import { useCallback, useEffect, useState } from "react";
import type { SessionSummary } from "../api/types";
import { Icon } from "./icons";

type RecentSessionClient = {
  recentSessions(limit?: number): Promise<SessionSummary[]>;
  sessionThumbnail(id: string, signal?: AbortSignal): Promise<Blob>;
};

export type FutureEntry = "folder" | "device";

type HomePageProps = {
  client: RecentSessionClient;
  onResume(sessionId: string): Promise<void> | void;
  onQuickEdit?(): Promise<void> | void;
  quickEditBusy?: boolean;
  onFuture(entry: FutureEntry): void;
};

// 暗房占位色调：会话摘要没有真实缩略图，先用暖色渐变 + 印相纸边框顶位，
// 后续接「按路径出缩略图」接口后替换 .session-thumb 的背景。
const THUMB_TONES = [
  "t-swan", "t-dragon", "t-bird", "t-magpie", "t-duck", "t-leaf", "t-dove", "t-teal",
] as const;

function toneFor(id: string): (typeof THUMB_TONES)[number] {
  let hash = 0;
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  return THUMB_TONES[hash % THUMB_TONES.length];
}

function frameCode(index: number): string {
  return `A·${String(index + 1).padStart(2, "0")}`;
}

function useSessionThumbnail(client: RecentSessionClient, session: SessionSummary): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    setUrl(null);
    if (!session.source_available) return;
    const controller = new AbortController();
    let objectUrl: string | null = null;
    void client.sessionThumbnail(session.id, controller.signal)
      .then((blob) => {
        if (controller.signal.aborted) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [client, session.id, session.source_available]);
  return url;
}

function SessionThumb({ client, session, index }: { client: RecentSessionClient; session: SessionSummary; index: number }) {
  const thumbnailUrl = useSessionThumbnail(client, session);
  return (
    <div className="session-thumb-wrap">
      <span className="sprocket tl" aria-hidden="true" />
      <span className="sprocket tr" aria-hidden="true" />
      <div className={`session-thumb ${toneFor(session.id)}`} aria-hidden="true">
        {thumbnailUrl && <img src={thumbnailUrl} alt="" />}
      </div>
      <span className="frame-code">{session.source_available ? frameCode(index) : "—"}</span>
    </div>
  );
}

export function HomePage({ client, onResume, onQuickEdit, quickEditBusy = false, onFuture }: HomePageProps) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openingId, setOpeningId] = useState<string | null>(null);

  const loadSessions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSessions(await client.recentSessions(8));
    } catch (reason) {
      setError(`最近会话载入失败：${reason instanceof Error ? reason.message : String(reason)}`);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => { void loadSessions(); }, [loadSessions]);

  const resume = async (sessionId: string) => {
    setOpeningId(sessionId);
    setError(null);
    try {
      await onResume(sessionId);
    } catch (reason) {
      setError(`会话恢复失败：${reason instanceof Error ? reason.message : String(reason)}`);
    } finally {
      setOpeningId(null);
    }
  };

  return (
    <main className="home-page" aria-label="首页">
      <section className="home-hero">
        <p className="pane-kicker">LookLift Workspace</p>
        <h1>今天想修哪组照片？</h1>
        <p className="home-hero-sub">从一张临时照片起手，或钻进已建索引的文件夹。原片始终留在原处——LookLift 只读、不动你的文件。</p>
      </section>

      <div className="home-actions" aria-label="开始修图">
        <button className="home-action primary" type="button" disabled={!onQuickEdit || quickEditBusy} onClick={() => void onQuickEdit?.()}>
          <span className="ic"><Icon name="aperture" /></span>
          <h3>{quickEditBusy ? "正在打开…" : "快速修图"}</h3>
          <p>选一张照片直接进 Studio，不加入图库。</p>
        </button>
        <button className="home-action" type="button" onClick={() => onFuture("folder")}>
          <span className="ic"><Icon name="folder-plus" /></span>
          <h3>添加文件夹</h3>
          <p>只建立本地索引，不复制、不移动。<span className="home-action-kbd">v2.3-A</span></p>
        </button>
        <button className="home-action" type="button" onClick={() => onFuture("device")}>
          <span className="ic"><Icon name="import" /></span>
          <h3>从设备导入</h3>
          <p>安全复制并校验，再加入图库。<span className="home-action-kbd">v2.3-B</span></p>
        </button>
      </div>

      <section className="recent-sessions" aria-labelledby="recent-heading">
        <div className="section-heading">
          <div><p className="pane-kicker">Contact Sheet · 最近</p><h2 id="recent-heading">继续修图</h2></div>
          {!loading && <button data-action="retry-sessions" type="button" onClick={() => void loadSessions()}>刷新</button>}
        </div>
        {loading && <p className="home-status" aria-live="polite">正在读取最近正式会话…</p>}
        {error && <div className="home-error" role="alert"><span>{error}</span><button data-action="retry-sessions" type="button" onClick={() => void loadSessions()}>重试</button></div>}
        {!loading && !error && sessions.length === 0 && <p className="home-status">还没有可继续的正式会话</p>}
        {!loading && sessions.length > 0 && <div className="session-cards">
          {sessions.map((session, index) => (
            <article className="session-card" key={session.id} data-available={session.source_available}>
              <SessionThumb client={client} session={session} index={index} />
              <div className="session-meta">
                <span className="session-name">{session.display_name}</span>
                <span className={`pill ${session.source_available ? "official" : "missing"}`}>
                  {session.source_available ? "正式版本" : "源文件不可用"}
                </span>
                <p className="session-note">{session.summary || "正式版本"}</p>
                <div className="session-row">
                  <time dateTime={session.updated_at}>{new Date(session.updated_at).toLocaleDateString("zh-CN")}</time>
                  {session.source_available ? (
                    <button
                      className="session-go"
                      type="button"
                      disabled={openingId !== null}
                      onClick={() => void resume(session.id)}
                    >{openingId === session.id ? "正在恢复…" : "继续"}</button>
                  ) : (
                    <button className="session-relocate" type="button" disabled aria-label={`${session.display_name} 重新定位`}>
                      <Icon name="relocate" className="go-ic" /> 重新定位
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>}
      </section>
    </main>
  );
}
