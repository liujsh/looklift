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
  dispose(): void;
};

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

  return {
    sessionId: snapshot.id,
    imagePath: snapshot.image_path,
    title: displayName(snapshot.image_path),
    store,
    coordinator,
    workflow,
    isAlive: () => alive,
    dispose() {
      if (!alive) return;
      alive = false;
      workflow.dispose();
    },
  };
}
