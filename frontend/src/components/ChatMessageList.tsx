import type { ChatMessage } from "../api/types";

export function ChatMessageList({ messages }: { messages: readonly ChatMessage[] }) {
  if (messages.length === 0) {
    return <div className="chat-empty"><strong>说说你想怎么调整</strong><span>例如：压低高光，让肤色更自然。</span></div>;
  }
  return <ol className="chat-messages" aria-label="对话记录">
    {messages.map((message, index) => <li key={`${index}-${message.role}`} data-role={message.role}>
      <span>{message.role === "user" ? "你" : "AI"}</span>
      <p>{message.content}</p>
    </li>)}
  </ol>;
}
