import type {
  Analysis,
  ChatMessage,
  CommitSessionRequest,
  CreateSessionRequest,
  RecordSessionMessagesRequest,
  SessionSnapshot,
} from "../../api/types";
import type { EditorStore } from "../../store/editorStore";

type SessionClient = {
  createSession?(payload: CreateSessionRequest): Promise<SessionSnapshot>;
  commitSession?(id: string, payload: CommitSessionRequest): Promise<SessionSnapshot>;
  recordSessionMessages?(id: string, payload: RecordSessionMessagesRequest): Promise<SessionSnapshot>;
};

export type SessionCoordinator = {
  open(path: string, initialAnalysis: Analysis): Promise<SessionSnapshot>;
  acceptPending(): Promise<void>;
  discardPending(): Promise<void>;
  continueManual(): Promise<readonly ChatMessage[]>;
  recordMessages(exchange: readonly ChatMessage[]): Promise<void>;
  getSessionId(): string | null;
};

export function createSessionCoordinator(
  client: SessionClient,
  store: EditorStore,
  initialSessionId: string | null = null,
): SessionCoordinator {
  let sessionId = initialSessionId;

  const requireSession = () => {
    if (!sessionId) throw new Error("编辑会话尚未建立");
    return sessionId;
  };
  const requirePending = () => {
    const editor = store.getSnapshot();
    if (!editor.pendingPreview) throw new Error("当前没有待确认版本");
    if (editor.render.status !== "ready") throw new Error("候选预览尚未渲染成功");
    return editor.pendingPreview;
  };
  const commitPending = async () => {
    const pending = requirePending();
    if (!client.commitSession) throw new Error("会话保存服务不可用");
    await client.commitSession(requireSession(), {
      exchange: [...pending.exchange], analysis: pending.candidate, source: "chat",
    });
    return pending;
  };

  return {
    async open(path, initialAnalysis) {
      if (!client.createSession) throw new Error("会话服务不可用");
      const snapshot = await client.createSession({ path, initial_analysis: initialAnalysis });
      sessionId = snapshot.id;
      store.restoreSession(snapshot.image_path, snapshot.current_analysis);
      return snapshot;
    },
    async acceptPending() {
      await commitPending();
      store.acceptPendingPreview();
    },
    async discardPending() {
      const pending = store.getSnapshot().pendingPreview;
      if (!pending) return;
      if (client.recordSessionMessages && sessionId) {
        await client.recordSessionMessages(sessionId, { exchange: [...pending.exchange] });
      }
      store.discardPendingPreview();
    },
    async continueManual() {
      const pending = await commitPending();
      store.beginManualFromPending();
      return pending.exchange;
    },
    async recordMessages(exchange) {
      if (!client.recordSessionMessages) throw new Error("会话消息服务不可用");
      await client.recordSessionMessages(requireSession(), { exchange: [...exchange] });
    },
    getSessionId: () => sessionId,
  };
}
