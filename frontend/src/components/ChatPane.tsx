import type { ChatWorkflow } from "../features/chat/chatWorkflow";
import type { SessionCoordinator } from "../features/sessions/sessionCoordinator";

type ChatPaneProps = {
  enabled: boolean;
  workflow?: ChatWorkflow | null;
  coordinator?: SessionCoordinator | null;
};

export function ChatPane({ enabled }: ChatPaneProps) {
  return (
    <aside
      className="chat-pane"
      data-pane="chat"
      data-state={enabled ? "enabled" : "reserved"}
      aria-label="AI 对话"
      hidden={!enabled}
    >
      <p className="pane-kicker">AI 对话</p>
      <p>对话式修图将在 v2.1 开放。</p>
    </aside>
  );
}
