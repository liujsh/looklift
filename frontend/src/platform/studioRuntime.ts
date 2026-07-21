import type { LookliftClient } from "../api/client";
import type { SessionSnapshot } from "../api/types";
import { createChatWorkflow, type ChatWorkflow } from "../features/chat/chatWorkflow";
import { createSessionCoordinator, type SessionCoordinator } from "../features/sessions/sessionCoordinator";
import { createEditorStore, type EditorStore } from "../store/editorStore";

export type StudioRuntime = {
  sessionId: string;
  imagePath: string;
  title: string;
  store: EditorStore;
  coordinator: SessionCoordinator;
  workflow: ChatWorkflow;
  isAlive(): boolean;
  closeRequirement(): CloseRequirement;
  stopAiForClose(): Exclude<CloseRequirement, "ai">;
  resolvePendingForClose(decision: PendingCloseDecision): Promise<void>;
  dispose(): void;
};

export type CloseRequirement = "direct" | "ai" | "pending";
export type PendingCloseDecision = "keep" | "discard";

function displayName(path: string): string {
  const parts = path.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] ?? "未命名照片";
}

export function createStudioRuntime(
  client: LookliftClient,
  snapshot: SessionSnapshot,
): StudioRuntime {
  const store = createEditorStore();
  store.restoreSession(snapshot.image_path, snapshot.current_analysis);
  const coordinator = createSessionCoordinator(client, store, snapshot.id);
  const workflow = createChatWorkflow(client, store, {
    onMessagesOnly: (exchange) => coordinator.recordMessages(exchange),
  });
  workflow.restoreMessages(snapshot.messages);
  let alive = true;

  const closeRequirement = (): CloseRequirement => {
    const editor = store.getSnapshot();
    if (editor.activeAiRequestId !== null) return "ai";
    if (editor.pendingPreview) return "pending";
    return "direct";
  };

  return {
    sessionId: snapshot.id,
    imagePath: snapshot.image_path,
    title: displayName(snapshot.image_path),
    store,
    coordinator,
    workflow,
    isAlive: () => alive,
    closeRequirement,
    stopAiForClose() {
      workflow.cancel();
      const requirement = closeRequirement();
      if (requirement === "ai") throw new Error("AI 请求尚未停止，请重试");
      return requirement;
    },
    async resolvePendingForClose(decision) {
      if (!alive) throw new Error("Studio 已关闭");
      if (!store.getSnapshot().pendingPreview) throw new Error("当前没有待确认版本");
      if (decision === "keep") await coordinator.acceptPending();
      else await coordinator.discardPending();
      workflow.settlePending();
    },
    dispose() {
      if (!alive) return;
      alive = false;
      workflow.dispose();
    },
  };
}
