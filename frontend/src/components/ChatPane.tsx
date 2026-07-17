type ChatPaneProps = { enabled: boolean };

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
