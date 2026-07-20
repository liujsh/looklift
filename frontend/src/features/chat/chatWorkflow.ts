import type { ChatMessage, ChatStepRequest, ChatStepResponse } from "../../api/types";
import type { EditorStore } from "../../store/editorStore";

type ChatClient = {
  chatStep(payload: ChatStepRequest, signal?: AbortSignal): Promise<ChatStepResponse>;
};

export type ChatStopReason = "done" | "no_changes" | "cancelled" | "round_limit" | null;
export type ChatWorkflowState = Readonly<{
  phase: "idle" | "requesting" | "pending" | "error" | "cancelled";
  messages: readonly ChatMessage[];
  lastResponse: ChatStepResponse | null;
  error: string | null;
  round: number;
  stopReason: ChatStopReason;
}>;

export type ChatWorkflow = {
  getSnapshot(): ChatWorkflowState;
  subscribe(listener: () => void): () => void;
  send(message: string): Promise<ChatStepResponse | null>;
  refine(): Promise<void>;
  cancel(): void;
  setIncludeMetadata(include: boolean): void;
  restoreMessages(messages: readonly ChatMessage[]): void;
  settlePending(): void;
};

type ChatWorkflowHooks = {
  onMessagesOnly?(exchange: readonly ChatMessage[]): Promise<void> | void;
};

const INITIAL: ChatWorkflowState = Object.freeze({
  phase: "idle", messages: Object.freeze([]), lastResponse: null,
  error: null, round: 0, stopReason: null,
});

export function createChatWorkflow(
  client: ChatClient,
  store: EditorStore,
  hooks: ChatWorkflowHooks = {},
): ChatWorkflow {
  let state = INITIAL;
  let controller: AbortController | null = null;
  let activeLockId: number | null = null;
  let requestId = store.getSnapshot().pendingPreview?.requestId ?? 0;
  let includeMetadata = true;
  const listeners = new Set<() => void>();

  const publish = (patch: Partial<ChatWorkflowState>) => {
    state = Object.freeze({ ...state, ...patch });
    for (const listener of listeners) listener();
  };

  const runStep = async (message: string, round: number): Promise<ChatStepResponse | null> => {
    const editor = store.getSnapshot();
    if (!editor.imagePath || !editor.displayAnalysis) throw new Error("请先导入照片再开始 AI 对话");
    const activeRequestId = ++requestId;
    if (!store.beginAiRequest(activeRequestId)) throw new Error("AI 正在处理，请稍候");
    activeLockId = activeRequestId;
    controller?.abort();
    const active = new AbortController();
    controller = active;
    const user: ChatMessage = { role: "user", content: message };
    publish({ phase: "requesting", error: null, round, stopReason: null });
    let response: ChatStepResponse;
    try {
      response = await client.chatStep({
        path: editor.imagePath,
        current_analysis: editor.displayAnalysis,
        factor: editor.factor,
        message,
        history: [...state.messages],
        include_metadata: includeMetadata,
      }, active.signal);
    } catch (reason) {
      store.endAiRequest(activeRequestId);
      if (active.signal.aborted || (reason instanceof DOMException && reason.name === "AbortError")) {
        const exchange: ChatMessage[] = [
          user, { role: "assistant", content: "已停止等待；供应商端已发出的请求可能仍会完成，正式版本未改变。", status: "cancelled" },
        ];
        publish({
          phase: "cancelled", stopReason: "cancelled", error: null,
          messages: Object.freeze([...state.messages, ...exchange]),
        });
        await hooks.onMessagesOnly?.(exchange);
        return null;
      }
      const message = reason instanceof Error ? reason.message : String(reason);
      const exchange: ChatMessage[] = [
        user, { role: "assistant", content: message, status: "failed" },
      ];
      publish({
        phase: "error", error: message,
        messages: Object.freeze([...state.messages, ...exchange]),
      });
      try { await hooks.onMessagesOnly?.(exchange); } catch { /* 保留原始服务错误。 */ }
      throw reason;
    } finally {
      if (controller === active) {
        controller = null;
        if (activeLockId === activeRequestId) activeLockId = null;
      }
    }

    if (active.signal.aborted) {
      store.endAiRequest(activeRequestId);
      return null;
    }
    const stillCurrent = store.getSnapshot().activeAiRequestId === activeRequestId
      && store.getSnapshot().imagePath === editor.imagePath;
    store.endAiRequest(activeRequestId);
    if (!stillCurrent) return null;
    const assistant: ChatMessage = {
      role: "assistant", content: response.explanation, provider: response.provider, status: "done",
    };
    const exchange = [user, assistant];
    const messages = Object.freeze([...state.messages, ...exchange]);
    const existingPending = store.getSnapshot().pendingPreview;
    if (response.changes.length > 0) {
      const prior = existingPending?.exchange ?? [];
      const accepted = store.beginPendingPreview(
        response.analysis, response.changes, [...prior, ...exchange], activeRequestId,
      );
      if (!accepted) {
        const reason = new Error("候选预览无法安全显示，请先解决渲染错误后重试");
        const failed = [user, { role: "assistant" as const, content: reason.message, status: "failed" as const }];
        publish({ phase: "error", error: reason.message, messages: Object.freeze([...state.messages, ...failed]) });
        await hooks.onMessagesOnly?.(failed);
        throw reason;
      }
    } else if (existingPending) {
      const accepted = store.beginPendingPreview(
        existingPending.candidate,
        existingPending.changes,
        [...existingPending.exchange, ...exchange],
        activeRequestId,
      );
      if (!accepted) throw new Error("候选预览状态已过期，请重试");
    }
    publish({
      phase: response.changes.length > 0 || existingPending ? "pending" : "idle",
      messages,
      lastResponse: response,
      stopReason: response.done ? "done" : response.changes.length === 0 ? "no_changes" : null,
    });
    if (response.changes.length === 0 && !existingPending) await hooks.onMessagesOnly?.(exchange);
    return response;
  };

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    send(message) {
      if (!message.trim()) return Promise.reject(new Error("请输入修图要求"));
      return runStep(message.trim(), 0);
    },
    async refine() {
      if (state.phase === "requesting") throw new Error("AI 正在处理，请稍候");
      if (!store.getSnapshot().pendingPreview) throw new Error("当前没有可精修的 AI 候选");
      if (state.round >= 2) {
        publish({ phase: "pending", stopReason: "round_limit", round: 2 });
        return;
      }
      if (store.getSnapshot().render.status !== "ready") {
        throw new Error("候选预览尚未渲染成功");
      }
      const nextRound = state.round + 1;
      const response = await runStep("继续精修当前效果", nextRound);
      if (!response || response.done || response.changes.length === 0) return;
      if (nextRound >= 2) publish({ phase: "pending", stopReason: "round_limit", round: 2 });
    },
    cancel() {
      if (!controller) return;
      controller.abort();
      if (activeLockId !== null) store.endAiRequest(activeLockId);
    },
    setIncludeMetadata(include) {
      includeMetadata = include;
    },
    restoreMessages(messages) {
      publish({
        phase: "idle", messages: Object.freeze([...messages]), lastResponse: null,
        error: null, round: 0, stopReason: null,
      });
    },
    settlePending() {
      publish({ phase: "idle", error: null, round: 0, stopReason: null });
    },
  };
}
