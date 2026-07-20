import { useCallback, useEffect, useState } from "react";
import type { SessionSummary } from "../api/types";

type RecentSessionClient = {
  recentSessions(limit?: number): Promise<SessionSummary[]>;
};

export type FutureEntry = "folder" | "device";

type HomePageProps = {
  client: RecentSessionClient;
  onResume(sessionId: string): Promise<void> | void;
  onQuickEdit?(): Promise<void> | void;
  quickEditBusy?: boolean;
  onFuture(entry: FutureEntry): void;
};

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
        <p>从一张临时照片开始；文件夹与设备工作流将在后续版本接入。</p>
        <div className="home-actions" aria-label="开始修图">
          <button type="button" onClick={() => onFuture("folder")}>
            <strong>添加文件夹</strong><span>v2.3-A · 只索引，不复制</span>
          </button>
          <button type="button" onClick={() => onFuture("device")}>
            <strong>从设备导入</strong><span>v2.3-B · 安全复制并校验</span>
          </button>
          <button className="primary" type="button" disabled={!onQuickEdit || quickEditBusy} onClick={() => void onQuickEdit?.()}>
            <strong>{quickEditBusy ? "正在打开…" : "快速修图"}</strong><span>选择一张照片，不加入图库</span>
          </button>
        </div>
      </section>

      <section className="recent-sessions" aria-labelledby="recent-heading">
        <div className="section-heading">
          <div><p className="pane-kicker">RECENT</p><h2 id="recent-heading">继续修图</h2></div>
          {!loading && <button data-action="retry-sessions" type="button" onClick={() => void loadSessions()}>刷新</button>}
        </div>
        {loading && <p className="home-status" aria-live="polite">正在读取最近正式会话…</p>}
        {error && <div className="home-error" role="alert"><span>{error}</span><button data-action="retry-sessions" type="button" onClick={() => void loadSessions()}>重试</button></div>}
        {!loading && !error && sessions.length === 0 && <p className="home-status">还没有可继续的正式会话</p>}
        {!loading && sessions.length > 0 && <div className="session-cards">
          {sessions.map((session) => (
            <article className="session-card" key={session.id} data-available={session.source_available}>
              <div><strong>{session.display_name}</strong><p>{session.summary || "正式版本"}</p></div>
              <time dateTime={session.updated_at}>{new Date(session.updated_at).toLocaleDateString("zh-CN")}</time>
              <button
                type="button"
                disabled={!session.source_available || openingId !== null}
                onClick={() => void resume(session.id)}
              >{session.source_available
                  ? openingId === session.id ? "正在恢复…" : `继续 ${session.display_name}`
                  : `${session.display_name} · 源文件不可用`}</button>
            </article>
          ))}
        </div>}
      </section>
    </main>
  );
}
