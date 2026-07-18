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
};

const INITIAL: ChatWorkflowState = Object.freeze({
  phase: "idle", messages: Object.freeze([]), lastResponse: null,
  error: null, round: 0, stopReason: null,
});

export function createChatWorkflow(client: ChatClient, store: EditorStore): ChatWorkflow {
  let state = INITIAL;
  let controller: AbortController | null = null;
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
    controller?.abort();
    const active = new AbortController();
    controller = active;
    const user: ChatMessage = { role: "user", content: message };
    publish({ phase: "requesting", error: null, round, stopReason: null });
    try {
      const response = await client.chatStep({
        path: editor.imagePath,
        current_analysis: editor.displayAnalysis,
        message,
        history: [...state.messages],
        include_metadata: includeMetadata,
      }, active.signal);
      if (active.signal.aborted) return null;
      const assistant: ChatMessage = {
        role: "assistant", content: response.explanation, provider: response.provider, status: "done",
      };
      const exchange = [user, assistant];
      const messages = Object.freeze([...state.messages, ...exchange]);
      if (response.changes.length > 0) {
        const prior = store.getSnapshot().pendingPreview?.exchange ?? [];
        store.beginPendingPreview(
          response.analysis, response.changes, [...prior, ...exchange], ++requestId,
        );
      }
      publish({
        phase: response.changes.length > 0 ? "pending" : "idle",
        messages,
        lastResponse: response,
        stopReason: response.done ? "done" : response.changes.length === 0 ? "no_changes" : null,
      });
      return response;
    } catch (reason) {
      if (active.signal.aborted || (reason instanceof DOMException && reason.name === "AbortError")) {
        publish({ phase: "cancelled", stopReason: "cancelled", error: null });
        return null;
      }
      const message = reason instanceof Error ? reason.message : String(reason);
      publish({ phase: "error", error: message });
      throw reason;
    } finally {
      if (controller === active) controller = null;
    }
  };

  return {
    getSnapshot: () => state,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    send(message) {
      if (!message.trim()) return Promise.reject(new Error("请输入修图要求"));
      return runStep(message.trim(), 1);
    },
    async refine() {
      if (!store.getSnapshot().pendingPreview) throw new Error("当前没有可精修的 AI 候选");
      for (let round = 1; round <= 2; round += 1) {
        const response = await runStep("继续精修当前效果", round);
        if (!response || response.done || response.changes.length === 0) return;
      }
      publish({ phase: "pending", stopReason: "round_limit", round: 2 });
    },
    cancel() {
      controller?.abort();
    },
    setIncludeMetadata(include) {
      includeMetadata = include;
    },
    restoreMessages(messages) {
      publish({ messages: Object.freeze([...messages]) });
    },
  };
}
